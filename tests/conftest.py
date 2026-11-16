"""Fixtures and hooks shared by all tests.

One environment variable decides what a run exercises:

- ``DRIVER``  ``direct`` (default), ``modbus`` or ``ocpp`` — how the controller reaches the wallbox

The behaviour of the control law is the same whichever wire the number travels down, so the
behaviour suites are marked ``once`` and run in the ``direct`` run only. The ``driver`` suites run
everywhere, because that is the part that differs. Every test has a docstring of one plain sentence:
it becomes the title in the Allure report and on the visual page. The run is saved to
``evidence/run-<driver>.json``.
"""

from __future__ import annotations

import os
import platform
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import allure
import pytest

from support.evidence import RECORDER, TestRecord
from support.rig import Rig, build
from surplus_lab import __version__
from surplus_lab.control import Settings

DRIVER = os.getenv("DRIVER", "direct")
ROOT = Path(__file__).resolve().parent.parent
DRIVERS = ("direct", "modbus", "ocpp")

if DRIVER not in DRIVERS:
    raise pytest.UsageError(f"DRIVER={DRIVER!r}: use one of {', '.join(DRIVERS)}")


def plain_title(item: pytest.Item) -> str:
    doc = getattr(getattr(item, "function", None), "__doc__", None) or ""
    return " ".join(doc.strip().split("\n\n")[0].split())


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    untitled = [item.nodeid for item in items if not plain_title(item)]
    if untitled:
        raise pytest.UsageError("tests without a one-sentence docstring:\n  " + "\n  ".join(untitled))
    for item in items:
        if "once" in item.keywords and DRIVER != "direct":
            item.add_marker(
                pytest.mark.skip(reason="the control law does not depend on the driver: this runs in the direct run")
            )


# ---- evidence ---------------------------------------------------------------------------------


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item: pytest.Item, nextitem: pytest.Item | None) -> Iterator[None]:
    name = getattr(item, "originalname", None) or item.name
    params = item.name[len(name) :].strip("[]") if item.name != name else ""
    suite = Path(str(item.fspath)).stem
    RECORDER.start(TestRecord(id=item.nodeid, name=name, suite=suite, title=plain_title(item), params=params))
    yield
    RECORDER.current = None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Iterator[None]:
    outcome = yield
    report = outcome.get_result()  # type: ignore[attr-defined]
    record = RECORDER.current
    if record is None:
        return
    if report.when == "call":
        record.ms = report.duration * 1000
    if report.skipped and record.outcome == "passed":
        record.outcome = "skipped"
        longrepr = report.longrepr
        record.reason = str(longrepr[2] if isinstance(longrepr, tuple) else longrepr).removeprefix("Skipped: ")
    elif report.failed:
        record.outcome = "failed"
        record.reason = str(call.excinfo.value).splitlines()[0][:300] if call.excinfo else report.when


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    records = RECORDER.records
    if not records or os.getenv("EVIDENCE", "1") == "0":
        return
    counts = {key: sum(r.outcome == key for r in records) for key in ("passed", "failed", "skipped")}
    meta = {
        "driver": DRIVER,
        "finished": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "release": __version__,
        "python": platform.python_version(),
        "commit": os.getenv("GITHUB_SHA", "")[:7],
        "run": os.getenv("GITHUB_RUN_NUMBER", ""),
        "tests": len(records),
        **counts,
        "frames": sum(r.frames for r in records),
    }
    out = ROOT / "evidence"
    out.mkdir(exist_ok=True)
    payload = {"meta": meta, "tests": [r.as_dict() for r in records]}
    import json

    (out / f"run-{DRIVER}.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


@pytest.fixture(autouse=True)
def _report_labels(request: pytest.FixtureRequest) -> None:
    allure.dynamic.title(plain_title(request.node))
    allure.dynamic.parameter("driver", DRIVER)
    allure.dynamic.parent_suite(f"through the {DRIVER} wallbox")


# ---- the house ---------------------------------------------------------------------------------


@pytest.fixture
def driver_name() -> str:
    return DRIVER


@pytest.fixture
def rig() -> Iterator[Rig]:
    """A clear day, a controller and a wallbox, fresh for every test."""
    built = build(DRIVER)
    yield built
    built.close()


class MakeRig(Protocol):
    """Build a rig on a named day, with other settings, or through another kind of wallbox."""

    def __call__(self, day: str = ..., settings: Settings | None = ..., driver: str | None = ...) -> Rig: ...


@pytest.fixture
def make_rig() -> Iterator[MakeRig]:
    """Build a rig on a named day, or with other settings, and close it afterwards."""
    built: list[Rig] = []

    def factory(day: str = "clear", settings: Settings | None = None, driver: str | None = None) -> Rig:
        rig = build(driver or DRIVER, day, settings)
        built.append(rig)
        return rig

    yield factory
    for rig in built:
        rig.close()
