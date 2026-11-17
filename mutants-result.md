# Mutation check

**38/38 planted bugs caught.** Control runs without a planted bug: passed.

| Id | File | Planted bug | Run | Result | Tests that failed |
| --- | --- | --- | --- | --- | --- |
| M01 | `src/surplus_lab/control.py` | The meter's sign is read the wrong way round, so buying looks like selling | direct | caught | 29 |
| M02 | `src/surplus_lab/control.py` | What the car is already taking is forgotten, so the offer collapses to the spare surplus | direct | caught | 18 |
| M03 | `src/surplus_lab/control.py` | Amps are rounded to the nearest whole one instead of down, so half the time the car buys | direct | caught | 10 |
| M04 | `src/surplus_lab/control.py` | The three phases are forgotten, so the car is offered three times what there is | direct | caught | 11 |
| M05 | `src/surplus_lab/control.py` | The wallbox's rating is ignored and the car is offered more than the cable can carry | direct | caught | 3 |
| M06 | `src/surplus_lab/control.py` | The margin the installation asked for is ignored | direct | caught | 1 |
| M07 | `src/surplus_lab/control.py` | The offer comes down as slowly as it goes up, so every cloud is bought through | direct | caught | 3 |
| M08 | `src/surplus_lab/control.py` | The offer goes up the instant the sun does, so the car is changed at every flicker | direct | caught | 2 |
| M09 | `src/surplus_lab/control.py` | The quiet time between raises is dropped, so the offer can climb every few seconds | direct | caught | 1 |
| M10 | `src/surplus_lab/control.py` | A value only has to be wanted once, not held, before it is acted on | direct | caught | 2 |
| M11 | `src/surplus_lab/control.py` | The wait is not restarted when the wanted value changes, so an old wait counts for a new value | direct | caught | 2 |
| M12 | `src/surplus_lab/control.py` | The pilot's floor is ignored and the car is offered three or four amps | direct | caught | 8 |
| M13 | `src/surplus_lab/control.py` | A shortage is ridden out for ever, so a long cloud is charged through on the grid | direct | caught | 1 |
| M14 | `src/surplus_lab/control.py` | Riding out a shadow is bounded only by the clock, so a day of cloud buys kilowatt-hours | direct | caught | 3 |
| M15 | `src/surplus_lab/control.py` | What riding out a shadow has cost is never counted, so the budget never runs out | direct | caught | 3 |
| M16 | `src/surplus_lab/control.py` | Every passing shadow stops the session instead of holding the floor | direct | caught | 3 |
| M17 | `src/surplus_lab/control.py` | Charging restarts the moment the sun peeps out, so the car is switched again and again | direct | caught | 2 |
| M18 | `src/surplus_lab/control.py` | The clock on a shortage is never reset, so the second cloud of the day stops the session at once | direct | caught | 3 |
| M19 | `src/surplus_lab/control.py` | Three phases are asked for as soon as one is full, where three cannot charge at all | direct | caught | 2 |
| M20 | `src/surplus_lab/control.py` | One phase is never asked for, so a modest surplus charges nothing | direct | caught | 11 |
| M21 | `src/surplus_lab/control.py` | The cooldown after a switch is gone, so the house is rewired back and forth | direct | caught | 1 |
| M22 | `src/surplus_lab/control.py` | The house is rewired on the first reading that suggests it, not on a settled one | direct | caught | 2 |
| M23 | `src/surplus_lab/control.py` | The first offer after a switch is still worked out for the old wiring | direct | caught | 1 |
| M24 | `src/surplus_lab/control.py` | A house with no switching hardware is rewired anyway | direct | caught | 7 |
| M25 | `src/surplus_lab/control.py` | A meter that stopped reporting is trusted, so the car charges blind off the grid | direct | caught | 2 |
| M26 | `src/surplus_lab/control.py` | An unplugged car is still offered current | direct | caught | 2 |
| M27 | `src/surplus_lab/control.py` | A quiet meter makes the controller charge at the floor instead of stopping | direct | caught | 4 |
| M28 | `src/surplus_lab/house.py` | The meter at the door does not see the car, so nothing it does shows up | direct | caught | 6 |
| M29 | `src/surplus_lab/house.py` | An offer of nothing becomes an offer of six amps, so a pause charges the car anyway | direct | caught | 20 |
| M30 | `src/surplus_lab/house.py` | A silent meter keeps publishing, so a failure cannot be noticed at all | direct | caught | 2 |
| M31 | `src/surplus_lab/drivers/modbus.py` | The wallbox register is read as amps when it is tenths of an amp | direct | caught | 4 |
| M32 | `src/surplus_lab/drivers/modbus.py` | The wallbox accepts any current at all, including ones no pilot can carry | direct | caught | 1 |
| M33 | `src/surplus_lab/drivers/modbus.py` | A negative meter reading is read as a huge positive one, so selling looks like buying | direct | caught | 5 |
| M34 | `src/surplus_lab/drivers/modbus.py` | An answer is accepted whatever question it belongs to | direct | caught | 1 |
| M35 | `src/surplus_lab/drivers/ocpp.py` | The station accepts every profile, even one it cannot honour | direct | caught | 1 |
| M36 | `src/surplus_lab/drivers/ocpp.py` | A limit in watts is treated as a limit in amps | direct | caught | 1 |
| M37 | `src/surplus_lab/drivers/ocpp.py` | A pause is sent to the station as a six amp limit, so the car charges through it | direct | caught | 1 |
| M38 | `src/surplus_lab/drivers/ocpp.py` | Every phase of a three-phase session is reported as L1, so three phases read as one | direct | caught | 1 |
