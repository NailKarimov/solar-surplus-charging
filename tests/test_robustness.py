"""Days nobody wrote: whatever the weather does, some things must always be true.

The named days in ``day.py`` are the ones a person thought of. These are the ones nobody thought of:
the sun and the household are generated at random, minute by minute, including weather no roof will
ever see. The controller does not have to be clever on these days. It has to keep the invariants —
never offer a current the pilot cannot carry, never exceed the wallbox, never go on charging without
a meter — because an invariant that only holds on the days somebody imagined is not an invariant.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from support.evidence import note, step
from surplus_lab.control import Command, Controller, Reading, Settings
from surplus_lab.house import MIN_CHARGE_A

pytestmark = pytest.mark.once

MAX_A = 16.0

readings = st.builds(
    Reading,
    clock=st.just(0),
    grid_w=st.floats(min_value=-30_000, max_value=30_000, allow_nan=False),
    grid_age_s=st.integers(min_value=0, max_value=600),
    car_w=st.floats(min_value=0, max_value=25_000, allow_nan=False),
    phases=st.sampled_from([1, 3]),
    plugged=st.booleans(),
)


def legal(command: Command) -> bool:
    return command.amps == 0 or (MIN_CHARGE_A <= command.amps <= MAX_A and command.amps == int(command.amps))


@settings(max_examples=400, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(readings)
def test_no_reading_at_all_produces_an_offer_the_pilot_cannot_carry(reading: Reading) -> None:
    """Whatever the meter says, the offer is zero or a whole number of amps between six and the rating."""
    controller = Controller(settings=Settings(max_a=MAX_A), phases=reading.phases)
    assert legal(controller.decide(reading))


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(readings, min_size=1, max_size=120))
def test_a_run_of_nonsense_never_produces_an_illegal_offer(readings_list: list[Reading]) -> None:
    """Two hours of randomly generated weather never gets the controller to make an illegal offer."""
    controller = Controller(settings=Settings(max_a=MAX_A))
    for index, reading in enumerate(readings_list):
        reading.clock = index * 60
        assert legal(controller.decide(reading))


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    grid_w=st.floats(min_value=-30_000, max_value=30_000, allow_nan=False),
    car_w=st.floats(min_value=0, max_value=25_000, allow_nan=False),
    age=st.integers(min_value=61, max_value=10_000),
)
def test_a_stale_reading_never_results_in_charging(grid_w: float, car_w: float, age: int) -> None:
    """However much sun a stale reading claims there is, a stale reading never starts or continues a charge."""
    controller = Controller(settings=Settings(stale_after_s=60))
    command = controller.decide(Reading(clock=0, grid_w=grid_w, grid_age_s=age, car_w=car_w, phases=3, plugged=True))
    assert command.amps == 0


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    grid_w=st.floats(min_value=0, max_value=30_000, allow_nan=False),
    car_w=st.floats(min_value=0, max_value=25_000, allow_nan=False),
)
def test_the_offer_never_rises_while_the_house_is_buying(grid_w: float, car_w: float) -> None:
    """While the meter says the house is buying, the next offer is never larger than the last one."""
    controller = Controller(phases=1)
    first = controller.decide(Reading(clock=0, grid_w=-5000, grid_age_s=0, car_w=0, phases=1, plugged=True))
    second = controller.decide(Reading(clock=10, grid_w=grid_w, grid_age_s=0, car_w=car_w, phases=1, plugged=True))
    if grid_w > car_w:  # the house is buying even without the car
        assert second.amps <= first.amps


def test_an_unplugged_car_is_never_offered_anything() -> None:
    """With nothing on the cable the answer is always nothing, whatever else is true."""
    controller = Controller()
    with step("a thousand random readings with nothing plugged in"):
        offers = set()
        for clock in range(0, 10_000, 10):
            command = controller.decide(
                Reading(clock=clock, grid_w=-9999, grid_age_s=0, car_w=0, phases=3, plugged=False)
            )
            offers.add(command.amps)
        note("the offers made", str(sorted(offers)))
        assert offers == {0.0}
