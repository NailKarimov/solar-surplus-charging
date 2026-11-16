"""Clouds: the thing that makes this problem hard.

A cloud takes the surplus away in about twenty seconds and gives it back a few minutes later. Stop
the session every time and the car is switched twenty times a day. Hold on through every one and the
house buys electricity for as long as the shadow lasts. The controller does neither: it holds the
floor while the shadow is cheap and lets go when it stops being cheap.
"""

from __future__ import annotations

import pytest

from conftest import MakeRig
from support.evidence import note, step, watt_hours
from support.rig import Rig
from surplus_lab.control import Settings
from surplus_lab.house import MIN_CHARGE_A, Cloud, Load

pytestmark = pytest.mark.once

HOUR = 3600


def charging_at(rig: Rig) -> float:
    return rig.house.offered_a


def one_phase(make_rig: MakeRig, day: str = "clear", **settings: object) -> Rig:
    """A house wired on one phase, where six amps is 1.4 kW rather than 4.1 kW.

    Most of these tests belong here. On one phase the floor is cheap enough to hold through a
    shadow, which is the interesting case; three phases get a test of their own, below, because
    there the same six amps costs three times as much and the controller is right to be impatient.
    """
    rig = make_rig(day, Settings(allow_phase_switching=False, **settings))  # type: ignore[arg-type]
    rig.house.phases = 1
    rig.controller.phases = 1
    return rig


@pytest.mark.smoke
def test_a_short_shadow_does_not_end_the_session(make_rig: MakeRig) -> None:
    """A cloud of a couple of minutes drops the offer to the floor but leaves the session running."""
    rig = one_phase(make_rig)
    with step("charging in full sun"):
        rig.hours(3)
        assert charging_at(rig) >= MIN_CHARGE_A
        note("offered before the cloud", f"{charging_at(rig):.0f} A")
    with step("a cloud takes most of the sun for two minutes"):
        rig.house.inverter.sky.clouds.append(Cloud(start_s=rig.house.clock, seconds=120, factor=0.1))
        rig.minutes(2)
        note("offered under the cloud", f"{charging_at(rig):.0f} A")
        assert charging_at(rig) >= MIN_CHARGE_A, "the session was stopped for a two-minute shadow"
    with step("the sun comes back"):
        rig.minutes(10)
        assert charging_at(rig) > MIN_CHARGE_A


def test_a_long_shadow_ends_the_session_rather_than_buying_through_it(make_rig: MakeRig) -> None:
    """A cloud that stays stops the session instead of holding the floor on bought electricity."""
    rig = one_phase(make_rig)
    rig.hours(3)
    before = rig.totals.bought_for_car_wh
    with step("a heavy cloud settles in for half an hour"):
        rig.house.inverter.sky.clouds.append(Cloud(start_s=rig.house.clock, seconds=30 * 60, factor=0.05))
        rig.minutes(30)
        bought = rig.totals.bought_for_car_wh - before
        watt_hours("bought while the shadow lasted", bought)
        assert charging_at(rig) == 0, "the controller was still charging half an hour into a heavy cloud"
        assert bought <= 80, "holding the floor through the shadow bought more than the budget allows"


def test_riding_out_a_shadow_stops_when_it_has_cost_enough(make_rig: MakeRig) -> None:
    """Holding the floor through a shadow ends on the money it has spent, not only on the clock."""
    cheap = one_phase(make_rig, ride_out_budget_wh=2.0, pause_delay_s=3600)
    dear = one_phase(make_rig, ride_out_budget_wh=1000.0, pause_delay_s=3600)
    for name, rig in (("a tight budget", cheap), ("a generous one", dear)):
        with step(f"{name}: three hours of sun, then a heavy cloud"):
            rig.hours(3)
            rig.house.inverter.sky.clouds.append(Cloud(start_s=rig.house.clock, seconds=20 * 60, factor=0.05))
            rig.minutes(10)
            note(f"offered ten minutes into the shadow, {name}", f"{charging_at(rig):.0f} A")
    assert charging_at(cheap) == 0, "a tight budget did not stop the ride-out"
    assert charging_at(dear) >= MIN_CHARGE_A, "a generous budget stopped it anyway"


