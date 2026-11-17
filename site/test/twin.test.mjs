/* Does the JavaScript house and controller behave exactly like the Python ones?

   `scripts/build_pages.py` plays a set of days through the real Python controller and writes down
   every reading it was given and every decision it made, including eight days generated at random
   so the twin is held to weather nobody wrote. This replays all of it through the twin and compares
   each tick. Any difference at all is a failure: the live page on the site is only honest while the
   thing it runs is the thing the tests test.

       node site/test/twin.test.mjs
*/
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const vectors = JSON.parse(readFileSync(join(here, 'vectors.json'), 'utf8'));

// The twin is written for a browser, so give it the one global it expects.
globalThis.window = globalThis;
await import(join(here, '..', 'js', 'twin.js'));
const Twin = globalThis.Twin;

const HOUR = 3600;

const DAYS = {
  clear: () => ({ clouds: [], loads: [], clock: 8 * HOUR }),
  'broken-cloud': () => ({
    clouds: Array.from({ length: 16 }, (_, n) => [9 * HOUR + n * 900, 300, n % 2 ? 0.25 : 0.45, 20]),
    loads: [],
    clock: 8 * HOUR,
  }),
  'one-long-cloud': () => ({ clouds: [[11 * HOUR, 50 * 60, 0.1, 20]], loads: [], clock: 8 * HOUR }),
  'kettle-and-oven': () => ({
    clouds: [],
    loads: [
      ['kettle', 2200.0, 9 * HOUR + 1200, 180],
      ['oven', 2400.0, 11 * HOUR, 45 * 60],
      ['washing machine', 2000.0, 13 * HOUR, 30 * 60],
      ['kettle', 2200.0, 14 * HOUR, 180],
    ],
    clock: 8 * HOUR,
  }),
  dull: () => ({ clouds: [], loads: [], clock: 8 * HOUR, haze: 0.22 }),
  'almost-full-car': () => ({ clouds: [], loads: [], clock: 8 * HOUR, charged_wh: 54000.0 }),
  'whole-day': () => ({
    clouds: [
      [10 * HOUR, 600, 0.3, 20],
      [12 * HOUR + 1800, 1200, 0.2, 20],
      [15 * HOUR, 400, 0.5, 20],
    ],
    loads: [
      ['kettle', 2200.0, 8 * HOUR, 200],
      ['oven', 2400.0, 12 * HOUR, 40 * 60],
      ['heat pump', 1200.0, 16 * HOUR, 90 * 60],
    ],
    clock: 7 * HOUR,
  }),
};

function buildHouse(script) {
  const base = DAYS[script.day]();
  const sky = new Twin.Sky({ peak_w: script.peak_w === undefined ? 6000.0 : script.peak_w, haze: base.haze });
  for (const [start, seconds, factor, edge] of base.clouds) sky.clouds.push(new Twin.Cloud(start, seconds, factor, edge));
  for (const [start, seconds, factor, edge] of script.clouds || []) {
    sky.clouds.push(new Twin.Cloud(start, seconds, factor, edge));
  }
  const household = new Twin.Household(300.0, base.loads.map(([n, w, s, d]) => new Twin.Load(n, w, s, d)));
  for (const [start, seconds, watts] of script.loads || []) {
    household.loads.push(new Twin.Load('something', watts, start, seconds));
  }
  const house = new Twin.House({
    inverter: new Twin.Inverter(5000.0, sky),
    household,
    car: new Twin.Car({ charged_wh: base.charged_wh }),
    meter: new Twin.Meter(5),
    clock: base.clock,
    phases: script.phases === undefined ? 3 : script.phases,
  });
  const controller = new Twin.Controller(new Twin.Settings(script.settings || {}), house.phases);
  return { house, controller };
}

let compared = 0;
let failures = 0;

