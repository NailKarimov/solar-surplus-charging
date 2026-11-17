"""A public-style charge point, driven over OCPP 1.6J, the way an operator's back office drives it.

The difference from the Modbus wallbox is not cosmetic, and it is the reason this driver exists.

- The wallbox is a register. The controller writes 10.0 A and that is the end of it.
- The station is a counterparty. The controller sends ``SetChargingProfile`` and the station answers
  ``Accepted`` or ``Rejected``, and it answers when it feels like it. A limit is a *request*.
- The station reports what the car is doing in ``MeterValues``, as its own messages, on its own
  schedule. Here the controller asks for one with ``TriggerMessage`` so that each tick is a clean
  question and answer rather than a race.
- OCPP has nothing to say about the grid meter at the front of the house. That is a different device
  on a different wire, and this driver reads it separately — exactly as a real installation does,
  where the wallbox speaks OCPP to the cloud while a meter speaks Modbus or MQTT to the controller.

So the same control law here has to cope with a limit that may be refused and a reading that arrives
as a message, rather than a number that is simply true. If it behaves the same way through both, the
law is about electricity and not about plumbing.
"""

from __future__ import annotations

import json
import threading
from itertools import count
from typing import Any

from websockets.sync.client import connect
from websockets.sync.server import ServerConnection, serve

from ..control import Command, Reading
from ..house import MIN_CHARGE_A, NOMINAL_V, House

CALL, CALLRESULT, CALLERROR = 2, 3, 4
SUBPROTOCOL = "ocpp1.6"


def _call(message_id: str, action: str, payload: dict[str, Any]) -> str:
    return json.dumps([CALL, message_id, action, payload])


def _result(message_id: str, payload: dict[str, Any]) -> str:
    return json.dumps([CALLRESULT, message_id, payload])


class Station:
    """The charge point: it connects out to the back office and does as it is asked, mostly."""

    def __init__(self, house: House, url: str, *, refuse_above_a: float | None = None) -> None:
        self.house = house
        self.url = url
        self.refuse_above_a = refuse_above_a
        self.accepted = 0
        self.rejected = 0
        self._ids = count(1)
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)

    def _run(self) -> None:
        with connect(self.url, subprotocols=[SUBPROTOCOL]) as socket:  # type: ignore[list-item]
            socket.send(_call(str(next(self._ids)), "BootNotification", {"chargePointModel": "surplus-lab"}))
            socket.recv()
            self._ready.set()
            while not self._stop.is_set():
                try:
                    raw = socket.recv(timeout=0.5)
                except TimeoutError:
                    continue
                except Exception:
                    return
                self._handle(socket, json.loads(raw))

    def _handle(self, socket: Any, frame: list[Any]) -> None:
        if frame[0] != CALL:
            return
        _kind, message_id, action, payload = frame
        if action == "SetChargingProfile":
            socket.send(_result(message_id, {"status": self._apply(payload)}))
        elif action == "TriggerMessage":
            socket.send(_result(message_id, {"status": "Accepted"}))
            socket.send(_call(str(next(self._ids)), "MeterValues", self._meter_values()))
            socket.recv()
        else:
            socket.send(json.dumps([CALLERROR, message_id, "NotImplemented", action, {}]))

    def _apply(self, payload: dict[str, Any]) -> str:
        profile = payload["csChargingProfiles"]
        schedule = profile["chargingSchedule"]
        period = schedule["chargingSchedulePeriod"][0]
        amps = float(period["limit"])
        phases = int(period.get("numberPhases", self.house.phases))
        if schedule.get("chargingRateUnit") != "A":
            self.rejected += 1
            return "Rejected"
        if self.refuse_above_a is not None and amps > self.refuse_above_a:
            self.rejected += 1
            return "Rejected"
        self.house.offer(amps, phases)
        self.accepted += 1
        return "Accepted"

    def _meter_values(self) -> dict[str, Any]:
        """What the station reports about the car: watts, the current offered, and one sample a phase.

        OCPP 1.6 has no field for "how many phases are in use". It has a ``phase`` on each sampled
        value, so a three-phase session reports three ``Current.Import`` samples, L1 to L3, and the
        reader counts them. An earlier version of this station put the number of phases into a
        ``Current.Offered`` sample, which means amps — see finding SS-6: the wire view of the visual
        page is what made it obvious.
        """
        house = self.house
        samples: list[dict[str, str]] = [
            {"value": f"{house.car_w():.1f}", "measurand": "Power.Active.Import", "unit": "W"},
            {"value": f"{house.offered_a:.1f}", "measurand": "Current.Offered", "unit": "A"},
        ]
        for phase in range(1, house.phases + 1):
            samples.append(
                {
                    "value": f"{house.car.drawing_a:.1f}",
                    "measurand": "Current.Import",
                    "unit": "A",
                    "phase": f"L{phase}",
                }
            )
        return {"connectorId": 1, "meterValue": [{"timestamp": f"{house.clock}", "sampledValue": samples}]}

    def close(self) -> None:
        self._stop.set()


