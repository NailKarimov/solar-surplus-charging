"""The two protocols, and the proof that the control law does not depend on either.

These are the only tests that run in all three runs. The rest of the suite runs against the model
directly, because electricity does not care whether the number arrived in a Modbus register or in a
``SetChargingProfile``. This file is where that claim is earned: the register map is checked against
what it says it is, the OCPP exchange against what the standard says it is, and then a whole day is
replayed through all three drivers and compared command for command.
"""

from __future__ import annotations

import socket as socket_module
import struct
import threading
from collections.abc import Iterator

import pytest

from support.evidence import note, step
from support.rig import Rig, build
from surplus_lab.control import Command, Settings
from surplus_lab.day import DAYS, HOUR
from surplus_lab.drivers.modbus import (
    CAR_DA,
    GRID_W,
    OFFER_DA,
    PHASES_SET,
    READ_HOLDING,
    STATUS,
    WRITE_SINGLE,
    ModbusDriver,
    ModbusError,
    Wallbox,
    WallboxServer,
)
from surplus_lab.drivers.ocpp import OcppDriver, Station
from surplus_lab.house import MIN_CHARGE_A, House

pytestmark = pytest.mark.driver


@pytest.mark.smoke
def test_an_offer_reaches_the_car_through_this_wallbox(rig: Rig) -> None:
    """Whatever kind of wallbox is on the wall, an offer of 10 A reaches the car as 10 A."""
    with step("the controller offers the car 10 A"):
        rig.driver.apply(Command(amps=10.0, phases=1, why="a test"))
        note("the wallbox now offers", f"{rig.house.offered_a:.0f} A")
        assert rig.house.offered_a == 10.0
        assert rig.house.phases == 1


def test_what_the_car_is_doing_comes_back_through_this_wallbox(rig: Rig) -> None:
    """Whatever kind of wallbox is on the wall, what the car is drawing is reported back faithfully."""
    with step("the car charges at 10 A on one phase for two minutes"):
        rig.driver.apply(Command(amps=10.0, phases=1, why="a test"))
        rig.house.advance(120)
        reading = rig.driver.read(rig.house.clock)
        note("the car is drawing", f"{rig.house.car_w():.0f} W")
        note("the wallbox reports", f"{reading.car_w:.0f} W")
        assert reading.car_w == pytest.approx(rig.house.car_w(), abs=1.0)
        assert reading.phases == 1


def test_an_offer_of_nothing_is_a_pause_and_not_a_tiny_charge(rig: Rig) -> None:
    """An offer of zero stops the car rather than being passed on as some very small current."""
    rig.driver.apply(Command(amps=10.0, phases=1, why="a test"))
    rig.house.advance(60)
    with step("the controller offers nothing"):
        rig.driver.apply(Command(amps=0.0, phases=1, why="a test"))
        rig.house.advance(60)
        note("the car is drawing", f"{rig.house.car.drawing_a:.1f} A")
        assert rig.house.offered_a == 0
        assert rig.house.car.drawing_a == 0


def test_the_grid_meter_reaches_the_controller_through_this_wallbox(rig: Rig) -> None:
    """The reading the controller acts on is the one the meter published, sign and all."""
    with step("the house is selling 2 kW to the grid"):
        rig.house.advance(60)
        reading = rig.driver.read(rig.house.clock)
        note("the meter published", f"{rig.house.meter.reading_w:.0f} W")
        note("the controller was given", f"{reading.grid_w:.0f} W")
        assert reading.grid_w == pytest.approx(rig.house.meter.reading_w, abs=1.0)
        assert reading.grid_w < 0


# ---- the Modbus register map --------------------------------------------------------------------


WallboxRig = tuple[House, Wallbox, ModbusDriver]


@pytest.fixture
def wallbox() -> Iterator[WallboxRig]:
    house = DAYS["clear"]()
    box = Wallbox(house)
    server = WallboxServer(box)
    driver = ModbusDriver(server.host, server.port)
    yield house, box, driver
    driver.close()
    server.close()


@pytest.mark.once
def test_the_register_map_says_what_it_claims_to_say(wallbox: WallboxRig) -> None:
    """Every register in the published map holds what the map says it holds, in the units it says."""
    house, box, driver = wallbox
    house.offer(12.0, 1)
    house.advance(120)
    with step("read the whole block the controller uses"):
        values = box.read(STATUS, 8)
        note("status", str(values[0]))
        note("phases in use", str(values[1]))
        note("what the car draws, in tenths of an amp", str(values[2]))
        assert values[0] == 2  # charging
        assert values[1] == 1
        assert values[2] == round(house.car.drawing_a * 10)
    with step("the offer is in tenths of an amp, not amps"):
        assert box.read(OFFER_DA, 1)[0] == 120


