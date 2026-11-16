"""One phase or three, and why the obvious threshold is the wrong one.

Three phases can carry a lot, but they cannot carry a little: the smallest three-phase charge is
3 x 6 A, which is 4140 W. One phase tops out at 16 A, which is 3680 W. Between those two numbers,
one phase is the only wiring that works at all. A controller that moves to three phases as soon as
one phase is full therefore moves to three phases at 3680 W and immediately finds it cannot charge.

Switching costs a stop and a start, so it is held back by a long wait and a cooldown. The price of
three phases is coarseness: one amp is 690 W there and only 230 W on one phase, so three-phase
charging always leaves a little more sun on the table.
"""

from __future__ import annotations

import pytest

from conftest import MakeRig
from support.evidence import note, step
from surplus_lab.control import Controller, Reading, Settings
from surplus_lab.house import MIN_CHARGE_A, NOMINAL_V

pytestmark = pytest.mark.once

THREE_PHASE_FLOOR = 3 * MIN_CHARGE_A * NOMINAL_V  # 4140 W
ONE_PHASE_CEILING = 16 * NOMINAL_V  # 3680 W


def hold(controller: Controller, *, grid_w: float, car_w: float, phases: int, seconds: int, step_s: int = 10) -> int:
    """Keep the world still for a while and return the clock when it stopped."""
    clock = 0
    for clock in range(0, seconds, step_s):
        controller.decide(
            Reading(clock=clock, grid_w=grid_w, grid_age_s=0, car_w=car_w, phases=controller.phases, plugged=True)
        )
    return clock


@pytest.mark.smoke
def test_three_phases_are_not_asked_for_until_three_phases_could_actually_charge() -> None:
    """The move up happens above the smallest three-phase charge, not above what one phase can carry."""
    controller = Controller(settings=Settings(phase_switch_delay_s=60), phases=1)
    with step(f"a surplus of {ONE_PHASE_CEILING + 100:.0f} W: more than one phase can carry, less than three can use"):
        hold(controller, grid_w=-(ONE_PHASE_CEILING + 100), car_w=0, phases=1, seconds=600)
        note("phases after ten minutes", str(controller.phases))
        assert controller.phases == 1, "moved to three phases where three phases cannot charge at all"


def test_three_phases_are_asked_for_once_there_is_really_enough_sun() -> None:
    """With comfortably more than the smallest three-phase charge, the controller moves up to three."""
    controller = Controller(settings=Settings(phase_switch_delay_s=60), phases=1)
    with step(f"a surplus of {THREE_PHASE_FLOOR + 1500:.0f} W, held for ten minutes"):
        hold(controller, grid_w=-(THREE_PHASE_FLOOR + 1500), car_w=0, phases=1, seconds=600)
        note("phases after ten minutes", str(controller.phases))
        assert controller.phases == 3


def test_one_phase_is_asked_for_when_three_can_no_longer_be_filled() -> None:
    """When the surplus falls below the smallest three-phase charge, the controller drops to one phase."""
    controller = Controller(settings=Settings(phase_switch_delay_s=60, phase_switch_cooldown_s=0), phases=3)
    with step("the surplus falls to 2500 W and stays there"):
        hold(controller, grid_w=-2500, car_w=0, phases=3, seconds=600)
        note("phases after ten minutes", str(controller.phases))
        assert controller.phases == 1


def test_a_switch_is_not_undone_a_minute_later() -> None:
    """After a switch the controller leaves the wiring alone for the cooldown, whatever the sun does."""
    controller = Controller(settings=Settings(phase_switch_delay_s=60, phase_switch_cooldown_s=1800), phases=3)
    with step("the surplus falls, and the controller drops to one phase"):
        clock = hold(controller, grid_w=-2500, car_w=0, phases=3, seconds=600)
        assert controller.phases == 1
    with step("the sun comes straight back to a three-phase surplus"):
        for tick in range(clock, clock + 900, 10):
            controller.decide(Reading(clock=tick, grid_w=-6000, grid_age_s=0, car_w=0, phases=1, plugged=True))
        note("phases fifteen minutes later", str(controller.phases))
        assert controller.phases == 1, "the wiring was switched twice inside the cooldown"


def test_a_brief_dip_does_not_rewire_the_house() -> None:
    """A surplus that dips below the three-phase floor for a minute does not cause a switch."""
    controller = Controller(settings=Settings(phase_switch_delay_s=600), phases=3)
    clock = 0
    with step("ten minutes of good sun, one minute of dip, ten minutes of good sun"):
        for block, grid in ((600, -6000), (60, -2500), (600, -6000)):
            for _ in range(0, block, 10):
                controller.decide(Reading(clock=clock, grid_w=grid, grid_age_s=0, car_w=0, phases=3, plugged=True))
                clock += 10
        note("phases at the end", str(controller.phases))
        assert controller.phases == 3


def test_the_offer_after_a_switch_is_worked_out_for_the_new_wiring() -> None:
    """The first offer after a switch is computed for the phases the car is about to be on."""
    controller = Controller(settings=Settings(phase_switch_delay_s=60, phase_switch_cooldown_s=0), phases=3)
    with step("a surplus of 3000 W, which is 13 A on one phase and 4 A on three"):
        at_the_switch = None
        was = controller.phases
        for clock in range(0, 600, 10):
            command = controller.decide(
                Reading(clock=clock, grid_w=-3000, grid_age_s=0, car_w=0, phases=controller.phases, plugged=True)
            )
            if command.phases != was and at_the_switch is None:
                at_the_switch = command
            was = command.phases
        assert at_the_switch is not None, "the wiring was never switched"
        note("the offer made at the switch", f"{at_the_switch.amps:.0f} A on {at_the_switch.phases} phase(s)")
        assert at_the_switch.phases == 1
        # 3000 W on one phase is 13 A. Worked out for three phases it would have been 4, which is
        # below the floor and would come out as the floor instead.
        assert at_the_switch.amps == 13


def test_switching_is_rare_across_a_whole_day(make_rig: MakeRig) -> None:
    """Over a whole day the house is rewired a handful of times at most, not whenever a cloud passes."""
    rig = make_rig("broken-cloud")
    with step("a day of cloud every quarter of an hour"):
        rig.run(until_s=21 * 3600)
        note("times the wiring was switched", str(rig.trace.phase_switches))
        assert rig.trace.phase_switches <= 6


def test_switching_can_be_turned_off_for_a_house_that_is_wired_one_way(make_rig: MakeRig) -> None:
    """A house with no switching hardware keeps the wiring it started with all day."""
    rig = make_rig("whole-day", Settings(allow_phase_switching=False))
    rig.run(until_s=21 * 3600)
    assert rig.trace.phase_switches == 0
    assert {tick.phases for tick in rig.trace.ticks} == {3}
