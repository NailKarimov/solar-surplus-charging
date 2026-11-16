/* View 2: a house you can operate, with the real controller in it and the real checks watching.

   The checks are short versions of the tests in `tests/`. They run after every simulated second, so
   a bug planted here goes red in the same way a planted bug turns a test red in Python. */
(function () {
  'use strict';
  var App = window.App;
  var Twin = window.Twin;
  var h = App.h;
  var MIN_A = Twin.MIN_CHARGE_A;

  var scene, house, controller, timer;
  var active = false;
  var speed = 10;
  var sun = 1.0;
  var bug = null;
  var allowSwitching = true;
  var checks = {};

  var LOADS = [
    { id: 'kettle', w: 2200, en: 'Kettle', ru: 'Чайник' },
    { id: 'oven', w: 2400, en: 'Oven', ru: 'Духовка' },
    { id: 'heat pump', w: 1200, en: 'Heat pump', ru: 'Тепловой насос' },
    { id: 'everything', w: 5000, en: 'Everything at once', ru: 'Всё сразу' },
  ];

  /* Each check: a sentence, the situation it needs, and what would count as broken. */
  var CHECKS = [
    {
      id: 'zero',
      en: 'The house does not buy electricity for the car',
      ru: 'Дом не покупает электричество для машины',
      need_en: 'Charge for a while.',
      need_ru: 'Позаряжайте немного.',
    },
    {
      id: 'floor',
      en: 'The offer is never below the smallest a car can take',
      ru: 'Предложение никогда не ниже минимума машины',
      need_en: 'Charge for a while.',
      need_ru: 'Позаряжайте немного.',
    },
    {
      id: 'cap',
      en: 'The offer never exceeds what the wallbox is rated for',
      ru: 'Предложение не больше того, на что рассчитан вольтбокс',
      need_en: 'Charge in good sun.',
      need_ru: 'Позаряжайте на хорошем солнце.',
    },
    {
      id: 'spill',
      en: 'Sun the car could take is not given to the grid',
      ru: 'Солнце, которое машина могла взять, не уходит в сеть',
      need_en: 'Let the roof make a few kilowatt-hours.',
      need_ru: 'Дайте крыше выработать несколько киловатт-часов.',
    },
    {
      id: 'calm',
      en: 'The car is not jerked about',
      ru: 'Машину не дёргают',
      need_en: 'Let an hour or so pass.',
      need_ru: 'Дайте пройти примерно часу.',
    },
    {
      id: 'blind',
      en: 'A meter that has gone quiet stops the charging',
      ru: 'Замолчавший счётчик останавливает зарядку',
      need_en: 'Cut the meter while charging.',
      need_ru: 'Оборвите счётчик во время зарядки.',
    },
    {
      id: 'unplugged',
      en: 'Nothing is offered when no car is there',
      ru: 'Без машины ничего не предлагается',
      need_en: 'Unplug the car.',
      need_ru: 'Отключите машину.',
    },
  ];

  function resetChecks() {
    checks = {};
    CHECKS.forEach(function (check) {
      checks[check.id] = { seen: 0, failed: false, why: '' };
    });
  }

  function fail(id, why) {
    if (!checks[id].failed) {
      checks[id].failed = true;
      checks[id].why = App.clock(house.clock, true) + ' ' + why;
    }
  }

  /* Some checks are about an event that either happened or did not, and those stay red once they go
     red. The three promises are about a day's worth of energy, so they are a verdict on the day so
     far and can go green again as the day goes on. */
  function verdict(id, broken, why) {
    checks[id].failed = broken;
    checks[id].why = broken ? App.clock(house.clock, true) + ' ' + why : '';
  }

  function seen(id) {
    checks[id].seen += 1;
  }

  /* The watchdogs. These are the three promises, measured the same way the Python tests measure
     them: against the energy that actually moved, not against a feeling about it. */
  var changes = [];
  var pauses = [];
  var lastOffer = 0;
  var blindFor = 0;
  var worst = { changes: 0, pauses: 0 };

  function probe() {
    var t = house.totals;

    // 1. buying for the car: the first promise, as a share of what the car got
    if (t.car_wh > 2000) {
      seen('zero');
      verdict(
        'zero',
        t.bought_for_car_wh > 150 && t.bought_for_car_wh > 0.015 * t.car_wh,
        (function () {
          return App.t(
            App.wh(t.bought_for_car_wh) + ' bought for the car, ' + App.num((100 * t.bought_for_car_wh) / t.car_wh, 1) + ' % of what it got',
            'куплено для машины ' + App.wh(t.bought_for_car_wh) + ' — ' + App.num((100 * t.bought_for_car_wh) / t.car_wh, 1) + ' % от полученного'
          );
        })()
      );
    }

    // 2. sun the car could have taken: the second promise, as a share of what the roof made
    if (t.pv_wh > 6000) {
      seen('spill');
      verdict(
        'spill',
        t.spilled_wh > 0.2 * t.pv_wh,
        (function () {
          return App.t(
            App.kwh(t.spilled_wh) + ' of what the roof made went to the grid',
            App.kwh(t.spilled_wh) + ' из того, что дала крыша, ушло в сеть'
          );
        })()
      );
    }

    // 3. how often the car is disturbed: the third promise
    if (house.offered_a !== lastOffer) {
      changes.push(house.clock);
      if (house.offered_a === 0) pauses.push(house.clock);
      lastOffer = house.offered_a;
    }
    var anHourAgo = house.clock - 3600;
    changes = changes.filter(function (at) {
      return at > anHourAgo;
    });
    pauses = pauses.filter(function (at) {
      return at > anHourAgo;
    });
    if (house.clock > 9 * 3600) seen('calm');
    worst.changes = Math.max(worst.changes, changes.length);
    worst.pauses = Math.max(worst.pauses, pauses.length);
    // This one stays red once it goes red: the question is whether there was ever an hour in which
    // the car was pestered, not whether it is being pestered this minute.
    if (changes.length > 30 || pauses.length > 8) {
      fail(
        'calm',
        App.t(
          changes.length + ' changes and ' + pauses.length + ' stops in one hour',
          'за один час изменений: ' + changes.length + ', остановок: ' + pauses.length
        )
      );
    }

    // the floor and the ceiling
    if (house.offered_a > 0) {
      seen('floor');
      seen('cap');
      if (house.offered_a < MIN_A) {
        fail('floor', App.t('offered ' + house.offered_a + ' A, below the floor', 'предложено ' + house.offered_a + ' А — ниже минимума'));
      }
      if (house.offered_a > controller.settings.max_a) {
        fail('cap', App.t('offered ' + house.offered_a + ' A', 'предложено ' + house.offered_a + ' А'));
      }
    }

    // a quiet meter
    if (house.meter.silent) {
      seen('blind');
      blindFor += 1;
      if (blindFor > 120 && house.offered_a > 0) {
        fail('blind', App.t('still charging with no meter', 'зарядка идёт, а счётчика нет'));
      }
    } else {
      blindFor = 0;
    }

    // no car
    if (!house.car.plugged) {
      seen('unplugged');
      if (house.offered_a > 0) {
        fail('unplugged', App.t('offered current with no car', 'ток предложен, а машины нет'));
      }
    }
  }

  // ---- the world --------------------------------------------------------------------------------

  function restart() {
    var sky = new Twin.Sky({ peak_w: 6000 * sun });
    house = new Twin.House({
      inverter: new Twin.Inverter(5000, sky),
      household: new Twin.Household(300, []),
      car: new Twin.Car({}),
      meter: new Twin.Meter(5),
      clock: 8 * 3600,
    });
    controller = new Twin.Controller(new Twin.Settings({ allow_phase_switching: allowSwitching }), house.phases);
    if (bug) Twin.applyBug(controller, bug);
    changes = [];
    pauses = [];
    lastOffer = 0;
    blindFor = 0;
    worst = { changes: 0, pauses: 0 };
    resetChecks();
  }

  function tick(seconds) {
    var before = house.clock;
    Twin.tick(house, controller, seconds || 10);
    for (var n = 0; n < house.clock - before; n++) probe();
    if (house.clock >= 21 * 3600) restart();
  }

  // ---- drawing ------------------------------------------------------------------------------------

  function paintState() {
    scene.update(App.snapshotOf(house));
    var grid = house.gridW();
    var led = document.getElementById('live-led');
    var charging = house.car.drawing_a > 0;
    led.style.background = charging ? 'var(--ok)' : house.offered_a > 0 ? 'var(--solar)' : 'var(--idle)';
    document.getElementById('live-state').textContent = charging
      ? App.t('charging', 'идёт зарядка')
      : house.offered_a > 0
        ? App.t('offered, waiting for the car', 'предложено, ждём машину')
        : house.car.plugged
          ? App.t('plugged in, not charging', 'подключена, не заряжается')
          : App.t('no car', 'машины нет');
    document.getElementById('live-phases').textContent = house.phases === 1 ? App.t('one phase', 'одна фаза') : App.t('three phases', 'три фазы');
    document.getElementById('live-grid').textContent =
      Math.abs(grid) < 50
        ? App.t('at zero', 'на нуле')
        : App.watts(Math.abs(grid)) + ' ' + (grid > 0 ? App.t('bought', 'куплено') : App.t('sold', 'отдано'));
    document.getElementById('live-offer').textContent = house.offered_a ? App.amps(house.offered_a, house.phases) : App.t('nothing', 'ничего');
    document.getElementById('live-car').textContent = App.watts(house.carW());
    document.getElementById('live-bought').textContent = App.wh(house.totals.bought_for_car_wh);
    document.getElementById('live-spilled').textContent = App.kwh(house.totals.spilled_wh);
    document.getElementById('live-energy').textContent = App.kwh(house.totals.car_wh);
    var why = App.clear(document.getElementById('live-why'));
    why.appendChild(document.createTextNode(App.whyWords(controller._lastWhy || '')));
  }

  function paintChecks() {
    var box = App.clear(document.getElementById('live-checks'));
    CHECKS.forEach(function (check) {
      var state = checks[check.id];
      var cls = state.failed ? 'check fail' : state.seen > 30 ? 'check ok' : 'check';
      box.appendChild(
        h('div', { class: cls, 'data-check': check.id }, [
          h('span', { class: 'mark' }, state.failed ? '✗' : state.seen > 30 ? '✓' : '○'),
          h('div', null, [
            h('div', { class: 'ttl' }, App.t(check.en, check.ru)),
            h(
              'div',
              { class: 'small muted' },
              state.failed
                ? state.why
                : state.seen > 30
                  ? App.t('checked ' + App.num(state.seen) + ' times', 'проверено раз: ' + App.num(state.seen))
                  : App.t(check.need_en, check.need_ru)
            ),
          ]),
        ])
      );
    });
  }

  function paintControls() {
    document.getElementById('live-sun-label').textContent = Math.round(sun * 100) + ' %';
    var loads = App.clear(document.getElementById('live-loads'));
    LOADS.forEach(function (load) {
      var on = house.household.loads.some(function (l) {
        return l.name === load.id && l.at(house.clock) > 0;
      });
      loads.appendChild(
        h(
          'button',
          {
            type: 'button',
            class: 'chip',
            'aria-pressed': String(on),
            onclick: function () {
              toggleLoad(load);
            },
          },
          App.t(load.en, load.ru) + ' · ' + App.watts(load.w)
        )
      );
    });
    var speeds = App.clear(document.getElementById('live-speed'));
    [
      [0, App.t('pause', 'пауза')],
      [1, '×1'],
      [10, '×10'],
      [60, '×60'],
    ].forEach(function (row) {
      speeds.appendChild(
        h(
          'button',
          {
            type: 'button',
            class: 'chip',
            'aria-pressed': String(speed === row[0]),
            onclick: function () {
              speed = row[0];
              paintControls();
            },
          },
          row[1]
        )
      );
    });
    document.getElementById('live-plug').setAttribute('aria-pressed', String(house.car.plugged));
    document.getElementById('live-switching').setAttribute('aria-pressed', String(allowSwitching));
    document.getElementById('live-meter').setAttribute('aria-pressed', String(house.meter.silent));
  }

  function toggleLoad(load) {
    var running = house.household.loads.filter(function (l) {
      return l.name === load.id && l.at(house.clock) > 0;
    });
    if (running.length) {
      running.forEach(function (l) {
        l.seconds = Math.max(0, house.clock - l.start_s);
      });
    } else {
      house.household.loads.push(new Twin.Load(load.id, load.w, house.clock, 3600));
    }
    paintControls();
  }

  function bugList() {
    var box = App.clear(document.getElementById('live-bugs'));
    var known = window.MUTANT_DATA.mutants || [];
    known
      .filter(function (m) {
        return Twin.BUGS[m.id];
      })
      .forEach(function (m) {
        var id = 'bug-' + m.id;
        var on = bug === m.id;
        box.appendChild(
          h('div', { class: 'bug' + (on ? ' on' : '') }, [
            h('input', {
              type: 'checkbox',
              id: id,
              checked: on,
              onchange: function (event) {
                bug = event.target.checked ? m.id : null;
                restart();
                bugList();
                paintChecks();
                paintState();
              },
            }),
            h('label', { for: id }, [h('span', { class: 'id' }, m.id), ' ', App.mutantTitle(m)]),
          ])
        );
      });
  }

  function frame() {
    if (!active) return;
    if (speed) {
      var steps = speed <= 1 ? 1 : speed <= 10 ? 2 : 10;
      for (var n = 0; n < steps; n++) tick(speed <= 1 ? 1 : 10);
      paintState();
      paintChecks();
    }
    timer = window.requestAnimationFrame(frame);
  }

  App.views.live = {
    init: function () {
      scene = App.Scene(document.getElementById('live-scene'));
      restart();
      document.getElementById('live-sun').addEventListener('input', function (event) {
        sun = Number(event.target.value) / 100;
        house.inverter.sky.peak_w = 6000 * sun;
        paintControls();
      });
      document.getElementById('live-cloud').addEventListener('click', function () {
        house.inverter.sky.clouds.push(new Twin.Cloud(house.clock + 10, 240, 0.2, 20));
      });
      document.getElementById('live-long-cloud').addEventListener('click', function () {
        house.inverter.sky.clouds.push(new Twin.Cloud(house.clock + 10, 45 * 60, 0.1, 30));
      });
      document.getElementById('live-plug').addEventListener('click', function () {
        house.car.plugged = !house.car.plugged;
        if (!house.car.plugged) house.car.drawing_a = 0;
        paintControls();
      });
      document.getElementById('live-switching').addEventListener('click', function () {
        allowSwitching = !allowSwitching;
        controller.settings.allow_phase_switching = allowSwitching;
        paintControls();
      });
      document.getElementById('live-meter').addEventListener('click', function () {
        house.meter.silent = !house.meter.silent;
        paintControls();
      });
      document.getElementById('live-reset').addEventListener('click', function () {
        restart();
        paintControls();
        paintState();
        paintChecks();
      });
      bugList();
      paintControls();
      paintState();
      paintChecks();
      App.onLang(function () {
        bugList();
        paintControls();
        paintState();
        paintChecks();
      });
    },
    show: function () {
      active = true;
      timer = window.requestAnimationFrame(frame);
    },
    hide: function () {
      active = false;
      if (timer) window.cancelAnimationFrame(timer);
    },
    /* For the browser tests: drive the world without waiting for animation frames. */
    debug: {
      tick: function (seconds) {
        tick(seconds || 10);
      },
      probe: probe,
      plant: function (id) {
        bug = id;
        restart();
        bugList();
        paintChecks();
      },
      state: function () {
        return { house: house, controller: controller, checks: checks, worst: worst };
      },
      paint: function () {
        paintState();
        paintChecks();
      },
    },
  };
})();
