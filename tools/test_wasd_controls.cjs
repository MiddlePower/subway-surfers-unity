// Run with: node tools/test_wasd_controls.cjs
// Uses a fake DOM so tests do not need the commercial game files.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class FakeKeyboardEvent {
  constructor(type, options) {
    this.type = type;
    Object.assign(this, options);
    this.keyCode = 0;
    this.which = 0;
    this.defaultPrevented = false;
    this.stopped = false;
  }
  preventDefault() { this.defaultPrevented = true; }
  stopImmediatePropagation() { this.stopped = true; }
}

const listeners = new Map();
const received = [];
const window = {
  addEventListener(type, callback) {
    const list = listeners.get(type) || [];
    list.push(callback);
    listeners.set(type, list);
  },
};
const canvas = {
  dispatchEvent(event) {
    received.push(event);
    for (const listener of (listeners.get(event.type) || [])) listener(event);
    return !event.defaultPrevented;
  },
};
const document = { querySelector(q) { return q === '#game canvas' ? canvas : null; } };
const source = fs.readFileSync(__dirname + '/wasd-controls.js', 'utf8');
const context = vm.createContext({ window, document, KeyboardEvent: FakeKeyboardEvent, WeakSet, Set, Boolean });
vm.runInContext(source, context);

function native(type, code, extras={}) {
  const original = new FakeKeyboardEvent(type, {
    code,
    key: code.startsWith('Key') ? code.slice(-1).toLowerCase() : code,
    repeat: false,
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    shiftKey: false,
    target: { closest() { return null; } },
    ...extras,
  });
  for (const callback of listeners.get(type) || []) callback(original);
  return original;
}

const expected = [ ['KeyW','ArrowUp',38], ['KeyA','ArrowLeft',37], ['KeyS','ArrowDown',40], ['KeyD','ArrowRight',39] ];
for (const [code, arrow, keyCode] of expected) {
  const before = received.length;
  const down = native('keydown', code);
  assert.equal(down.stopped, true);
  assert.equal(down.defaultPrevented, true);
  assert.equal(received.length, before+1);
  assert.equal(received.at(-1).key, arrow);
  assert.equal(received.at(-1).code, arrow);
  assert.equal(received.at(-1).keyCode, keyCode);
  assert.equal(received.at(-1).which, keyCode);
  assert.equal(received.at(-1).type, 'keydown');
  native('keyup', code);
  assert.equal(received.at(-1).type, 'keyup');
  assert.equal(received.at(-1).key, arrow);
}
assert.equal(received.length,8);
const arrow = native('keydown','ArrowLeft');
assert.equal(arrow.stopped,false);
assert.equal(received.length,8);
const ctrl = native('keydown','KeyW',{ctrlKey:true});
assert.equal(ctrl.stopped,false);
const editable = native('keydown','KeyW',{target:{closest(){return true;}}});
assert.equal(editable.stopped,false);
assert.equal(received.length,8);
native('keydown','KeyW');
assert.equal(received.at(-1).type,'keydown');
for(const f of listeners.get('blur')) f();
assert.equal(received.at(-1).type,'keyup');
assert.equal(received.at(-1).key,'ArrowUp');
console.log('WASD mapping, arrow compatibility, editable fields, modifiers, and blur tests passed');