for (const vector of vectors) {
  const { house, controller } = buildHouse(vector.script);
  const driver = {
    read: () => ({
      clock: house.clock,
      grid_w: house.meter.reading_w,
      grid_age_s: house.meter.reading_age_s,
      car_w: house.carW(),
      phases: house.phases,
      plugged: house.car.plugged,
    }),
  };
  for (const [clock, gridW, age, carW, amps, phases, why] of vector.ticks) {
    if (vector.script.silent_from && house.clock >= vector.script.silent_from) house.meter.silent = true;
    const reading = driver.read();
    const mine = [
      reading.clock,
      Number(reading.grid_w.toFixed(6)),
      reading.grid_age_s,
      Number(reading.car_w.toFixed(6)),
    ];
    const theirs = [clock, gridW, age, carW];
    for (let i = 0; i < 4; i++) {
      if (mine[i] !== theirs[i]) {
        failures += 1;
        if (failures < 6) {
          console.error(
            `${vector.name} at ${clock}s: reading differs — javascript ${JSON.stringify(mine)}, python ${JSON.stringify(theirs)}`
          );
        }
        break;
      }
    }
    const command = controller.decide(reading);
    if (command.amps !== amps || command.phases !== phases || command.why !== why) {
      failures += 1;
      if (failures < 6) {
        console.error(
          `${vector.name} at ${clock}s: decision differs — javascript ${command.amps} A x${command.phases} "${command.why}", python ${amps} A x${phases} "${why}"`
        );
      }
    }
    house.offer(command.amps, command.phases);
    house.advance(10);
    compared += 1;
  }
  const mineTotals = {
    car: Number(house.totals.car_wh.toFixed(6)),
    bought: Number(house.totals.bought_for_car_wh.toFixed(6)),
    spilled: Number(house.totals.spilled_wh.toFixed(6)),
  };
  for (const key of ['car', 'bought', 'spilled']) {
    if (Math.abs(mineTotals[key] - vector.totals[key]) > 1e-6) {
      failures += 1;
      console.error(`${vector.name}: ${key} differs — javascript ${mineTotals[key]}, python ${vector.totals[key]}`);
    }
  }
}

// ---- and the two encoders, against frames that really went down a socket -------------------------

await import(join(here, '..', 'js', 'encode.js'));
await import(join(here, '..', 'data', 'wire.js'));
const Wire = globalThis.Wire;
const recorded = globalThis.WIRE_DATA;
let frames = 0;

function amps(hex) {
  return parseInt(hex.slice(26, 30), 16) / 10;
}
function phasesOf(hex) {
  return parseInt(hex.slice(30, 34), 16);
}

for (const moment of recorded.moments) {
  const real = moment.modbus.write.ask.hex;
  const transaction = parseInt(real.slice(0, 4), 16);
  const unit = parseInt(real.slice(12, 14), 16);
  const mine = Wire.modbusWrite(amps(real), phasesOf(real), transaction, unit);
  if (mine !== real) {
    failures += 1;
    console.error(`wire ${moment.id}: modbus frame differs — javascript ${mine}, python ${real}`);
  }
  frames += 1;

  const call = moment.ocpp.find((line) => line.dir === '->');
  const theirs = JSON.parse(call.text);
  const ours = Wire.ocppProfile(amps(real), phasesOf(real), theirs[1]);
  if (JSON.stringify(ours) !== JSON.stringify(theirs)) {
    failures += 1;
    console.error(
      `wire ${moment.id}: ocpp message differs — javascript ${JSON.stringify(ours)}, python ${JSON.stringify(theirs)}`
    );
  }
  frames += 1;
}

if (failures) {
  console.error(`twin: ${failures} differences across ${compared} turns of the loop in ${vectors.length} days`);
  process.exit(1);
}
console.log(`twin: ${compared} turns of the loop in ${vectors.length} days, all identical to the Python controller`);
console.log(`wire: ${frames} frames rebuilt in JavaScript, all identical to the ones Python sent`);
