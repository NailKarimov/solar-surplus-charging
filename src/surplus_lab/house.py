"""The house: the sun on the roof, what the household uses, the car on the cable, and the meter at the door.

Nothing here knows about control. The house simply is: the sun rises, clouds pass, a kettle goes on,
the car takes what the cable offers it. The controller in ``control.py`` sees this world only through
the grid meter and has to keep that meter reading zero.

Simulated time moves only when ``advance`` is called, so every run sees the same day.

Sign convention, which is the thing to get right once and never think about again:

    grid = house + car - pv

Positive grid means **import**: the house is buying from the grid. Negative means **export**: it is
selling. The controller's whole job is to keep that number at zero by changing one thing only — how
many amps the cable offers the car.

What is modelled:

- the **sun**: a clear-sky curve for the day, multiplied by a cloud factor that can drop to a fifth of
  full sun within a few seconds and come back. Broken cloud is the hardest weather for this job.
- the **inverter**: it clips at its rated power, and it reports with a delay, because a real one
  publishes an average over its sampling period.
- the **household**: a quiet baseline plus switched loads — a kettle, an oven, a heat pump — that come
  on without warning. 2 kW appearing in one second is the same event, to the meter, as a cloud.
- the **car**: it takes up to what the pilot offers, never more, and it ramps rather than jumping. A
  nearly full car tapers and takes less than it is allowed; the controller must notice.
- the **meter**: it samples, it averages over its period, and it can go silent. A controller that
  trusts a stale reading will buy from the grid for as long as the meter stays stuck.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

NOMINAL_V = 230.0
MIN_CHARGE_A = 6.0  # below this the pilot cannot ask a car to charge (IEC 61851-1)
SECONDS_PER_DAY = 24 * 3600


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


# ---- the sun --------------------------------------------------------------------------------------


@dataclass
class Cloud:
    """One cloud passing over the roof: when it starts, how long it lasts, how much light is left."""

    start_s: int
    seconds: int
    factor: float  # 1.0 is no cloud at all, 0.15 is a heavy one
    edge_s: int = 20  # how long the shadow takes to cross the array

    def at(self, clock: int) -> float:
        """How much of full sun is left at this moment."""
        if clock <= self.start_s or clock >= self.start_s + self.seconds:
            return 1.0
        into = clock - self.start_s
        left = self.start_s + self.seconds - clock
        edge = max(1, self.edge_s)
        ramp = min(1.0, into / edge, left / edge)
        return 1.0 - (1.0 - self.factor) * ramp


@dataclass
class Sky:
    """The clear-sky curve of one day, with clouds laid over it.

    The curve is a half sine between sunrise and sunset: crude, but it is the shape that matters —
    the surplus is small and twitchy at the edges of the day and broad in the middle.
    """

    peak_w: float = 6000.0  # what the array makes at noon with no cloud
    sunrise_s: int = 6 * 3600
    sunset_s: int = 21 * 3600
    clouds: list[Cloud] = field(default_factory=list)
    haze: float = 1.0  # a flat factor for a dull day

    def clear_sky_w(self, clock: int) -> float:
        if clock <= self.sunrise_s or clock >= self.sunset_s:
            return 0.0
        day = (clock - self.sunrise_s) / (self.sunset_s - self.sunrise_s)
        return self.peak_w * math.sin(math.pi * day) * self.haze

    def cloud_factor(self, clock: int) -> float:
        factor = 1.0
        for cloud in self.clouds:
            factor = min(factor, cloud.at(clock))
        return factor

    def power_w(self, clock: int) -> float:
        return self.clear_sky_w(clock) * self.cloud_factor(clock)


@dataclass
class Inverter:
    """The inverter between the panels and the house: it clips, and it reports an average."""

    rated_w: float = 5000.0
    sky: Sky = field(default_factory=Sky)

    def power_w(self, clock: int) -> float:
        return min(self.rated_w, self.sky.power_w(clock))


# ---- the household --------------------------------------------------------------------------------


@dataclass
class Load:
    """A switched household load: a kettle, an oven, a heat pump."""

    name: str
    watts: float
    start_s: int
    seconds: int

    def at(self, clock: int) -> float:
        return self.watts if self.start_s <= clock < self.start_s + self.seconds else 0.0


@dataclass
class Household:
    """What the house uses without the car: a baseline plus whatever is switched on."""

    baseline_w: float = 300.0
    loads: list[Load] = field(default_factory=list)

    def power_w(self, clock: int) -> float:
        return self.baseline_w + sum(load.at(clock) for load in self.loads)

    def running(self, clock: int) -> list[str]:
        return [load.name for load in self.loads if load.at(clock) > 0]


# ---- the car --------------------------------------------------------------------------------------


@dataclass
class Car:
    """The car on the cable.

    It never takes more than the pilot offers. It ramps towards the offer rather than jumping, and
    once it is nearly full it tapers: the offer stays high while the car quietly takes less. A
    controller that assumes the car takes exactly what it was offered will buy from the grid or spill
    sun into it, and never know why.
    """

    battery_wh: float = 60_000.0
    charged_wh: float = 18_000.0
    max_a: float = 16.0  # what the car's own charger can take, per phase
    ramp_a_per_s: float = 2.0  # how fast it follows a change in the offer
    taper_from: float = 0.85  # above this state of charge it starts taking less
    plugged: bool = True
    drawing_a: float = 0.0  # per phase, right now

    def soc(self) -> float:
        return clamp(self.charged_wh / self.battery_wh, 0.0, 1.0)

    def wanted_a(self, offered_a: float) -> float:
        """What the car will settle at, given this offer."""
        if not self.plugged or offered_a < MIN_CHARGE_A:
            return 0.0
        ceiling = min(offered_a, self.max_a)
        soc = self.soc()
        if soc >= 1.0:
            return 0.0
        if soc > self.taper_from:
            left = (1.0 - soc) / (1.0 - self.taper_from)
            ceiling = min(ceiling, max(MIN_CHARGE_A, self.max_a * left))
        return ceiling

    def step(self, offered_a: float, phases: int, seconds: int) -> float:
        """Move towards the offer for this many seconds and return the energy taken, in watt-hours."""
        target = self.wanted_a(offered_a)
        step_a = self.ramp_a_per_s * seconds
        if target <= 0.0:
            # Letting go: the contactor opens once the current is down near nothing.
            self.drawing_a = max(0.0, self.drawing_a - step_a)
            if self.drawing_a < MIN_CHARGE_A:
                self.drawing_a = 0.0
        elif self.drawing_a < MIN_CHARGE_A:
            # Starting: a car does not creep up from zero, it closes its contactor at the floor.
            self.drawing_a = min(target, MIN_CHARGE_A)
        elif target > self.drawing_a:
            self.drawing_a = min(target, self.drawing_a + step_a)
        else:
            self.drawing_a = max(target, self.drawing_a - step_a)
        watt_hours = self.power_w(phases) * seconds / 3600.0
        self.charged_wh = min(self.battery_wh, self.charged_wh + watt_hours)
        return watt_hours

    def power_w(self, phases: int) -> float:
        return self.drawing_a * phases * NOMINAL_V


# ---- the meter ------------------------------------------------------------------------------------


@dataclass
class Meter:
    """The meter at the house connection point.

    It does not report the instant truth. It averages over its sampling period and publishes that,
    which is why a controller reacting to a single sample reacts to something that already ended.
    ``silent`` makes it stop publishing: the last reading stays on the wire and goes stale.
    """

    period_s: int = 5
    noise_w: float = 0.0
    silent: bool = False
    reading_w: float = 0.0
    reading_age_s: int = 0
    _sum_w: float = 0.0
    _sum_s: int = 0

    def observe(self, grid_w: float, seconds: int) -> None:
        self._sum_w += grid_w * seconds
        self._sum_s += seconds
        self.reading_age_s += seconds
        if self._sum_s >= self.period_s:
            if not self.silent:
                self.reading_w = self._sum_w / self._sum_s + self.noise_w
                self.reading_age_s = 0
            self._sum_w = 0.0
            self._sum_s = 0


# ---- the whole place ------------------------------------------------------------------------------


@dataclass
class Totals:
    """What the day added up to. These are the numbers the promises are measured against.

    Two of them are the promises themselves, and both are written to be fair to the controller:

    - ``bought_for_car_wh`` is the part of the import the car is responsible for. If the household
      uses more than the roof is making, the house buys electricity and no controller can stop it;
      that is not a broken promise. What would not have happened with the car unplugged is.
    - ``spilled_wh`` is export the car could actually have taken: the car has to be plugged in, not
      full, and the surplus has to be at least the smallest charge the pilot can ask for. Sun given
      away below that floor is physics, not a mistake.
    """

    imported_wh: float = 0.0  # bought from the grid, all of it
    exported_wh: float = 0.0  # sold to the grid, all of it
    car_wh: float = 0.0  # into the car
    car_from_sun_wh: float = 0.0  # of that, what the sun paid for
    pv_wh: float = 0.0
    house_wh: float = 0.0
    bought_for_car_wh: float = 0.0  # promise 1: import that the car caused
    spilled_wh: float = 0.0  # promise 2: export the car could have taken and did not


@dataclass
class House:
    """The sun, the household, the car and the meter, stepped together by a simulated clock."""

    inverter: Inverter = field(default_factory=Inverter)
    household: Household = field(default_factory=Household)
    car: Car = field(default_factory=Car)
    meter: Meter = field(default_factory=Meter)
    clock: int = 6 * 3600
    phases: int = 3
    offered_a: float = 0.0
    totals: Totals = field(default_factory=Totals)

    def pv_w(self) -> float:
        return self.inverter.power_w(self.clock)

    def house_w(self) -> float:
        return self.household.power_w(self.clock)

    def car_w(self) -> float:
        return self.car.power_w(self.phases)

    def grid_w(self) -> float:
        """Positive is bought from the grid, negative is sold to it."""
        return self.house_w() + self.car_w() - self.pv_w()

    def usable_export_w(self, export_w: float) -> float:
        """How much of this export the car could actually have taken at this moment.

        A car that is unplugged or full can take nothing. A car already charging can take whatever is
        left up to its own ceiling. A car standing idle can only be started if there is at least the
        smallest charge the pilot can ask for — below that, the sun has nowhere to go.
        """
        car = self.car
        ceiling_a = car.wanted_a(car.max_a)  # what the car itself would accept, tapering included
        if ceiling_a <= 0.0:
            return 0.0
        one_amp_w = self.phases * NOMINAL_V
        if car.drawing_a > 0:
            headroom_a = max(0.0, ceiling_a - car.drawing_a)
            usable = min(export_w, headroom_a * one_amp_w)
            # A pilot speaks in whole amps. Less than one amp of sun going out could not have been
            # offered to the car at all without buying the difference, so it does not count.
            return usable if usable >= one_amp_w else 0.0
        return export_w if export_w >= MIN_CHARGE_A * NOMINAL_V else 0.0

    def offer(self, amps: float, phases: int | None = None) -> None:
        """What the cable offers the car. This is the only thing a controller may change."""
        if phases is not None:
            self.phases = phases
        self.offered_a = 0.0 if amps < MIN_CHARGE_A else amps

    def advance(self, seconds: int) -> None:
        """Let the world run for this many seconds, one second at a time."""
        for _ in range(seconds):
            pv = self.pv_w()
            house = self.house_w()
            car_wh = self.car.step(self.offered_a, self.phases, 1)
            grid = self.grid_w()
            self.meter.observe(grid, 1)
            hours = 1 / 3600.0
            self.totals.pv_wh += pv * hours
            self.totals.house_wh += house * hours
            self.totals.car_wh += car_wh
            if grid > 0:
                self.totals.imported_wh += grid * hours
                # Only what the car caused: with the car unplugged this much would not be bought.
                self.totals.bought_for_car_wh += min(grid, self.car_w()) * hours
            else:
                export = -grid
                self.totals.exported_wh += export * hours
                self.totals.spilled_wh += self.usable_export_w(export) * hours
            # the share of the car's energy the sun paid for: the sun first covers the house
            sun_left = max(0.0, pv - house)
            self.totals.car_from_sun_wh += min(car_wh, sun_left * hours)
            self.clock += 1

    def snapshot(self) -> dict[str, float]:
        """What a dashboard would show right now."""
        return {
            "clock": self.clock,
            "pv_w": self.pv_w(),
            "house_w": self.house_w(),
            "car_w": self.car_w(),
            "grid_w": self.grid_w(),
            "offered_a": self.offered_a,
            "drawing_a": self.car.drawing_a,
            "phases": self.phases,
            "soc": self.car.soc(),
        }
