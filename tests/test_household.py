"""The house itself: the kettle, the oven, the washing machine.

To the meter, 2 kW switched on in the kitchen is the same event as a cloud of the same size. The
difference is that a kettle appears in one second rather than twenty, and goes away just as fast.
These are the tests that the house comes first: the household always gets its power, and the car
gets what is left.
"""

from __future__ import annotations

import pytest

from conftest import MakeRig
from support.evidence import note, step, watt_hours
from support.rig import Rig
from surplus_lab.control import Settings
from surplus_lab.house import Load

pytestmark = pytest.mark.once

HOUR = 3600


def one_phase(make_rig: MakeRig, day: str = "clear", **settings: object) -> Rig:
    rig = make_rig(day, Settings(allow_phase_switching=False, **settings))  # type: ignore[arg-type]
    rig.house.phases = 1
    rig.controller.phases = 1
    return rig


@pytest.mark.smoke
def test_the_house_comes_first_and_the_car_gets_what_is_left(make_rig: MakeRig) -> None:
    """When a 2.2 kW kettle goes on, the offer to the car falls by about the same amount."""
    # A 32 A single-phase wallbox, so the offer has room to fall rather than sitting against its cap.
    rig = one_phase(make_rig, max_a=32)
    rig.hours(4)
    before = rig.house.offered_a
    with step("a 2.2 kW kettle goes on in the kitchen"):
        rig.house.household.loads.append(Load("kettle", 2200.0, rig.house.clock, 10 * 60))
        rig.minutes(2)
        after = rig.house.offered_a
        note("offered before the kettle", f"{before:.0f} A")
        note("offered while it boils", f"{after:.0f} A")
        note("the difference, in watts", f"{(before - after) * 230:.0f} W")
        assert (before - after) * 230 == pytest.approx(2200, abs=500)


def test_the_offer_comes_back_when_the_kettle_goes_off(make_rig: MakeRig) -> None:
    """Once the kettle has boiled the car is offered the power back, after the rise delay."""
    rig = one_phase(make_rig, rise_delay_s=60)
    rig.hours(4)
    before = rig.house.offered_a
    with step("the kettle boils for three minutes and switches itself off"):
        rig.house.household.loads.append(Load("kettle", 2200.0, rig.house.clock, 3 * 60))
        rig.minutes(3)
        rig.minutes(5)
        note("offered before", f"{before:.0f} A")
        note("offered afterwards", f"{rig.house.offered_a:.0f} A")
        assert rig.house.offered_a >= before - 1


def test_a_load_that_outlasts_the_sun_does_not_leave_the_car_buying(make_rig: MakeRig) -> None:
    """An oven on for forty minutes takes the car's power, not the grid's."""
    rig = make_rig("kettle-and-oven")
    with step("a day with a kettle, an oven and a washing machine"):
        rig.run(until_s=21 * HOUR)
        totals = rig.totals
        watt_hours("used by the household", totals.house_wh)
        watt_hours("bought for the car", totals.bought_for_car_wh)
        assert totals.bought_for_car_wh <= 0.015 * totals.car_wh


def test_the_household_is_never_short_of_power(make_rig: MakeRig) -> None:
    """Whatever the controller does, the household takes everything it asked for, every second."""
    rig = make_rig("kettle-and-oven")
    rig.run(until_s=21 * HOUR)
    with step("every turn of the loop across the day"):
        asked = [tick.house_w for tick in rig.trace.ticks]
        note("the most the household asked for", f"{max(asked):.0f} W")
        assert min(asked) >= 300.0


def test_several_loads_at_once_are_just_a_bigger_load(make_rig: MakeRig) -> None:
    """Three appliances together move the offer by the sum of them, not by the largest."""
    rig = one_phase(make_rig, max_a=32)
    rig.hours(4)
    before = rig.house.offered_a
    with step("a kettle, a washing machine and an oven all go on together"):
        clock = rig.house.clock
        for name, watts in (("kettle", 900.0), ("washing machine", 800.0), ("oven", 700.0)):
            rig.house.household.loads.append(Load(name, watts, clock, 10 * 60))
        rig.minutes(2)
        note("the three together", "2400 W")
        note("the offer fell by", f"{(before - rig.house.offered_a) * 230:.0f} W")
        assert (before - rig.house.offered_a) * 230 == pytest.approx(2400, abs=500)


def test_a_load_bigger_than_the_sun_stops_the_car_rather_than_charging_on_the_grid(make_rig: MakeRig) -> None:
    """A load that swallows the whole surplus stops the session instead of charging from the grid."""
    rig = one_phase(make_rig)
    rig.hours(4)
    before = rig.totals.bought_for_car_wh
    with step("a 6 kW load that takes more than the roof is making"):
        rig.house.household.loads.append(Load("everything at once", 6000.0, rig.house.clock, 20 * 60))
        rig.minutes(10)
        bought = rig.totals.bought_for_car_wh - before
        note("offered", f"{rig.house.offered_a:.0f} A")
        watt_hours("bought for the car", bought)
        assert rig.house.offered_a == 0
        assert bought <= 80
