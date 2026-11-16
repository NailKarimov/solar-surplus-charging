/* View 1: the project in two minutes.

   The day does not race past. It is stopped at seven moments, each one played slowly enough to
   follow, with a line saying what the house just did and what the controller did about it. The
   controller is the real one — the JavaScript twin checked decision by decision against the Python
   original — so nothing here is a cartoon of the system under test. */
(function () {
  'use strict';
  var App = window.App;
  var Twin = window.Twin;
  var h = App.h;
  var SPEC = App.SPEC;
  var scene;
  var house, controller;
  var at = 0;
  var raf = null;
  var hold = null;
  var active = false;
  var playing = false;
  var done = false;
  var lastTs = 0;
  var carry = 0;
  var said = null;
  var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  var START = 7 * 3600;
  var TICK = 10;

  function dayNamed(id) {
    return window.DAY_DATA.days.filter(function (d) {
      return d.id === id;
    })[0];
  }

  // ---- the day the tour plays ---------------------------------------------------------------------
  //
  // One phase, the common home wallbox: a whole amp is 230 W there rather than 690 W, so the offer
  // moves in steps small enough to see. A roof of four kilowatts, a cloud at eleven that takes a
  // third of the sun, the oven at half past twelve, and a thick shadow at four that drops the roof
  // below the smallest charge a car can be given.

  function build() {
    var sky = new Twin.Sky({
      peak_w: 4200,
      clouds: [new Twin.Cloud(11 * 3600, 480, 0.6, 30), new Twin.Cloud(16 * 3600, 420, 0.12, 25)],
    });
    house = new Twin.House({
      inverter: new Twin.Inverter(4000, sky),
      household: new Twin.Household(300, [new Twin.Load('the oven', 2000, 12 * 3600 + 1800, 40 * 60)]),
      car: new Twin.Car({}),
      meter: new Twin.Meter(5),
      clock: START,
      phases: 1,
    });
    controller = new Twin.Controller(new Twin.Settings({ allow_phase_switching: false }), 1);
    said = null;
  }

  var CHAPTERS = [
    {
      from: 7 * 3600,
      to: 7 * 3600 + 2400,
      real: 10,
      label: ['First light', 'Первый свет'],
      what: [
        'Seven in the morning. The roof is awake, but it is making about 800 W and the house is using 300 of them.',
        'Семь утра. Крыша проснулась, но даёт около 800 Вт, из которых 300 забирает сам дом.',
      ],
      does: [
        'The 500 W left over cannot be given to the car. The smallest charge a car can be offered is 6 A — 1.4 kW on one phase — and below that there is no slow charging, there is no charging. So the cable offers nothing and that little surplus goes to the grid. No controller can mend this, and the project does not pretend otherwise: sun the car could not have taken is not counted against it.',
        'Оставшиеся 500 Вт машине отдать нельзя. Самый маленький заряд, который можно предложить машине, — 6 А, то есть 1,4 кВт на одной фазе; ниже этого нет медленной зарядки, а есть никакая. Поэтому кабель не предлагает ничего, и этот остаток уходит в сеть. Этого не исправит никакой контроллер, и проект не делает вид, что исправит: солнце, которое машина взять не могла, ему в вину не ставят.',
      ],
    },
    {
      from: 7 * 3600 + 2400,
      to: 9 * 3600 + 2400,
      real: 18,
      label: ['The sun arrives', 'Солнце приходит'],
      what: [
        'Just before eight the roof passes 1.7 kW, and for the first time there is enough to spare for the smallest charge there is.',
        'Около восьми крыша переходит 1,7 кВт, и впервые излишка хватает на самый маленький заряд.',
      ],
      does: [
        'The controller waits five minutes to be sure the sun is really there, starts at 6 A, and then climbs: one whole amp at a time, and never more often than once every two minutes. By twenty to ten it is offering eleven amps and the needle is sitting on zero.',
        'Контроллер пять минут проверяет, что солнце действительно есть, начинает с 6 А и потом растёт: по целому амперу и не чаще раза в две минуты. К десяти без двадцати он предлагает одиннадцать ампер, а стрелка стоит на нуле.',
      ],
    },
    {
      from: 11 * 3600 - 150,
      to: 11 * 3600 + 240,
      real: 13,
      label: ['A cloud', 'Облако'],
      what: [
        'Just before eleven the house is in balance at fourteen amps. Then a cloud slides over the roof and takes away a third of the sun in half a minute.',
        'Перед одиннадцатью дом в равновесии на четырнадцати амперах. Потом на крышу наезжает облако и за полминуты забирает треть солнца.',
      ],
      does: [
        'The offer comes down on the very next reading of the meter — no waiting, no averaging. The needle does flick towards “buying” for a few seconds, because the meter averages over five seconds and the car needs three to obey. That flick is about one watt-hour, and watt-hours are exactly what the tests add up over a whole day.',
        'Предложение падает на следующем же показании счётчика — без ожидания и усреднения. Стрелка всё же на несколько секунд уходит в «покупаем»: счётчик усредняет за пять секунд, а машине нужно три, чтобы послушаться. Этот всплеск — около одного ватт-часа, а ватт-часы и есть то, что тесты складывают за целый день.',
      ],
    },
    {
      from: 11 * 3600 + 330,
      to: 11 * 3600 + 900,
      real: 15,
      label: ['…and gone', '…и ушло'],
      what: [
        'The cloud thins out and goes. By about ten past eleven the sun is fully back.',
        'Облако истончается и уходит. К десяти минутам двенадцатого солнце возвращается целиком.',
      ],
      does: [
        'This time the controller does not hurry. It waits two minutes before offering more, and for those two minutes the house hands the grid up to 1.5 kW. That is the cheap mistake, and it is chosen on purpose: sun given away is worth about a quarter of electricity bought, and a car that is pestered every few seconds eventually refuses to wake up at all.',
        'Теперь контроллер не торопится. Он ждёт две минуты, прежде чем предложить больше, и за эти две минуты дом отдаёт сети до 1,5 кВт. Это дешёвая ошибка, и она выбрана намеренно: отданное солнце стоит примерно четверть купленного, а машина, которую дёргают каждые несколько секунд, в конце концов просто перестанет просыпаться.',
      ],
    },
    {
      from: 12 * 3600 + 1680,
      to: 12 * 3600 + 2160,
      real: 14,
      label: ['The oven', 'Печь'],
      what: [
        'Half past twelve: the oven goes on in the kitchen — two kilowatts in one second. To the meter that is the same event as a cloud.',
        'Половина первого: на кухне включается печь — два киловатта за одну секунду. Для счётчика это то же событие, что облако.',
      ],
      does: [
        'The house always takes what it asked for, and the car gets what is left. The needle swings towards “buying” for about five seconds, because a car cannot give up nine amps faster than that, and then settles back on zero with the car taking exactly what the oven did not.',
        'Дом всегда берёт столько, сколько попросил, а машине достаётся остаток. Стрелка уходит в «покупаем» секунд на пять — быстрее машина девять ампер отдать не может, — а потом возвращается на ноль, и машина берёт ровно то, что не взяла печь.',
      ],
    },
    {
      from: 16 * 3600 - 120,
      to: 16 * 3600 + 480,
      real: 16,
      label: ['A deep shadow', 'Густая тень'],
      what: [
        'Four in the afternoon, and this shadow is a thick one: the roof falls to a few hundred watts and the surplus disappears altogether.',
        'Четыре часа дня, и эта тень густая: крыша падает до нескольких сотен ватт, а излишек исчезает совсем.',
      ],
      does: [
        'Two choices, and no third: stop the session, or hold the smallest charge there is and buy the difference. The controller holds on, and counts what holding on costs — the pill below is its own running bill. When it has spent about 60 Wh it lets go. Then watch what letting go costs: it will not trust the sun for five minutes, so when the shadow passes the whole surplus goes to the grid. That is why the limit is money and not minutes — the first version waited a fixed three minutes and bought 1.5 kWh on a day of broken cloud.',
        'Два варианта, третьего нет: остановить сессию или держать самый маленький заряд и докупать разницу. Контроллер держится и считает, во что это ему обходится, — плашка ниже и есть его счёт. Потратив около 60 Вт·ч, он отпускает. А теперь посмотрите, во что обходится отпустить: следующие пять минут он солнцу не доверяет, поэтому, когда тень уходит, весь излишек уходит в сеть. Вот почему предел здесь в деньгах, а не в минутах: первая версия ждала фиксированные три минуты и за день рваной облачности купила 1,5 кВт·ч.',
      ],
    },
    {
      from: 18 * 3600 + 3000,
      to: 19 * 3600 + 1800,
      real: 14,
      label: ['Evening', 'Вечер'],
      what: [
        'The sun goes down, and a little after seven the surplus drops below the smallest charge for good.',
        'Солнце садится, и чуть позже семи излишек окончательно падает ниже самого маленького заряда.',
      ],
      does: [
        'The session ends rather than being kept alive on bought electricity. For a few minutes the last kilowatt of sun goes to the grid — nothing in this house can take a kilowatt when the smallest charge is 1.4 — and then the night is spent buying nothing at all.',
        'Сессия заканчивается, а не держится на купленном электричестве. Несколько минут последний киловатт солнца уходит в сеть — в этом доме киловатт взять нечем, когда самый маленький заряд 1,4 кВт, — а дальше за всю ночь не куплено ничего.',
      ],
    },
  ];

  // ---- running one moment --------------------------------------------------------------------------

  /* One tick of the real law, remembering the last decision that actually changed something: the
     controller says "no change" most of the time, and a caption that says so teaches nothing. */
  function step() {
    Twin.tick(house, controller, TICK);
    if (controller._lastWhy && controller._lastWhy !== 'no change') said = controller._lastWhy;
  }

  function seek(target) {
    if (!house || house.clock > target) build();
    var guard = 0;
    while (house.clock < target && guard < 20000) {
      step();
      guard += 1;
    }
  }

  function chapters() {
    var box = App.clear(document.getElementById('tour-chapters'));
    CHAPTERS.forEach(function (chapter, index) {
      box.appendChild(
        h(
          'button',
          {
            type: 'button',
            class: 'chip',
            'aria-pressed': String(index === at),
            onclick: function () {
              go(index, true);
            },
          },
          [h('span', { class: 'n' }, String(index + 1)), App.both(chapter.label[0], chapter.label[1])]
        )
      );
    });
  }

  function caption() {
    var chapter = CHAPTERS[at];
    App.clear(document.getElementById('tour-what')).appendChild(
      App.both(App.clock(chapter.from) + ' · ' + chapter.what[0], App.clock(chapter.from) + ' · ' + chapter.what[1])
    );
    App.clear(document.getElementById('tour-does')).appendChild(App.both(chapter.does[0], chapter.does[1]));
    var rate = Math.round((chapter.to - chapter.from) / chapter.real);
    App.clear(document.getElementById('tour-pace')).appendChild(
      App.both(
        'Moment ' + (at + 1) + ' of ' + CHAPTERS.length + ' · ' + rate + '× real time',
        'Момент ' + (at + 1) + ' из ' + CHAPTERS.length + ' · в ' + rate + ' раз быстрее реального времени'
      )
    );
    Array.prototype.forEach.call(document.getElementById('tour-chapters').children, function (node, index) {
      node.setAttribute('aria-pressed', String(index === at));
    });
  }

  function controls() {
    var play = App.clear(document.getElementById('tour-play'));
    play.appendChild(
      done
        ? App.both('↻ Watch it again', '↻ Посмотреть снова')
        : playing
          ? App.both('❚❚ Pause', '❚❚ Пауза')
          : App.both('▶ Play', '▶ Смотреть')
    );
    var prev = App.clear(document.getElementById('tour-prev'));
    prev.appendChild(App.both('‹ Back', '‹ Назад'));
    prev.disabled = at === 0;
    var next = App.clear(document.getElementById('tour-next'));
    next.appendChild(App.both('Next ›', 'Дальше ›'));
    next.disabled = at === CHAPTERS.length - 1;
  }

  function says() {
    var box = App.clear(document.getElementById('tour-says'));
    var amps = house.offered_a;
    box.appendChild(
      h(
        'span',
        { class: amps ? 'pill sun' : 'pill' },
        App.both(
          amps ? 'the cable is offering ' + App.amps(amps, house.phases) : 'the cable is offering nothing',
          amps ? 'кабель предлагает ' + App.amps(amps, house.phases) : 'кабель не предлагает ничего'
        )
      )
    );
    var why = App.whyWords(said);
    if (why) box.appendChild(h('span', { class: 'pill' }, '“' + why + '”'));
    if (controller._below_floor_since !== null && amps > 0) {
      box.appendChild(
        h(
          'span',
          { class: 'pill bad' },
          App.both(
            'holding on has cost ' +
              App.wh(controller._ride_out_wh) +
              ' of the ' +
              App.wh(SPEC.settings.ride_out_budget_wh) +
              ' it may spend',
            'держаться уже обошлось в ' +
              App.wh(controller._ride_out_wh) +
              ' из ' +
              App.wh(SPEC.settings.ride_out_budget_wh) +
              ', которые можно потратить'
          )
        )
      );
    }
  }

  function paint() {
    scene.update(App.snapshotOf(house));
    var grid = house.gridW();
    App.clear(document.getElementById('tour-now')).appendChild(
      App.both(
        App.clock(house.clock, true) +
          ' · the roof ' +
          App.watts(house.pvW()) +
          ' · the house ' +
          App.watts(house.houseW()) +
          ' · the car ' +
          App.watts(house.carW()) +
          ' · the meter ' +
          (Math.abs(grid) < 50 ? 'at zero' : App.watts(Math.abs(grid)) + (grid > 0 ? ' bought' : ' sold')),
        App.clock(house.clock, true) +
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
    says();
    var chapter = CHAPTERS[at];
    var share = (house.clock - chapter.from) / (chapter.to - chapter.from);
    document.getElementById('tour-bar').style.width = (100 * Math.max(0, Math.min(1, share))).toFixed(1) + '%';
  }

  function stop() {
    if (raf) window.cancelAnimationFrame(raf);
    if (hold) window.clearTimeout(hold);
    raf = null;
    hold = null;
    playing = false;
  }

  function frame(ts) {
    if (!active || !playing) return;
    if (!lastTs) lastTs = ts;
    var seconds = Math.min(0.25, (ts - lastTs) / 1000);
    lastTs = ts;
    var chapter = CHAPTERS[at];
    carry += (seconds * (chapter.to - chapter.from)) / chapter.real;
    while (carry >= TICK && house.clock < chapter.to) {
      carry -= TICK;
      step();
    }
    paint();
    if (house.clock >= chapter.to) {
      if (at < CHAPTERS.length - 1) {
        playing = false;
        raf = null;
        hold = window.setTimeout(function () {
          hold = null;
          go(at + 1, true);
        }, 1100);
        return;
      }
      stop();
      done = true;
      controls();
      return;
    }
    raf = window.requestAnimationFrame(frame);
  }

  function go(index, play) {
    stop();
    done = false;
    at = Math.max(0, Math.min(CHAPTERS.length - 1, index));
    var chapter = CHAPTERS[at];
    seek(chapter.from);
    carry = 0;
    lastTs = 0;
    caption();
    if (play && !reduced) {
      playing = true;
      raf = window.requestAnimationFrame(frame);
    } else if (reduced) {
      seek(chapter.to);
    }
    controls();
    paint();
  }

  // ---- the rest of the view -------------------------------------------------------------------------

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
      chapters();
      document.getElementById('tour-play').addEventListener('click', function () {
        if (done) {
          go(0, true);
          return;
        }
        if (playing) {
          stop();
          controls();
          return;
        }
        if (house.clock >= CHAPTERS[at].to) {
          go(Math.min(at + 1, CHAPTERS.length - 1), true);
          return;
        }
        playing = true;
        lastTs = 0;
        raf = window.requestAnimationFrame(frame);
        controls();
      });
      document.getElementById('tour-prev').addEventListener('click', function () {
        go(at - 1, playing);
      });
      document.getElementById('tour-next').addEventListener('click', function () {
        go(at + 1, playing);
      });
      promises();
      why();
      numbers();
      go(0, false);
      App.onLang(function () {
        chapters();
        caption();
        controls();
        promises();
        why();
        numbers();
        paint();
      });
    },
    show: function () {
      active = true;
      if (!reduced && !playing && !done && house.clock < CHAPTERS[at].to) {
        playing = true;
        lastTs = 0;
        raf = window.requestAnimationFrame(frame);
        controls();
      }
    },
    hide: function () {
      active = false;
      stop();
      controls();
    },
    debug: {
      go: go,
      chapters: CHAPTERS,
      state: function () {
        return { house: house, controller: controller, at: at, playing: playing, done: done };
      },
    },
  };
})();
