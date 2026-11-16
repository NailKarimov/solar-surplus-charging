# Test summary report — solar-surplus-charging

Structure after ISO/IEC/IEEE 29119-3. Covers the run of 16 November 2026, `surplus_lab` 1.0.0.

## 1. What was run

| Pass                          | Command                 | Passed | Skipped |
| ------------------------------- | ------------------------- | -------: | --------: |
| Straight into the model       | `pytest`                |     90 |       0 |
| Through a Modbus TCP wallbox  | `DRIVER=modbus pytest`  |      5 |      85 |
| Through an OCPP charge point  | `DRIVER=ocpp pytest`    |      5 |      85 |
| The visual page in a browser  | `pytest -m pages`       |     25 |       0 |
| **Total**                     |                         | **125** |         |

Nothing failed. The skips are the design of the matrix, not gaps: a behaviour test runs once, against the model,
because the control law does not depend on the wire its number travels down — and that claim is itself one of the
tests, which builds all three drivers and replays a whole day through each.

Beside the suite:

- **Mutation check.** 37 of 37 planted bugs caught, in 306 seconds; the control run without a bug passed. The
  table is [`mutants-result.md`](../mutants-result.md). By area: 8 in the floor and the hysteresis around it,
  7 in the arithmetic, 7 in the two drivers, 6 in the phase switching, 5 in the timing, 4 in the fail-safe.
- **Twin check.** The JavaScript controller in the visual page made **88 560 decisions across 20 days**, eight of
  them generated at random, all identical to the Python controller's — and the three energy totals matched to
  within a millionth of a watt-hour.
- **Static checks.** `ruff check`, `ruff format --check` and `mypy --strict` over `src`, `tests` and `scripts`:
  clean.

## 2. What the days cost

The promises are not pass/fail assertions about state; they are kilowatt-hours. This is the measured result of
running the controller against the model, and it is what the suite asserts budgets against.

| Day                | The roof made | Into the car | Bought for the car | Given away it could have had | Changes | Stops |
| -------------------- | --------------: | -------------: | -------------------: | -----------------------------: | --------: | ------: |
| A clear day        |     51.1 kWh |    39.4 kWh |      6 Wh (0.0 %) |             0.9 kWh (1.8 %) |      21 |     2 |
| Broken cloud       |     47.5 kWh |    34.1 kWh |    400 Wh (1.2 %) |            5.1 kWh (10.8 %) |      75 |    12 |
| One long cloud     |     47.4 kWh |    37.4 kWh |     75 Wh (0.2 %) |             1.3 kWh (2.7 %) |      26 |     4 |
| A busy kitchen     |     51.1 kWh |    36.8 kWh |    205 Wh (0.6 %) |             2.8 kWh (5.5 %) |      33 |     5 |
| A dull day         |     12.1 kWh |       4 Wh |              3 Wh |                           0 |       2 |     1 |
| An almost full car |     51.1 kWh |     6.0 kWh |      0 Wh (0.0 %) |             0.4 kWh (0.7 %) |      21 |     2 |
| A whole day        |     51.0 kWh |    36.4 kWh |    277 Wh (0.8 %) |             2.5 kWh (4.9 %) |      47 |     8 |

Broken cloud is where the trade-off shows. Sixteen shadows in four hours cost 400 Wh of bought electricity and
5.1 kWh of spilled sun, against 34 kWh delivered. On a clear day the same controller buys six watt-hours.

## 3. Findings

The item under test is this project's own controller, so a finding is fixed rather than filed. Each was found by
a test or by the mutation check, and each is now pinned.

**SS-1 — waiting out a cloud for a fixed three minutes bought kilowatt-hours.** Severity: major. The first
version held the 6 A floor through a shadow for a fixed `pause_delay_s` of three minutes, on the reasoning that
stopping a session is worse than a short shortage. Measured over a day of broken cloud, that cost **1509 Wh of
bought electricity, 4.4 % of everything that reached the car** — sixteen shadows, each buying up to 1.4 kW on one
phase or 4.1 kW on three for three minutes. A fixed wait is a promise to spend whatever that wait costs.

