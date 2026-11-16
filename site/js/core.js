/* Shared helpers: language, a small DOM builder, number formats, and the plain words for the things
   the controller says to itself. */
(function () {
  'use strict';
  var SPEC = window.SPEC_DATA;
  var App = (window.App = { views: {}, lang: 'en', SPEC: SPEC });

  // ---- language ---------------------------------------------------------------------------------

  var langListeners = [];
  App.onLang = function (fn) {
    langListeners.push(fn);
  };
  App.t = function (en, ru) {
    return App.lang === 'ru' ? ru : en;
  };
  App.setLang = function (lang, silent) {
    App.lang = lang === 'ru' ? 'ru' : 'en';
    var html = document.documentElement;
    html.setAttribute('data-lang', App.lang);
    html.setAttribute('lang', App.lang);
    document.getElementById('lang-en').setAttribute('aria-pressed', String(App.lang === 'en'));
    document.getElementById('lang-ru').setAttribute('aria-pressed', String(App.lang === 'ru'));
    try {
      localStorage.setItem('lang', App.lang);
    } catch (e) {
      /* storage is optional */
    }
    if (!silent)
      langListeners.forEach(function (fn) {
        fn();
      });
  };
  App.initialLang = function () {
    var saved = null;
    try {
      saved = localStorage.getItem('lang');
    } catch (e) {
      /* storage is optional */
    }
    if (saved === 'ru' || saved === 'en') return saved;
    return /^ru/i.test(navigator.language || '') ? 'ru' : 'en';
  };

  // ---- DOM ----------------------------------------------------------------------------------------

  App.h = function (tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs)
      Object.keys(attrs).forEach(function (key) {
        var value = attrs[key];
        if (value === null || value === undefined || value === false) return;
        if (key.slice(0, 2) === 'on') node.addEventListener(key.slice(2), value);
        else if (key === 'html') node.innerHTML = value;
        else node.setAttribute(key, value === true ? '' : value);
      });
    (Array.isArray(children) ? children : children === undefined ? [] : [children]).forEach(function (child) {
      if (child === null || child === undefined || child === false) return;
      node.appendChild(typeof child === 'object' ? child : document.createTextNode(String(child)));
    });
    return node;
  };
  App.clear = function (node) {
    while (node.firstChild) node.removeChild(node.firstChild);
    return node;
  };
  App.both = function (en, ru) {
    var frag = document.createDocumentFragment();
    frag.appendChild(App.h('span', { class: 'en' }, en));
    frag.appendChild(App.h('span', { class: 'ru' }, ru));
    return frag;
  };

  // ---- formats ------------------------------------------------------------------------------------

  App.num = function (value, digits) {
    return Number(value).toLocaleString(App.lang === 'ru' ? 'ru-RU' : 'en-US', {
      minimumFractionDigits: digits || 0,
      maximumFractionDigits: digits || 0,
    });
  };
  App.clock = function (seconds, withSeconds) {
    var s = ((seconds % 86400) + 86400) % 86400;
    var hh = Math.floor(s / 3600);
    var mm = Math.floor((s % 3600) / 60);
    var text = (hh < 10 ? '0' : '') + hh + ':' + (mm < 10 ? '0' : '') + mm;
    if (withSeconds) text += ':' + (s % 60 < 10 ? '0' : '') + (s % 60);
    return text;
  };
  App.watts = function (value) {
    var w = Math.round(value);
    if (Math.abs(w) >= 1000) return App.num(w / 1000, 1) + ' ' + App.t('kW', 'кВт');
    return App.num(w) + ' ' + App.t('W', 'Вт');
  };
  App.kwh = function (wh) {
    return App.num(wh / 1000, 1) + ' ' + App.t('kWh', 'кВт·ч');
  };
  App.wh = function (value) {
    if (Math.abs(value) >= 1000) return App.kwh(value);
    return App.num(value) + ' ' + App.t('Wh', 'Вт·ч');
  };
  App.amps = function (value, phases) {
    if (!value) return App.t('nothing', 'ничего');
    return App.num(value) + ' ' + App.t('A', 'А') + (phases ? ' × ' + phases : '');
  };

  // ---- what the controller says to itself, in plain words -------------------------------------------

  var WHY = {
    'no change': ['nothing changed', 'ничего не изменилось'],
    'the meter has gone quiet': ['the meter has gone quiet, so stop', 'счётчик замолчал — остановиться'],
    'no car on the cable': ['no car on the cable', 'на кабеле нет машины'],
    'not enough sun for the smallest charge': [
      'not enough sun for the smallest charge there is',
      'солнца не хватает даже на самый маленький заряд',
    ],
    'the sun has been short for too long': [
      'the sun has been short for too long: let go',
      'солнца не хватает слишком долго — отпустить',
    ],
    'riding out the shadow has cost enough': [
      'riding out the shadow has cost enough: let go',
      'переждать тень обошлось дорого — отпустить',
    ],
    'riding out a short shortage at 6 A': [
      'holding the floor through a passing shadow',
      'держим минимум, пока тень проходит',
    ],
    'waiting to be sure the sun is back': ['waiting to be sure the sun is back', 'ждём, точно ли солнце вернулось'],
    'the sun is back for good': ['the sun is back for good: start again', 'солнце вернулось — начинаем снова'],
    'less sun, giving the car less at once': [
      'less sun: give the car less, at once',
      'солнца меньше — сразу даём машине меньше',
    ],
    'the surplus has held, giving the car more': [
      'the surplus has held: give the car more',
      'излишек держится — даём машине больше',
    ],
  };
  App.whyWords = function (why) {
    if (!why) return '';
    var row = WHY[why];
    if (row) return App.t(row[0], row[1]);
    var match = /^switching to (\d) phase\(s\)$/.exec(why);
    if (match) {
      return App.t(
        'rewiring to ' + (match[1] === '1' ? 'one phase' : 'three phases'),
        'переключаем на ' + (match[1] === '1' ? 'одну фазу' : 'три фазы')
      );
    }
    return why;
  };

  // ---- test titles and the rest of the Russian --------------------------------------------------------

  var RU = window.RU_DATA || { tests: {}, steps: [], mutants: {}, suites: {}, areas: {} };
  var stepPatterns = (RU.steps || []).map(function (pair) {
    return [new RegExp('^' + pair[0] + '$'), pair[1]];
  });
  App.testTitle = function (test) {
    return App.lang === 'ru' && RU.tests[test.name] ? RU.tests[test.name] : test.title;
  };
  App.stepText = function (text) {
    if (App.lang !== 'ru') return text;
    for (var i = 0; i < stepPatterns.length; i++) {
      if (stepPatterns[i][0].test(text)) return text.replace(stepPatterns[i][0], stepPatterns[i][1]);
    }
    return text;
  };
  App.suiteName = function (suite) {
    var row = RU.suites[suite];
    return row ? App.t(row[0], row[1]) : suite;
  };
  App.suiteBlurb = function (suite) {
    var row = RU.suites[suite];
    return row ? App.t(row[2], row[3]) : '';
  };
  App.mutantTitle = function (mutant) {
    return App.lang === 'ru' && RU.mutants[mutant.id] ? RU.mutants[mutant.id] : mutant.title;
  };
  App.areaName = function (area) {
    var row = (RU.areas || {})[area];
    return row ? App.t(row[0], row[1]) : area;
  };
  App.dayName = function (id) {
    var row = (window.DAY_DATA.words || {})[id];
    return row ? App.t(row[0], row[1]) : id;
  };
  App.dayBlurb = function (id) {
    var row = (window.DAY_DATA.words || {})[id];
    return row ? App.t(row[2], row[3]) : '';
  };
  App.RU = RU;
})();
