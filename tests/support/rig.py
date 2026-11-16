"""The world a test runs in: a house, a controller, and whichever driver this run is using.

``DRIVER=direct`` is the reference and the default: the controller talks to the model in the same
process, so a failure is a failure of the control law. ``DRIVER=modbus`` puts a real Modbus TCP
wallbox and a real socket in between; ``DRIVER=ocpp`` puts a real OCPP 1.6J charge point on a real
WebSocket. The behaviour suites run once, on the reference, because electricity does not care which
cable the number came down. The driver suites run everywhere, and one of them replays a whole day
through all three and compares them command for command.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import Any

from surplus_lab.control import Command, Controller, Reading, Settings
from surplus_lab.day import DAYS, HOUR, Trace, run
from surplus_lab.drivers.direct import DirectDriver
from surplus_lab.drivers.modbus import ModbusDriver, Wallbox, WallboxServer
from surplus_lab.drivers.ocpp import OcppDriver, Station
from surplus_lab.house import House

from .evidence import RECORDER


class Recorded:
    """Any driver, with every exchange written into the evidence of the running test."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.name = inner.name

    def read(self, clock: int) -> Reading:
        reading: Reading = self.inner.read(clock)
        if self.name != "direct":
            RECORDER.frame("<-", f"meter {reading.grid_w:.0f} W, car {reading.car_w:.0f} W, {reading.phases} phase(s)")
        return reading

    def apply(self, command: Command) -> None:
        if self.name != "direct":
            RECORDER.frame("->", f"offer {command.amps:.0f} A on {command.phases} phase(s)")
        self.inner.apply(command)

    def close(self) -> None:
        self.inner.close()


@dataclass
class Rig:
    """Everything one test needs, and the one call that runs a stretch of day through it."""

    house: House
    controller: Controller
    driver: Any
    trace: Trace = field(default_factory=Trace)
    _shut: list[Any] = field(default_factory=list)

    def run(self, *, until_s: int, tick_s: int = 10, events: dict[int, Any] | None = None) -> Trace:
        return run(
            self.house,
            self.controller,
            self.driver,
            until_s=until_s,
            tick_s=tick_s,
            trace=self.trace,
            events=events,
        )

    def hours(self, count: float, *, tick_s: int = 10) -> Trace:
        return self.run(until_s=self.house.clock + int(count * HOUR), tick_s=tick_s)

    def minutes(self, count: float, *, tick_s: int = 10) -> Trace:
        return self.run(until_s=self.house.clock + int(count * 60), tick_s=tick_s)

    def tick(self, *, tick_s: int = 10) -> Command:
        """One turn of the loop, for a test that wants to look between two of them."""
        reading = self.driver.read(self.house.clock)
        command = self.controller.decide(reading)
        self.driver.apply(command)
        self.house.advance(tick_s)
        return command

    @property
    def totals(self) -> Any:
        return self.house.totals

    def close(self) -> None:
        for thing in [self.driver, *reversed(self._shut)]:
            # Tearing down a socket must never be the thing that fails a test.
            with contextlib.suppress(Exception):
                thing.close()


def build(driver_name: str, day: str = "clear", settings: Settings | None = None) -> Rig:
    """A house on the given day, with a controller, reached through the given kind of wallbox."""
    house = DAYS[day]()
    controller = Controller(settings=settings or Settings(), phases=house.phases)
    shut: list[Any] = []

    if driver_name == "direct":
        driver: Any = DirectDriver(house)
    elif driver_name == "modbus":
        wallbox = Wallbox(house)
        server = WallboxServer(wallbox)
        shut.append(server)
        driver = ModbusDriver(server.host, server.port)
    elif driver_name == "ocpp":
        back_office = OcppDriver(house)
        station = Station(house, back_office.url)
        shut.append(station)
        driver = back_office
    else:  # pragma: no cover - the environment variable is checked in conftest
        raise ValueError(driver_name)

    return Rig(house=house, controller=controller, driver=Recorded(driver), _shut=shut)
