/* View 4: the last test run. Suites, checks in plain words, the steps and the numbers each measured. */
(function () {
  'use strict';
  var App = window.App;
  var h = App.h;
  var run = window.RUN_DATA;
  var DRIVERS = ['direct', 'modbus', 'ocpp'];
  var TEXT = {
    direct: ['Straight into the model', 'Прямо в модель', 'No protocol in the way, so a failure is the control law and nothing else.', 'Между ними нет протокола, поэтому падение — это именно закон управления.'],
    modbus: ['A Modbus TCP wallbox', 'Вольтбокс по Modbus TCP', 'How a home wallbox is really driven: a current written into a register every few seconds.', 'Так на самом деле управляют домашним вольтбоксом: ток пишут в регистр каждые несколько секунд.'],
    ocpp: ['An OCPP 1.6 charge point', 'Станция по OCPP 1.6', 'How a public station is driven: a charging profile the station may accept or refuse.', 'Так управляют публичной станцией: профилем, который станция может принять или отклонить.'],
  };
  var SKIP_RU = {
    'the control law does not depend on the driver: this runs in the direct run':
      'закон управления не зависит от драйвера: выполняется в прогоне против модели',
  };
  var query = '';
  var open = {};

  function overall(test) {
    var result = 'skipped';
    DRIVERS.forEach(function (driver) {
      var outcome = test.runs[driver];
      if (outcome === 'failed') result = 'failed';
      else if (outcome === 'passed' && result !== 'failed') result = 'passed';
    });
    return result;
  }

  function driverCards() {
    var box = App.clear(document.getElementById('replay-links'));
    DRIVERS.forEach(function (driver) {
      var meta = run.meta[driver];
      if (!meta) return;
      var text = TEXT[driver];
      box.appendChild(
        h('div', { class: 'card' }, [
          h('div', { class: 'eyebrow' }, driver),
          h('h3', null, App.t(text[0], text[1])),
          h('div', { class: 'big' }, [
            App.num(meta.passed),
            ' ',
            h('span', { class: 'pill ' + (meta.failed ? 'bad' : 'ok') }, meta.failed ? App.t(meta.failed + ' failed', 'упало: ' + meta.failed) : App.t('all passed', 'все прошли')),
          ]),
          h('div', { class: 'small muted' }, App.t(meta.skipped + ' skipped', 'пропущено: ' + meta.skipped)),
          h('p', { class: 'small muted' }, App.t(text[2], text[3])),
        ])
      );
    });
  }

  function detail(test) {
    var box = h('div', { class: 'detail' });
    var steps = test.steps || [];
    steps.forEach(function (step) {
      if (step.text) box.appendChild(h('div', { class: 'step' }, App.stepText(step.text)));
      if (step.notes && step.notes.length) {
        var notes = h('div', { class: 'notes' });
        step.notes.forEach(function (note) {
          notes.appendChild(h('div', { class: 'n' }, [h('span', null, App.stepText(note[0])), h('b', null, note[1])]));
        });
        box.appendChild(notes);
      }
      (step.frames || []).forEach(function (frame) {
        box.appendChild(
          h('div', { class: 'fr ' + (frame[0] === '->' ? 'tx' : 'rx') }, [
            h('span', { class: 'dir' }, frame[0] === '->' ? '→' : '←'),
            h('div', { class: 'wire' }, frame[1]),
          ])
        );
      });
    });
    if (!steps.length) {
      box.appendChild(h('p', { class: 'small muted' }, App.both('This check works on the rules directly and measures nothing in watt-hours.', 'Эта проверка работает прямо с правилами и ничего не измеряет в ватт-часах.')));
    }
    DRIVERS.forEach(function (driver) {
      var reason = test.skip && test.skip[driver];
      if (reason) {
        box.appendChild(h('p', { class: 'small muted' }, driver + ' — ' + App.t('skipped: ', 'пропущена: ') + (App.lang === 'ru' && SKIP_RU[reason] ? SKIP_RU[reason] : reason)));
      }
    });
    box.appendChild(h('p', { class: 'small muted mono' }, 'tests/' + test.suite + '.py::' + test.name + (test.params ? '[' + test.params + ']' : '')));
    return box;
  }

  function testRow(test) {
    var result = overall(test);
    var chips = h('span', { class: 'lk' });
    DRIVERS.forEach(function (driver) {
      var outcome = test.runs[driver];
      if (outcome) chips.appendChild(h('i', { class: outcome === 'passed' ? 'p' : outcome === 'failed' ? 'f' : 's' }, driver));
    });
    var node = h('div', { class: 'test ' + result });
    var button = h(
      'button',
      {
        type: 'button',
        'aria-expanded': String(!!open[test.id]),
        onclick: function () {
          open[test.id] = !open[test.id];
          paintSuites();
        },
      },
      [
        h('span', { class: 'mk' }, result === 'failed' ? '✗' : result === 'skipped' ? '○' : '✓'),
        h('span', { class: 'ttl' }, App.testTitle(test)),
        chips,
      ]
    );
    node.appendChild(button);
    if (open[test.id]) node.appendChild(detail(test));
    return node;
  }

  function paintSuites() {
    var box = App.clear(document.getElementById('replay-suites'));
    var suites = {};
    var order = [];
    run.tests.forEach(function (test) {
      if (!suites[test.suite]) {
        suites[test.suite] = [];
        order.push(test.suite);
      }
      suites[test.suite].push(test);
    });
    var shown = 0;
    order.forEach(function (suite) {
      var tests = suites[suite].filter(function (test) {
        if (!query) return true;
        return (App.testTitle(test) + ' ' + test.name + ' ' + suite).toLowerCase().indexOf(query) >= 0;
      });
      if (!tests.length) return;
      shown += tests.length;
      var body = h('div', { class: 'tests' });
      tests.forEach(function (test) {
        body.appendChild(testRow(test));
      });
      var details = h('details', { class: 'suite', open: query ? true : suite === order[0] }, [
        h('summary', null, [
          h('span', null, App.suiteName(suite)),
          h('span', { class: 'pill' }, tests.length),
          h('span', { class: 'small muted' }, App.suiteBlurb(suite)),
        ]),
        body,
      ]);
      box.appendChild(details);
    });
    document.getElementById('replay-none').hidden = shown > 0;
  }

  function paint() {
    driverCards();
    paintSuites();
  }

  App.views.replay = {
    init: function () {
      var search = document.getElementById('replay-search');
      search.placeholder = App.t('search the checks', 'поиск по проверкам');
      search.addEventListener('input', function (event) {
        query = event.target.value.trim().toLowerCase();
        paintSuites();
      });
      paint();
      App.onLang(function () {
        search.placeholder = App.t('search the checks', 'поиск по проверкам');
        paint();
      });
    },
    show: function () {},
    hide: function () {},
  };
})();
