/* View 3: what the decision looks like on each of the two wires.

   Every frame drawn here was captured from a real socket while the page was built — the Modbus
   bytes from a real wallbox on a real TCP connection, the OCPP messages from a real charge point on
   a real WebSocket — and every byte carries the label the recorder worked out for it. See
   `scripts/wire.py`. */
(function () {
  'use strict';
  var App = window.App;
  var h = App.h;
  var DATA = window.WIRE_DATA || { moments: [], registers: [] };
  var at = 0;

  // ---- Modbus: one frame, byte by byte ------------------------------------------------------------

  function segment(part) {
    return h('div', { class: 'seg ' + part.kind }, [
      h(
        'div',
        { class: 'bx' },
        part.hex.map(function (byte) {
          return h('span', null, byte);
        })
      ),
      h('div', { class: 'cap' }, App.both(part.en, part.ru)),
    ]);
  }

  function frame(exchange, which) {
    var side = exchange[which];
    var out = h('div', { class: 'msg' });
    out.appendChild(
      h('div', { class: 'small muted' }, [
        h('strong', null, which === 'ask' ? '→ ' : '← '),
        App.both(
          which === 'ask' ? 'the controller asks' : 'the wallbox answers',
          which === 'ask' ? 'контроллер спрашивает' : 'вольтбокс отвечает'
        ),
      ])
    );
    out.appendChild(h('div', { class: 'hexline' }, side.hex));
    out.appendChild(
      h(
        'div',
        { class: 'bytes' },
        side.parts.map(function (part) {
          return segment(part);
        })
      )
    );
    return out;
  }

  function modbus(box, exchange) {
    App.clear(box);
    if (!exchange) return;
    box.appendChild(frame(exchange, 'ask'));
    box.appendChild(h('div', { style: 'height:14px' }));
    box.appendChild(frame(exchange, 'say'));
  }

  // ---- OCPP: one message, and what it is asking for ------------------------------------------------

  function message(line) {
    var box = h('div', { class: 'msg' });
    box.appendChild(
      h('div', { class: 'small muted' }, [
        h('strong', null, line.dir === '->' ? '→ ' : '← '),
        App.both(
          line.dir === '->' ? 'to the station' : 'from the station',
          line.dir === '->' ? 'станции' : 'от станции'
        ),
      ])
    );
    box.appendChild(
      h('div', { class: 'wire' }, [
        h('i', { class: 'kind' }, line.kind),
        ' ',
        h('i', { class: 'mid' }, '#' + line.id),
        ' ',
        line.action ? h('i', { class: 'act' }, line.action) : null,
        ' ',
        h('i', { class: 'body' }, line.body),
      ])
    );
    if (line.fields && line.fields.length) {
      box.appendChild(
        h(
          'div',
          { class: 'parts' },
          line.fields.map(function (field) {
            return h('div', { class: 'part' }, [
              h('div', { class: 'small muted' }, App.both(field.en, field.ru)),
              h('div', { class: 'mono' }, field.v),
            ]);
          })
        )
      );
    }
    return box;
  }

  function ocpp(box, lines) {
    App.clear(box);
    (lines || []).forEach(function (line, index) {
      if (index) box.appendChild(h('div', { style: 'height:14px' }));
      box.appendChild(message(line));
    });
  }

  // ---- the four moments ------------------------------------------------------------------------------

  function moments() {
    var box = App.clear(document.getElementById('wire-moments'));
    DATA.moments.forEach(function (moment, index) {
      box.appendChild(
        h(
          'button',
          {
            type: 'button',
            class: 'chip',
            'aria-pressed': String(index === at),
            'data-moment': moment.id,
            onclick: function () {
              at = index;
              paint();
            },
          },
          [h('span', { class: 'n' }, App.clock(moment.clock)), App.both(moment.short_en, moment.short_ru)]
        )
      );
    });
  }

  function paint() {
    var moment = DATA.moments[at];
    Array.prototype.forEach.call(document.getElementById('wire-moments').children, function (node, index) {
      node.setAttribute('aria-pressed', String(index === at));
    });
    if (!moment) return;
    var said = App.clear(document.getElementById('wire-said'));
    said.appendChild(h('strong', null, App.clock(moment.clock) + ' · '));
    said.appendChild(h('strong', null, App.both(moment.en, moment.ru)));
    said.appendChild(document.createTextNode(' '));
    said.appendChild(App.both(moment.say_en, moment.say_ru));
    modbus(document.getElementById('wire-modbus'), moment.modbus && moment.modbus.write);
    ocpp(document.getElementById('wire-ocpp'), moment.ocpp);
  }

  function fixed() {
    modbus(document.getElementById('wire-read-modbus'), DATA.read && DATA.read.modbus);
    ocpp(document.getElementById('wire-read-ocpp'), DATA.read && DATA.read.ocpp);
    modbus(document.getElementById('wire-no-modbus'), DATA.refused && DATA.refused.modbus);
    ocpp(document.getElementById('wire-no-ocpp'), DATA.refused && DATA.refused.ocpp);

    var map = App.clear(document.getElementById('wire-map'));
    (DATA.registers || []).forEach(function (row) {
      map.appendChild(
        h('div', { class: 'part' }, [
          h('div', { class: 'mono' }, [String(row.at), ' ', h('span', { class: 'muted' }, row.rw)]),
          h('div', null, App.both(row.en, row.ru)),
        ])
      );
    });
  }

  App.views.wire = {
    init: function () {
      moments();
      fixed();
      paint();
      App.onLang(function () {
        moments();
        fixed();
        paint();
      });
    },
    debug: {
      data: DATA,
      go: function (index) {
        at = index;
        paint();
      },
    },
  };
})();
