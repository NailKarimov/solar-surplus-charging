"""A home wallbox, driven over Modbus TCP, the way evcc drives a go-e, an Easee or an Alfen.

This is how most solar-surplus charging is actually done in a house: the wallbox exposes a handful
of registers, the controller writes a current into one of them every few seconds, and that is the
whole protocol. There is no session, no authorisation, no cloud. It is a number on a wire, which
makes it fast and unforgiving: nothing in the protocol will tell you that your number was silly.

The register map, holding registers, unit 1:

    1000  R   status: 0 nothing plugged, 1 plugged, 2 charging, 3 paused
    1001  R   phases in use, 1 or 3
    1002  R   what the car is drawing, per phase, in tenths of an amp
    1003  R   what the car is drawing, in watts (two registers, 1003 and 1004)
    1005  R   the grid meter, signed watts, positive is import (two registers, 1005 and 1006)
    1007  R   how old that meter reading is, in seconds
    2000  RW  what to offer the car, per phase, in tenths of an amp; 0 pauses
    2001  RW  how many phases to use, 1 or 3

Tenths of an amp, and not amps, because that is what these devices do, and because it is exactly the
kind of unit that gets forgotten once and then shows up as a car charging at 1.6 A.
"""

from __future__ import annotations

import socket
import struct
import threading

from ..control import Command, Reading
from ..house import MIN_CHARGE_A, House

STATUS, PHASES_IN_USE, CAR_DA, CAR_W, GRID_W, GRID_AGE = 1000, 1001, 1002, 1003, 1005, 1007
OFFER_DA, PHASES_SET = 2000, 2001

READ_HOLDING, WRITE_SINGLE, WRITE_MULTIPLE = 3, 6, 16
ILLEGAL_FUNCTION, ILLEGAL_ADDRESS, ILLEGAL_VALUE = 1, 2, 3


class ModbusError(Exception):
    """The wallbox refused, with the code the standard gives for that kind of refusal."""

    def __init__(self, code: int) -> None:
        super().__init__(f"modbus exception {code}")
        self.code = code


def _signed32(value: int) -> tuple[int, int]:
    raw = struct.unpack(">HH", struct.pack(">i", int(value)))
    return raw[0], raw[1]


def _to_signed32(high: int, low: int) -> int:
    return int(struct.unpack(">i", struct.pack(">HH", high, low))[0])


class Wallbox:
    """The registers themselves, and what reading and writing them does to the house."""

    def __init__(self, house: House) -> None:
        self.house = house
        self.writes = 0

    def _registers(self) -> dict[int, int]:
        house = self.house
        car = house.car
        if not car.plugged:
            status = 0
        elif car.drawing_a > 0:
            status = 2
        elif house.offered_a >= MIN_CHARGE_A:
            status = 1
        else:
            status = 3
        car_w_high, car_w_low = _signed32(round(house.car_w()))
        grid_high, grid_low = _signed32(round(house.meter.reading_w))
        return {
            STATUS: status,
            PHASES_IN_USE: house.phases,
            CAR_DA: round(car.drawing_a * 10),
            CAR_W: car_w_high,
            CAR_W + 1: car_w_low,
            GRID_W: grid_high,
            GRID_W + 1: grid_low,
            GRID_AGE: min(0xFFFF, house.meter.reading_age_s),
            OFFER_DA: round(house.offered_a * 10),
            PHASES_SET: house.phases,
        }

    def read(self, address: int, count: int) -> list[int]:
        if not 1 <= count <= 125:
            raise ModbusError(ILLEGAL_VALUE)
        registers = self._registers()
        out = []
        for one in range(address, address + count):
            if one not in registers:
                raise ModbusError(ILLEGAL_ADDRESS)
            out.append(registers[one])
        return out

    def write(self, address: int, values: list[int]) -> None:
        for offset, value in enumerate(values):
            one = address + offset
            if one == OFFER_DA:
                if value != 0 and not (MIN_CHARGE_A * 10 <= value <= 320):
                    raise ModbusError(ILLEGAL_VALUE)
                self.house.offer(value / 10.0)
            elif one == PHASES_SET:
                if value not in (1, 3):
                    raise ModbusError(ILLEGAL_VALUE)
                self.house.phases = value
            else:
                raise ModbusError(ILLEGAL_ADDRESS)
        self.writes += 1

    # ---- the wire ---------------------------------------------------------------------------

    def handle(self, pdu: bytes) -> bytes:
        """One request in, one answer out. An exception answer has the function code plus 0x80."""
        if not pdu:
            raise ModbusError(ILLEGAL_FUNCTION)
        function = pdu[0]
        try:
            if function == READ_HOLDING:
                address, count = struct.unpack(">HH", pdu[1:5])
                values = self.read(address, count)
                return struct.pack(">BB", function, count * 2) + b"".join(struct.pack(">H", v) for v in values)
            if function == WRITE_SINGLE:
                address, value = struct.unpack(">HH", pdu[1:5])
                self.write(address, [value])
                return pdu[:5]
            if function == WRITE_MULTIPLE:
                address, count, _bytes = struct.unpack(">HHB", pdu[1:6])
                values = list(struct.unpack(f">{count}H", pdu[6 : 6 + count * 2]))
                self.write(address, values)
                return struct.pack(">BHH", function, address, count)
        except struct.error as error:
            raise ModbusError(ILLEGAL_VALUE) from error
        raise ModbusError(ILLEGAL_FUNCTION)

    def answer(self, pdu: bytes) -> bytes:
        try:
            return self.handle(pdu)
        except ModbusError as error:
            return struct.pack(">BB", (pdu[0] if pdu else 0) | 0x80, error.code)


