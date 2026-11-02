/**
 * Fallback for the WebGL game's hoverboard controls.
 *
 * The game's saved-inventory delta is NOT a reliable activation signal:
 * this particular Unity build does not call IncreaseAmount(-1) when the
 * board is used. The website therefore recognizes the documented browser
 * activation gestures (Space and double-tap) WHILE a timed run is active.
 *
 * Limitation: this detects an activation ATTEMPT, not whether the game
 * accepted it (cooldown, disabled activation, etc.). A verified native
 * activation hook is preferred and disables this fallback.
 */
(() => {
  'use strict';

  if (window.__runnerBoardInputLoaded) return;
  window.__runnerBoardInputLoaded = true;
  if (document.body?.dataset.runMode !== 'no-coin') return;

  const stage = document.getElementById('challenge-stage');
  const host = document.getElementById('challenge-game');
  if (!stage || !host) return;

  let lastTouch = null;

  function running() {
    return window.RunnerRunTimer?.snapshot()?.state === 'running';
  }

  function announce() {
    if (!running()) return;
    window.dispatchEvent(new CustomEvent('runner-game-event', {
      detail: { kind: 'hoverboard', source: 'input-fallback' },
    }));
  }

  function editable(target) {
    return !!target?.closest?.('input,textarea,select,button,a,[contenteditable]');
  }

  window.addEventListener('keydown', event => {
    if ((event.code === 'Space' || event.key === ' ') &&
        !event.repeat && !event.ctrlKey && !event.altKey && !event.metaKey &&
        !editable(event.target)) {
      announce();
    }
  }, { capture: true });

  // Mouse double-click maps to the WebGL game's double-tap gesture.
  host.addEventListener('dblclick', announce, { capture: true });

  host.addEventListener('pointerdown', event => {
    if (event.pointerType !== 'touch' || !running()) return;
    const at = performance.now();
    const x = event.clientX, y = event.clientY;
    if (lastTouch && at - lastTouch.at < 350 &&
        Math.hypot(x - lastTouch.x, y - lastTouch.y) < 55) announce();
    lastTouch = { at, x, y };
  }, { capture: true });
})();
