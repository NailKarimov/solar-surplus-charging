"""Record what actually goes down the wire, and label every byte of it.

The controller's decision is one number. Getting that number to a wallbox is a protocol, and the
two protocols in this project could hardly be less alike: Modbus TCP writes a register and is
answered by an echo, OCPP asks a station for permission and may be told no. The visual page shows
both, so this module captures real traffic — a real socket to a real wallbox, a real WebSocket to a
real charge point — and annotates it field by field.

Nothing here is drawn by hand. Every frame on the page came out of a controller deciding something
and a wallbox answering, during the build of that page. The one exception is labelled on the page:
the two refusals, which the controller never provokes, because not asking for silly things is
precisely what it is for.

The one thing that goes nowhere: the inverter. A surplus controller never speaks to it. It reads
the meter at the door and writes to the wallbox, and that is the entire conversation it is capable
of having. The inverter is the subject of solar-inverter-testing instead.
"""

from __future__ import annotations

import contextlib
import json
import struct
from typing import Any

from surplus_lab.control import Command, Controller, Settings
from surplus_lab.day import DAYS
from surplus_lab.drivers.modbus import (
    CAR_DA,
    CAR_W,
    GRID_AGE,
    GRID_W,
    OFFER_DA,
    PHASES_IN_USE,
    PHASES_SET,
    STATUS,
    ModbusDriver,
    ModbusError,
    Wallbox,
    WallboxServer,
)
from surplus_lab.drivers.ocpp import OcppDriver, Station

# The register map as the page shows it: addresses from the driver, words from here.
REGISTERS: list[dict[str, Any]] = [
    {
        "at": STATUS,
        "rw": "R",
        "en": "status: 0 nothing plugged, 1 plugged, 2 charging, 3 paused",
        "ru": "состояние: 0 ничего не подключено, 1 подключено, 2 заряжается, 3 пауза",
    },
    {"at": PHASES_IN_USE, "rw": "R", "en": "phases in use, 1 or 3", "ru": "сколько фаз в работе, 1 или 3"},
    {
        "at": CAR_DA,
        "rw": "R",
        "en": "what the car is drawing, per phase, in tenths of an amp",
        "ru": "что берёт машина, на фазу, в десятых долях ампера",
    },
    {
        "at": CAR_W,
        "rw": "R",
        "en": "what the car is drawing, in watts (two registers)",
        "ru": "что берёт машина, в ваттах (два регистра)",
    },
    {
        "at": GRID_W,
        "rw": "R",
        "en": "the meter at the door, signed watts, plus means buying (two registers)",
        "ru": "счётчик на вводе, ватты со знаком, плюс — покупаем (два регистра)",
    },
    {
        "at": GRID_AGE,
        "rw": "R",
        "en": "how old that meter reading is, in seconds",
        "ru": "сколько секунд этому показанию счётчика",
    },
    {
        "at": OFFER_DA,
        "rw": "RW",
        "en": "what to offer the car, per phase, in tenths of an amp; 0 pauses",
        "ru": "что предложить машине, на фазу, в десятых долях ампера; 0 — пауза",
    },
    {"at": PHASES_SET, "rw": "RW", "en": "how many phases to use, 1 or 3", "ru": "сколько фаз использовать, 1 или 3"},
]

NAMES = {
    STATUS: ("status", "состояние"),
    PHASES_IN_USE: ("phases in use", "фаз в работе"),
    CAR_DA: ("the car is drawing", "машина берёт"),
    CAR_W: ("the car in watts, high half", "машина в ваттах, старшая половина"),
    CAR_W + 1: ("the car in watts, low half", "машина в ваттах, младшая половина"),
    GRID_W: ("the meter, high half", "счётчик, старшая половина"),
    GRID_W + 1: ("the meter, low half", "счётчик, младшая половина"),
    GRID_AGE: ("the age of that reading", "возраст показания"),
    OFFER_DA: ("offer the car", "предложить машине"),
    PHASES_SET: ("use this many phases", "столько фаз"),
}

STATUS_WORDS = {
    0: ("nothing plugged in", "ничего не подключено"),
    1: ("plugged in, waiting", "подключено, ждёт"),
    2: ("charging", "заряжается"),
    3: ("paused", "пауза"),
}


