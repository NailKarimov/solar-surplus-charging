/* View 5: the mutation check. One card per planted bug. */
(function () {
  'use strict';
  var App = window.App;
  var h = App.h;
  var data = window.MUTANT_DATA;
  var area = 'all';
  var byName = {};
  window.RUN_DATA.tests.forEach(function (test) {
    if (!byName[test.name]) byName[test.name] = test;
  });

  function tile(big, en, ru) {
    return h('div', { class: 'tile' }, [h('div', { class: 'big' }, big), h('div', { class: 'what' }, App.both(en, ru))]);
  }

  function tiles() {
    var box = App.clear(document.getElementById('bugs-tiles'));
    var meta = data.meta;
    var killers = data.mutants.reduce(function (sum, m) {
      return sum + m.killer_count;
    }, 0);
    box.appendChild(tile(String(meta.total), 'bugs planted, one at a time', 'багов посажено, по одному за раз'));
    box.appendChild(tile(meta.caught + ' / ' + meta.total, meta.caught === meta.total ? 'caught: none got through' : 'caught: some got through', meta.caught === meta.total ? 'поймано: ни один не прошёл' : 'поймано: часть прошла'));
    box.appendChild(tile(App.num(killers), 'failed checks in total', 'упавших проверок в сумме'));
    box.appendChild(tile(meta.control ? '✓' : '✗', 'control run without any bug passes, so a failure means a bug', 'контрольный прогон без багов проходит, значит падение означает баг'));
  }

  function areas() {
    var box = App.clear(document.getElementById('bugs-areas'));
    var counts = {};
    var order = [];
    data.mutants.forEach(function (m) {
      if (!counts[m.area]) order.push(m.area);
      counts[m.area] = (counts[m.area] || 0) + 1;
    });
    function chip(id, label) {
      box.appendChild(
        h(
          'button',
          {
            type: 'button',
            class: 'chip',
            'aria-pressed': String(area === id),
            onclick: function () {
              area = id;
              areas();
              list();
            },
          },
          label
        )
      );
    }
    chip('all', App.t('all', 'все') + ' · ' + data.mutants.length);
    order.forEach(function (id) {
      chip(id, App.areaName(id) + ' · ' + counts[id]);
    });
  }

  function list() {
    var box = App.clear(document.getElementById('bugs-list'));
    data.mutants
      .filter(function (m) {
        return area === 'all' || m.area === area;
      })
      .forEach(function (m) {
        var killers = h('ul');
        m.killers.slice(0, 3).forEach(function (k) {
          var test = byName[k.name];
          killers.appendChild(h('li', null, test ? App.testTitle(test) : k.name));
        });
        var n = m.killer_count;
        var by = m.caught
          ? App.t('Caught by ' + n + (n === 1 ? ' check' : ' checks') + (n > 3 ? ', for example:' : ':'), 'Поймали проверок: ' + n + (n > 3 ? ', например:' : ':'))
          : App.t('No check noticed this bug.', 'Ни одна проверка не заметила этот баг.');
        box.appendChild(
          h('div', { class: 'card mut', id: 'mut-' + m.id }, [
            h('div', { class: 'hd' }, [h('span', { class: 'id' }, m.id + ' · ' + App.areaName(m.area)), h('span', { class: 'pill ' + (m.caught ? 'ok' : 'bad') }, m.caught ? App.t('caught', 'пойман') : App.t('survived', 'выжил'))]),
            h('h3', null, App.mutantTitle(m)),
            h('div', { class: 'diff', title: m.file }, [h('div', { class: 'old' }, m.old || ' '), h('div', { class: 'new' }, m.new || App.t('(line removed)', '(строка удалена)'))]),
            h('div', { class: 'by' }, by),
            m.caught ? killers : null,
          ])
        );
      });
  }

  App.views.bugs = {
    init: function () {
      tiles();
      areas();
      list();
      App.onLang(function () {
        tiles();
        areas();
        list();
      });
    },
    show: function () {},
    hide: function () {},
  };
})();
