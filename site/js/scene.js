/* The picture: the sun on the roof, the house, the car on the cable, and the meter at the door.

   One idea carries the whole page, so the picture is built around it: the meter in the middle has a
   needle, and the controller's entire job is to keep that needle on zero. Left of zero the house is
   giving sun away. Right of zero it is buying. */
(function () {
  'use strict';
  var App = window.App;
  var Twin = window.Twin;
  var NS = 'http://www.w3.org/2000/svg';
  var count = 0;

  function both(x, y, en, ru, cls, anchor) {
    var a = anchor ? ' text-anchor="' + anchor + '"' : '';
    return (
      '<text class="en ' + (cls || '') + '" x="' + x + '" y="' + y + '"' + a + '>' + en + '</text>' +
      '<text class="ru ' + (cls || '') + '" x="' + x + '" y="' + y + '"' + a + '>' + ru + '</text>'
    );
  }

  function markup(id) {
    return (
      '<svg xmlns="' + NS + '" viewBox="0 0 760 360" role="img" aria-labelledby="' + id + '-t">' +
      '<title id="' + id + '-t">The sun on a roof, the house below it, a car on a cable, and the meter on the wall with its needle on zero</title>' +
      '<rect width="760" height="360" fill="var(--sky-day)"/>' +
      '<rect y="300" width="760" height="60" fill="var(--sunk)"/>' +
      '<line x1="0" y1="300" x2="760" y2="300" stroke="var(--line)"/>' +
      // the sun
      '<g class="sun">' +
      '<circle class="disc" cx="300" cy="62" r="26" fill="var(--solar)"/>' +
      '<g class="rays" stroke="var(--solar)" stroke-width="3" stroke-linecap="round">' +
      '<path d="M300 20 v-12 M300 104 v12 M258 62 h-12 M342 62 h12 M270 32 l-9-9 M330 92 l9 9 M330 32 l9-9 M270 92 l-9 9"/>' +
      '</g></g>' +
      // the cloud that slides over it
      '<g class="cloud" opacity="0">' +
      '<path d="M266 56 q0-20 22-20 q8-18 30-14 q18-10 30 8 q22 0 22 20 q0 18-22 18 h-60 q-22 0-22-12 z" fill="var(--surface)" stroke="var(--line)" stroke-width="1.5"/>' +
      '</g>' +
      // the roof with its panels
      '<path d="M222 182 L288 128 L430 128 L364 182 Z" fill="var(--roof)"/>' +
      '<path class="panelglow" d="M222 182 L288 128 L430 128 L364 182 Z" fill="var(--solar)" opacity="0"/>' +
      '<path d="M242 174 L300 134 M270 174 L328 134 M298 174 L356 134 M326 174 L384 134" stroke="var(--line)" stroke-width="1"/>' +
      // the house
      '<rect x="232" y="182" width="140" height="118" fill="var(--surface)" stroke="var(--ink)" stroke-width="1.5"/>' +
      '<rect class="window" x="252" y="202" width="40" height="32" rx="3" fill="var(--sunk)" stroke="var(--line)"/>' +
      '<rect class="window2" x="312" y="202" width="40" height="32" rx="3" fill="var(--sunk)" stroke="var(--line)"/>' +
      '<rect x="282" y="256" width="40" height="44" rx="3" fill="var(--sunk)" stroke="var(--line)"/>' +
      both(302, 322, 'the house', 'дом', 'lbl', 'middle') +
      // the car and its cable
      '<g class="car">' +
      '<path d="M502 282 L512 252 Q515 244 525 244 L603 244 Q613 244 618 252 L630 282 Z" fill="var(--surface)" stroke="var(--ink)" stroke-width="1.5"/>' +
      '<path d="M524 276 L532 256 Q534 252 539 252 L590 252 Q595 252 597 256 L605 276 Z" fill="var(--sky-night)" opacity="0.25"/>' +
      '<rect x="496" y="278" width="140" height="18" rx="7" fill="var(--surface)" stroke="var(--ink)" stroke-width="1.5"/>' +
      '<circle cx="524" cy="298" r="11" fill="var(--ink)"/><circle cx="608" cy="298" r="11" fill="var(--ink)"/>' +
      '<rect class="battery" x="544" y="281" width="44" height="12" rx="3" fill="var(--sunk)" stroke="var(--ink)"/>' +
      '<rect class="batteryfill" x="546" y="283" width="0" height="8" rx="2" fill="var(--ok)"/>' +
      '</g>' +
      '<path class="plug" d="M372 268 Q 436 268 456 278 Q 478 286 494 286"/>' +
      '<path class="flow power" d="M376 264 L 490 282"/>' +
      '<text class="lbl amps" x="434" y="254" text-anchor="middle">—</text>' +
      both(566, 322, 'the car', 'машина', 'lbl', 'middle') +
      // the grid, and the meter on the wall between it and the house
      '<g class="pole">' +
      '<path d="M56 150 v150 M32 170 h48 M36 194 h40" stroke="var(--ink)" stroke-width="2.5" fill="none"/>' +
      '</g>' +
      both(56, 322, 'the grid', 'сеть', 'lbl', 'middle') +
      '<path class="flow grid" d="M228 212 L 70 212"/>' +
      // the meter: a needle that must sit on zero
      '<rect x="92" y="226" width="116" height="52" rx="7" fill="var(--surface)" stroke="var(--ink)" stroke-width="1.5"/>' +
      '<path d="M122 266 A 28 28 0 0 1 178 266" fill="none" stroke="var(--line)" stroke-width="3"/>' +
      '<line x1="150" y1="266" x2="150" y2="242" stroke="var(--muted)" stroke-width="1"/>' +
      '<line class="needle" x1="150" y1="266" x2="150" y2="244" stroke="var(--bad)" stroke-width="2.5" stroke-linecap="round"/>' +
      both(98, 222, 'selling', 'отдаём', 'tiny', 'start') +
      both(202, 222, 'buying', 'покупаем', 'tiny', 'end') +
      '<text class="lcd gridtext" x="150" y="275" text-anchor="middle" style="font-size:10.5px" fill="var(--muted)"></text>' +
      both(150, 322, 'the meter at the door', 'счётчик на вводе', 'lbl', 'middle') +
      '<text class="lcd clk" x="16" y="30" style="font-size:15px"></text>' +
      '<text class="lcd pvtext" x="744" y="30" text-anchor="end" style="font-size:13px"></text>' +
      '</svg>'
    );
  }

  App.Scene = function (container) {
    count += 1;
    container.innerHTML = markup('scene' + count);
    var svg = container.querySelector('svg');
    function q(selector) {
      return svg.querySelector(selector);
    }
    var parts = {
      sun: q('.sun'),
      disc: q('.disc'),
      cloud: q('.cloud'),
      panelglow: q('.panelglow'),
      power: q('.flow.power'),
      grid: q('.flow.grid'),
      needle: q('.needle'),
      gridtext: q('.gridtext'),
      amps: q('.amps'),
      plug: q('.plug'),
      batteryfill: q('.batteryfill'),
      window: q('.window'),
      window2: q('.window2'),
      clk: q('.clk'),
      pvtext: q('.pvtext'),
    };

    function flow(node, fraction) {
      if (fraction > 0.002) {
        node.classList.add('on');
        node.style.setProperty('--flow-s', (2.0 - 1.6 * Math.min(1, fraction)).toFixed(2) + 's');
      } else {
        node.classList.remove('on');
      }
    }

    return {
      /* s: {clock, pv, house, car, grid, amps, phases, soc, cloud, loads} */
      update: function (s) {
        var peak = 6000;
        parts.clk.textContent = App.clock(s.clock);
        parts.clk.setAttribute('fill', 'var(--ink)');
        parts.pvtext.textContent = App.t('the roof is making ', 'крыша даёт ') + App.watts(s.pv);
        parts.pvtext.setAttribute('fill', 'var(--muted)');

        var brightness = Math.min(1, s.pv / peak);
        parts.disc.setAttribute('r', (18 + 10 * brightness).toFixed(1));
        parts.sun.setAttribute('opacity', (0.35 + 0.65 * brightness).toFixed(2));
        parts.panelglow.setAttribute('opacity', (0.55 * brightness).toFixed(2));
        parts.cloud.setAttribute('opacity', s.cloud < 0.98 ? Math.min(1, (1 - s.cloud) * 1.6).toFixed(2) : '0');

        flow(parts.power, s.car / 7000);
        flow(parts.grid, Math.abs(s.grid) / 3000);
        parts.grid.classList.toggle('buying', s.grid > 0);
        parts.grid.setAttribute('d', s.grid > 0 ? 'M70 212 L 228 212' : 'M228 212 L 70 212');

        // the needle: zero in the middle, three kilowatts at either end
        var span = Math.max(-1, Math.min(1, s.grid / 3000));
        var angle = span * 70;
        parts.needle.setAttribute('transform', 'rotate(' + angle.toFixed(1) + ' 150 266)');
        parts.needle.setAttribute('stroke', Math.abs(s.grid) < 120 ? 'var(--ok)' : 'var(--bad)');
        parts.gridtext.textContent =
          Math.abs(s.grid) < 50
            ? App.t('balanced', 'в ноль')
            : (s.grid > 0 ? App.t('buying ', 'покупаем ') : App.t('selling ', 'отдаём ')) + App.watts(Math.abs(s.grid));

        parts.amps.textContent = s.amps ? App.amps(s.amps, s.phases) : App.t('nothing', 'ничего');
        parts.amps.setAttribute('fill', s.amps ? 'var(--ink)' : 'var(--muted)');
        parts.plug.setAttribute('stroke', s.amps ? 'var(--roof)' : 'var(--line)');
        parts.batteryfill.setAttribute('width', (40 * Math.min(1, s.soc || 0)).toFixed(1));

        var busy = (s.loads || []).length > 0;
        parts.window.setAttribute('fill', busy ? 'var(--sun-fill)' : 'var(--sunk)');
        parts.window2.setAttribute('fill', busy ? 'var(--sun-fill)' : 'var(--sunk)');
      },
    };
  };

  App.snapshotOf = function (house) {
    return {
      clock: house.clock,
      pv: house.pvW(),
      house: house.houseW(),
      car: house.carW(),
      grid: house.gridW(),
      amps: house.offered_a,
      phases: house.phases,
      soc: house.car.soc(),
      cloud: house.inverter.sky.cloudFactor(house.clock),
      loads: house.household.running(house.clock),
    };
  };
  void Twin;
})();
