"""The three promises, measured over whole days.

These are the tests the project exists for. Everything else checks a rule; these check the result of
all the rules together, on a day that actually happened, in kilowatt-hours.

The budgets are not zero, and saying so is the honest part. A controller that promised to buy
absolutely nothing would have to leave a safety margin so wide that it gave most of the sun away,
and one that promised to give nothing away would buy electricity every time a cloud crossed. What
can be promised is that the mistakes stay small and stay on the cheap side: a few watt-hours bought,
a fraction of the surplus spilled, and a car that is left alone.
"""

from __future__ import annotations

import pytest

from conftest import MakeRig
from support.evidence import note, step, watt_hours
from support.rig import Rig
from surplus_lab.day import HOUR

pytestmark = pytest.mark.once

# Each day, and what it is allowed to cost. Watt-hours bought for the car, watt-hours of surplus
# given away that the car could have taken, and how often the car may be disturbed.
BOUGHT_SHARE = 0.015
"""Promise one, as one number for every day: of the energy that reached the car, at most this much
came off the grid rather than off the roof."""

BOUGHT_CAP_WH = 600
"""And never more than this in absolute terms, so a day that charges very little cannot pass on a
percentage."""

BUDGETS = {
    "clear": {"spill_share": 0.05, "changes_per_hour": 3.0, "pauses_per_hour": 0.5},
    "broken-cloud": {"spill_share": 0.16, "changes_per_hour": 8.0, "pauses_per_hour": 1.5},
    "one-long-cloud": {"spill_share": 0.06, "changes_per_hour": 4.0, "pauses_per_hour": 0.6},
    "kettle-and-oven": {"spill_share": 0.09, "changes_per_hour": 4.0, "pauses_per_hour": 0.6},
    "almost-full-car": {"spill_share": 0.05, "changes_per_hour": 3.0, "pauses_per_hour": 0.5},
    "whole-day": {"spill_share": 0.09, "changes_per_hour": 5.0, "pauses_per_hour": 0.8},
}


def whole_day(rig: Rig) -> tuple[float, float]:
    started = rig.house.clock
    rig.run(until_s=21 * HOUR, tick_s=10)
    return started, (rig.house.clock - started) / HOUR


@pytest.mark.smoke
@pytest.mark.parametrize("day", list(BUDGETS))
def test_the_day_is_charged_without_buying_electricity_for_the_car(make_rig: MakeRig, day: str) -> None:
    """On every day of the set, what the car cost in bought electricity stays inside its budget."""
    rig = make_rig(day)
    with step(f"a whole day: {day.replace('-', ' ')}"):
        whole_day(rig)
        totals = rig.totals
        share = totals.bought_for_car_wh / max(1.0, totals.car_wh)
        watt_hours("into the car", totals.car_wh)
        watt_hours("bought for the car", totals.bought_for_car_wh)
        note("of the car's energy, bought rather than made", f"{100 * share:.1f} %")
        assert share <= BOUGHT_SHARE
        assert totals.bought_for_car_wh <= BOUGHT_CAP_WH


@pytest.mark.parametrize("day", list(BUDGETS))
def test_the_sun_is_not_given_away_while_the_car_could_take_it(make_rig: MakeRig, day: str) -> None:
    """On every day of the set, the surplus handed to the grid that the car could have had stays small."""
    rig = make_rig(day)
    budget = BUDGETS[day]
    with step(f"a whole day: {day.replace('-', ' ')}"):
        whole_day(rig)
        totals = rig.totals
        share = totals.spilled_wh / max(1.0, totals.pv_wh)
        watt_hours("made by the roof", totals.pv_wh)
        watt_hours("given away that the car could have taken", totals.spilled_wh)
        note("of everything the roof made", f"{100 * share:.1f} %")
        assert share <= budget["spill_share"]


@pytest.mark.parametrize("day", list(BUDGETS))
def test_the_car_is_not_jerked_about(make_rig: MakeRig, day: str) -> None:
    """On every day of the set, the offer is changed and the session stopped no more often than allowed."""
    rig = make_rig(day)
    budget = BUDGETS[day]
    with step(f"a whole day: {day.replace('-', ' ')}"):
        _started, hours = whole_day(rig)
        trace = rig.trace
        note("changes of the offer", f"{trace.changes} in {hours:.0f} h")
        note("times the session was stopped", str(trace.pauses))
        note("times it was started again", str(trace.resumes))
        assert trace.changes / hours <= budget["changes_per_hour"]
        assert trace.pauses / hours <= budget["pauses_per_hour"]


def test_a_dull_day_charges_almost_nothing_rather_than_buying_it(make_rig: MakeRig) -> None:
    """On a day with too little sun for the smallest charge, the car is left alone instead of bought for."""
    rig = make_rig("dull")
    with step("a dull day: the roof never makes enough for 6 A"):
        whole_day(rig)
        totals = rig.totals
        watt_hours("into the car", totals.car_wh)
        watt_hours("bought for the car", totals.bought_for_car_wh)
        assert totals.car_wh < 500
        assert totals.bought_for_car_wh < 50


def test_nearly_all_of_what_the_car_got_was_paid_for_by_the_roof(make_rig: MakeRig) -> None:
    """Over a whole ordinary day, at least nineteen twentieths of the car's energy came from the roof."""
    rig = make_rig("whole-day")
    with step("a whole day from first light, with cloud, a kettle, an oven and a heat pump"):
        whole_day(rig)
        totals = rig.totals
        share = totals.car_from_sun_wh / max(1.0, totals.car_wh)
        note("the sun's share of the car's energy", f"{100 * share:.1f} %")
        assert share >= 0.95


def test_the_meter_balance_is_not_bought_by_spilling_instead(make_rig: MakeRig) -> None:
    """Keeping the meter at zero is not achieved by simply refusing to charge: the car is filled."""
    rig = make_rig("clear")
    with step("a clear day"):
        whole_day(rig)
        totals = rig.totals
        taken = totals.car_wh / max(1.0, totals.car_wh + totals.spilled_wh)
        note("the car's share of the surplus it could have had", f"{100 * taken:.0f} %")
        assert totals.car_wh > 25_000
        assert taken >= 0.9