class WallboxServer:
    """The wallbox listening on a TCP port, framing every exchange in an MBAP header."""

    def __init__(self, wallbox: Wallbox, host: str = "127.0.0.1", port: int = 0) -> None:
        self.wallbox = wallbox
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, port))
        self.sock.listen(4)
        self.host, self.port = self.sock.getsockname()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._talk, args=(conn,), daemon=True).start()

    def _talk(self, conn: socket.socket) -> None:
        with conn:
            while not self._stop.is_set():
                header = _recv(conn, 7)
                if not header:
                    return
                transaction, protocol, length, unit = struct.unpack(">HHHB", header)
                pdu = _recv(conn, length - 1)
                if pdu is None:
                    return
                if protocol != 0:
                    return  # not Modbus at all: the standard says say nothing
                answer = self.wallbox.answer(pdu)
                conn.sendall(struct.pack(">HHHB", transaction, 0, len(answer) + 1, unit) + answer)

    def close(self) -> None:
        self._stop.set()
        self.sock.close()


def _recv(conn: socket.socket, count: int) -> bytes | None:
    buffer = b""
    while len(buffer) < count:
        chunk = conn.recv(count - len(buffer))
        if not chunk:
            return buffer or None
        buffer += chunk
    return buffer


class ModbusDriver:
    """The controller's end: a Modbus TCP client that reads the block and writes the current."""

    name = "modbus"

    def __init__(self, host: str, port: int, unit: int = 1) -> None:
        self.unit = unit
        self.transaction = 0
        self.sock = socket.create_connection((host, port), timeout=5)
        # When this is a list, every exchange is kept whole, both ways, exactly as it went down the
        # wire. The visual page is built from it, so what it draws is traffic and not an artist's
        # impression of traffic.
        self.tape: list[dict[str, str]] | None = None

    def ask(self, pdu: bytes) -> bytes:
        """Send one PDU and return the answer's PDU, raising ModbusError if the wallbox refused."""
        self.transaction = (self.transaction + 1) % 0x10000
        request = struct.pack(">HHHB", self.transaction, 0, len(pdu) + 1, self.unit) + pdu
        self.sock.sendall(request)
        header = _recv(self.sock, 7)
        if header is None or len(header) < 7:
            raise ConnectionError("the wallbox stopped answering")
        transaction, _protocol, length, _unit = struct.unpack(">HHHB", header)
        body = _recv(self.sock, length - 1) or b""
        if self.tape is not None:
            self.tape.append({"ask": request.hex(), "say": (header + body).hex()})
        if transaction != self.transaction:
            raise ConnectionError(f"answer {transaction} is not for question {self.transaction}")
        if body and body[0] & 0x80:
            raise ModbusError(body[1])
        return body

    def read(self, clock: int) -> Reading:
        values = list(struct.unpack(">8H", self.ask(struct.pack(">BHH", READ_HOLDING, STATUS, 8))[2:]))
        status, phases, _car_da, car_high, car_low, grid_high, grid_low, age = values
        return Reading(
            clock=clock,
            grid_w=float(_to_signed32(grid_high, grid_low)),
            grid_age_s=age,
            car_w=float(_to_signed32(car_high, car_low)),
            phases=phases,
            plugged=status != 0,
        )

    def apply(self, command: Command) -> None:
        self.ask(struct.pack(">BHHBHH", WRITE_MULTIPLE, OFFER_DA, 2, 4, round(command.amps * 10), command.phases))

    def close(self) -> None:
        self.sock.close()
