"""Build the visual page from the project itself, so it cannot drift from it.

    python scripts/build_pages.py            # write docs/surplus-charging.html
    python scripts/build_pages.py --check    # and fail if anything is left untranslated

Nothing on the page is typed in by hand. The constants come from the source, the days come from
running the real controller over the real model, the test list comes from the evidence the last run
wrote, and the planted bugs come from the mutation check. The page is one self-contained file so it
can be opened from anywhere, including straight off a memory stick at an interview.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from wire import record as record_wire  # noqa: E402

from surplus_lab import __version__  # noqa: E402
from surplus_lab.control import Controller, Settings  # noqa: E402
from surplus_lab.day import DAYS, HOUR, run  # noqa: E402
from surplus_lab.drivers.direct import DirectDriver  # noqa: E402
from surplus_lab.house import MIN_CHARGE_A, NOMINAL_V, Cloud, House, Load  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
EVIDENCE = ROOT / "evidence"
OUT = ROOT / "docs" / "surplus-charging.html"
PAGE_TICKS = 900  # points kept per day on the chart: a day is 4700 ticks, a chart needs far fewer


def js(name: str, value: Any) -> str:
    return f"window.{name} = {json.dumps(value, ensure_ascii=False, separators=(',', ':'))};"


# ---- what the page needs to explain the problem ---------------------------------------------------


def export_spec() -> dict[str, Any]:
    """The numbers that matter, taken from the source rather than retyped."""
    settings = Settings()
    return {
        "release": __version__,
        "volts": NOMINAL_V,
        "minA": MIN_CHARGE_A,
        "onePhaseAmpW": NOMINAL_V,
        "threePhaseAmpW": 3 * NOMINAL_V,
        "threePhaseFloorW": 3 * MIN_CHARGE_A * NOMINAL_V,
        "onePhaseFloorW": MIN_CHARGE_A * NOMINAL_V,
        "settings": {key: getattr(settings, key) for key in settings.__dataclass_fields__},
        "days": list(DAYS),
    }


# ---- whole days, run for real --------------------------------------------------------------------

DAY_WORDS = {
    "clear": ["A clear day", "Ясный день", "Nothing in the way of the sun.", "Солнцу ничего не мешает."],
    "broken-cloud": [
        "Broken cloud",
        "Рваная облачность",
        "A cloud every quarter of an hour: the hardest weather there is for this job.",
        "Облако каждые пятнадцать минут: самая трудная погода для этой задачи.",
    ],
    "one-long-cloud": [
        "One long cloud",
        "Одно долгое облако",
        "Long enough that holding the session open is the wrong answer.",
        "Достаточно долгое, чтобы держать сессию открытой было неправильно.",
    ],
    "kettle-and-oven": [
        "A busy kitchen",
        "Занятая кухня",
        "Clear sky, but the household keeps switching things on.",
        "Небо чистое, но в доме всё время что-то включают.",
    ],
    "dull": [
        "A dull day",
        "Пасмурный день",
        "Never enough sun for the smallest charge the pilot can ask for.",
        "Солнца ни разу не хватает на самый маленький ток, который может запросить Pilot.",
    ],
    "almost-full-car": [
        "An almost full car",
        "Почти полная машина",
        "The car tapers: the offer stays high while it quietly takes less.",
        "Машина сбавляет: предложение высокое, а она тихо берёт меньше.",
    ],
    "whole-day": [
        "A whole day",
        "Целый день",
        "From first light, with cloud, a kettle, an oven and a heat pump.",
        "С рассвета, с облаками, чайником, духовкой и тепловым насосом.",
    ],
}


def play(day: str, settings: Settings | None = None, until_s: int = 21 * HOUR) -> dict[str, Any]:
    """Run one named day for real and keep enough of it to draw."""
    house = DAYS[day]()
    controller = Controller(settings=settings or Settings(), phases=house.phases)
    trace = run(house, controller, DirectDriver(house), until_s=until_s, tick_s=10)
    every = max(1, len(trace.ticks) // PAGE_TICKS)
    points = [
        {
            "t": tick.clock,
            "pv": round(tick.pv_w),
            "house": round(tick.house_w),
            "car": round(tick.car_w),
            "grid": round(tick.grid_w),
            "a": tick.offered_a,
            "p": tick.phases,
            "soc": round(tick.soc, 4),
        }
        for index, tick in enumerate(trace.ticks)
        if index % every == 0
    ]
    moments = [
        {"t": tick.clock, "why": tick.why, "a": tick.offered_a, "p": tick.phases}
        for index, tick in enumerate(trace.ticks)
        if tick.why != "no change" and (index == 0 or trace.ticks[index - 1].offered_a != tick.offered_a)
    ]
    totals = house.totals
    return {
        "id": day,
        "points": points,
        "moments": moments[:400],
        "totals": {
            "pv": round(totals.pv_wh),
            "house": round(totals.house_wh),
            "car": round(totals.car_wh),
            "bought": round(totals.bought_for_car_wh),
            "spilled": round(totals.spilled_wh),
            "fromSun": round(totals.car_from_sun_wh),
            "imported": round(totals.imported_wh),
            "exported": round(totals.exported_wh),
        },
        "counts": {
            "changes": trace.changes,
            "pauses": trace.pauses,
            "resumes": trace.resumes,
            "phases": trace.phase_switches,
        },
    }


def export_days() -> dict[str, Any]:
    return {"words": DAY_WORDS, "days": [play(day) for day in DAYS]}


# ---- the conversations the twin has to reproduce ---------------------------------------------------

SCRIPTS: list[dict[str, Any]] = [
    {"name": "a clear day", "day": "clear", "hours": 13},
    {"name": "broken cloud all day", "day": "broken-cloud", "hours": 13},
    {"name": "one long cloud", "day": "one-long-cloud", "hours": 13},
    {"name": "a busy kitchen", "day": "kettle-and-oven", "hours": 13},
    {"name": "a dull day", "day": "dull", "hours": 13},
    {"name": "an almost full car", "day": "almost-full-car", "hours": 13},
    {"name": "a whole day from first light", "day": "whole-day", "hours": 14},
    {"name": "a clear day on one phase", "day": "clear", "hours": 10, "phases": 1},
    {
        "name": "a clear day with no switching",
        "day": "clear",
        "hours": 10,
        "settings": {"allow_phase_switching": False},
    },
    {"name": "a clear day with a 250 W margin", "day": "clear", "hours": 10, "settings": {"margin_w": 250.0}},
    {"name": "a clear day with a 32 A wallbox", "day": "clear", "hours": 10, "settings": {"max_a": 32.0}},
    {"name": "a clear day the meter goes quiet in", "day": "clear", "hours": 10, "silent_from": 11 * HOUR},
]


def _random_day(seed: int) -> dict[str, Any]:
    """A day nobody wrote, so the twin is held to weather the author did not think of."""
    rng = random.Random(seed)
    clouds = []
    clock = 7 * HOUR
    while clock < 20 * HOUR:
        clock += rng.randint(300, 3600)
        clouds.append([clock, rng.randint(60, 2400), round(rng.uniform(0.05, 0.9), 3), rng.choice([2, 20, 120])])
    loads = []
    for _ in range(rng.randint(0, 6)):
        loads.append([rng.randint(7 * HOUR, 20 * HOUR), rng.randint(120, 5400), round(rng.uniform(300, 4000), 1)])
    return {
        "name": f"a day nobody wrote ({seed})",
        "day": "clear",
        "hours": 13,
        "peak_w": round(rng.uniform(2500, 9000), 1),
        "clouds": clouds,
        "loads": loads,
        "phases": rng.choice([1, 3]),
    }


def build_from_script(script: dict[str, Any]) -> tuple[House, Controller]:
    house = DAYS[script["day"]]()
    if "peak_w" in script:
        house.inverter.sky.peak_w = script["peak_w"]
    for start, seconds, factor, edge in script.get("clouds", []):
        house.inverter.sky.clouds.append(Cloud(start_s=start, seconds=seconds, factor=factor, edge_s=edge))
    for start, seconds, watts in script.get("loads", []):
        house.household.loads.append(Load("something", watts, start, seconds))
    if "phases" in script:
        house.phases = script["phases"]
    controller = Controller(settings=Settings(**script.get("settings", {})), phases=house.phases)
    return house, controller


def record_vectors() -> list[dict[str, Any]]:
    """Play every script through the Python controller and write down every decision it made."""
    scripts = SCRIPTS + [_random_day(seed) for seed in range(1, 9)]
    out = []
    for script in scripts:
        house, controller = build_from_script(script)
        driver = DirectDriver(house)
        ticks = []
        until = house.clock + int(script["hours"] * HOUR)
        while house.clock < until:
            if script.get("silent_from") and house.clock >= script["silent_from"]:
                house.meter.silent = True
            reading = driver.read(house.clock)
            command = controller.decide(reading)
            driver.apply(command)
            house.advance(10)
            ticks.append(
                [
                    reading.clock,
                    round(reading.grid_w, 6),
                    reading.grid_age_s,
                    round(reading.car_w, 6),
                    command.amps,
                    command.phases,
                    command.why,
                ]
            )
        out.append(
            {
                "name": script["name"],
                "script": script,
                "ticks": ticks,
                "totals": {
                    "car": round(house.totals.car_wh, 6),
                    "bought": round(house.totals.bought_for_car_wh, 6),
                    "spilled": round(house.totals.spilled_wh, 6),
                },
            }
        )
    return out


# ---- the last test run and the planted bugs ---------------------------------------------------------


def load_run() -> dict[str, Any]:
    metas: dict[str, Any] = {}
    tests: dict[str, Any] = {}
    order: list[str] = []
    for path in sorted(EVIDENCE.glob("run-*.json")):
        data = json.loads(path.read_text())
        key = data["meta"]["driver"]
        metas[key] = data["meta"]
        for test in data["tests"]:
            node = test["id"]
            if node not in tests:
                tests[node] = {k: test[k] for k in ("id", "name", "suite", "title", "params", "outcome", "ms")}
                tests[node]["runs"] = {}
                order.append(node)
            entry = tests[node]
            entry["runs"][key] = test["outcome"]
            if test["outcome"] == "skipped":
                entry.setdefault("skip", {})[key] = test["reason"]
            if test["outcome"] != "skipped" and "steps" not in entry:
                entry["steps"] = test["steps"]
                entry["via"] = key
    return {"meta": metas, "tests": [tests[node] for node in order]}


def load_mutants() -> dict[str, Any]:
    path = EVIDENCE / "mutants.json"
    if not path.exists():
        return {"meta": {}, "mutants": []}
    data: dict[str, Any] = json.loads(path.read_text())
    for mutant in data["mutants"]:
        mutant["killers"] = [{"name": k["name"], "suite": k["suite"]} for k in mutant["killers"][:6]]
    return data


# ---- putting the file together -------------------------------------------------------------------------


def assemble() -> str:
    shell = (SITE / "shell.html").read_text()
    out = []
    for line in shell.split("\n"):
        marker = line.strip()
        if marker.startswith("<!-- include:") and marker.endswith("-->"):
            name = marker[len("<!-- include:") : -3].strip()
            body = (SITE / name).read_text()
            if name.endswith(".css"):
                out.append("<style>\n" + body + "</style>")
            elif name.endswith(".js"):
                out.append("<script>\n" + body + "</script>")
            else:
                out.append(body)
        else:
            out.append(line)
    return "\n".join(out)


def check_translations(run: dict[str, Any], mutants: dict[str, Any]) -> list[str]:
    ru = json.loads((SITE / "i18n" / "ru.json").read_text())
    missing = []
    for test in run["tests"]:
        if test["name"] not in ru["tests"]:
            missing.append(f"test: {test['name']}")
        if test["suite"] not in ru["suites"]:
            missing.append(f"suite: {test['suite']}")
    patterns = [pair[0] for pair in ru["steps"]]
    import re

    for test in run["tests"]:
        for step in test.get("steps", []):
            text = step["text"]
            if text and not any(re.fullmatch(pattern, text) for pattern in patterns):
                missing.append(f"step: {text}")
    for test in run["tests"]:
        for step in test.get("steps", []):
            for note in step.get("notes", []):
                if not any(re.fullmatch(pattern, note[0]) for pattern in patterns):
                    missing.append(f"note: {note[0]}")
    for mutant in mutants["mutants"]:
        if mutant["id"] not in ru["mutants"]:
            missing.append(f"mutant: {mutant['id']}")
        if mutant["area"] not in ru["areas"]:
            missing.append(f"area: {mutant['area']}")
    for day in DAYS:
        if day not in DAY_WORDS:
            missing.append(f"day: {day}")
    return sorted(set(missing))


def main(argv: list[str]) -> int:
    check = "--check" in argv
    run = load_run()
    mutants = load_mutants()
    days = export_days()

    (SITE / "data").mkdir(exist_ok=True)
    (SITE / "data" / "spec.js").write_text(js("SPEC_DATA", export_spec()) + "\n")
    (SITE / "data" / "run.js").write_text(js("RUN_DATA", run) + "\n")
    (SITE / "data" / "mutants.js").write_text(js("MUTANT_DATA", mutants) + "\n")
    (SITE / "data" / "days.js").write_text(js("DAY_DATA", days) + "\n")
    (SITE / "data" / "wire.js").write_text(js("WIRE_DATA", record_wire()) + "\n")
    ru = json.loads((SITE / "i18n" / "ru.json").read_text())
    (SITE / "data" / "ru.js").write_text(js("RU_DATA", ru) + "\n")

    vectors = record_vectors()
    (SITE / "test").mkdir(exist_ok=True)
    (SITE / "test" / "vectors.json").write_text(json.dumps(vectors, separators=(",", ":")) + "\n")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    html = assemble()
    OUT.write_text(html)
    size = len(html.encode()) // 1024
    print(f"{OUT.relative_to(ROOT)}: {size} KB, {len(run['tests'])} tests, {len(mutants['mutants'])} mutants")

    if check:
        missing = check_translations(run, mutants)
        if missing:
            print("untranslated:", file=sys.stderr)
            for line in missing:
                print("  " + line, file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
