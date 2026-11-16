"""Days to run, and the loop that runs one.

A day is a set of weather, a household and a car. The loop is four lines: ask the wallbox what is
happening, decide, tell the wallbox, let a few seconds pass. Everything the project claims is
measured over a whole day of that loop, because a controller can look perfect for one tick and still
buy a kilowatt-hour before lunch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .control import Command, Controller, Reading
from .house import Car, Cloud, House, Household, Inverter, Load, Meter, Sky

HOUR = 3600


class AnyDriver(Protocol):
    name: str

    def read(self, clock: int) -> Reading: ...
    def apply(self, command: Command) -> None: ...
    def close(self) -> None: ...


@dataclass
class Tick:
    """One turn of the loop, kept so the report and the visual page can replay the day."""

    clock: int
    pv_w: float
    house_w: float
    car_w: float
    grid_w: float
    offered_a: float
    phases: int
    why: str
    soc: float


@dataclass
class Trace:
    """A whole day as it happened."""

    ticks: list[Tick] = field(default_factory=list)
    changes: int = 0
    pauses: int = 0
    resumes: int = 0
    phase_switches: int = 0

    def add(self, house: House, command: Command, previous: Command | None) -> None:
        self.ticks.append(
            Tick(
                clock=house.clock,
                pv_w=house.pv_w(),
                house_w=house.house_w(),
                car_w=house.car_w(),
                grid_w=house.grid_w(),
                offered_a=command.amps,
                phases=command.phases,
                why=command.why,
                soc=house.car.soc(),
            )
        )
        if previous is None:
            return
        if command.amps != previous.amps:
            self.changes += 1
            if command.amps == 0:
                self.pauses += 1
            elif previous.amps == 0:
                self.resumes += 1
        if command.phases != previous.phases:
            self.phase_switches += 1

    def per_hour(self, count: int, house: House, started: int) -> float:
        hours = max(1e-9, (house.clock - started) / HOUR)
        return count / hours


def run(
    house: House,
    controller: Controller,
    driver: AnyDriver,
    *,
    until_s: int,
    tick_s: int = 10,
    trace: Trace | None = None,
    events: dict[int, Any] | None = None,
) -> Trace:
    """Run the loop until the clock reaches ``until_s``. Returns what happened."""
    trace = trace if trace is not None else Trace()
    previous: Command | None = None
    events = events or {}
    while house.clock < until_s:
        for at, change in list(events.items()):
            if house.clock >= at:
                change(house)
                del events[at]
        reading = driver.read(house.clock)
        command = controller.decide(reading)
        driver.apply(command)
        house.advance(tick_s)
        trace.add(house, command, previous)
        previous = command
    return trace


# ---- the days ---------------------------------------------------------------------------------


def _house(sky: Sky, loads: list[Load], *, car: Car | None = None, start_h: int = 8) -> House:
    return House(
        inverter=Inverter(rated_w=5000.0, sky=sky),
        household=Household(baseline_w=300.0, loads=loads),
        car=car if car is not None else Car(),
        meter=Meter(period_s=5),
        clock=start_h * HOUR,
    )


def clear_day() -> House:
    """Nothing in the way of the sun, nothing much on in the house."""
    return _house(Sky(peak_w=6000.0), [])


def broken_cloud() -> House:
    """The hard one: cloud after cloud, each a few minutes, the surplus halving and coming back."""
    clouds = [Cloud(start_s=9 * HOUR + n * 900, seconds=300, factor=0.25 if n % 2 else 0.45) for n in range(16)]
    return _house(Sky(peak_w=6000.0, clouds=clouds), [])


def one_long_cloud() -> House:
    """A single cloud long enough that holding the session open is the wrong answer."""
    return _house(Sky(peak_w=6000.0, clouds=[Cloud(start_s=11 * HOUR, seconds=50 * 60, factor=0.1)]), [])


def kettle_and_oven() -> House:
    """Clear sky, but the household keeps switching things on without warning."""
    loads = [
        Load("kettle", 2200.0, 9 * HOUR + 1200, 180),
        Load("oven", 2400.0, 11 * HOUR, 45 * 60),
        Load("washing machine", 2000.0, 13 * HOUR, 30 * 60),
        Load("kettle", 2200.0, 14 * HOUR, 180),
    ]
    return _house(Sky(peak_w=6000.0), loads)


def dull_day() -> House:
    """Not enough sun for the smallest charge the pilot can ask for, most of the day."""
    return _house(Sky(peak_w=6000.0, haze=0.22), [])


def almost_full_car() -> House:
    """The car tapers: the offer stays high while it quietly takes less."""
    return _house(Sky(peak_w=6000.0), [], car=Car(charged_wh=54_000.0))


def morning_to_evening() -> House:
    """A whole day from first light, with everything in it: cloud, loads and a tapering car."""
    clouds = [
        Cloud(start_s=10 * HOUR, seconds=600, factor=0.3),
        Cloud(start_s=12 * HOUR + 1800, seconds=1200, factor=0.2),
        Cloud(start_s=15 * HOUR, seconds=400, factor=0.5),
    ]
    loads = [
        Load("kettle", 2200.0, 8 * HOUR, 200),
        Load("oven", 2400.0, 12 * HOUR, 40 * 60),
        Load("heat pump", 1200.0, 16 * HOUR, 90 * 60),
    ]
    return _house(Sky(peak_w=6000.0, clouds=clouds), loads, start_h=7)


DAYS = {
    "clear": clear_day,
    "broken-cloud": broken_cloud,
    "one-long-cloud": one_long_cloud,
    "kettle-and-oven": kettle_and_oven,
    "dull": dull_day,
    "almost-full-car": almost_full_car,
    "whole-day": morning_to_evening,
}