@pytest.mark.once
def test_a_current_the_wallbox_cannot_give_is_refused_rather_than_clipped(wallbox: WallboxRig) -> None:
    """A current below the pilot's floor or above the wallbox's rating is refused, not quietly changed."""
    _house, box, _driver = wallbox
    for value, what in ((30, "3 A, below the floor"), (400, "40 A, above the rating")):
        with step(f"write {what}"), pytest.raises(ModbusError) as refused:
            box.write(OFFER_DA, [value])
        note(f"writing {what} gave", f"exception {refused.value.code}")
        assert refused.value.code == 3  # illegal data value


@pytest.mark.once
def test_a_register_that_does_not_exist_is_refused(wallbox: WallboxRig) -> None:
    """Reading or writing a register outside the map gives the exception the standard names for it."""
    _house, box, _driver = wallbox
    with pytest.raises(ModbusError) as refused:
        box.read(9999, 1)
    assert refused.value.code == 2  # illegal data address
    with pytest.raises(ModbusError) as refused:
        box.write(9999, [1])
    assert refused.value.code == 2


@pytest.mark.once
def test_an_exception_answer_carries_the_function_code_with_its_top_bit_set(wallbox: WallboxRig) -> None:
    """A refusal is the function code plus 0x80 and one byte of reason, as Modbus has always done it."""
    _house, box, _driver = wallbox
    with step("ask for a register that is not in the map"):
        answer = box.answer(struct.pack(">BHH", READ_HOLDING, 9999, 1))
        note("the answer, in hex", answer.hex())
        assert answer == bytes([READ_HOLDING | 0x80, 2])
    with step("ask for a function the wallbox does not have"):
        answer = box.answer(bytes([0x2B, 0x0E]))
        assert answer == bytes([0x2B | 0x80, 1])


@pytest.mark.once
def test_a_negative_meter_reading_survives_two_registers(wallbox: WallboxRig) -> None:
    """Export is a negative number spread over two registers, and it comes back as the same number."""
    house, box, driver = wallbox
    house.meter.reading_w = -4321.0
    with step("the meter is selling 4321 W"):
        values = box.read(GRID_W, 2)
        note("the two registers", f"{values[0]} {values[1]}")
        assert driver.read(0).grid_w == pytest.approx(-4321.0)


@pytest.mark.once
def test_a_single_register_write_works_as_well_as_a_block_one(wallbox: WallboxRig) -> None:
    """Function 6 and function 16 both set the offer, because real wallboxes differ about which they want."""
    house, box, _driver = wallbox
    box.answer(struct.pack(">BHH", WRITE_SINGLE, OFFER_DA, 80))
    assert house.offered_a == 8.0
    box.write(OFFER_DA, [140, 3])
    assert (house.offered_a, house.phases) == (14.0, 3)
    assert box.read(CAR_DA, 1)[0] >= 0
    assert box.read(PHASES_SET, 1)[0] == 3


# ---- the OCPP exchange ---------------------------------------------------------------------------


@pytest.mark.once
def test_a_station_that_refuses_a_profile_does_not_charge_more_than_it_was_allowed() -> None:
    """When a station rejects a charging profile, the car keeps the limit it already had."""
    house = DAYS["clear"]()
    back_office = OcppDriver(house)
    station = Station(house, back_office.url, refuse_above_a=10.0)
    try:
        with step("a profile of 8 A is accepted"):
            back_office.apply(Command(amps=8.0, phases=1, why="a test"))
            assert house.offered_a == 8.0
        with step("a profile of 16 A is refused by the station"):
            back_office.apply(Command(amps=16.0, phases=1, why="a test"))
            note("accepted profiles", str(station.accepted))
            note("refused profiles", str(station.rejected))
            assert station.rejected == 1
            assert house.offered_a == 8.0, "a refused profile was applied anyway"
    finally:
        station.close()
        back_office.close()


@pytest.mark.once
def test_the_station_sends_a_reading_when_the_back_office_asks_for_one() -> None:
    """The back office asks with TriggerMessage and the station answers with a MeterValues of its own."""
    house = DAYS["clear"]()
    back_office = OcppDriver(house)
    station = Station(house, back_office.url)
    try:
        house.offer(10.0, 1)
        house.advance(120)
        with step("the back office asks for a meter reading"):
            reading = back_office.read(house.clock)
            note("the station reported", f"{reading.car_w:.0f} W")
            assert reading.car_w == pytest.approx(house.car_w(), abs=1.0)
    finally:
        station.close()
        back_office.close()


# ---- the three of them together --------------------------------------------------------------------


