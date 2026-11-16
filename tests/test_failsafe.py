"""What the controller does when it cannot see.

The meter is the only instrument there is. A controller that keeps charging on a reading that
stopped changing half an hour ago is not keeping a promise about the grid; it is hoping. The safe
answer is to stop, because stopping cannot buy electricity.

The same goes for a car that has been unplugged and a wallbox that will not answer at all.
"""

from __future__ import annotations

import pytest

from conftest import MakeRig
from support.evidence import note, step, watt_hours
from surplus_lab.control import Controller, Reading, Settings
from surplus_lab.house import MIN_CHARGE_A

pytestmark = pytest.mark.once


@pytest.mark.smoke
def test_a_meter_that_has_stopped_reporting_stops_the_charging(make_rig: MakeRig) -> None:
    """When the meter reading goes stale the session stops rather than carry on in the dark."""
    rig = make_rig("clear")
    with step("charging in good sun"):
        rig.hours(4)
        assert rig.house.offered_a >= MIN_CHARGE_A
    with step("the meter goes quiet"):
        rig.house.meter.silent = True
        rig.minutes(3)
        note("age of the last reading", f"{rig.house.meter.reading_age_s} s")
        note("offered", f"{rig.house.offered_a:.0f} A")
        assert rig.house.offered_a == 0


def test_nothing_is_bought_while_the_meter_is_quiet(make_rig: MakeRig) -> None:
    """Across a long silence the car buys nothing, because it is not charging at all."""
    rig = make_rig("clear")
    rig.hours(4)
    rig.house.meter.silent = True
    with step("the meter stays quiet for an hour while the household uses power"):
        before = rig.totals.bought_for_car_wh
        rig.hours(1)
        bought = rig.totals.bought_for_car_wh - before
        watt_hours("bought for the car during the silence", bought)
        assert bought <= 5


def test_charging_starts_again_when_the_meter_comes_back(make_rig: MakeRig) -> None:
    """Once the meter is reporting again the controller picks the session back up by itself."""
    rig = make_rig("clear")
    rig.hours(4)
    with step("the meter is quiet for five minutes"):
        rig.house.meter.silent = True
        rig.minutes(5)
        assert rig.house.offered_a == 0
    with step("the meter comes back"):
        rig.house.meter.silent = False
        rig.minutes(10)
        note("offered ten minutes later", f"{rig.house.offered_a:.0f} A")
        assert rig.house.offered_a >= MIN_CHARGE_A


def test_how_stale_is_too_stale_is_a_setting_and_is_obeyed() -> None:
    """A reading is used right up to the age the installation allows, and refused one second later."""
    controller = Controller(settings=Settings(stale_after_s=60), phases=1)
    fresh = Reading(clock=0, grid_w=-3000, grid_age_s=60, car_w=0, phases=1, plugged=True)
    stale = Reading(clock=10, grid_w=-3000, grid_age_s=61, car_w=0, phases=1, plugged=True)
    with step("a reading exactly at the limit is still a reading"):
        assert controller.decide(fresh).why != "the meter has gone quiet"
    with step("one second older and it is not"):
        command = controller.decide(stale)
        note("what the controller said", command.why)
        assert command.amps == 0


def test_an_unplugged_car_is_offered_nothing(make_rig: MakeRig) -> None:
    """With no car on the cable the controller offers nothing, whatever the sun is doing."""
    rig = make_rig("clear")
    rig.hours(4)
    with step("the driver unplugs and leaves"):
        rig.house.car.plugged = False
        rig.house.car.drawing_a = 0.0
        rig.minutes(2)
        note("offered", f"{rig.house.offered_a:.0f} A")
        assert rig.house.offered_a == 0


def test_the_sun_is_not_followed_into_the_night(make_rig: MakeRig) -> None:
    """When the sun sets the session ends, and the small hours are not spent buying electricity."""
    rig = make_rig("clear")
    with step("from midday until after dark"):
        rig.run(until_s=23 * 3600)
        evening = [tick for tick in rig.trace.ticks if tick.clock > 22 * 3600]
        note("offers made after ten at night", str({tick.offered_a for tick in evening}))
        assert all(tick.offered_a == 0 for tick in evening)