def _seg(kind: str, blob: bytes, en: str, ru: str) -> dict[str, Any]:
    return {"kind": kind, "hex": [f"{b:02x}" for b in blob], "en": en, "ru": ru}


def _signed(high: int, low: int) -> int:
    return int(struct.unpack(">i", struct.pack(">HH", high, low))[0])


def _registers_said(address: int, values: list[int]) -> list[dict[str, Any]]:
    """Turn the registers of a read answer into one labelled segment each, already decoded."""
    out: list[dict[str, Any]] = []
    index = 0
    while index < len(values):
        at = address + index
        blob = struct.pack(">H", values[index])
        if at in (CAR_W, GRID_W) and index + 1 < len(values):
            blob += struct.pack(">H", values[index + 1])
            watts = _signed(values[index], values[index + 1])
            if at == GRID_W:
                sense_en = "buying from the grid" if watts > 0 else "giving to the grid"
                sense_ru = "покупаем у сети" if watts > 0 else "отдаём в сеть"
                out.append(_seg("data", blob, f"the meter: {watts} W, {sense_en}", f"счётчик: {watts} Вт, {sense_ru}"))
            else:
                out.append(_seg("data", blob, f"the car is taking {watts} W", f"машина берёт {watts} Вт"))
            index += 2
            continue
        value = values[index]
        name_en, name_ru = NAMES.get(at, (f"register {at}", f"регистр {at}"))
        if at == STATUS:
            word_en, word_ru = STATUS_WORDS.get(value, ("?", "?"))
            out.append(_seg("data", blob, f"{name_en}: {value} — {word_en}", f"{name_ru}: {value} — {word_ru}"))
        elif at in (CAR_DA, OFFER_DA):
            out.append(
                _seg("data", blob, f"{name_en}: {value / 10:.1f} A per phase", f"{name_ru}: {value / 10:.1f} А на фазу")
            )
        elif at == GRID_AGE:
            out.append(_seg("data", blob, f"{name_en}: {value} s", f"{name_ru}: {value} с"))
        else:
            out.append(_seg("data", blob, f"{name_en}: {value}", f"{name_ru}: {value}"))
        index += 1
    return out


