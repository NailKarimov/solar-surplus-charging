"""What every test did, saved for the report and the visual page.

A test is one plain sentence — its docstring. ``step()`` adds a line in plain words, ``note()`` adds a
number the test measured, and the drivers hand over whatever crossed the wire. At the end of the run
``conftest.py`` writes ``evidence/run-<driver>.json``, which the page "Last test run" is built from.

The numbers matter here more than in most projects. "The controller bought 275 Wh of electricity on
a day of broken cloud" is the finding; "the test passed" is only the summary of it.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import allure

MAX_FRAMES = 30  # frames kept per test; the total is still counted


@dataclass
class Step:
    text: str
    frames: list[list[str]] = field(default_factory=list)  # [direction, what was on the wire]
    notes: list[list[str]] = field(default_factory=list)  # [what was measured, the value]


@dataclass
class TestRecord:
    __test__ = False

    id: str
    name: str
    suite: str
    title: str
    params: str = ""
    outcome: str = "passed"
    reason: str = ""
    ms: float = 0.0
    frames: int = 0
    steps: list[Step] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "suite": self.suite,
            "title": self.title,
            "params": self.params,
            "outcome": self.outcome,
            "reason": self.reason,
            "ms": round(self.ms, 1),
            "frames": self.frames,
            "steps": [
                {"text": s.text, "frames": s.frames, "notes": s.notes}
                for s in self.steps
                if s.text or s.frames or s.notes
            ],
        }


class Recorder:
    def __init__(self) -> None:
        self.current: TestRecord | None = None
        self.records: list[TestRecord] = []

    def start(self, record: TestRecord) -> None:
        self.current = record
        self.records.append(record)

    def _tail(self) -> Step | None:
        record = self.current
        if record is None:
            return None
        if not record.steps:
            record.steps.append(Step(""))
        return record.steps[-1]

    def step(self, text: str) -> None:
        if self.current is not None:
            self.current.steps.append(Step(text))

    def note(self, what: str, value: str) -> None:
        tail = self._tail()
        if tail is not None:
            tail.notes.append([what, value])

    def frame(self, direction: str, text: str) -> None:
        record = self.current
        tail = self._tail()
        if record is None or tail is None:
            return
        record.frames += 1
        if sum(len(s.frames) for s in record.steps) < MAX_FRAMES:
            tail.frames.append([direction, text[:400]])


RECORDER = Recorder()


@contextmanager
def step(text: str) -> Iterator[None]:
    """One step of a test in plain words. Shown in the Allure report and on the replay page."""
    RECORDER.step(text)
    with allure.step(text):
        yield


def note(what: str, value: str) -> None:
    """One number the test measured, in the units a person would say it in."""
    RECORDER.note(what, value)
    allure.dynamic.parameter(what, value)


def watt_hours(what: str, value: float) -> None:
    note(what, f"{value:.0f} Wh")