Fixed by bounding the wait by money as well as by time: the controller counts what the meter says it is buying
while it holds on, and lets go when that reaches `ride_out_budget_wh`. The budget is not arbitrary — letting go
costs a restart, a restart costs the five-minute resume delay, and five minutes of surplus is about 330 Wh of
spilled sun, worth roughly 80 Wh of bought electricity at the usual ratio of import to export tariffs. Sixty
watt-hours sits just inside that. The same budget makes the controller three times as impatient on three phases,
where the same six amps costs three times as much, which is the correct behaviour and has a test of its own.

Afterwards the same day cost **400 Wh, 1.2 %**. Pinned by
`test_a_long_shadow_ends_the_session_rather_than_buying_through_it`,
`test_riding_out_a_shadow_stops_when_it_has_cost_enough`,
`test_riding_out_costs_three_times_as_much_on_three_phases_and_ends_three_times_sooner`, and planted bugs M13,
M14 and M15.

**SS-2 — the controller moved to three phases where three phases cannot charge.** Severity: major. The rule for
switching up was "one phase is full", which is 16 A × 230 V = 3680 W. But the smallest charge three phases can
carry is 3 × 6 A × 230 V = **4140 W**. Between those two numbers one phase is the only wiring that works at all,
and the controller was switching into a range where it would immediately find itself below the floor and start
riding out or stopping. Fixed by putting the threshold at the three-phase floor plus a margin, so the pair of
thresholds do not sit on top of each other and flap. Pinned by
`test_three_phases_are_not_asked_for_until_three_phases_could_actually_charge` and by planted bug M19.

**SS-3 — the car in the model never started charging.** Severity: critical to the test rig, and the reason the
first full day showed 0 Wh into the car. The car ramps towards the offer at 2 A/s, and a guard zeroed the current
whenever it fell below half the floor — so every second it climbed to 2 A and was reset to nothing. A real car
does not creep up from zero; it closes its contactor at the floor and ramps from there. Fixed accordingly, and
the model is itself under the mutation check (M28–M30) precisely because a model that lies makes every test above
it meaningless.

**SS-4 — a planted bug that no test could catch, because the design had two of the same clock.** Severity: minor
in effect, significant in what it showed. Mutation M11 removes the line that restarts the "how long have we
wanted this" timer when the wanted value changes — a real defect, which would let an old wait count towards a new
value and raise the offer too soon. No test caught it, and no test could: a second code path was quietly doing
the same reset, so removing the first changed nothing. The honest conclusion was not "write a cleverer test" but
"there should not be two places that reset one clock". The timing state was rewritten as a single
`(value, since)` pair with exactly one function that resets it, M11 was re-pointed at that line, and it is now
caught. Mutation testing found a design problem rather than a test gap, which is the more useful result.

**SS-5 — the meter was defined twice, so a bug in one definition changed nothing.** Severity: minor. `House`
had `grid_w()` returning `house + car − pv`, and the stepping loop computed the same expression again inline.
Planted bug M28 broke the first one and nothing failed. Fixed by making the loop call `grid_w()`, so there is one
definition of what the meter at the door sees. M28 is now caught by six tests.

No defect is open.

## 4. Deviations from the plan

- **No home battery.** The house has panels, a household and a car, and no storage. A hybrid inverter with a
  battery changes the control law fundamentally — the battery masks the surplus and competes with the car for
  it — and it was left out on purpose to keep one problem in view. It is the obvious next version.
- **No hardware.** The pilot wire, the meter and the car are modelled. The pilot's duty-cycle relation is honoured
  (6 A floor, whole amps), but nothing here has been on an oscilloscope.
- **The live page carries 7 of the 37 planted bugs.** A bug belongs on that page only if one of the live checks
  can show it to a visitor. The ones about timing are real defects and the Python suite catches every one, but on
  a single day in a browser they are not visibly different from a controller doing its job. The page says so.
- **Tariffs are a constant, not an input.** The ride-out budget is derived from the usual ratio between import and
  export prices rather than from a live price feed.

## 5. Assessment

The exit criteria of the test plan are met: three green passes and a green page suite, no untranslated text in the
page build, no difference between the twin and the Python controller across twenty days, 37 of 37 planted bugs
caught with a passing control run, and every finding recorded with its fix.

What the suite is good at is the thing that matters commercially: it states the promises in the units the
electricity bill is in, and it measures them over whole days rather than asserting that a flag was set. The
weakest point is the one named in section 4 — the absence of a battery — and it is the next thing to build.