class OcppDriver:
    """The back office end: it holds the socket, sends profiles and asks for readings.

    The grid meter is not part of OCPP, so it is passed in separately. That is not a shortcut; it is
    what the wiring in a real house looks like.
    """

    name = "ocpp"

    def __init__(self, house: House, host: str = "127.0.0.1", port: int = 0) -> None:
        self.house = house  # only its meter is read here; the car is read over OCPP
        self._ids = count(1)
        self._connection: ServerConnection | None = None
        self._arrived = threading.Event()
        self._server = serve(self._on_connect, host, port, subprotocols=[SUBPROTOCOL])  # type: ignore[list-item]
        self.host, self.port = self._server.socket.getsockname()
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        self.last_car_w = 0.0
        self.last_phases = house.phases
        self.plugged = True
        # As on the Modbus driver: when this is a list, every message is kept as it was sent or
        # received, so the page can show the conversation rather than a drawing of one.
        self.tape: list[dict[str, str]] | None = None

    def _say(self, socket: ServerConnection, raw: str) -> None:
        if self.tape is not None:
            self.tape.append({"dir": "->", "text": raw})
        socket.send(raw)

    def _hear(self, socket: ServerConnection, timeout: float = 5) -> list[Any]:
        raw = str(socket.recv(timeout=timeout))
        if self.tape is not None:
            self.tape.append({"dir": "<-", "text": raw})
        frame: list[Any] = json.loads(raw)
        return frame

    @property
    def url(self) -> str:
        return f"ws://{self.host}:{self.port}/surplus"

    def _on_connect(self, connection: ServerConnection) -> None:
        self._connection = connection
        boot = json.loads(connection.recv())
        connection.send(_result(boot[1], {"status": "Accepted", "interval": 300, "currentTime": "now"}))
        self._arrived.set()
        self._stay = threading.Event()
        self._stay.wait()

    def _wait_for_station(self) -> ServerConnection:
        if not self._arrived.wait(timeout=5) or self._connection is None:
            raise ConnectionError("no charge point connected")
        return self._connection

    def read(self, clock: int) -> Reading:
        socket = self._wait_for_station()
        message_id = str(next(self._ids))
        self._say(socket, _call(message_id, "TriggerMessage", {"requestedMessage": "MeterValues"}))
        while True:
            frame = self._hear(socket)
            if frame[0] == CALLRESULT and frame[1] == message_id:
                continue
            if frame[0] == CALL and frame[2] == "MeterValues":
                self._say(socket, _result(frame[1], {}))
                self._take(frame[3])
                break
        meter = self.house.meter  # the grid meter: a separate device, not part of OCPP
        return Reading(
            clock=clock,
            grid_w=meter.reading_w,
            grid_age_s=meter.reading_age_s,
            car_w=self.last_car_w,
            phases=self.last_phases,
            plugged=self.plugged,
        )

    def _take(self, payload: dict[str, Any]) -> None:
        phases = set()
        for sample in payload["meterValue"][0]["sampledValue"]:
            if sample["measurand"] == "Power.Active.Import":
                self.last_car_w = float(sample["value"])
            elif sample["measurand"] == "Current.Import" and sample.get("phase"):
                phases.add(sample["phase"])
        if phases:
            self.last_phases = len(phases)

    def send(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Send the station any OCPP call and wait for its answer. The back office may ask anything."""
        socket = self._wait_for_station()
        message_id = str(next(self._ids))
        self._say(socket, _call(message_id, action, payload))
        while True:
            frame = self._hear(socket)
            if frame[0] == CALLRESULT and frame[1] == message_id:
                return dict(frame[2])
            if frame[0] == CALLERROR and frame[1] == message_id:
                return {"error": frame[2]}

    def apply(self, command: Command) -> None:
        socket = self._wait_for_station()
        message_id = str(next(self._ids))
        limit = command.amps if command.amps >= MIN_CHARGE_A else 0.0
        self._say(
            socket,
            _call(
                message_id,
                "SetChargingProfile",
                {
                    "connectorId": 1,
                    "csChargingProfiles": {
                        "chargingProfileId": 1,
                        "stackLevel": 0,
                        "chargingProfilePurpose": "TxDefaultProfile",
                        "chargingProfileKind": "Absolute",
                        "chargingSchedule": {
                            "chargingRateUnit": "A",
                            "chargingSchedulePeriod": [
                                {"startPeriod": 0, "limit": limit, "numberPhases": command.phases}
                            ],
                        },
                    },
                },
            ),
        )
        while True:
            frame = self._hear(socket)
            if frame[0] in (CALLRESULT, CALLERROR) and frame[1] == message_id:
                break

    def close(self) -> None:
        if hasattr(self, "_stay"):
            self._stay.set()
        self._server.shutdown()


def watts(amps: float, phases: int) -> float:
    return amps * phases * NOMINAL_V
