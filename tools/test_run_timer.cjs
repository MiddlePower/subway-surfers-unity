// Run: node tools/test_run_timer.cjs
// Browser-independent tests for run start/end, duplicate SDK events and resets.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

let clock = 0;
const intervals = [];
const frames = new Map();
let nextFrame = 0;
const listeners = new Map();

class FakeNode {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.style = {};
    this.textContent = '';
    this.attributes = {};
  }
  append(...nodes) { this.children.push(...nodes); }
  appendChild(node) { this.children.push(node); return node; }
  setAttribute(name, value) { this.attributes[name] = value; }
}

class FakeCustomEvent {
  constructor(type, options) { this.type = type; this.detail = options.detail; }
}

const document = {
  readyState: 'complete',
  body: new FakeNode('body'),
  createElement: tag => new FakeNode(tag),
  addEventListener: (name, fn) => {
    if (!listeners.has('document:' + name)) listeners.set('document:' + name, []);
    listeners.get('document:' + name).push(fn);
  },
};
const window = {
  addEventListener(name, fn) {
    if (!listeners.has(name)) listeners.set(name, []);
    listeners.get(name).push(fn);
  },
  dispatchEvent(evt) {
    for (const fn of listeners.get(evt.type) || []) fn(evt);
  },
};
const context = vm.createContext({
  window, document,
  performance: { now: () => clock },
  requestAnimationFrame(fn) { frames.set(++nextFrame, fn); return nextFrame; },
  cancelAnimationFrame(id) { frames.delete(id); },
  setInterval(fn) { intervals.push(fn); return intervals.length; },
  CustomEvent: FakeCustomEvent, console,
});
vm.runInContext(fs.readFileSync(__dirname + '/run-timer.js', 'utf8'), context);

const timer = window.RunnerRunTimer;
assert.ok(timer, 'timer should be installed');
assert.equal(timer.snapshot().state, 'ready');
assert.equal(timer.snapshot().formatted, '00:00.00');
assert.equal(document.body.children.length, 1);
const panel = document.body.children[0];
assert.equal(panel.children[0].textContent, 'NO-COIN TIMER');

const sdk = {
  calls: [],
  gameplayStart(...args) { this.calls.push(['gameplayStart', ...args]); },
  roundStart(...args) { this.calls.push(['roundStart', ...args]); },
  gameplayStop(...args) { this.calls.push(['gameplayStop', ...args]); },
  roundEnd(...args) { this.calls.push(['roundEnd', ...args]); },
};
window.PokiSDK = sdk;
for (const f of intervals) f();
const observed = [];
window.addEventListener('runner-sdk-lifecycle', evt => observed.push(evt.detail.name));

sdk.roundStart('menu'); // Ignore other rounds.
assert.equal(timer.snapshot().state, 'ready');

clock = 1_000;
sdk.gameplayStart('run');
assert.equal(timer.snapshot().state, 'running');
assert.equal(timer.snapshot().formatted, '00:00.00');
clock = 13_345;
assert.equal(timer.snapshot().formatted, '00:12.34');

sdk.roundStart('run'); // Duplicate start must NOT reset the timer.
clock = 14_001;
assert.equal(timer.snapshot().formatted, '00:13.00');

sdk.gameplayStop();
assert.equal(timer.snapshot().state, 'finished');
assert.equal(timer.snapshot().formatted, '00:13.00');
assert.equal(panel.children[0].textContent, 'FINAL TIME');

clock = 19_000;
sdk.roundEnd('run'); // Duplicate stop must NOT mutate frozen time.
assert.equal(timer.snapshot().formatted, '00:13.00');
assert.deepEqual(sdk.calls.map(x => x[0]), ['roundStart', 'gameplayStart', 'roundStart', 'gameplayStop', 'roundEnd']);

clock = 20_000;
sdk.roundStart('run'); // A new run resets to zero.
assert.equal(timer.snapshot().state, 'running');
assert.equal(timer.snapshot().formatted, '00:00.00');
clock = 80_567;
assert.equal(timer.snapshot().formatted, '01:00.56');
sdk.roundEnd('run');
assert.equal(timer.snapshot().state, 'finished');
assert.equal(timer.snapshot().formatted, '01:00.56');

// The SDK might be replaced by its asynchronously loaded implementation.
const replacement = {
  gameplayStart() {},
  roundStart() {},
  gameplayStop() {},
  roundEnd() {},
};
window.PokiSDK = replacement;
for (const f of intervals) f();
clock = 81_000;
replacement.roundStart('run');
clock = 82_999;
replacement.roundEnd('run');
assert.equal(timer.snapshot().formatted, '00:01.99');
assert.equal(observed.length, 8);

console.log('Timer tests passed: start, stop, freeze, reset, duplicate events, SDK replacement and display');