def annotate(frame: bytes) -> list[dict[str, Any]]:
    """Every byte of one Modbus TCP frame, in order, with what it means."""
    transaction, _protocol, length, unit = struct.unpack(">HHHB", frame[:7])
    parts = [
        _seg(
            "mbap",
            frame[0:2],
            f"question {transaction}: the answer has to carry the same number",
            f"вопрос {transaction}: ответ обязан прийти с тем же номером",
        ),
        _seg("mbap", frame[2:4], "protocol 0: this is Modbus", "протокол 0: это Modbus"),
        _seg("mbap", frame[4:6], f"{length} bytes follow", f"дальше {length} байт"),
        _seg("unit", frame[6:7], f"unit {unit}: which device on the line", f"адрес {unit}: какое устройство на линии"),
    ]
    pdu = frame[7:]
    function = pdu[0]

    if function & 0x80:  # an exception answer: the function code with the top bit set
        parts.append(_seg("ex", pdu[0:1], f"refused: function {function & 0x7F}", f"отказ: функция {function & 0x7F}"))
        code = pdu[1]
        words = {
            1: ("no such function", "нет такой функции"),
            2: ("no such register", "нет такого регистра"),
            3: ("that value is not allowed", "такое значение не разрешено"),
        }
        word_en, word_ru = words.get(code, ("refused", "отказано"))
        parts.append(_seg("ex", pdu[1:2], f"exception {code}: {word_en}", f"исключение {code}: {word_ru}"))
        return parts

    if function == 3 and len(pdu) == 5:  # read request
        address, count = struct.unpack(">HH", pdu[1:5])
        parts.append(_seg("fn", pdu[0:1], "function 3: read holding registers", "функция 3: чтение регистров"))
        parts.append(_seg("addr", pdu[1:3], f"from register {address}", f"начиная с регистра {address}"))
        parts.append(_seg("count", pdu[3:5], f"{count} of them", f"столько регистров: {count}"))
        return parts

    if function == 3:  # read answer
        count = pdu[1]
        values = list(struct.unpack(f">{count // 2}H", pdu[2 : 2 + count]))
        parts.append(_seg("fn", pdu[0:1], "function 3: here are the registers", "функция 3: вот регистры"))
        parts.append(_seg("count", pdu[1:2], f"{count} bytes of them", f"столько байт: {count}"))
        parts.extend(_registers_said(STATUS, values))
        return parts

    if function == 16 and len(pdu) > 5:  # write request
        address, count, _bytes = struct.unpack(">HHB", pdu[1:6])
        values = list(struct.unpack(f">{count}H", pdu[6 : 6 + count * 2]))
        parts.append(_seg("fn", pdu[0:1], "function 16: write registers", "функция 16: запись регистров"))
        parts.append(_seg("addr", pdu[1:3], f"from register {address}", f"начиная с регистра {address}"))
        parts.append(_seg("count", pdu[3:5], f"{count} of them", f"столько регистров: {count}"))
        parts.append(_seg("count", pdu[5:6], f"{count * 2} bytes of values", f"{count * 2} байта значений"))
        for offset, value in enumerate(values):
            at = address + offset
            blob = struct.pack(">H", value)
            if at == OFFER_DA:
                said = "pause" if value == 0 else f"{value / 10:.1f} A per phase"
                said_ru = "пауза" if value == 0 else f"{value / 10:.1f} А на фазу"
                parts.append(
                    _seg("data", blob, f"offer the car: {value} = {said}", f"предложить машине: {value} = {said_ru}")
                )
            elif at == PHASES_SET:
                en = "on one phase" if value == 1 else f"on {value} phases"
                ru = "на одной фазе" if value == 1 else f"на {value} фазах"
                parts.append(_seg("data", blob, en, ru))
            else:  # pragma: no cover - the driver writes only those two
                parts.append(_seg("data", blob, f"register {at}: {value}", f"регистр {at}: {value}"))
        return parts

    if function == 16:  # write answer: the address and the count, echoed back
        address, count = struct.unpack(">HH", pdu[1:5])
        parts.append(_seg("fn", pdu[0:1], "function 16: done", "функция 16: сделано"))
        parts.append(_seg("addr", pdu[1:3], f"from register {address}", f"начиная с регистра {address}"))
        parts.append(_seg("count", pdu[3:5], f"{count} written", f"записано регистров: {count}"))
        return parts

    return parts  # pragma: no cover - the driver sends nothing else


def _exchange(entry: dict[str, str]) -> dict[str, Any]:
    ask, say = bytes.fromhex(entry["ask"]), bytes.fromhex(entry["say"])
    return {
        "ask": {"hex": entry["ask"], "parts": annotate(ask)},
        "say": {"hex": entry["say"], "parts": annotate(say)},
    }


# ---- what an OCPP message is saying ------------------------------------------------------------


def _ocpp_fields(frame: list[Any]) -> list[dict[str, str]]:
    """The handful of fields in one OCPP-J message that a reader actually needs."""
    kind = frame[0]
    out: list[dict[str, str]] = []
    if kind == 2 and frame[2] == "SetChargingProfile":
        schedule = frame[3]["csChargingProfiles"]["chargingSchedule"]
        period = schedule["chargingSchedulePeriod"][0]
        unit = schedule.get("chargingRateUnit")
        out.append({"en": "the limit", "ru": "предел", "v": f"{period['limit']} {unit}"})
        out.append({"en": "on how many phases", "ru": "на скольких фазах", "v": str(period.get("numberPhases", "—"))})
        out.append({"en": "which connector", "ru": "какой коннектор", "v": str(frame[3]["connectorId"])})
        if period["limit"] == 0:
            out.append({"en": "zero means", "ru": "ноль значит", "v": "stop charging / остановить зарядку"})
    elif kind == 2 and frame[2] == "TriggerMessage":
        out.append({"en": "asked for", "ru": "просим прислать", "v": str(frame[3]["requestedMessage"])})
    elif kind == 2 and frame[2] == "MeterValues":
        for sample in frame[3]["meterValue"][0]["sampledValue"]:
            name = sample["measurand"] + (f" {sample['phase']}" if sample.get("phase") else "")
            out.append({"en": name, "ru": name, "v": f"{sample['value']} {sample['unit']}"})
    elif kind == 3 and isinstance(frame[2], dict) and "status" in frame[2]:
        status = frame[2]["status"]
        out.append({"en": "the station says", "ru": "станция отвечает", "v": str(status)})
    return out