@pytest.mark.once
@pytest.mark.parametrize("day", ["clear", "broken-cloud", "kettle-and-oven"])
def test_the_same_day_gives_the_same_commands_through_all_three_wallboxes(day: str) -> None:
    """A whole day replayed through the model, a Modbus wallbox and an OCPP station gives one answer."""
    runs = {}
    for name in ("direct", "modbus", "ocpp"):
        rig = build(name, day, Settings())
        try:
            with step(f"{day.replace('-', ' ')} through the {name} wallbox"):
                rig.run(until_s=13 * HOUR, tick_s=30)
                runs[name] = [(tick.offered_a, tick.phases) for tick in rig.trace.ticks]
                note(f"commands through {name}", str(len(runs[name])))
        finally:
            rig.close()
    with step("compare them command for command"):
        note("turns of the loop compared", str(len(runs["direct"])))
        assert runs["modbus"] == runs["direct"]
        assert runs["ocpp"] == runs["direct"]


@pytest.mark.once
def test_the_same_day_fills_the_car_to_the_same_level_through_all_three() -> None:
    """The three wallboxes do not merely agree on the commands: the car ends up with the same energy."""
    energy = {}
    for name in ("direct", "modbus", "ocpp"):
        rig = build(name, "whole-day", Settings())
        try:
            rig.run(until_s=13 * HOUR, tick_s=30)
            energy[name] = rig.totals.car_wh
            note(f"into the car through {name}", f"{energy[name]:.0f} Wh")
        finally:
            rig.close()
    assert energy["modbus"] == pytest.approx(energy["direct"], rel=1e-9)
    assert energy["ocpp"] == pytest.approx(energy["direct"], rel=1e-9)


def test_the_floor_is_the_floor_whichever_wallbox_it_is(rig: Rig, driver_name: str) -> None:
    """No wallbox turns an offer below the pilot's floor into a charge: it refuses it or ignores it."""
    with step("offer the car 5 A, which the pilot cannot ask for"):
        refused = None
        try:
            rig.driver.apply(Command(amps=MIN_CHARGE_A - 1, phases=1, why="a test"))
        except ModbusError as error:
            refused = error.code
        if refused is not None:
            note(f"the {driver_name} wallbox", f"refused it with exception {refused}")
            assert refused == 3
            return
        rig.house.advance(60)
        note(f"the {driver_name} wallbox", "took it and charged nothing")
        assert rig.house.car.drawing_a == 0


@pytest.mark.once
def test_an_answer_to_a_question_nobody_asked_is_refused(wallbox: WallboxRig) -> None:
    """A Modbus answer whose transaction number is not the one in flight is refused, not believed."""
    listener = socket_module.socket(socket_module.AF_INET, socket_module.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)

    def confused_wallbox() -> None:
        conn, _ = listener.accept()
        with conn:
            header = conn.recv(7)
            transaction = struct.unpack(">H", header[:2])[0]
            conn.recv(struct.unpack(">H", header[4:6])[0] - 1)
            body = struct.pack(">BB", READ_HOLDING, 16) + bytes(16)
            conn.sendall(struct.pack(">HHHB", transaction + 7, 0, len(body) + 1, 1) + body)

    threading.Thread(target=confused_wallbox, daemon=True).start()
    rogue = ModbusDriver(*listener.getsockname())
    try:
        with step("the wallbox answers with somebody else's transaction number"), pytest.raises(ConnectionError):
            rogue.read(0)
        note("the controller", "refused the answer instead of acting on it")
    finally:
        rogue.close()
        listener.close()


@pytest.mark.once
def test_a_station_refuses_a_limit_written_in_the_wrong_unit() -> None:
    """A charging profile in watts is refused by a station that limits current, rather than read as amps."""
    house = DAYS["clear"]()
    back_office = OcppDriver(house)
    station = Station(house, back_office.url)
    try:
        with step("the back office sends a limit of 4000, in watts"):
            answer = back_office.send(
                "SetChargingProfile",
                {
                    "connectorId": 1,
                    "csChargingProfiles": {
                        "chargingProfileId": 1,
                        "stackLevel": 0,
                        "chargingProfilePurpose": "TxDefaultProfile",
                        "chargingProfileKind": "Absolute",
                        "chargingSchedule": {
                            "chargingRateUnit": "W",
                            "chargingSchedulePeriod": [{"startPeriod": 0, "limit": 4000, "numberPhases": 1}],
                        },
                    },
                },
            )
            note("the station answered", str(answer.get("status")))
            assert answer["status"] == "Rejected"
            assert house.offered_a == 0, "a limit in watts was applied as though it were amps"
    finally:
        station.close()
        back_office.close()