def test_the_offer_comes_down_in_the_same_breath_as_the_sun(make_rig: MakeRig) -> None:
    """When the sun goes, the offer goes with it on the very next turn of the loop, not later."""
    rig = one_phase(make_rig)
    rig.hours(4)
    before = charging_at(rig)
    with step("a cloud cuts the sun by three quarters"):
        rig.house.inverter.sky.clouds.append(Cloud(start_s=rig.house.clock, seconds=15 * 60, factor=0.25, edge_s=1))
        rig.minutes(1)  # time for the meter to see it
        rig.tick()
        note("offered before", f"{before:.0f} A")
        note("offered after one turn of the loop", f"{charging_at(rig):.0f} A")
        assert charging_at(rig) < before


def test_the_offer_goes_back_up_slowly_enough_to_ignore_a_gap_in_the_cloud(make_rig: MakeRig) -> None:
    """A minute of sun inside a long cloud does not get the offer raised and then dropped again."""
    rig = one_phase(make_rig, rise_delay_s=300)
    rig.hours(4)
    with step("a long cloud with one bright minute in the middle of it"):
        clock = rig.house.clock
        sky = rig.house.inverter.sky
        sky.clouds.append(Cloud(start_s=clock, seconds=10 * 60, factor=0.3, edge_s=5))
        sky.clouds.append(Cloud(start_s=clock + 11 * 60, seconds=10 * 60, factor=0.3, edge_s=5))
        changes_before = rig.trace.changes
        rig.minutes(22)
        note("changes of the offer across the whole episode", str(rig.trace.changes - changes_before))
        assert rig.trace.changes - changes_before <= 6


def test_cloud_after_cloud_does_not_become_switch_after_switch(make_rig: MakeRig) -> None:
    """A whole day of broken cloud leaves the session stopped and started a handful of times, not dozens."""
    rig = make_rig("broken-cloud")
    with step("a day of cloud every quarter of an hour"):
        rig.run(until_s=21 * HOUR)
        note("times the session was stopped", str(rig.trace.pauses))
        watt_hours("bought for the car across the day", rig.totals.bought_for_car_wh)
        assert rig.trace.pauses <= 18


def test_a_kettle_is_a_cloud_as_far_as_the_meter_is_concerned(make_rig: MakeRig) -> None:
    """Two kilowatts switched on in the house moves the offer exactly as a cloud of the same size would."""
    sunny = one_phase(make_rig)
    shaded = one_phase(make_rig)
    sunny.hours(4)
    shaded.hours(4)
    with step("one house switches on a 2.2 kW kettle; over the other, a cloud takes 2.2 kW of sun"):
        sunny.house.household.loads.append(Load("kettle", 2200.0, sunny.house.clock, 15 * 60))
        sky = shaded.house.inverter.sky
        # The factor is worked out against what the inverter is actually putting out, not against
        # the clear sky above it: at noon the array makes more than the inverter can pass on.
        clear = max(1.0, sky.clear_sky_w(shaded.house.clock))
        factor = max(0.0, (shaded.house.pv_w() - 2200.0) / clear)
        sky.clouds.append(Cloud(start_s=shaded.house.clock, seconds=15 * 60, factor=factor, edge_s=1))
        sunny.minutes(5)
        shaded.minutes(5)
        note("offered after the kettle", f"{sunny.house.offered_a:.0f} A")
        note("offered after the cloud", f"{shaded.house.offered_a:.0f} A")
    assert abs(sunny.house.offered_a - shaded.house.offered_a) <= 1


def test_riding_out_costs_three_times_as_much_on_three_phases_and_ends_three_times_sooner(make_rig: MakeRig) -> None:
    """The same six amps is 4.1 kW on three phases, so the shadow is ridden out for a third as long."""
    single = one_phase(make_rig)
    triple = make_rig("clear", Settings(allow_phase_switching=False))
    triple.house.phases = 3
    triple.controller.phases = 3
    held = {}
    for name, rig in (("one phase", single), ("three phases", triple)):
        with step(f"{name}: charging, then a heavy cloud that stays"):
            rig.hours(4)
            rig.house.inverter.sky.clouds.append(Cloud(start_s=rig.house.clock, seconds=30 * 60, factor=0.05))
            started = rig.house.clock
            while rig.house.clock < started + 20 * 60 and charging_at(rig) > 0:
                rig.tick()
            held[name] = rig.house.clock - started
            note(f"held the floor for, on {name}", f"{held[name]} s")
            watt_hours(f"bought while holding on, on {name}", rig.totals.bought_for_car_wh)
    assert held["three phases"] < held["one phase"]


