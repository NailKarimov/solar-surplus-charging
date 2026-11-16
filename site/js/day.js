/* View 3: one whole day, drawn from a real run. */
(function () {
  'use strict';
  var App = window.App;
  var h = App.h;
  var DATA = window.DAY_DATA;
  var current = 'whole-day';

  function day() {
    return DATA.days.filter(function (d) {
      return d.id === current;
    })[0] || DATA.days[0];
  }

  function pick() {
    var box = App.clear(document.getElementById('day-pick'));
    DATA.days.forEach(function (d) {
      box.appendChild(
        h(
          'button',
          {
            type: 'button',
            class: 'chip',
            'aria-pressed': String(d.id === current),
            onclick: function () {
              current = d.id;
              paint();
            },
          },
          App.dayName(d.id)
        )
      );
    });
  }

  function tile(big, en, ru, tone) {
    return h('div', { class: 'tile' + (tone ? ' ' + tone : '') }, [
      h('div', { class: 'big' }, big),
      h('div', { class: 'what' }, App.both(en, ru)),
    ]);
  }

  function tiles() {
    var d = day();
    var t = d.totals;
    var box = App.clear(document.getElementById('day-tiles'));
    box.appendChild(tile(App.kwh(t.pv), 'made by the roof', 'дала крыша'));
    box.appendChild(tile(App.kwh(t.car), 'went into the car', 'вошло в машину'));
    box.appendChild(
      tile(
        App.wh(t.bought),
        'bought from the grid for the car, which is ' + App.num((100 * t.bought) / Math.max(1, t.car), 1) + ' % of what it got',
        'куплено из сети для машины — это ' + App.num((100 * t.bought) / Math.max(1, t.car), 1) + ' % от того, что она получила'
      )
    );
    box.appendChild(
      tile(
        App.kwh(t.spilled),
        'of sun the car could have taken went to the grid instead',
        'солнца, которое машина могла взять, ушло в сеть'
      )
    );
    box.appendChild(
      tile(String(d.counts.changes), 'changes of the offer, ' + d.counts.pauses + ' stops', 'изменений предложения, остановок: ' + d.counts.pauses)
    );
    box.appendChild(
      tile(
        App.num((100 * t.fromSun) / Math.max(1, t.car)) + ' %',
        'of the car’s energy was paid for by the roof',
        'энергии машины оплатила крыша'
      )
    );
  }

  function moments() {
    var box = App.clear(document.getElementById('day-moments'));
    var list = day().moments;
    if (!list.length) {
      box.appendChild(h('p', { class: 'small muted' }, App.both('Nothing happened all day.', 'За весь день ничего не произошло.')));
      return;
    }
    list.forEach(function (m) {
      box.appendChild(
        h('div', { class: 'm' }, [
          h('time', null, App.clock(m.t)),
          h('b', null, m.a ? App.amps(m.a, m.p) : App.t('stop', 'стоп')),
          h('span', null, App.whyWords(m.why)),
        ])
      );
    });
  }

  function paint() {
    pick();
    var d = day();
    App.clear(document.getElementById('day-blurb')).appendChild(document.createTextNode(App.dayBlurb(d.id)));
    App.dayChart(document.getElementById('day-chart'), d);
    App.chartLegend(document.getElementById('day-legend'));
    tiles();
    moments();
  }

  App.views.day = {
    init: function () {
      paint();
      App.onLang(paint);
    },
    show: function () {},
    hide: function () {},
  };
})();
