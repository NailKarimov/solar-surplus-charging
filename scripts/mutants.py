"""Mutation check: plant one bug at a time and make sure the test suite notices.

    python scripts/mutants.py              # every mutant
    python scripts/mutants.py M07 M21      # only these

Each mutant is one small change to the source, applied to a private copy of the project. The suite
then runs against the copy. A mutant is "caught" if at least one test fails. A control run with no
change must pass, otherwise the result means nothing.

The bugs are the ones a person would actually write: the sign of the meter the wrong way round,
rounding up instead of down, raising the offer as fast as lowering it, forgetting that a register is
in tenths of an amp. Every one of them leaves a controller that works on a clear day.

Writes ``evidence/mutants.json`` (shown on the "Bug hunt" page) and ``mutants-result.md``.
Exit code 1 if a mutant survives or a control run fails.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = "src/surplus_lab/"


@dataclass(frozen=True)
class Mutant:
    id: str
    area: str  # sums | timing | floor | phases | safety | wire
    file: str
    old: str
    new: str
    title: str  # what is broken, in plain words
    driver: str = "direct"


# fmt: off
MUTANTS = [
    # ---- the arithmetic: how much the car may have ---------------------------------------------
    Mutant("M01", "sums", "control.py", "return reading.car_w - reading.grid_w + self.settings.margin_w", "return reading.car_w + reading.grid_w + self.settings.margin_w", "The meter's sign is read the wrong way round, so buying looks like selling"),
    Mutant("M02", "sums", "control.py", "return reading.car_w - reading.grid_w + self.settings.margin_w", "return -reading.grid_w + self.settings.margin_w", "What the car is already taking is forgotten, so the offer collapses to the spare surplus"),
    Mutant("M03", "sums", "control.py", "return float(int(clamp(amps, 0.0, self.settings.max_a)))", "return float(round(clamp(amps, 0.0, self.settings.max_a)))", "Amps are rounded to the nearest whole one instead of down, so half the time the car buys"),
    Mutant("M04", "sums", "control.py", "amps = self.available_w(reading) / (phases * NOMINAL_V)", "amps = self.available_w(reading) / NOMINAL_V", "The three phases are forgotten, so the car is offered three times what there is"),
    Mutant("M05", "sums", "control.py", "return float(int(clamp(amps, 0.0, self.settings.max_a)))", "return float(int(max(amps, 0.0)))", "The wallbox's rating is ignored and the car is offered more than the cable can carry"),
    Mutant("M06", "sums", "control.py", "return reading.car_w - reading.grid_w + self.settings.margin_w", "return reading.car_w - reading.grid_w", "The margin the installation asked for is ignored"),

    # ---- timing: how fast to follow the sun -----------------------------------------------------
    Mutant("M07", "timing", "control.py", "            if now - self._wanted_since(wanted, now) >= s.fall_delay_s:", "            if now - self._wanted_since(wanted, now) >= s.rise_delay_s:", "The offer comes down as slowly as it goes up, so every cloud is bought through"),
    Mutant("M08", "timing", "control.py", "            if now - self._wanted_since(wanted, now) >= s.rise_delay_s:", "            if now - self._wanted_since(wanted, now) >= 0:", "The offer goes up the instant the sun does, so the car is changed at every flicker"),
    Mutant("M09", "timing", "control.py", "            if self.last_raise_s is not None and now - self.last_raise_s < s.min_dwell_s:\n                return self._hold(now)", "            if False:\n                return self._hold(now)", "The quiet time between raises is dropped, so the offer can climb every few seconds"),
    Mutant("M10", "timing", "control.py", "        if self._want is None or self._want[0] != value:\n            self._want = (value, now)\n        return self._want[1]", "        self._want = (value, now)\n        return self._want[1] - 10_000", "A value only has to be wanted once, not held, before it is acted on"),
    Mutant("M11", "timing", "control.py", "        if self._want is None or self._want[0] != value:", "        if self._want is None:", "The wait is not restarted when the wanted value changes, so an old wait counts for a new value"),

    # ---- the floor: six amps or nothing ---------------------------------------------------------
    Mutant("M12", "floor", "control.py", "        if wanted < MIN_CHARGE_A:", "        if wanted < 0:", "The pilot's floor is ignored and the car is offered three or four amps"),
    Mutant("M13", "floor", "control.py", "            if now - self._below_floor_since >= s.pause_delay_s:\n                return self._set(0.0, self.phases, \"the sun has been short for too long\", now)", "            if False:\n                return self._set(0.0, self.phases, \"the sun has been short for too long\", now)", "A shortage is ridden out for ever, so a long cloud is charged through on the grid"),
    Mutant("M14", "floor", "control.py", "            if self._ride_out_wh >= s.ride_out_budget_wh:\n                return self._set(0.0, self.phases, \"riding out the shadow has cost enough\", now)", "            if False:\n                return self._set(0.0, self.phases, \"riding out the shadow has cost enough\", now)", "Riding out a shadow is bounded only by the clock, so a day of cloud buys kilowatt-hours"),
    Mutant("M15", "floor", "control.py", "            self._ride_out_wh += max(0.0, reading.grid_w) * since_last / 3600.0", "            self._ride_out_wh += 0.0", "What riding out a shadow has cost is never counted, so the budget never runs out"),
    Mutant("M16", "floor", "control.py", "            return self._set(MIN_CHARGE_A, self.phases, \"riding out a short shortage at 6 A\", now)", "            return self._set(0.0, self.phases, \"riding out a short shortage at 6 A\", now)", "Every passing shadow stops the session instead of holding the floor"),
    Mutant("M17", "floor", "control.py", "            if now - self._above_floor_since < s.resume_delay_s:\n                return self._set(0.0, self.phases, \"waiting to be sure the sun is back\", now)", "            if False:\n                return self._set(0.0, self.phases, \"waiting to be sure the sun is back\", now)", "Charging restarts the moment the sun peeps out, so the car is switched again and again"),
    Mutant("M18", "floor", "control.py", "        self._below_floor_since = None\n        self._ride_out_wh = 0.0", "        self._ride_out_wh = 0.0", "The clock on a shortage is never reset, so the second cloud of the day stops the session at once"),

    # ---- phases: one or three ---------------------------------------------------------------------
    Mutant("M19", "phases", "control.py", "        elif self.phases == 1 and watts > three_phase_floor + s.phase_switch_margin_w:", "        elif self.phases == 1 and watts > s.max_a * NOMINAL_V:", "Three phases are asked for as soon as one is full, where three cannot charge at all"),
    Mutant("M20", "phases", "control.py", "        if self.phases == 3 and watts < three_phase_floor:", "        if self.phases == 3 and watts < 0:", "One phase is never asked for, so a modest surplus charges nothing"),
    Mutant("M21", "phases", "control.py", "        if self.last_phase_switch_s is not None and now - self.last_phase_switch_s < s.phase_switch_cooldown_s:\n            return self.phases", "        if False:\n            return self.phases", "The cooldown after a switch is gone, so the house is rewired back and forth"),
    Mutant("M22", "phases", "control.py", "        if now - self._phase_wished_since(wish, now) >= s.phase_switch_delay_s:", "        if now - self._phase_wished_since(wish, now) >= 0:", "The house is rewired on the first reading that suggests it, not on a settled one"),
    Mutant("M23", "phases", "control.py", "            wanted = self.available_a(reading, phases)\n            return self._set(max(wanted, MIN_CHARGE_A), phases, f\"switching to {phases} phase(s)\", now)", "            return self._set(max(wanted, MIN_CHARGE_A), phases, f\"switching to {phases} phase(s)\", now)", "The first offer after a switch is still worked out for the old wiring"),
    Mutant("M24", "phases", "control.py", "        if not s.allow_phase_switching:\n            return self.phases", "        if False:\n            return self.phases", "A house with no switching hardware is rewired anyway"),

    # ---- safety: when the controller cannot see ---------------------------------------------------
    Mutant("M25", "safety", "control.py", "        if reading.grid_age_s > s.stale_after_s:", "        if False:", "A meter that stopped reporting is trusted, so the car charges blind off the grid"),
    Mutant("M26", "safety", "control.py", "        if not reading.plugged:\n            return self._set(0.0, self.phases, \"no car on the cable\", now)", "        if False:\n            return self._set(0.0, self.phases, \"no car on the cable\", now)", "An unplugged car is still offered current"),
    Mutant("M27", "safety", "control.py", "            return self._set(0.0, self.phases, \"the meter has gone quiet\", now)", "            return self._set(MIN_CHARGE_A, self.phases, \"the meter has gone quiet\", now)", "A quiet meter makes the controller charge at the floor instead of stopping"),

    # ---- the model: what the house and the car really do ------------------------------------------
    Mutant("M28", "sums", "house.py", "        return self.house_w() + self.car_w() - self.pv_w()", "        return self.house_w() - self.pv_w()", "The meter at the door does not see the car, so nothing it does shows up"),
    Mutant("M29", "floor", "house.py", "        self.offered_a = 0.0 if amps < MIN_CHARGE_A else amps", "        self.offered_a = max(amps, MIN_CHARGE_A)", "An offer of nothing becomes an offer of six amps, so a pause charges the car anyway"),
    Mutant("M30", "safety", "house.py", "            if not self.silent:\n                self.reading_w = self._sum_w / self._sum_s + self.noise_w\n                self.reading_age_s = 0", "            self.reading_w = self._sum_w / self._sum_s + self.noise_w\n            self.reading_age_s = 0", "A silent meter keeps publishing, so a failure cannot be noticed at all"),

    # ---- the wire: the two drivers ------------------------------------------------------------------
    Mutant("M31", "wire", "drivers/modbus.py", "                self.house.offer(value / 10.0)", "                self.house.offer(float(value))", "The wallbox register is read as amps when it is tenths of an amp"),
    Mutant("M32", "wire", "drivers/modbus.py", "                if value != 0 and not (MIN_CHARGE_A * 10 <= value <= 320):\n                    raise ModbusError(ILLEGAL_VALUE)", "                if False:\n                    raise ModbusError(ILLEGAL_VALUE)", "The wallbox accepts any current at all, including ones no pilot can carry"),
    Mutant("M33", "wire", "drivers/modbus.py", "    return int(struct.unpack(\">i\", struct.pack(\">HH\", high, low))[0])", "    return int(struct.unpack(\">I\", struct.pack(\">HH\", high, low))[0])", "A negative meter reading is read as a huge positive one, so selling looks like buying"),
    Mutant("M34", "wire", "drivers/modbus.py", "        if transaction != self.transaction:\n            raise ConnectionError(f\"answer {transaction} is not for question {self.transaction}\")", "        if False:\n            raise ConnectionError(f\"answer {transaction} is not for question {self.transaction}\")", "An answer is accepted whatever question it belongs to"),
    Mutant("M35", "wire", "drivers/ocpp.py", "        if self.refuse_above_a is not None and amps > self.refuse_above_a:\n            self.rejected += 1\n            return \"Rejected\"", "        if False:\n            self.rejected += 1\n            return \"Rejected\"", "The station accepts every profile, even one it cannot honour"),
    Mutant("M36", "wire", "drivers/ocpp.py", "        if schedule.get(\"chargingRateUnit\") != \"A\":\n            self.rejected += 1\n            return \"Rejected\"", "        if False:\n            self.rejected += 1\n            return \"Rejected\"", "A limit in watts is treated as a limit in amps"),
    Mutant("M37", "wire", "drivers/ocpp.py", "        limit = command.amps if command.amps >= MIN_CHARGE_A else 0.0", "        limit = max(command.amps, MIN_CHARGE_A)", "A pause is sent to the station as a six amp limit, so the car charges through it"),
]
# fmt: on

IGNORE = shutil.ignore_patterns(
    ".venv",
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".hypothesis",
    "evidence",
    "allure-*",
    "site",
    "docs",
)


def run_suite(workdir: Path, driver: str) -> tuple[bool, list[dict[str, str]], float]:
    """Run the suite in ``workdir``. Returns (passed, failed tests, seconds)."""
    env = {**os.environ, "DRIVER": driver, "PYTHONDONTWRITEBYTECODE": "1", "EVIDENCE": "1"}
    started = time.monotonic()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-m", "not pages"],
        cwd=workdir,
        env=env,
        capture_output=True,
        text=True,
    )
    seconds = time.monotonic() - started
    failed: list[dict[str, str]] = []
    evidence = workdir / "evidence" / f"run-{driver}.json"
    if evidence.exists():
        for test in json.loads(evidence.read_text())["tests"]:
            if test["outcome"] == "failed":
                failed.append({"id": test["id"], "name": test["name"], "title": test["title"], "suite": test["suite"]})
    if result.returncode not in (0, 1):
        failed.append({"id": "pytest", "name": "pytest", "title": result.stdout[-400:], "suite": "pytest"})
    return result.returncode == 0, failed, seconds


def check(mutant: Mutant | None, tmp: Path, driver: str) -> dict[str, object]:
    name = mutant.id if mutant else f"control-{driver}"
    work = tmp / name
    shutil.copytree(ROOT, work, ignore=IGNORE)
    if mutant:
        target = work / SRC / mutant.file
        text = target.read_text()
        if text.count(mutant.old) != 1:
            raise SystemExit(f"{mutant.id}: pattern found {text.count(mutant.old)} times in {mutant.file}, expected 1")
        target.write_text(text.replace(mutant.old, mutant.new))
    passed, failed, seconds = run_suite(work, driver)
    shutil.rmtree(work, ignore_errors=True)
    return {"passed": passed, "failed": failed, "seconds": round(seconds, 1)}


def main(argv: list[str]) -> int:
    chosen = [m for m in MUTANTS if not argv or m.id in argv]
    workers = int(os.getenv("MUTANT_WORKERS", str(min(6, os.cpu_count() or 2))))
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="mutants-") as tmp_name, ThreadPoolExecutor(workers) as pool:
        tmp = Path(tmp_name)
        drivers = sorted({m.driver for m in chosen})
        controls = {d: pool.submit(check, None, tmp, d) for d in drivers}
        futures = {m.id: pool.submit(check, m, tmp, m.driver) for m in chosen}
        control_ok = True
        for driver, future in controls.items():
            outcome = future.result()
            print(f"control ({driver}): {'passed' if outcome['passed'] else 'FAILED'} in {outcome['seconds']} s")
            if not outcome["passed"]:
                control_ok = False
                print(json.dumps(outcome["failed"], indent=1)[:2000], file=sys.stderr)
        results = []
        for mutant in chosen:
            outcome = futures[mutant.id].result()
            failed = outcome["failed"]
            assert isinstance(failed, list)
            caught = not outcome["passed"]
            print(
                f"{mutant.id}: {'caught by ' + str(len(failed)) + ' tests' if caught else 'SURVIVED'} - {mutant.title}"
            )
            results.append(
                {
                    "id": mutant.id,
                    "area": mutant.area,
                    "file": SRC + mutant.file,
                    "title": mutant.title,
                    "driver": mutant.driver,
                    "old": mutant.old.strip("\n"),
                    "new": mutant.new.strip("\n"),
                    "caught": caught,
                    "killers": failed[:12],
                    "killer_count": len(failed),
                    "seconds": outcome["seconds"],
                }
            )

    survived = [r for r in results if not r["caught"]]
    total = len(results)
    meta = {
        "finished": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": os.getenv("GITHUB_SHA", "")[:7],
        "total": total,
        "caught": total - len(survived),
        "control": control_ok,
        "seconds": round(time.monotonic() - started),
    }
    out = ROOT / "evidence"
    out.mkdir(exist_ok=True)
    (out / "mutants.json").write_text(
        json.dumps({"meta": meta, "mutants": results}, ensure_ascii=False, indent=1) + "\n"
    )

    lines = [
        "# Mutation check",
        "",
        f"**{meta['caught']}/{total} planted bugs caught.** Control runs without a planted bug: "
        f"{'passed' if control_ok else 'FAILED'}.",
        "",
        "| Id | File | Planted bug | Run | Result | Tests that failed |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        verdict = "caught" if r["caught"] else "**survived**"
        lines.append(f"| {r['id']} | `{r['file']}` | {r['title']} | {r['driver']} | {verdict} | {r['killer_count']} |")
    (ROOT / "mutants-result.md").write_text("\n".join(lines) + "\n")
    print(f"{meta['caught']}/{total} caught in {meta['seconds']} s")
    return 1 if survived or not control_ok else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