def wobble(rig: Rig, *, watts: float, seconds: int, times: int) -> int:
    """Make the sun dip by this many watts every other stretch, and count the raises it caused."""
    sky = rig.house.inverter.sky
    raises_before = raises(rig)
    for n in range(times):
        if n % 2 == 0:
            clear = max(1.0, sky.clear_sky_w(rig.house.clock))
            factor = max(0.0, (rig.house.pv_w() - watts) / clear)
            sky.clouds.append(Cloud(start_s=rig.house.clock, seconds=seconds, factor=factor, edge_s=1))
        rig.run(until_s=rig.house.clock + seconds, tick_s=10)
    return raises(rig) - raises_before


def raises(rig: Rig) -> int:
    ticks = rig.trace.ticks
    return sum(1 for index, tick in enumerate(ticks[1:], 1) if tick.offered_a > ticks[index - 1].offered_a)


def test_a_jittery_surplus_does_not_become_a_jittery_offer(make_rig: MakeRig) -> None:
    """A surplus that wobbles by 700 W every twenty seconds barely moves the offer at all."""
    rig = one_phase(make_rig, max_a=32)
    rig.hours(4)
    changes_before = rig.trace.changes
    with step("half an hour of sun flickering up and down by 700 W every twenty seconds"):
        wobble(rig, watts=700.0, seconds=20, times=90)
        changed = rig.trace.changes - changes_before
        note("changes of the offer in half an hour", str(changed))
        assert changed <= 6, "the offer followed every flicker of the sun"


def test_a_surplus_that_never_settles_never_gets_the_offer_raised(make_rig: MakeRig) -> None:
    """A surplus wobbling by one amp, too fast to settle, produces no raise at all, not a slow creep."""
    rig = one_phase(make_rig, max_a=32)
    rig.hours(4)
    with step("ten minutes of the sun wobbling by one amp every thirty seconds"):
        raised = wobble(rig, watts=260.0, seconds=30, times=20)
        note("times the offer was raised", str(raised))
        assert raised == 0, "a wobble that never settles still added up to a raise"


def test_raises_are_kept_apart_even_where_the_installation_asks_for_a_fast_one(make_rig: MakeRig) -> None:
    """With the rise delay turned off, raises are still kept two quiet minutes apart from each other."""
    rig = one_phase(make_rig, max_a=32, rise_delay_s=0, min_dwell_s=120)
    rig.hours(4)
    with step("a light cloud that takes two and a half minutes to clear, while charging continues"):
        start = rig.house.clock
        rig.house.inverter.sky.clouds.append(Cloud(start_s=start, seconds=6 * 60, factor=0.55, edge_s=150))
        rig.run(until_s=start + 12 * 60, tick_s=10)
        moments = [
            tick.clock
            for index, tick in enumerate(rig.trace.ticks[1:], 1)
            if tick.offered_a > rig.trace.ticks[index - 1].offered_a and tick.clock >= start
        ]
        gaps = [b - a for a, b in zip(moments, moments[1:], strict=False)]
        note("times the offer was raised as the cloud cleared", str(len(moments)))
        note("the shortest gap between two raises", f"{min(gaps) if gaps else 0} s")
        assert moments, "the cloud cleared and the offer was never raised"
        assert not gaps or min(gaps) >= 120


def test_a_sun_that_climbs_steadily_raises_the_offer_a_step_at_a_time(make_rig: MakeRig) -> None:
    """As the morning sun climbs, the offer is raised in steps minutes apart, not continuously."""
    rig = one_phase(make_rig, max_a=32)
    with step("four hours of a sun climbing from nothing to its midday strength"):
        rig.hours(4)
        moments = [
            tick.clock
            for index, tick in enumerate(rig.trace.ticks[1:], 1)
            if tick.offered_a > rig.trace.ticks[index - 1].offered_a
        ]
        gaps = [b - a for a, b in zip(moments, moments[1:], strict=False)]
        note("times the offer was raised across the morning", str(len(moments)))
        note("the shortest gap between two raises", f"{min(gaps) if gaps else 0} s")
        assert len(moments) <= 20
        assert not gaps or min(gaps) >= 120
