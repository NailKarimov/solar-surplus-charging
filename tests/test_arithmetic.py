"""The one line of arithmetic the whole controller rests on, and the way it is rounded.

If this is wrong, every other test is measuring the wrong thing, so it is checked on its own, with
numbers a person can do in their head.
"""

from __future__ import annotations

import pytest

from support.evidence import note, step
from surplus_lab.control import Controller, Reading, Settings
from surplus_lab.house import NOMINAL_V

pytestmark = pytest.mark.once


def reading(grid_w: float, car_w: float, phases: int = 3, age: int = 0) -> Reading:
    return Reading(clock=0, grid_w=grid_w, grid_age_s=age, car_w=car_w, phases=phases, plugged=True)


@pytest.mark.smoke
def test_the_car_may_have_what_it_takes_now_minus_what_the_meter_reads() -> None:
    """The car may have what it is taking now, less whatever of that is coming from the grid."""
    controller = Controller()
    with step("the car is taking 3000 W and the meter says 200 W is being bought"):
        assert controller.available_w(reading(grid_w=200, car_w=3000)) == pytest.approx(2800)
        note("the car may have", "2800 W")
    with step("the car is taking 3000 W and the meter says 1500 W is being sold"):
        assert controller.available_w(reading(grid_w=-1500, car_w=3000)) == pytest.approx(4500)
        note("the car may have", "4500 W")
    with step("nothing is plugged in and 2000 W is being sold"):
        assert controller.available_w(reading(grid_w=-2000, car_w=0)) == pytest.approx(2000)


def test_a_margin_is_electricity_bought_on_purpose() -> None:
    """A positive margin aims the meter at buying that much, and the car is offered that much more."""
    controller = Controller(settings=Settings(margin_w=250))
    with step("the meter is already balanced at zero"):
        assert controller.available_w(reading(grid_w=0, car_w=4000)) == pytest.approx(4250)
        note("bought on purpose", "250 W")


def test_watts_become_whole_amps_and_always_round_down() -> None:
    """Watts become whole amps per phase, rounded down, because rounding up buys electricity."""
    controller = Controller()
    one_phase = reading(grid_w=-3449, car_w=0, phases=1)  # 3449 W is 14.99 A on one phase
    with step("3449 W on one phase is 14.99 A"):
        assert controller.available_a(one_phase, 1) == 14
        note("offered", "14 A")
    with step("the same surplus split over three phases is 4.99 A, which is below the floor"):
        assert controller.available_a(one_phase, 3) == 4


def test_the_offer_never_goes_above_what_the_wallbox_can_give() -> None:
    """However much sun there is, the offer stops at what the wallbox is rated for."""
    controller = Controller(settings=Settings(max_a=16))
    with step("20 kW of surplus on three phases would be 28 A per phase"):
        assert controller.available_a(reading(grid_w=-20000, car_w=0), 3) == 16
        note("offered", "16 A")


def test_a_negative_surplus_is_not_a_negative_offer() -> None:
    """When the house is buying, the car may have nothing, and nothing is zero rather than less."""
    controller = Controller()
    assert controller.available_a(reading(grid_w=2500, car_w=0), 3) == 0


@pytest.mark.parametrize("phases", [1, 3])
def test_one_amp_is_230_watts_on_each_phase(phases: int) -> None:
    """One amp more on the offer means 230 W more per phase, which is where the coarseness comes from."""
    controller = Controller()
    low = controller.available_a(reading(grid_w=-(6 * phases * NOMINAL_V), car_w=0, phases=phases), phases)
    high = controller.available_a(reading(grid_w=-(7 * phases * NOMINAL_V), car_w=0, phases=phases), phases)
    assert (low, high) == (6, 7)
    note("one amp on this wiring", f"{phases * NOMINAL_V:.0f} W")
