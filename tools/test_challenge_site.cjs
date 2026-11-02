// Run: node tools/test_challenge_site.cjs
// Purely synthetic browser checks for scrollable challenge records.
// Does not require a Unity build or internet access.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Node {
  constructor(tag='div') {
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.style = {};
    this.textContent = '';
    this.parentElement = null;
    this.attributes = {};
    this.hidden = false;
  }
  appendChild(el) {
    this.children.push(el);
    el.parentElement = this;
    return el;
  }
  append(...els) { for (const el of els) this.appendChild(el); }
  replaceChildren(...els) { this.children = []; this.append(...els); }
  setAttribute(key, val) { this.attributes[key] = val; }
  getBoundingClientRect() { return {top: 0, bottom: 900}; }
  querySelector() { return this.children[1] || null; }
  closest() { return null; }
}

function boot(mode, saved) {
  let ms = 0;
  const listeners = new Map();
  const intervals = [];
  const nodes = new Map();
  const body = new Node('body');
  body.dataset.runMode = mode;
  const stage = new Node('section');
  const game = new Node('div');
  const fullscreen = new Node('button');
  fullscreen.appendChild(new Node('span'));
  fullscreen.appendChild(new Node('span'));
  const best = new Node();
  const last = new Node();
  const total = new Node();
  const history = new Node('ol');
  const note = new Node('p');
  for (const [id, el] of Object.entries({
    'challenge-stage': stage,
    'challenge-game': game,
    'challenge-fullscreen': fullscreen,
    'best-score': best,
    'last-score': last,
    'total-runs': total,
    'run-history': history,
    'storage-message': note,
  })) nodes.set(id, el);
  let frameId = 0;
  const addListener = (k, fn) => listeners.set(k, [...(listeners.get(k) || []), fn]);
  const dispatch = (event) => {
    for (const fn of listeners.get(event.type) || []) fn(event);
  };
  const doc = {
    body,
    readyState: 'complete',
    fullscreenElement: null,
    getElementById(id) { return nodes.get(id) || null; },
    createElement(tag) { return new Node(tag); },
    addEventListener(k, fn) { addListener('doc.'+k, fn); },
    dispatchEvent(e) { for(const fn of listeners.get('doc.'+e.type)||[]) fn(e); },
  };
  const win = {
    innerHeight: 900,
    addEventListener: addListener,
    dispatchEvent: dispatch,
  };
  const storage = {
    getItem(key) { return saved[key] || null; },
    setItem(key, value) { saved[key] = value; },
  };
  const context = vm.createContext({
    window: win, document: doc, localStorage: storage,
    MutationObserver: class { observe() {} },
    CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
    performance: { now() { return ms; } },
    requestAnimationFrame() { return ++frameId; },
    cancelAnimationFrame() {},
    setInterval(fn) { intervals.push(fn); },
    console, Date,
  });
  for (const file of ['challenge-site.js', 'run-timer.js']) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, file), 'utf8'), context, {filename:file});
  }
  const poki = {
    gameplayStart() {}, roundStart() {}, gameplayStop() {}, roundEnd() {},
  };
  win.PokiSDK = poki;
  for (const fn of intervals) fn();
  return {
    win, poki, stage, game, best, last, total, history, note, saved,
    setTime(next) { ms = next; },
  };
}

const stored = {};
const game = boot('no-coin', stored);
assert.equal(game.best.textContent, '--:--.--');
assert.equal(game.last.textContent, '--:--.--');
assert.equal(game.total.textContent, '0');

game.setTime(1000);
game.poki.gameplayStart('run');
game.setTime(6250);
game.poki.roundEnd('run');
game.poki.gameplayStop(); // duplicate end must not record twice
assert.equal(game.best.textContent, '00:05.25');
assert.equal(game.last.textContent, '00:05.25');
assert.equal(game.total.textContent, '1');

game.setTime(7000);
game.poki.roundStart('run');
game.poki.gameplayStart('run'); // duplicate start must not reset
game.setTime(8000);
game.poki.gameplayStop();
assert.equal(game.best.textContent, '00:05.25');
assert.equal(game.last.textContent, '00:01.00');
assert.equal(game.total.textContent, '2');
assert.equal(game.history.children.length, 2);
assert.equal(game.win.RunnerRunTimer.snapshot().formatted, '00:01.00');

const reloaded = boot('no-coin', stored);
assert.equal(reloaded.best.textContent, '00:05.25');
assert.equal(reloaded.last.textContent, '00:01.00');
assert.equal(reloaded.total.textContent, '2');

const original = boot('standard', stored);
original.setTime(5000);
original.poki.gameplayStart('run');
original.setTime(45000);
original.poki.gameplayStop();
assert.equal(original.total.textContent, '2', 'base game must not update No-Coin record');
assert.equal(JSON.parse(stored['no-coin-challenge.records.v1']).completedRuns, 2);

console.log('PASS: best time, last time, run history, persisted records, no duplicate counting, standard game excluded');
