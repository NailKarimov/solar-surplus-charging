"""The 6 A floor, and the hysteresis that keeps it from being a cliff.

IEC 61851-1 says the pilot cannot ask a car for less than six amps. That turns a smooth control
problem into a step: either the car charges at 1.4 kW, or it does not charge at all. Everything in
this file is about not falling off that step and climbing back up it every few minutes.
"""

from __future__ import annotations

import pytest

from conftest import MakeRig
from support.evidence import note, step
from support.rig import Rig
from surplus_lab.control import Settings
from surplus_lab.house import MIN_CHARGE_A, Cloud

pytestmark = pytest.mark.once


def offers(rig: Rig) -> list[float]:
    return [tick.offered_a for tick in rig.trace.ticks]


@pytest.mark.smoke
def test_the_offer_is_never_between_nothing_and_six_amps(make_rig: MakeRig) -> None:
    """Across a whole day the offer is either zero or at least six amps, and never anything between."""
    rig = make_rig("whole-day")
    with step("a whole day with cloud, a kettle, an oven and a heat pump"):
        rig.run(until_s=21 * 3600)
        between = [amps for amps in offers(rig) if 0 < amps < MIN_CHARGE_A]
        note("offers made across the day", str(len(offers(rig))))
        note("offers between nothing and the floor", str(len(between)))
        assert between == []


def test_the_offer_is_always_a_whole_number_of_amps(make_rig: MakeRig) -> None:
    """Every offer is a whole number of amps, because the pilot has no way to say three and a half."""
    rig = make_rig("broken-cloud")
    rig.run(until_s=21 * 3600)
    assert all(amps == int(amps) for amps in offers(rig))


def test_the_offer_never_goes_above_what_the_wallbox_is_rated_for(make_rig: MakeRig) -> None:
    """However much sun there is, the offer never exceeds the wallbox's rating."""
    rig = make_rig("clear", Settings(max_a=10))
    rig.run(until_s=21 * 3600)
    note("the highest offer made", f"{max(offers(rig)):.0f} A")
    assert max(offers(rig)) <= 10


def test_the_session_is_not_started_again_the_moment_the_sun_peeps_out(make_rig: MakeRig) -> None:
    """After a stop, a brief return of the sun is not enough: the sun has to stay before charging resumes."""
    rig = make_rig("clear", Settings(resume_delay_s=300, allow_phase_switching=False))
    rig.house.phases = 1
    rig.controller.phases = 1
    with step("charging, then a cloud long enough to stop the session"):
        rig.hours(4)
        sky = rig.house.inverter.sky
        sky.clouds.append(Cloud(start_s=rig.house.clock, seconds=20 * 60, factor=0.05, edge_s=5))
        rig.minutes(10)
        assert rig.house.offered_a == 0
    with step("one bright minute in the middle of the cloud"):
        clock = rig.house.clock
        sky.clouds[-1] = Cloud(start_s=sky.clouds[-1].start_s, seconds=clock - sky.clouds[-1].start_s, factor=0.05)
        sky.clouds.append(Cloud(start_s=clock + 60, seconds=9 * 60, factor=0.05, edge_s=5))
        rig.minutes(1)
        note("offered after one bright minute", f"{rig.house.offered_a:.0f} A")
        assert rig.house.offered_a == 0, "the session restarted for a single minute of sun"


def test_the_session_does_start_again_when_the_sun_really_is_back(make_rig: MakeRig) -> None:
    """Once the sun has held above the floor for the resume delay, charging starts again by itself."""
    rig = make_rig("clear", Settings(resume_delay_s=120, allow_phase_switching=False))
    rig.house.phases = 1
    rig.controller.phases = 1
    with step("charging, then a cloud that stops the session"):
        rig.hours(4)
        rig.house.inverter.sky.clouds.append(Cloud(start_s=rig.house.clock, seconds=12 * 60, factor=0.05, edge_s=5))
        rig.minutes(12)
        assert rig.house.offered_a == 0
    with step("the cloud passes and the sun stays"):
        rig.minutes(6)
        note("offered once the sun was back", f"{rig.house.offered_a:.0f} A")
        assert rig.house.offered_a >= MIN_CHARGE_A


def test_a_car_charging_at_the_floor_is_still_a_car_charging(make_rig: MakeRig) -> None:
    """At the floor the car really is taking current: the floor is an offer, not a polite fiction."""
    rig = make_rig("dull")
    rig.house.phases = 1
    rig.controller.phases = 1
    rig.house.inverter.sky.haze = 0.30  # just enough for six amps on one phase
    with step("a hazy day with barely enough sun for the smallest charge"):
        rig.hours(4)
        if rig.house.offered_a >= MIN_CHARGE_A:
            note("the car is drawing", f"{rig.house.car.drawing_a:.1f} A")
            assert rig.house.car.drawing_a >= MIN_CHARGE_A - 0.01
        else:
            pytest.skip("not even the floor was reachable on this day")
