"""The surplus controller: the thing under test.

It has one lever — how many amps the cable offers the car, and on how many phases — and one
instrument: the meter at the house connection point. It never sees the sun directly. That is on
purpose, and it is how every real installation works: the meter is the only place where the truth
about import and export exists.

The arithmetic is one line. Everything else in this file is about time.

    the car may take  =  what the car takes now  -  what the meter reads  +  the margin we allow

If the meter reads +200 W while the car is pulling 3000 W, then 2800 W of what the car is taking is
coming from the sun and 200 W from the grid: the car may have 2800 W. If the meter reads -1500 W, the
house is spilling 1500 W into the grid and the car may have 4500 W.

Turning that into a command is where it gets interesting, because three promises pull against each
other:

1. **Buy nothing.** When a cloud arrives or a kettle goes on, the surplus vanishes in one second. The
   offer has to come down at once, or the house starts buying.
2. **Sell nothing.** When the sun comes back, the offer has to go up, or the house gives the surplus
   away.
3. **Leave the car alone.** A car is not a dimmer. Every change is a message, every pause is a
   contactor, and a car that is paused and resumed every ninety seconds will eventually sulk and
   refuse to wake up.

Promise 1 wants an instant reaction. Promise 3 wants none. This controller resolves that by being
**asymmetric in time**: it comes down immediately and goes up only after the higher surplus has
held for a while. Broken cloud therefore costs a little spilled energy, which is the cheap mistake,
rather than a bought kilowatt-hour or a car that has been switched twenty times, which are the
expensive ones.

The rest is bookkeeping: the 6 A floor of IEC 61851-1, below which the pilot cannot ask a car for
anything at all; hysteresis so the floor is not a cliff to fall off and climb back up every minute;
a cooldown on switching between one and three phases, which costs a stop and a start; and a
fail-safe for the moment the meter goes quiet, because a controller that keeps charging on a stale
reading is buying from the grid with its eyes shut.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .house import MIN_CHARGE_A, NOMINAL_V, clamp


@dataclass(frozen=True)
class Settings:
    """Every number the control law uses, in one place, in the units a person would say them in."""

    margin_w: float = 0.0
    """What we aim the meter at. Zero means break even. A positive value buys a little on purpose,
    which some people prefer because it keeps the meter off the export side entirely."""

    max_a: float = 16.0
    """What the wallbox can offer per phase."""

    rise_delay_s: int = 120
    """A larger offer is made only after that much surplus has been there this long. This is the
    number that decides how much a passing cloud costs and how much a car is pestered."""

    fall_delay_s: int = 0
    """A smaller offer is made at once. This exists so a test can prove that it is zero."""

    pause_delay_s: int = 180
    """Below 6 A the car cannot charge at all, but a cloud is not a reason to stop a session."""

    ride_out_budget_wh: float = 60.0
    """What riding out a cloud is allowed to cost.

    Holding the floor through a shadow keeps the session alive, and it buys electricity for as long
    as the shadow lasts: 6 A on one phase is 1.4 kW coming off the grid, and on three phases it is
    4.1 kW. Waiting a fixed three minutes is therefore a promise to spend whatever three minutes
    costs, which on a day of broken cloud is kilowatt-hours. So the wait is bounded by money as well
    as by time.

    Sixty watt-hours is not arbitrary. Letting go costs a restart, and a restart costs the resume
    delay — five minutes of surplus given to the grid, which at four kilowatts is about 330 Wh of
    sun. Bought electricity costs roughly four times what spilled electricity earns, so 330 Wh of
    spilled sun is worth about 80 Wh of bought electricity. Anything under that and holding on is
    the cheaper mistake. The budget sits just inside it.

    It also makes the controller sensibly impatient on three phases, where the same six amps costs
    three times as much, and the budget therefore runs out three times sooner."""

    resume_delay_s: int = 300
    """Starting again is the expensive move, so it asks for more patience than stopping did."""

    min_dwell_s: int = 60
    """No two raises closer together than this, whatever the sun does."""

    phase_switch_delay_s: int = 600
    phase_switch_cooldown_s: int = 1800
    """Switching between one and three phases means stopping the session, so it is rare by design."""

    phase_switch_margin_w: float = 500.0
    """How far above the three-phase floor the surplus must be before going up to three phases.

    Three phases cannot carry anything at all below 3 x 6 A, which is 4140 W: the smallest three-
    phase charge there is. One phase carries up to 16 A, which is 3680 W. Between those two numbers
    one phase is the only thing that works, so the switch up has to be at the three-phase floor and
    not at the one-phase ceiling, and it needs this much room above it so the pair of thresholds do
    not sit on top of each other and flap."""

    stale_after_s: int = 60
    """A meter reading older than this is not a reading. The controller stops rather than guess."""

    allow_phase_switching: bool = True


@dataclass
class Reading:
    """What the controller is given at each tick: the meter, the car, and the clock."""

    clock: int
    grid_w: float
    """Positive is bought from the grid, negative is sold to it."""
    grid_age_s: int
    car_w: float
    """What the car is drawing right now, as the wallbox reports it."""
    phases: int
    plugged: bool = True


@dataclass(frozen=True)
class Command:
    """What the controller wants the cable to do. ``amps`` of zero means pause."""

    amps: float
    phases: int
    why: str

    @property
    def charging(self) -> bool:
        return self.amps >= MIN_CHARGE_A


@dataclass
class Controller:
    """The surplus controller. One lever, one instrument, three promises."""

    settings: Settings = field(default_factory=Settings)
    offered_a: float = 0.0
    phases: int = 3
    last_raise_s: int | None = None
    last_phase_switch_s: int | None = None
    _want: tuple[float, int] | None = None
    """What the controller last wanted to offer, and the moment it started wanting it."""
    _below_floor_since: int | None = None
    _above_floor_since: int | None = None
    _ride_out_wh: float = 0.0
    _last_clock: int | None = None
    _phase_wish: tuple[int, int] | None = None
    history: list[Command] = field(default_factory=list)

    # ---- the arithmetic ---------------------------------------------------------------------

    def available_w(self, reading: Reading) -> float:
        """How much the car may take, in watts, if the meter is to read the margin we aim at."""
        return reading.car_w - reading.grid_w + self.settings.margin_w

    def available_a(self, reading: Reading, phases: int) -> float:
        """The same, as whole amps per phase. Rounded down, because rounding up buys electricity."""
        amps = self.available_w(reading) / (phases * NOMINAL_V)
        return float(int(clamp(amps, 0.0, self.settings.max_a)))

    # ---- the timing -------------------------------------------------------------------------

    def _wanted_since(self, value: float, now: int) -> int:
        """Since when the controller has wanted exactly this. Wanting something else restarts the clock.

        This is the only place where that clock is kept, and the only place it is restarted. Every
        rule about how fast the offer may move is then one subtraction against it, which is the point:
        a second place to reset the clock is a second place to get it wrong, and the bug it hides
        would look exactly like the controller working.
        """
        if self._want is None or self._want[0] != value:
            self._want = (value, now)
        return self._want[1]

    def _phase_wished_since(self, wish: int, now: int) -> int:
        """The same clock, for wanting the house wired a different way."""
        if self._phase_wish is None or self._phase_wish[0] != wish:
            self._phase_wish = (wish, now)
        return self._phase_wish[1]

    def decide(self, reading: Reading) -> Command:
        """Look at the meter and say what the cable should offer."""
        s = self.settings
        now = reading.clock
        since_last = 0 if self._last_clock is None else max(0, now - self._last_clock)
        self._last_clock = now

        if reading.grid_age_s > s.stale_after_s:
            # Without a meter there is no way to keep a promise about import, so stop promising.
            return self._set(0.0, self.phases, "the meter has gone quiet", now)
        if not reading.plugged:
            return self._set(0.0, self.phases, "no car on the cable", now)

        wanted = self.available_a(reading, self.phases)

        phases = self._phases_wanted(reading, now)
        if phases != self.phases:
            # Changing phases stops the session, so the new offer is computed for the new wiring.
            wanted = self.available_a(reading, phases)
            return self._set(max(wanted, MIN_CHARGE_A), phases, f"switching to {phases} phase(s)", now)

        if wanted < MIN_CHARGE_A:
            self._above_floor_since = None
            if self._below_floor_since is None:
                self._below_floor_since = now
                self._ride_out_wh = 0.0
            if self.offered_a == 0.0:
                return self._set(0.0, self.phases, "not enough sun for the smallest charge", now)
            self._ride_out_wh += max(0.0, reading.grid_w) * since_last / 3600.0
            if now - self._below_floor_since >= s.pause_delay_s:
                return self._set(0.0, self.phases, "the sun has been short for too long", now)
            if self._ride_out_wh >= s.ride_out_budget_wh:
                return self._set(0.0, self.phases, "riding out the shadow has cost enough", now)
            # Hold the floor through a passing cloud rather than stop the session for it.
            return self._set(MIN_CHARGE_A, self.phases, "riding out a short shortage at 6 A", now)

        self._below_floor_since = None
        self._ride_out_wh = 0.0
        if self.offered_a == 0.0:
            if self._above_floor_since is None:
                self._above_floor_since = now
            if now - self._above_floor_since < s.resume_delay_s:
                return self._set(0.0, self.phases, "waiting to be sure the sun is back", now)
            return self._set(wanted, self.phases, "the sun is back for good", now)

        if wanted < self.offered_a:
            if now - self._wanted_since(wanted, now) >= s.fall_delay_s:
                return self._set(wanted, self.phases, "less sun, giving the car less at once", now)
            return self._hold(now)

        if wanted > self.offered_a:
            if self.last_raise_s is not None and now - self.last_raise_s < s.min_dwell_s:
                return self._hold(now)
            if now - self._wanted_since(wanted, now) >= s.rise_delay_s:
                self.last_raise_s = now
                return self._set(wanted, self.phases, "the surplus has held, giving the car more", now)
            return self._hold(now)

        self._wanted_since(wanted, now)
        return self._hold(now)

    # ---- phases -----------------------------------------------------------------------------

    def _phases_wanted(self, reading: Reading, now: int) -> int:
        s = self.settings
        if not s.allow_phase_switching:
            return self.phases
        if self.last_phase_switch_s is not None and now - self.last_phase_switch_s < s.phase_switch_cooldown_s:
            return self.phases
        watts = self.available_w(reading)
        three_phase_floor = 3 * MIN_CHARGE_A * NOMINAL_V  # 4140 W: the smallest a three-phase car can take
        wish = self.phases
        if self.phases == 3 and watts < three_phase_floor:
            wish = 1
        elif self.phases == 1 and watts > three_phase_floor + s.phase_switch_margin_w:
            wish = 3
        if wish == self.phases:
            self._phase_wish = None
            return self.phases
        if now - self._phase_wished_since(wish, now) >= s.phase_switch_delay_s:
            self.last_phase_switch_s = now
            self._phase_wish = None
            return wish
        return self.phases

    # ---- bookkeeping ------------------------------------------------------------------------

    def _set(self, amps: float, phases: int, why: str, now: int) -> Command:
        if phases != self.phases:
            self.phases = phases
        if amps > self.offered_a and amps > 0:
            self.last_raise_s = now
        self.offered_a = amps
        command = Command(amps=amps, phases=phases, why=why)
        self.history.append(command)
        return command

    def _hold(self, now: int) -> Command:
        command = Command(amps=self.offered_a, phases=self.phases, why="no change")
        self.history.append(command)
        return command
