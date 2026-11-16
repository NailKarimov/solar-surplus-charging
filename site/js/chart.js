/* A small SVG chart for a whole day: the roof, the house, the car, and the line that must stay at zero.

   Drawn by hand rather than with a library, because the page has to be one file that opens from a
   memory stick, and because the only interesting part of this chart is the zero line. */
(function () {
  'use strict';
  var App = window.App;
  var NS = 'http://www.w3.org/2000/svg';

  var W = 980;
  var H = 320;
  var PAD = { left: 54, right: 16, top: 16, bottom: 30 };

  function el(name, attrs) {
    var node = document.createElementNS(NS, name);
    Object.keys(attrs || {}).forEach(function (key) {
      node.setAttribute(key, attrs[key]);
    });
    return node;
  }

  function path(points, x, y) {
    var out = '';
    for (var i = 0; i < points.length; i++) {
      out += (i ? 'L' : 'M') + x(points[i].t).toFixed(1) + ' ' + y(points[i].v).toFixed(1) + ' ';
    }
    return out.trim();
  }

  /* series: [{key, label_en, label_ru, colour, fill}] over day.points */
  App.dayChart = function (container, day, options) {
    options = options || {};
    App.clear(container);
    var points = day.points;
    if (!points.length) return;
    var t0 = points[0].t;
    var t1 = points[points.length - 1].t;
    var top = 0;
    var bottom = 0;
    points.forEach(function (p) {
      top = Math.max(top, p.pv, p.house, p.car, p.grid);
      bottom = Math.min(bottom, p.grid);
    });
    top = Math.ceil(top / 1000) * 1000 || 1000;
    // Below the line is export, and it has to fit: when the car stops at noon the whole roof goes out.
    bottom = Math.max(1000, Math.ceil(-bottom / 1000) * 1000);

    var innerW = W - PAD.left - PAD.right;
    var innerH = H - PAD.top - PAD.bottom;
    var zero = PAD.top + (innerH * top) / (top + bottom);
    var scale = (zero - PAD.top) / top;

    function x(t) {
      return PAD.left + (innerW * (t - t0)) / Math.max(1, t1 - t0);
    }
    function y(v) {
      return zero - v * scale;
    }

    var svg = el('svg', {
      viewBox: '0 0 ' + W + ' ' + H,
      class: 'daychart',
      role: 'img',
      'aria-label': App.t(
        'A day: what the roof made, what the house used, what the car took, and the grid line at zero',
        'День: что дала крыша, что потратил дом, что взяла машина, и линия сети на нуле'
      ),
    });

    // the hours
    for (var hour = Math.ceil(t0 / 3600); hour * 3600 <= t1; hour += 2) {
      var hx = x(hour * 3600);
      svg.appendChild(el('line', { x1: hx, y1: PAD.top, x2: hx, y2: H - PAD.bottom, class: 'grid' }));
      var label = el('text', { x: hx, y: H - PAD.bottom + 16, class: 'tick', 'text-anchor': 'middle' });
      label.textContent = App.clock(hour * 3600);
      svg.appendChild(label);
    }
    // the kilowatts, above the line and below it
    var step = top >= 4000 ? 2000 : 1000;
    for (var w = -bottom; w <= top; w += step) {
      if (w === 0) continue;
      var wy = y(w);
      if (wy < PAD.top || wy > H - PAD.bottom) continue;
      svg.appendChild(el('line', { x1: PAD.left, y1: wy, x2: W - PAD.right, y2: wy, class: 'grid' }));
      var wlabel = el('text', { x: PAD.left - 8, y: wy + 4, class: 'tick', 'text-anchor': 'end' });
      wlabel.textContent = (w > 0 ? '' : '−') + Math.abs(w) / 1000 + ' ' + App.t('kW', 'кВт');
      svg.appendChild(wlabel);
    }

    function series(key, cls, sign) {
      return points.map(function (p) {
        return { t: p.t, v: (sign || 1) * p[key] };
      });
    }

    // the roof, filled, because it is the budget everything else is spent from
    var pv = series('pv');
    var area =
      path(pv, x, y) + ' L' + x(t1).toFixed(1) + ' ' + y(0).toFixed(1) + ' L' + x(t0).toFixed(1) + ' ' + y(0).toFixed(1) + ' Z';
    svg.appendChild(el('path', { d: area, class: 'ar pv' }));
    svg.appendChild(el('path', { d: path(pv, x, y), class: 'ln pv' }));
    svg.appendChild(el('path', { d: path(series('car'), x, y), class: 'ln car' }));
    svg.appendChild(el('path', { d: path(series('house'), x, y), class: 'ln house' }));

    // the zero line, and the grid around it
    svg.appendChild(el('path', { d: path(series('grid'), x, y), class: 'ln grid-line' }));
    svg.appendChild(el('line', { x1: PAD.left, y1: zero, x2: W - PAD.right, y2: zero, class: 'zero' }));
    var zlabel = el('text', { x: PAD.left - 8, y: zero + 4, class: 'tick zerolabel', 'text-anchor': 'end' });
    zlabel.textContent = App.t('zero', 'ноль');
    svg.appendChild(zlabel);

    // the moments worth pointing at
    if (!options.plain) {
      // Only the moments a person would point at: where charging stopped or started again.
      var last = null;
      (day.moments || []).forEach(function (moment) {
        var stop = moment.a === 0 && last !== 0;
        var start = moment.a !== 0 && last === 0;
        last = moment.a;
        if (!stop && !start) return;
        var mx = x(moment.t);
        if (mx < PAD.left || mx > W - PAD.right) return;
        svg.appendChild(el('line', { x1: mx, y1: PAD.top, x2: mx, y2: H - PAD.bottom, class: 'moment ' + (stop ? 'stop' : 'start') }));
      });
    }

    container.appendChild(svg);
    return { x: x, y: y, zero: zero };
  };

  App.chartLegend = function (container) {
    App.clear(container);
    [
      ['pv', 'what the roof made', 'что дала крыша'],
      ['car', 'what the car took', 'что взяла машина'],
      ['house', 'what the house used', 'что потратил дом'],
      ['grid-line', 'the grid: above the line is bought, below it is sold, and it must stay at zero', 'сеть: выше линии — куплено, ниже — отдано, и она должна стоять на нуле'],
    ].forEach(function (row) {
      container.appendChild(
        App.h('span', { class: 'key' }, [App.h('i', { class: row[0] }), App.t(row[1], row[2])])
      );
    });
  };
})();
