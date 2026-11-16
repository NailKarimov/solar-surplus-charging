"""The driver with no protocol in it: the controller talks to the model in the same process.

This is the reference. The behaviour suites run here because nothing can go wrong on the way, so a
failing test means the control law is wrong rather than a frame being mangled. The other two drivers
are then held against this one.
"""

from __future__ import annotations

from ..control import Command, Reading
from ..house import House


class DirectDriver:
    name = "direct"

    def __init__(self, house: House) -> None:
        self.house = house

    def read(self, clock: int) -> Reading:
        meter = self.house.meter
        return Reading(
            clock=clock,
            grid_w=meter.reading_w,
            grid_age_s=meter.reading_age_s,
            car_w=self.house.car_w(),
            phases=self.house.phases,
            plugged=self.house.car.plugged,
        )

    def apply(self, command: Command) -> None:
        self.house.offer(command.amps, command.phases)

    def close(self) -> None:
        return None
