# Test plan — solar-surplus-charging

Structure after ISO/IEC/IEEE 29119-3. One page, because the project is one component.

## 1. Context

| Item               | Value                                                                                                                 |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Item under test    | `surplus_lab` 1.0.0 — a controller that charges an electric car from the surplus of a rooftop solar array            |
| Purpose            | Show, on a portfolio project, how a control law is tested: in energy that actually moved, over whole days, not in assertions about internal state |
| Audience           | Interviewers and reviewers, including those who do not read code; hence the visual page beside the report             |
| Test levels        | Component and component-integration. No system level: there is no product around the component                        |
| Standards involved | IEC 61851-1 for the 6 A floor and the control-pilot duty cycle; Modbus Application Protocol V1.1b3 and Modbus TCP for the wallbox driver; OCPP 1.6 Edition 2 (JSON) for the charge-point driver |

## 2. What is in scope

1. **The arithmetic.** How much the car may take, from the meter reading and what the car is already drawing; the
   margin; the conversion to whole amps per phase, rounded down.
2. **The three promises, over whole days.** What the car cost in bought electricity; how much of the roof's output
   was handed to the grid while the car could have taken it; how often the offer was changed and the session
   stopped. These are measured in watt-hours and counted events, not inferred.
3. **Clouds.** A short shadow is ridden out at the floor; a long one ends the session; the ride-out is bounded by
   what it has cost as well as by the clock; the offer falls at once and rises only after the surplus has held.
4. **The household.** A kettle, an oven, a washing machine, several at once, and a load larger than the roof's
   output. The house always takes what it asked for; the car gets what is left.
5. **The 6 A floor of IEC 61851-1.** The offer is never between nothing and six amps; it is always a whole number
   of amps; the floor has hysteresis so a passing cloud does not start a stop-and-start cycle.
6. **One phase or three.** Three phases cannot carry less than 3 × 6 A = 4140 W, and one phase tops out at 3680 W,
   so the switch up belongs at the three-phase floor and not at the one-phase ceiling. A switch costs a stop and a
   start and is held back by a wait and a cooldown.
7. **Fail-safe.** A meter reading older than the configured age is not a reading; an unplugged car is offered
   nothing; the night is not spent buying electricity.
8. **The two drivers.** The Modbus register map in its published units, its exceptions, and a 32-bit signed meter
   reading; the OCPP exchange, a profile the station may refuse, and a limit in the wrong unit.
9. **Driver equivalence.** A whole day replayed through the model, a Modbus wallbox and an OCPP station, compared
   decision by decision and by the energy that ended up in the car.
10. **Robustness.** Hypothesis over randomly generated readings and runs: the offer is always legal, a stale
    reading never charges, the offer never rises while the house is buying.
11. **The visual page.** Six views open, the language switch works, the chart is drawn from the real run,
    planting a bug in the live house turns the matching check red, the tour's seven moments play slowly
    enough to follow and do what their captions claim, and the wire view shows the frames the drivers
    really sent — including what a refusal looks like in each protocol.

## 3. What is out of scope

- Real hardware. There is no roof, no car and no wallbox; all three are modelled.
- A home battery. The house in this project has none, so the surplus is not shared with one. That is the single
  biggest simplification and it changes the control law; it is named here so nobody has to guess.
- Tariffs, spot prices and scheduled charging. The controller optimises for self-consumption only.
- OCPP sessions, authorisation and smart-charging profiles as a subject in their own right — those are tested in
  [ev-charging-testing](https://github.com/NailKarimov/ev-charging-testing). Here OCPP is only a way to carry a
  limit to a station.
- Performance and endurance. The suite proves behaviour, not throughput.

## 4. Approach

| Technique                      | Where                                                      | Why                                                                                                  |
| -------------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| Functional, over whole days    | `test_promises`                                            | A control law can look perfect for one tick and still buy a kilowatt-hour before lunch               |
| Specification-based            | `test_floor`, `test_phases`                                | IEC 61851-1 sets the floor and the duty-cycle relation; the wiring sets the three-phase floor        |
| Boundary values                | `test_arithmetic`, `test_phases`, `test_failsafe`          | 6 A exactly, 4140 W exactly, a reading exactly at the staleness limit and one second past it         |
| State transitions              | `test_clouds`, `test_floor`                                | Charging, riding out the floor, stopped, waiting to resume — the machine the day runs over           |
| Negative testing               | `test_drivers`                                             | A current the wallbox cannot give, a register that does not exist, a profile in the wrong unit       |
| Property-based (Hypothesis)    | `test_robustness`                                          | Invariants that must hold on days nobody wrote, including weather no roof will ever see              |
| Cross-implementation           | `test_drivers`, `site/test/twin.test.mjs`                  | Three wallboxes must agree; the page's twin must decide exactly like the Python original, and rebuild its frames byte for byte |
| Mutation testing               | `scripts/mutants.py`                                       | 38 planted bugs measure whether the suite would notice a real one                                    |

Each test carries one claim, written as the docstring sentence. Collection fails without it, so the report and the
visual page cannot drift from the code.

**What a budget is.** The promises are not "never". A controller that promised to buy nothing at all would have to
leave a margin so wide it gave most of the surplus away, and one that promised to spill nothing would buy
electricity every time a cloud crossed. Each day therefore has a budget, and the budgets are written in the test
file as plain numbers: at most 1.5 % of the car's energy bought, and a share of the roof's output spilled that
depends on how broken the weather is.

## 5. Test environment

| Item         | Value                                                                                                     |
| -------------- | ----------------------------------------------------------------------------------------------------------- |
| Runtime      | Python 3.12 on Linux; Node.js 24 for the twin; Chromium through Playwright for the page                   |
| Dependencies | pytest, pytest-timeout, Hypothesis, websockets, allure-pytest, ruff, mypy                                 |
| Drivers      | `DRIVER=direct` (default), `modbus` (a real TCP socket), `ocpp` (a real WebSocket)                        |
| Clock        | Simulated. The house advances one second at a time only when a test asks it to                            |
| CI           | GitHub Actions: lint, type check, three passes of the suite, page build, twin check, browser tests        |

The behaviour suites are marked `once` and run in the `direct` pass only: electricity does not care which cable
the number came down, and the claim that it does not is itself tested by the equivalence tests, which build all
three drivers inside that same pass.

## 6. Entry and exit criteria

**Entry.** The package installs, `ruff` and `mypy` are clean.

**Exit.** All three passes green and the 34 browser tests green; `build_pages.py --check` leaves no text
untranslated; the twin check reports no difference across all twenty days; the mutation check catches 38 of 38
with the control run passing; every finding recorded in the test report with its fix.

## 7. Risks

| Risk                                                                  | Handling                                                                                        |
| ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| A controller tested against its own model passes by agreeing with it | The promises are measured in energy the model moved, and the model is mutated too (M28–M30)     |
| Budgets tuned until the tests pass                                   | Budgets are round numbers with headroom, written per day, and the measured values are published |
| A test passes because it asserts what the code happens to do         | Mutation testing: 38 planted bugs must each turn some test red                                  |
| The visual page shows something other than the real controller       | The twin is compared decision by decision; a difference fails the build                         |
| A bug that two code paths can mask each other on                     | Found exactly that way once; see finding SS-4                                                   |
| Weather the author happened to think of                              | Eight days generated at random feed the twin check, and Hypothesis generates readings           |

## 8. Deliverables

Allure report, the six-view visual page, `docs/test-report.md`, `mutants-result.md`, and the evidence files
`evidence/run-<driver>.json`.
