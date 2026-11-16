"""What a driver is.

The controller does not know what kind of wallbox is on the wall. It knows two verbs: tell me what
the car is doing, and offer the car this many amps on this many phases. Everything protocol-shaped
lives behind that.

This is the seam the project is built around. The same control law is driven three ways — straight
into the model, over Modbus TCP as a home wallbox is driven, and over OCPP as a public station is —
and a test compares the three command for command. A control law that behaves differently depending
on which cable it is shouting down is not a control law; it is a coincidence.
"""

from __future__ import annotations

from typing import Protocol

from ..control import Command, Reading


class Driver(Protocol):
    """A wallbox, however it happens to be spoken to."""

    name: str

    def read(self, clock: int) -> Reading:
        """What the meter and the car say right now."""
        ...

    def apply(self, command: Command) -> None:
        """Offer the car this many amps on this many phases. Zero amps means pause."""
        ...

    def close(self) -> None:
        """Let go of whatever had to be opened."""
        ...
