/**
 * Add optional WASD controls to the existing Unity WebGL keyboard controls.
 * W / A / S / D mirror Up / Left / Down / Right arrow keys.
 *
 * Unity's 2019 Emscripten input layer listens to DOM keyboard events and
 * consumes key, code, keyCode and which. This forwards all four values.
 */
(() => {
  'use strict';

  // The generated test pages reuse index.html; do not register twice.
  if (window.__runnerWasdControlsLoaded) return;
  window.__runnerWasdControlsLoaded = true;

  const keys = {
    KeyW: { key: 'ArrowUp', code: 'ArrowUp', keyCode: 38 },
    KeyA: { key: 'ArrowLeft', code: 'ArrowLeft', keyCode: 37 },
    KeyS: { key: 'ArrowDown', code: 'ArrowDown', keyCode: 40 },
    KeyD: { key: 'ArrowRight', code: 'ArrowRight', keyCode: 39 },
  };
  const fallback = { w: 'KeyW', a: 'KeyA', s: 'KeyS', d: 'KeyD' };
  const forwarded = new WeakSet();
  const held = new Set();

  function editable(target) {
    if (!target || typeof target.closest !== 'function') return false;
    return Boolean(target.closest('input,textarea,select,[contenteditable], [role="textbox"]'));
  }

  function keyCodeFrom(event) {
    const code = event.code || fallback[(event.key || '').toLowerCase()];
    return keys[code] ? code : null;
  }

  function arrowEvent(type, original, mapping) {
    const translated = new KeyboardEvent(type, {
      bubbles: true,
      cancelable: true,
      composed: true,
      key: mapping.key,
      code: mapping.code,
      location: 0,
      repeat: Boolean(original && original.repeat),
      ctrlKey: Boolean(original && original.ctrlKey),
      shiftKey: Boolean(original && original.shiftKey),
      altKey: false,
      metaKey: false,
    });
    Object.defineProperties(translated, {
      keyCode: { configurable: true, get: () => mapping.keyCode },
      which: { configurable: true, get: () => mapping.keyCode },
      charCode: { configurable: true, get: () => 0 },
    });
    forwarded.add(translated);
    // Canvas -> document -> window bubbling covers Emscripten callbacks
    // regardless of which of those three targets Unity subscribes to.
    const target = document.querySelector('#game canvas') || document.querySelector('canvas') || document;
    target.dispatchEvent(translated);
  }

  function onKey(event) {
    if (forwarded.has(event)) return;
    const physicalKey = keyCodeFrom(event);
    if (!physicalKey) return;

    if (event.type === 'keydown') {
      if (event.ctrlKey || event.metaKey || event.altKey || editable(event.target)) return;
      held.add(physicalKey);
    } else if (!held.has(physicalKey)) {
      return;
    } else {
      held.delete(physicalKey);
    }

    event.preventDefault();
    event.stopImmediatePropagation();
    arrowEvent(event.type, event, keys[physicalKey]);
  }

  window.addEventListener('keydown', onKey, true);
  window.addEventListener('keyup', onKey, true);
  // If focus leaves the tab mid-keypress, release the corresponding arrow.
  window.addEventListener('blur', () => {
    for (const physicalKey of held) arrowEvent('keyup', null, keys[physicalKey]);
    held.clear();
  });
})();