def _ocpp_line(entry: dict[str, str]) -> dict[str, Any]:
    frame: list[Any] = json.loads(entry["text"])
    kind = {2: "CALL", 3: "CALLRESULT", 4: "CALLERROR"}.get(frame[0], str(frame[0]))
    return {
        "dir": entry["dir"],
        "kind": kind,
        "id": str(frame[1]),
        "action": str(frame[2]) if frame[0] == 2 else "",
        "body": json.dumps(frame[3] if frame[0] == 2 else frame[2], ensure_ascii=False, separators=(",", ":")),
        "text": entry["text"],
        "fields": _ocpp_fields(frame),
    }


# ---- the moments the page shows ----------------------------------------------------------------

MOMENTS: list[dict[str, Any]] = [
    {
        "id": "start",
        "short_en": "Start",
        "short_ru": "Старт",
        "en": "Start charging, at the smallest current there is",
        "ru": "Начать зарядку — самым маленьким током, какой есть",
        "say_en": "The roof has had enough to spare for five minutes, so the controller offers the car six amps.",
        "say_ru": "Излишка хватает уже пять минут, и контроллер предлагает машине шесть ампер.",
    },
    {
        "id": "more",
        "short_en": "More",
        "short_ru": "Больше",
        "en": "Give the car more",
        "ru": "Дать машине больше",
        "say_en": "The surplus has held for two minutes, so the offer goes up by whole amps.",
        "say_ru": "Излишек продержался две минуты — предложение растёт на целые амперы.",
    },
    {
        "id": "less",
        "short_en": "Less, at once",
        "short_ru": "Сразу меньше",
        "en": "Something took the surplus away: give the car less, at once",
        "ru": "Излишек забрали: сразу дать машине меньше",
        "say_en": "A cloud or a kitchen. The offer falls on the very next reading — there is no waiting on this side.",
        "say_ru": "Облако или кухня. Предложение падает на следующем же показании — в эту сторону ждать нельзя.",
    },
    {
        "id": "stop",
        "short_en": "Stop",
        "short_ru": "Стоп",
        "en": "Stop: there is not enough sun for any charging at all",
        "ru": "Остановиться: солнца не хватает ни на какую зарядку",
        "say_en": "Zero amps. On this wire, stopping is the same message as any other, with a different number in it.",
        "say_ru": "Ноль ампер. На проводе остановка — такое же сообщение, как любое другое, просто с другим числом.",
    },
]


def _pick(tape: list[dict[str, str]], want: str) -> int | None:
    """Find the exchange in a recorded day that is the moment we want to show.

    The first of its kind, except for the stop: the interesting stop is the one at the end of the
    day, not the flap at first light when the sun crosses the floor and falls back under it.
    """
    last = 0
    found: int | None = None
    for index, entry in enumerate(tape):
        pdu = bytes.fromhex(entry["ask"])[7:]
        if pdu[0] != 16:
            continue
        value = struct.unpack(">H", pdu[6:8])[0]
        was, last = last, value
        if want == "start" and was == 0 and value == 60 and found is None:
            found = index
        if want == "more" and was >= 60 and value > was and value >= 100 and found is None:
            found = index
        if want == "less" and was >= 60 and value > 60 and was - value >= 20 and found is None:
            found = index
        if want == "stop" and was >= 60 and value == 0:
            found = index  # keep the last one: the end of the day
    return found


