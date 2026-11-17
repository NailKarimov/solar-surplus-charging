"""The visual page, opened in a real browser.

The page is the part of this project most people will actually look at, so it is tested like
everything else: every view opens, the language switch works, the chart is drawn from the real run,
and — the one that matters — planting a bug in the live house turns the matching check red, exactly
as planting it in Python turns a test red.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.pages

PAGE = Path(__file__).resolve().parent.parent / "docs" / "surplus-charging.html"
VIEWS = ("tour", "live", "wire", "day", "replay", "bugs")

# planted bug -> the live check it must turn red
BUG_TO_CHECK = {
    "M01": "spill",
    "M03": "zero",
    "M07": "zero",
    "M12": "floor",
    "M14": "zero",
    "M25": "blind",
    "M26": "unplugged",
}

# One script that puts the house through everything the checks watch for.
EXERCISE = """() => {
  const d = App.views.live.debug;
  const house = d.state().house;
  const until = (clock) => { while (house.clock < clock) d.tick(10); };
  // The same day the Python suite calls "broken cloud": a cloud every quarter of an hour, five
  // minutes long, from nine in the morning. Plus a quiet meter and a driver who takes the car away.
  for (let n = 0; n < 16; n++) {
    house.inverter.sky.clouds.push(new Twin.Cloud(9 * 3600 + n * 900, 300, n % 2 ? 0.25 : 0.45, 20));
  }
  until(14 * 3600);
  house.meter.silent = true;
  until(14 * 3600 + 600);
  house.meter.silent = false;
  until(16 * 3600);
  house.car.plugged = false;
  house.car.drawing_a = 0;
  until(16 * 3600 + 300);
  house.car.plugged = true;
  until(20 * 3600 + 3000);
  d.paint();
}"""


# One moment of the tour, played at the twin's own tick rather than in real time.
PLAY_MOMENT = """(index) => {
  const d = App.views.tour.debug;
  const chapter = d.chapters[index];
  d.go(index, false);
  const house = d.state().house;
  const controller = d.state().controller;
  const first = house.offered_a;
  let spent = 0;
  while (house.clock < chapter.to) {
    Twin.tick(house, controller, 10);
    spent = Math.max(spent, controller._ride_out_wh);
  }
  return { first: first, last: house.offered_a, spent: spent };
}"""


@pytest.fixture(scope="module")
def browser() -> Iterator[Any]:
    missing = "Playwright is not installed: pip install -e '.[pages]'"
    sync_api = pytest.importorskip("playwright.sync_api", reason=missing)
    if not PAGE.exists():
        pytest.skip("docs/surplus-charging.html is not built: python scripts/build_pages.py")
    with sync_api.sync_playwright() as playwright:
        chromium = playwright.chromium.launch()
        yield chromium
        chromium.close()


@pytest.fixture
def page(browser: Any) -> Iterator[Any]:
    context = browser.new_context(viewport={"width": 1280, "height": 900}, locale="en-US")
    tab = context.new_page()
    tab.errors = []
    tab.on("pageerror", lambda error: tab.errors.append(str(error)))
    yield tab
    context.close()


def open_view(page: Any, view: str) -> None:
    page.goto(f"{PAGE.as_uri()}#{view}")
    page.wait_for_selector(f"#view-{view}.on")


def red_checks(page: Any) -> list[str]:
    result: list[str] = page.eval_on_selector_all(".check.fail", "els => els.map(e => e.dataset.check)")
    return result


@pytest.mark.parametrize("view", VIEWS)
def test_every_view_opens_without_a_script_error(page: Any, view: str) -> None:
    """Each of the five views of the visual page opens by its own address and runs without a script error."""
    open_view(page, view)
    page.wait_for_timeout(400)
    assert page.errors == []
    assert page.locator(f"#view-{view} h2").inner_text().strip()
    assert page.locator(".view.on").count() == 1


@pytest.mark.parametrize(("bug", "check"), BUG_TO_CHECK.items())
def test_a_planted_bug_turns_its_own_check_red(page: Any, bug: str, check: str) -> None:
    """In the live house, switching on a planted bug turns the check that watches for it red."""
    open_view(page, "live")
    page.click(f"label[for=bug-{bug}]")
    page.evaluate(EXERCISE)
    page.wait_for_timeout(300)
    assert check in red_checks(page)
    assert page.errors == []


def test_a_healthy_house_keeps_every_check_green(page: Any) -> None:
    """With no bug planted, a day of cloud, a quiet meter and an unplugged car turns no check red."""
    open_view(page, "live")
    page.evaluate(EXERCISE)
    page.wait_for_timeout(300)
    assert red_checks(page) == []
    assert page.errors == []


def test_the_live_house_really_charges_the_car(page: Any) -> None:
    """Left alone in good sun the live house puts energy into the car rather than standing still."""
    open_view(page, "live")
    page.evaluate("() => { const d = App.views.live.debug; for (let i = 0; i < 1200; i++) d.tick(10); d.paint(); }")
    energy = page.evaluate("() => App.views.live.debug.state().house.totals.car_wh")
    assert energy > 5000


def test_the_tour_plays_one_day_slowly_enough_to_follow(page: Any) -> None:
    """The tour is seven stopped moments, and the ones where a decision happens run near real time."""
    open_view(page, "tour")
    pace = page.evaluate("() => App.views.tour.debug.chapters.map(c => [c.label[0], (c.to - c.from) / c.real])")
    rates = dict(pace)
    assert len(pace) == 7
    assert max(rates.values()) <= 420
    assert rates["A cloud"] <= 40
    assert rates["The oven"] <= 40


def test_each_moment_of_the_tour_says_what_the_controller_did(page: Any) -> None:
    """Every moment of the tour carries its own caption, the offer on the cable and its place in the day."""
    open_view(page, "tour")
    for index in range(7):
        page.evaluate("(i) => App.views.tour.debug.go(i, false)", index)
        page.wait_for_timeout(120)
        assert len(page.locator("#tour-what").inner_text().strip()) > 40
        assert len(page.locator("#tour-does").inner_text().strip()) > 80
        assert "offering" in page.locator("#tour-says").inner_text()
        assert f"Moment {index + 1} of 7" in page.locator("#tour-pace").inner_text()
    assert page.errors == []


def test_the_moments_of_the_tour_do_what_their_captions_claim(page: Any) -> None:
    """Played through, the cloud moment lowers the offer and the deep shadow spends the budget and lets go."""
    open_view(page, "tour")
    cloud = page.evaluate(PLAY_MOMENT, 2)
    assert cloud["last"] < cloud["first"]
    assert cloud["last"] >= 6
    shadow = page.evaluate(PLAY_MOMENT, 5)
    assert shadow["spent"] >= 60
    assert shadow["last"] == 0


def test_the_wire_view_shows_the_real_frames_of_both_drivers(page: Any) -> None:
    """Each moment shows the Modbus frame and the OCPP message that carried that very decision."""
    open_view(page, "wire")
    assert page.locator("#wire-moments button").count() == 4
    for index in range(4):
        page.locator("#wire-moments button").nth(index).click()
        page.wait_for_timeout(120)
        hexes = page.locator("#wire-modbus .hexline").all_inner_texts()
        assert len(hexes) == 2, "a question and an answer"
        ask = hexes[0]
        assert ask[14:18] == "1007", f"function 16 writing register 2000, not {ask}"
        assert page.locator("#wire-modbus .seg").count() >= 8, "every byte carries a label"
        assert "SetChargingProfile" in page.locator("#wire-ocpp").inner_text()
        assert "chargingRateUnit" in page.locator("#wire-ocpp").inner_text()
    assert page.errors == []


def test_the_wire_view_shows_the_reading_and_the_two_refusals(page: Any) -> None:
    """It also shows what each driver reads, and what a wallbox says when it will not do as asked."""
    open_view(page, "wire")
    assert "function 3" in page.locator("#wire-read-modbus").inner_text()
    assert "the meter" in page.locator("#wire-read-modbus").inner_text()
    assert "TriggerMessage" in page.locator("#wire-read-ocpp").inner_text()
    assert "MeterValues" in page.locator("#wire-read-ocpp").inner_text()
    assert page.locator("#wire-no-modbus .seg.ex").count() >= 1, "the exception bytes are marked as such"
    assert "Rejected" in page.locator("#wire-no-ocpp").inner_text()
    assert page.locator("#wire-map .part").count() >= 8
    assert page.errors == []


def test_the_live_house_does_not_race_past_the_eye(page: Any) -> None:
    """Time in the live house runs at the speed the buttons say, not at whatever the frame rate is."""
    open_view(page, "live")
    for label, cap in (("×10", 30), ("×60", 150)):
        page.locator(f"#live-speed button:text-is('{label}')").click()
        page.wait_for_timeout(100)
        before = page.evaluate("() => App.views.live.debug.state().house.clock")
        page.wait_for_timeout(1000)
        after = page.evaluate("() => App.views.live.debug.state().house.clock")
        assert after - before <= cap, f"{label} ran at {after - before} simulated seconds per second"
    assert "10 seconds" in page.locator("#live-pace").inner_text()


def test_the_live_house_shows_what_went_down_the_wire(page: Any) -> None:
    """The live house prints the last decision as both drivers would put it on the wire."""
    open_view(page, "live")
    page.evaluate("() => { const d = App.views.live.debug; for (let i = 0; i < 600; i++) d.tick(10); d.paint(); }")
    page.wait_for_timeout(200)
    text = page.locator("#live-wire").inner_text()
    assert "07d0" in text, "the register the current is written into"
    assert "SetChargingProfile" in text
    assert "register 2000" in text
    assert page.errors == []


def test_the_day_view_draws_the_run_that_really_happened(page: Any) -> None:
    """The whole-day view draws a chart with a line for the roof, the car, the house and the grid."""
    open_view(page, "day")
    page.wait_for_selector("#day-chart svg")
    assert page.locator("#day-chart .ln.pv").count() == 1
    assert page.locator("#day-chart .ln.car").count() == 1
    assert page.locator("#day-chart .ln.grid-line").count() == 1
    assert page.locator("#day-chart .zero").count() == 1
    assert page.locator("#day-moments .m").count() > 5


def test_every_day_can_be_picked_and_redraws_the_chart(page: Any) -> None:
    """Each of the days has its own button, and picking one draws that day instead."""
    open_view(page, "day")
    buttons = page.locator("#day-pick button")
    assert buttons.count() >= 6
    first = page.locator("#day-chart .ln.pv").get_attribute("d")
    buttons.nth(0).click()
    page.wait_for_timeout(200)
    assert page.locator("#day-chart .ln.pv").get_attribute("d") != first
    assert page.errors == []


def test_the_run_view_shows_the_numbers_a_check_measured(page: Any) -> None:
    """Opening a check in the run view shows its steps and the watt-hours it measured."""
    open_view(page, "replay")
    page.wait_for_selector("details.suite[open] .test button")
    page.locator("details.suite[open] .test button").first.click()
    page.wait_for_timeout(200)
    assert page.locator("#replay-suites .detail").count() >= 1
    text = page.locator("#replay-suites .detail").first.inner_text()
    assert "tests/" in text


def test_the_bug_hunt_lists_every_planted_bug(page: Any) -> None:
    """The bug hunt shows each planted bug, the line that was changed, and the checks that caught it."""
    open_view(page, "bugs")
    cards = page.locator("#bugs-list .mut")
    total = page.evaluate("() => window.MUTANT_DATA.meta.total")
    assert cards.count() == total
    assert page.locator("#bugs-list .diff").count() >= total - 2


def test_the_language_switch_translates_the_page(page: Any) -> None:
    """The RU button puts the headings and the test titles into Russian, and EN puts them back."""
    open_view(page, "replay")
    page.click("#lang-ru")
    page.wait_for_timeout(200)
    assert "прогон" in page.locator("#view-replay h2").inner_text().lower()
    page.click("#lang-en")
    page.wait_for_timeout(200)
    assert "test run" in page.locator("#view-replay h2").inner_text().lower()


def test_the_russian_page_names_the_days_in_russian(page: Any) -> None:
    """The whole-day view names its days and explains the chart in Russian too."""
    open_view(page, "day")
    page.click("#lang-ru")
    page.wait_for_timeout(200)
    assert "день" in page.locator("#day-pick").inner_text().lower()
    assert "сет" in page.locator("#day-legend").inner_text().lower()


@pytest.mark.parametrize("view", VIEWS)
def test_the_page_fits_a_phone_screen(browser: Any, view: str) -> None:
    """At the width of a phone no view scrolls sideways."""
    context = browser.new_context(viewport={"width": 390, "height": 844}, locale="en-US")
    tab = context.new_page()
    tab.goto(f"{PAGE.as_uri()}#{view}")
    tab.wait_for_timeout(400)
    width = tab.evaluate("() => document.documentElement.scrollWidth")
    context.close()
    assert width <= 391
