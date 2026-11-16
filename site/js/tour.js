/* View 1: the project in two minutes. A day plays itself, and the three promises are priced. */
(function () {
  'use strict';
  var App = window.App;
  var Twin = window.Twin;
  var h = App.h;
  var SPEC = App.SPEC;
  var scene, timer, active = false;
  var house, controller, clockAt;
  var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function dayNamed(id) {
    return window.DAY_DATA.days.filter(function (d) {
      return d.id === id;
    })[0];
  }

  function restart() {
    var sky = new Twin.Sky({
      peak_w: 6000,
      clouds: [
        new Twin.Cloud(10 * 3600, 600, 0.3),
        new Twin.Cloud(12 * 3600 + 1800, 1200, 0.2),
        new Twin.Cloud(15 * 3600, 400, 0.5),
      ],
    });
    house = new Twin.House({
      inverter: new Twin.Inverter(5000, sky),
      household: new Twin.Household(300, [
        new Twin.Load('kettle', 2200, 8 * 3600, 200),
        new Twin.Load('oven', 2400, 12 * 3600, 40 * 60),
        new Twin.Load('heat pump', 1200, 16 * 3600, 90 * 60),
      ]),
      car: new Twin.Car({}),
      meter: new Twin.Meter(5),
      clock: 7 * 3600,
    });
    controller = new Twin.Controller(new Twin.Settings({}), house.phases);
    clockAt = house.clock;
  }

  function paint() {
    scene.update(App.snapshotOf(house));
    var line = document.getElementById('tour-now');
    App.clear(line);
    var grid = house.gridW();
    line.appendChild(
      App.both(
        App.clock(house.clock) +
          ' · the roof ' +
          App.watts(house.pvW()) +
          ' · the house ' +
          App.watts(house.houseW()) +
          ' · the car ' +
          App.watts(house.carW()) +
          ' · the meter ' +
          (Math.abs(grid) < 50 ? 'at zero' : App.watts(Math.abs(grid)) + (grid > 0 ? ' bought' : ' sold')),
        App.clock(house.clock) +
          ' · крыша ' +
          App.watts(house.pvW()) +
          ' · дом ' +
          App.watts(house.houseW()) +
          ' · машина ' +
          App.watts(house.carW()) +
          ' · счётчик ' +
          (Math.abs(grid) < 50 ? 'на нуле' : App.watts(Math.abs(grid)) + (grid > 0 ? ' куплено' : ' отдано'))
      )
    );
  }

  function frame() {
    if (!active) return;
    for (var n = 0; n < 12; n++) {
      Twin.tick(house, controller, 10);
      if (house.clock >= 21 * 3600) {
        restart();
        break;
      }
    }
    paint();
    timer = window.requestAnimationFrame(frame);
  }

  function promise(no, en, ru, costEn, costRu, value) {
    return h('div', { class: 'promise' }, [
      h('div', { class: 'no' }, no),
      h('h3', null, App.both(en, ru)),
      h('div', { class: 'cost' }, value),
      h('div', { class: 'small muted' }, App.both(costEn, costRu)),
    ]);
  }

  function promises() {
    var box = App.clear(document.getElementById('tour-promises'));
    var day = dayNamed('whole-day');
    var t = day.totals;
    var hours = (day.points[day.points.length - 1].t - day.points[0].t) / 3600;
    box.appendChild(
      promise(
        '1',
        'Buy nothing',
        'Ничего не покупать',
        'bought from the grid for the car on a whole ordinary day, against ' + App.kwh(t.car) + ' put into it',
        'куплено из сети для машины за целый обычный день — при ' + App.kwh(t.car) + ', которые в неё вошли',
        App.watts(t.bought)
      )
    );
    box.appendChild(
      promise(
        '2',
        'Sell nothing the car could take',
        'Не отдавать то, что машина могла взять',
        'of what the roof made went to the grid while the car had room for it',
        'из того, что дала крыша, ушло в сеть, хотя у машины было место',
        App.num((100 * t.spilled) / Math.max(1, t.pv), 1) + ' %'
      )
    );
    box.appendChild(
      promise(
        '3',
        'Leave the car alone',
        'Не дёргать машину',
        'changes to the offer in ' +
          Math.round(hours) +
          ' hours, and the session was stopped ' +
          day.counts.pauses +
          ' times',
        'изменений предложения за ' + Math.round(hours) + ' ч; сессия останавливалась ' + day.counts.pauses + ' раз',
        String(day.counts.changes)
      )
    );
  }

  function tile(big, en, ru) {
    return h('div', { class: 'tile' }, [h('div', { class: 'big' }, big), h('div', { class: 'what' }, App.both(en, ru))]);
  }

  function why() {
    var box = App.clear(document.getElementById('tour-tiles'));
    box.appendChild(
      tile(
        App.num(SPEC.minA) + ' ' + App.t('A', 'А'),
        'the smallest current a car can be asked for. Below it there is no slow charging, only no charging',
        'самый маленький ток, который можно попросить у машины. Ниже него нет медленной зарядки — есть никакой'
      )
    );
    box.appendChild(
      tile(
        App.watts(SPEC.threePhaseFloorW),
        'is what three phases need before they can charge at all, while one phase tops out at ' +
          App.watts(SPEC.onePhaseAmpW * SPEC.settings.max_a),
        'нужно трём фазам, чтобы заряжать хоть как-то, а одна фаза вытягивает максимум ' +
          App.watts(SPEC.onePhaseAmpW * SPEC.settings.max_a)
      )
    );
    box.appendChild(
      tile(
        '~20 ' + App.t('s', 'с'),
        'is how long a cloud takes to cross the roof. A kettle does the same thing to the meter in one second',
        'столько тень облака идёт через крышу. Чайник делает со счётчиком то же самое за секунду'
      )
    );
    box.appendChild(
      tile(
        App.num(SPEC.settings.rise_delay_s) + ' ' + App.t('s', 'с'),
        'the offer waits before going up, but comes down on the very next reading. Mistakes belong on the cheap side',
        'столько предложение ждёт, прежде чем вырасти, — а падает на следующем же показании. Ошибаться надо в дешёвую сторону'
      )
    );
  }

  function numbers() {
    var run = window.RUN_DATA;
    var box = App.clear(document.getElementById('tour-numbers'));
    var passed = 0;
    var runs = 0;
    Object.keys(run.meta).forEach(function (key) {
      runs += 1;
      passed += run.meta[key].passed;
    });
    box.appendChild(tile(App.num(run.tests.length), 'checks, each one a plain sentence', 'проверок, каждая — понятное предложение'));
    box.appendChild(
      tile(String(runs), 'runs: the same controller through three kinds of wallbox', 'прогона: один контроллер через три вида вольтбокса')
    );
    box.appendChild(tile(App.num(passed), 'passes in the last run', 'прохождений в последнем прогоне'));
    box.appendChild(
      tile(String(window.DAY_DATA.days.length), 'whole days replayed end to end', 'целых дней, проигранных от начала до конца')
    );

    var hunt = window.MUTANT_DATA;
    var dots = App.clear(document.getElementById('tour-dots'));
    (hunt.mutants || []).forEach(function (m) {
      dots.appendChild(h('i', { class: m.caught ? null : 'bad', title: m.id }));
    });
    var line = App.clear(document.getElementById('tour-hunt'));
    if (!hunt.meta || !hunt.meta.total) return;
    line.appendChild(
      h(
        'strong',
        null,
        App.both(
          hunt.meta.caught + ' of ' + hunt.meta.total + ' planted bugs were caught.',
          'Поймано ' + hunt.meta.caught + ' из ' + hunt.meta.total + ' посаженных багов.'
        )
      )
    );
    line.appendChild(document.createTextNode(' '));
    line.appendChild(h('span', { class: 'muted' }, App.both('Each square is one bug.', 'Каждый квадрат — один баг.')));
  }

  App.views.tour = {
    init: function () {
      scene = App.Scene(document.getElementById('tour-scene'));
      restart();
      if (reduced) {
        for (var n = 0; n < 1800; n++) Twin.tick(house, controller, 10);
      }
      promises();
      why();
      numbers();
      paint();
      App.onLang(function () {
        promises();
        why();
        numbers();
        paint();
      });
      void clockAt;
    },
    show: function () {
      active = true;
      if (!reduced) timer = window.requestAnimationFrame(frame);
    },
    hide: function () {
      active = false;
      if (timer) window.cancelAnimationFrame(timer);
    },
  };
})();