def record() -> dict[str, Any]:
    """Run a day through a real Modbus wallbox and a real OCPP station, and keep the traffic."""
    out: dict[str, Any] = {"registers": REGISTERS, "moments": []}

    # --- Modbus: a whole day down a real socket, then the four moments picked out of the tape
    house = DAYS["whole-day"]()
    server = WallboxServer(Wallbox(house))
    driver = ModbusDriver(server.host, server.port)
    tape: list[dict[str, str]] = []
    driver.tape = tape
    clocks: list[int] = []
    controller = Controller(settings=Settings(), phases=house.phases)
    while house.clock < 21 * 3600:
        clocks.append(house.clock)  # the read
        reading = driver.read(house.clock)
        clocks.append(house.clock)  # and the write it leads to
        driver.apply(controller.decide(reading))
        house.advance(10)

    modbus: dict[str, Any] = {}
    when: dict[str, int] = {}
    for moment in MOMENTS:
        at = _pick(tape, str(moment["id"]))
        if at is None:  # pragma: no cover - a whole day always has all four
            continue
        when[str(moment["id"])] = clocks[at]
        modbus[moment["id"]] = {"write": _exchange(tape[at]), "read": _exchange(tape[at - 1]) if at else None}
    silly = _silly_write(driver)
    driver.close()
    server.close()

    # --- OCPP: the same four decisions, carried to a real charge point over a real WebSocket
    ocpp_house = DAYS["whole-day"]()
    back_office = OcppDriver(ocpp_house)
    station = Station(ocpp_house, back_office.url)
    ocpp: dict[str, Any] = {}
    for moment in MOMENTS:
        amps, phases = _amps_of(modbus.get(str(moment["id"])))
        talk: list[dict[str, str]] = []
        back_office.tape = talk
        back_office.apply(Command(amps=amps, phases=phases, why=str(moment["id"])))
        ocpp[moment["id"]] = [_ocpp_line(entry) for entry in talk]

    # A reading is only worth showing when there is something to read: put the house in the middle of
    # a charging session first, exactly as the driver tests do.
    ocpp_house.offer(11.0, 1)
    ocpp_house.advance(600)
    talk = []
    back_office.tape = talk
    back_office.read(ocpp_house.clock)
    ocpp_read = [_ocpp_line(entry) for entry in talk]

    talk = []
    back_office.tape = talk
    refused = back_office.send(
        "SetChargingProfile",
        {
            "connectorId": 1,
            "csChargingProfiles": {
                "chargingProfileId": 1,
                "stackLevel": 0,
                "chargingProfilePurpose": "TxDefaultProfile",
                "chargingProfileKind": "Absolute",
                "chargingSchedule": {
                    "chargingRateUnit": "W",  # watts, not amps: the station is right to refuse this
                    "chargingSchedulePeriod": [{"startPeriod": 0, "limit": 3680, "numberPhases": 1}],
                },
            },
        },
    )
    ocpp_refused = [_ocpp_line(entry) for entry in talk]
    station.close()
    back_office.close()

    for moment in MOMENTS:
        out["moments"].append(
            {
                **moment,
                "clock": when.get(str(moment["id"]), 0),
                "modbus": modbus.get(str(moment["id"])),
                "ocpp": ocpp.get(moment["id"]),
            }
        )
    read_sample = modbus.get("more") or {}
    out["read"] = {"modbus": read_sample.get("read"), "ocpp": ocpp_read}
    out["refused"] = {"modbus": silly, "ocpp": ocpp_refused, "status": str(refused.get("status", ""))}
    return out


def _amps_of(entry: dict[str, Any] | None) -> tuple[float, int]:
    """The amps and phases that the recorded Modbus write carried, so OCPP shows the same decision."""
    if entry is None:  # pragma: no cover
        return 0.0, 1
    pdu = bytes.fromhex(entry["write"]["ask"]["hex"])[7:]
    values = struct.unpack(">2H", pdu[6:10])
    return values[0] / 10.0, values[1]


def _silly_write(driver: ModbusDriver) -> dict[str, Any]:
    """Ask the wallbox for three amps. It refuses: no car can be charged at three amps.

    The controller never sends this. It is here because a wallbox that accepts nonsense is a
    wallbox that will charge a car at 1.6 A one day, and the page should show that it does not.
    """
    talk: list[dict[str, str]] = []
    driver.tape = talk
    with contextlib.suppress(ModbusError):  # the refusal is the point; the driver raises on it
        driver.ask(struct.pack(">BHH", 6, OFFER_DA, 30))
    return _exchange(talk[-1])
