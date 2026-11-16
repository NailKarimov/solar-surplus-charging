/* The same house and the same controller, written again in JavaScript so the page can run them live.

   This is a twin, not an illustration. Every number below is the same arithmetic in the same order
   as `src/surplus_lab/house.py` and `src/surplus_lab/control.py`, and `site/test/twin.test.mjs`
   replays scripted days through both and compares every single decision. If the two ever disagree,
   the build fails and the page does not ship: a picture that is not the system under test is worse
   than no picture, because it is convincing. */
(function () {
  'use strict';

  var NOMINAL_V = 230.0;
  var MIN_CHARGE_A = 6.0;

  function clamp(value, low, high) {
    return Math.max(low, Math.min(high, value));
  }

  // ---- the sun ------------------------------------------------------------------------------------

  function Cloud(startS, seconds, factor, edgeS) {
    this.start_s = startS;
    this.seconds = seconds;
    this.factor = factor;
    this.edge_s = edgeS === undefined ? 20 : edgeS;
  }
  Cloud.prototype.at = function (clock) {
    if (clock <= this.start_s || clock >= this.start_s + this.seconds) return 1.0;
    var into = clock - this.start_s;
    var left = this.start_s + this.seconds - clock;
    var edge = Math.max(1, this.edge_s);
    var ramp = Math.min(1.0, into / edge, left / edge);
    return 1.0 - (1.0 - this.factor) * ramp;
  };

  function Sky(options) {
    options = options || {};
    this.peak_w = options.peak_w === undefined ? 6000.0 : options.peak_w;
    this.sunrise_s = options.sunrise_s === undefined ? 6 * 3600 : options.sunrise_s;
    this.sunset_s = options.sunset_s === undefined ? 21 * 3600 : options.sunset_s;
    this.clouds = options.clouds || [];
    this.haze = options.haze === undefined ? 1.0 : options.haze;
  }
  Sky.prototype.clearSkyW = function (clock) {
    if (clock <= this.sunrise_s || clock >= this.sunset_s) return 0.0;
    var day = (clock - this.sunrise_s) / (this.sunset_s - this.sunrise_s);
    return this.peak_w * Math.sin(Math.PI * day) * this.haze;
  };
  Sky.prototype.cloudFactor = function (clock) {
    var factor = 1.0;
    for (var i = 0; i < this.clouds.length; i++) factor = Math.min(factor, this.clouds[i].at(clock));
    return factor;
  };
  Sky.prototype.powerW = function (clock) {
    return this.clearSkyW(clock) * this.cloudFactor(clock);
  };

  function Inverter(ratedW, sky) {
    this.rated_w = ratedW === undefined ? 5000.0 : ratedW;
    this.sky = sky || new Sky();
  }
  Inverter.prototype.powerW = function (clock) {
    return Math.min(this.rated_w, this.sky.powerW(clock));
  };

  // ---- the household -------------------------------------------------------------------------------

  function Load(name, watts, startS, seconds) {
    this.name = name;
    this.watts = watts;
    this.start_s = startS;
    this.seconds = seconds;
  }
  Load.prototype.at = function (clock) {
    return this.start_s <= clock && clock < this.start_s + this.seconds ? this.watts : 0.0;
  };

  function Household(baselineW, loads) {
    this.baseline_w = baselineW === undefined ? 300.0 : baselineW;
    this.loads = loads || [];
  }
  Household.prototype.powerW = function (clock) {
    var total = this.baseline_w;
    for (var i = 0; i < this.loads.length; i++) total += this.loads[i].at(clock);
    return total;
  };
  Household.prototype.running = function (clock) {
    var names = [];
    for (var i = 0; i < this.loads.length; i++) if (this.loads[i].at(clock) > 0) names.push(this.loads[i].name);
    return names;
  };

  // ---- the car ---------------------------------------------------------------------------------------

  function Car(options) {
    options = options || {};
    this.battery_wh = options.battery_wh === undefined ? 60000.0 : options.battery_wh;
    this.charged_wh = options.charged_wh === undefined ? 18000.0 : options.charged_wh;
    this.max_a = options.max_a === undefined ? 16.0 : options.max_a;
    this.ramp_a_per_s = options.ramp_a_per_s === undefined ? 2.0 : options.ramp_a_per_s;
    this.taper_from = options.taper_from === undefined ? 0.85 : options.taper_from;
    this.plugged = options.plugged === undefined ? true : options.plugged;
    this.drawing_a = 0.0;
  }
  Car.prototype.soc = function () {
    return clamp(this.charged_wh / this.battery_wh, 0.0, 1.0);
  };
  Car.prototype.wantedA = function (offeredA) {
    if (!this.plugged || offeredA < MIN_CHARGE_A) return 0.0;
    var ceiling = Math.min(offeredA, this.max_a);
    var soc = this.soc();
    if (soc >= 1.0) return 0.0;
    if (soc > this.taper_from) {
      var left = (1.0 - soc) / (1.0 - this.taper_from);
      ceiling = Math.min(ceiling, Math.max(MIN_CHARGE_A, this.max_a * left));
    }
    return ceiling;
  };
  Car.prototype.step = function (offeredA, phases, seconds) {
    var target = this.wantedA(offeredA);
    var stepA = this.ramp_a_per_s * seconds;
    if (target <= 0.0) {
      this.drawing_a = Math.max(0.0, this.drawing_a - stepA);
      if (this.drawing_a < MIN_CHARGE_A) this.drawing_a = 0.0;
    } else if (this.drawing_a < MIN_CHARGE_A) {
      this.drawing_a = Math.min(target, MIN_CHARGE_A);
    } else if (target > this.drawing_a) {
      this.drawing_a = Math.min(target, this.drawing_a + stepA);
    } else {
      this.drawing_a = Math.max(target, this.drawing_a - stepA);
    }
    var wattHours = (this.powerW(phases) * seconds) / 3600.0;
    this.charged_wh = Math.min(this.battery_wh, this.charged_wh + wattHours);
    return wattHours;
  };
  Car.prototype.powerW = function (phases) {
    return this.drawing_a * phases * NOMINAL_V;
  };

  // ---- the meter ---------------------------------------------------------------------------------------

  function Meter(periodS) {
    this.period_s = periodS === undefined ? 5 : periodS;
    this.noise_w = 0.0;
    this.silent = false;
    this.reading_w = 0.0;
    this.reading_age_s = 0;
    this._sum_w = 0.0;
    this._sum_s = 0;
  }
  Meter.prototype.observe = function (gridW, seconds) {
    this._sum_w += gridW * seconds;
    this._sum_s += seconds;
    this.reading_age_s += seconds;
    if (this._sum_s >= this.period_s) {
      if (!this.silent) {
        this.reading_w = this._sum_w / this._sum_s + this.noise_w;
        this.reading_age_s = 0;
      }
      this._sum_w = 0.0;
      this._sum_s = 0;
    }
  };

  // ---- the whole place -----------------------------------------------------------------------------------

  function Totals() {
    this.imported_wh = 0.0;
    this.exported_wh = 0.0;
    this.car_wh = 0.0;
    this.car_from_sun_wh = 0.0;
    this.pv_wh = 0.0;
    this.house_wh = 0.0;
    this.bought_for_car_wh = 0.0;
    this.spilled_wh = 0.0;
  }

  function House(options) {
    options = options || {};
    this.inverter = options.inverter || new Inverter();
    this.household = options.household || new Household();
    this.car = options.car || new Car();
    this.meter = options.meter || new Meter();
    this.clock = options.clock === undefined ? 8 * 3600 : options.clock;
    this.phases = options.phases === undefined ? 3 : options.phases;
    this.offered_a = 0.0;
    this.totals = new Totals();
  }
  House.prototype.pvW = function () {
    return this.inverter.powerW(this.clock);
  };
  House.prototype.houseW = function () {
    return this.household.powerW(this.clock);
  };
  House.prototype.carW = function () {
    return this.car.powerW(this.phases);
  };
  House.prototype.gridW = function () {
    return this.houseW() + this.carW() - this.pvW();
  };
  House.prototype.usableExportW = function (exportW) {
    var car = this.car;
    var ceilingA = car.wantedA(car.max_a);
    if (ceilingA <= 0.0) return 0.0;
    var oneAmpW = this.phases * NOMINAL_V;
    if (car.drawing_a > 0) {
      var headroomA = Math.max(0.0, ceilingA - car.drawing_a);
      var usable = Math.min(exportW, headroomA * oneAmpW);
      return usable >= oneAmpW ? usable : 0.0;
    }
    return exportW >= MIN_CHARGE_A * NOMINAL_V ? exportW : 0.0;
  };
  House.prototype.offer = function (amps, phases) {
    if (phases !== undefined && phases !== null) this.phases = phases;
    this.offered_a = amps < MIN_CHARGE_A ? 0.0 : amps;
  };
  House.prototype.advance = function (seconds) {
    for (var n = 0; n < seconds; n++) {
      var pv = this.pvW();
      var house = this.houseW();
      var carWh = this.car.step(this.offered_a, this.phases, 1);
      var grid = this.gridW();
      this.meter.observe(grid, 1);
      var hours = 1 / 3600.0;
      this.totals.pv_wh += pv * hours;
      this.totals.house_wh += house * hours;
      this.totals.car_wh += carWh;
      if (grid > 0) {
        this.totals.imported_wh += grid * hours;
        this.totals.bought_for_car_wh += Math.min(grid, this.carW()) * hours;
      } else {
        var exported = -grid;
        this.totals.exported_wh += exported * hours;
        this.totals.spilled_wh += this.usableExportW(exported) * hours;
      }
      var sunLeft = Math.max(0.0, pv - house);
      this.totals.car_from_sun_wh += Math.min(carWh, sunLeft * hours);
      this.clock += 1;
    }
  };

  // ---- the controller --------------------------------------------------------------------------------------

  function Settings(options) {
    options = options || {};
    var d = {
      margin_w: 0.0,
      max_a: 16.0,
      rise_delay_s: 120,
      fall_delay_s: 0,
      pause_delay_s: 180,
      ride_out_budget_wh: 60.0,
      resume_delay_s: 300,
      min_dwell_s: 60,
      phase_switch_delay_s: 600,
      phase_switch_cooldown_s: 1800,
      phase_switch_margin_w: 500.0,
      stale_after_s: 60,
      allow_phase_switching: true,
    };
    for (var key in d) this[key] = options[key] === undefined ? d[key] : options[key];
  }

  function Controller(settings, phases) {
    this.settings = settings || new Settings();
    this.offered_a = 0.0;
    this.phases = phases === undefined ? 3 : phases;
    this.last_raise_s = null;
    this.last_phase_switch_s = null;
    this._want = null;
    this._phase_wish = null;
    this._below_floor_since = null;
    this._above_floor_since = null;
    this._ride_out_wh = 0.0;
    this._last_clock = null;
  }
  Controller.prototype.availableW = function (reading) {
    return reading.car_w - reading.grid_w + this.settings.margin_w;
  };
  Controller.prototype.availableA = function (reading, phases) {
    var amps = this.availableW(reading) / (phases * NOMINAL_V);
    return Math.trunc(clamp(amps, 0.0, this.settings.max_a));
  };
  Controller.prototype._wantedSince = function (value, now) {
    if (this._want === null || this._want[0] !== value) this._want = [value, now];
    return this._want[1];
  };
  Controller.prototype._phaseWishedSince = function (wish, now) {
    if (this._phase_wish === null || this._phase_wish[0] !== wish) this._phase_wish = [wish, now];
    return this._phase_wish[1];
  };
  Controller.prototype._set = function (amps, phases, why, now) {
    if (phases !== this.phases) this.phases = phases;
    if (amps > this.offered_a && amps > 0) this.last_raise_s = now;
    this.offered_a = amps;
    return { amps: amps, phases: phases, why: why, charging: amps >= MIN_CHARGE_A };
  };
  Controller.prototype._hold = function () {
    return { amps: this.offered_a, phases: this.phases, why: 'no change', charging: this.offered_a >= MIN_CHARGE_A };
  };
  Controller.prototype._phasesWanted = function (reading, now) {
    var s = this.settings;
    if (!s.allow_phase_switching) return this.phases;
    if (this.last_phase_switch_s !== null && now - this.last_phase_switch_s < s.phase_switch_cooldown_s) {
      return this.phases;
    }
    var watts = this.availableW(reading);
    var threePhaseFloor = 3 * MIN_CHARGE_A * NOMINAL_V;
    var wish = this.phases;
    if (this.phases === 3 && watts < threePhaseFloor) wish = 1;
    else if (this.phases === 1 && watts > threePhaseFloor + s.phase_switch_margin_w) wish = 3;
    if (wish === this.phases) {
      this._phase_wish = null;
      return this.phases;
    }
    if (now - this._phaseWishedSince(wish, now) >= s.phase_switch_delay_s) {
      this.last_phase_switch_s = now;
      this._phase_wish = null;
      return wish;
    }
    return this.phases;
  };
  Controller.prototype.decide = function (reading) {
    var s = this.settings;
    var now = reading.clock;
    var sinceLast = this._last_clock === null ? 0 : Math.max(0, now - this._last_clock);
    this._last_clock = now;

    if (reading.grid_age_s > s.stale_after_s) return this._set(0.0, this.phases, 'the meter has gone quiet', now);
    if (!reading.plugged) return this._set(0.0, this.phases, 'no car on the cable', now);

    var wanted = this.availableA(reading, this.phases);
    var phases = this._phasesWanted(reading, now);
    if (phases !== this.phases) {
      wanted = this.availableA(reading, phases);
      return this._set(Math.max(wanted, MIN_CHARGE_A), phases, 'switching to ' + phases + ' phase(s)', now);
    }

    if (wanted < MIN_CHARGE_A) {
      this._above_floor_since = null;
      if (this._below_floor_since === null) {
        this._below_floor_since = now;
        this._ride_out_wh = 0.0;
      }
      if (this.offered_a === 0.0) {
        return this._set(0.0, this.phases, 'not enough sun for the smallest charge', now);
      }
      this._ride_out_wh += (Math.max(0.0, reading.grid_w) * sinceLast) / 3600.0;
      if (now - this._below_floor_since >= s.pause_delay_s) {
        return this._set(0.0, this.phases, 'the sun has been short for too long', now);
      }
      if (this._ride_out_wh >= s.ride_out_budget_wh) {
        return this._set(0.0, this.phases, 'riding out the shadow has cost enough', now);
      }
      return this._set(MIN_CHARGE_A, this.phases, 'riding out a short shortage at 6 A', now);
    }

    this._below_floor_since = null;
    this._ride_out_wh = 0.0;
    if (this.offered_a === 0.0) {
      if (this._above_floor_since === null) this._above_floor_since = now;
      if (now - this._above_floor_since < s.resume_delay_s) {
        return this._set(0.0, this.phases, 'waiting to be sure the sun is back', now);
      }
      return this._set(wanted, this.phases, 'the sun is back for good', now);
    }

    if (wanted < this.offered_a) {
      if (now - this._wantedSince(wanted, now) >= s.fall_delay_s) {
        return this._set(wanted, this.phases, 'less sun, giving the car less at once', now);
      }
      return this._hold();
    }

    if (wanted > this.offered_a) {
      if (this.last_raise_s !== null && now - this.last_raise_s < s.min_dwell_s) return this._hold();
      if (now - this._wantedSince(wanted, now) >= s.rise_delay_s) {
        this.last_raise_s = now;
        return this._set(wanted, this.phases, 'the surplus has held, giving the car more', now);
      }
      return this._hold();
    }

    this._wantedSince(wanted, now);
    return this._hold();
  };

  // ---- one loop, and the planted bugs ------------------------------------------------------------------

  /* The bugs the live page can plant, written here exactly as scripts/mutants.py writes them in
     Python. Switching one on in the browser does to this twin what the mutation check does to the
     real controller.

     Not all thirty-seven are here. A bug belongs on this page only if one of the live checks can
     actually show it to a visitor; the ones about timing are real defects, and the Python suite
     catches every one of them, but on a single day in a browser they are not visibly different from
     a controller doing its job. The whole set is in the bug hunt. */
  var BUGS = {
    M01: function (c) {
      c.availableW = function (r) {
        return r.car_w + r.grid_w + this.settings.margin_w;
      };
    },
    M03: function (c) {
      c.availableA = function (r, p) {
        return Math.round(clamp(this.availableW(r) / (p * NOMINAL_V), 0.0, this.settings.max_a));
      };
    },
    M07: function (c) {
      c.settings.fall_delay_s = c.settings.rise_delay_s;
    },
    M12: function (c) {
      c.availableA = function (r, p) {
        var amps = this.availableW(r) / (p * NOMINAL_V);
        var whole = Math.trunc(clamp(amps, 0.0, this.settings.max_a));
        return whole > 0 && whole < MIN_CHARGE_A ? whole : whole;
      };
      c._floorOff = true;
    },
    M14: function (c) {
      c.settings.ride_out_budget_wh = 1e9;
    },
    M25: function (c) {
      c.settings.stale_after_s = 1e9;
    },
    M26: function (c) {
      c._ignorePlugged = true;
    },
  };

  function applyBug(controller, id) {
    var bug = BUGS[id];
    if (bug) bug(controller);
    return controller;
  }

  /* The twin's own version of `day.run`: one turn of the loop. */
  function tick(house, controller, tickS) {
    var reading = {
      clock: house.clock,
      grid_w: house.meter.reading_w,
      grid_age_s: house.meter.reading_age_s,
      car_w: house.carW(),
      phases: house.phases,
      plugged: controller._ignorePlugged ? true : house.car.plugged,
    };
    var command = controller.decide(reading);
    controller._lastWhy = command.why;
    if (controller._floorOff) {
      var raw = Math.trunc(clamp(controller.availableW(reading) / (house.phases * NOMINAL_V), 0, controller.settings.max_a));
      house.offered_a = raw;
      house.phases = command.phases;
    } else {
      house.offer(command.amps, command.phases);
    }
    house.advance(tickS);
    return { reading: reading, command: command };
  }

  window.Twin = {
    NOMINAL_V: NOMINAL_V,
    MIN_CHARGE_A: MIN_CHARGE_A,
    Cloud: Cloud,
    Sky: Sky,
    Inverter: Inverter,
    Load: Load,
    Household: Household,
    Car: Car,
    Meter: Meter,
    House: House,
    Settings: Settings,
    Controller: Controller,
    tick: tick,
    applyBug: applyBug,
    BUGS: BUGS,
  };
})();
