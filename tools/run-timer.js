/**
 * No-Coin Challenge stopwatch.
 *
 * Uses the Unity game's actual PokiSDK gameplayStart/roundStart and
 * gameplayStop/roundEnd calls as run lifecycle notifications. It does not
 * guess from key presses or start when the game is still on the menu.
 *
 * The overlay is independent of Unity's compiled game and is deliberately
 * non-interactive, so controls keep working.
 */
(() => {
  'use strict';

  if (window.__runnerTimerLoaded) return;
  window.__runnerTimerLoaded = true;

  const LIFECYCLE_EVENTS = ['gameplayStart', 'roundStart', 'gameplayStop', 'roundEnd'];
  const WRAPPED = Symbol('runner-timer-hook');

  let state = 'ready';
  let startedAt = 0;
  let elapsedMs = 0;
  let stoppedBy = null;
  let frameId = null;
  let labelNode = null;
  let timeNode = null;
  let panel = null;

  function now() {
    return performance.now();
  }

  function formatted(milliseconds) {
    const centiseconds = Math.floor(Math.max(0, milliseconds) / 10);
    const minutes = Math.floor(centiseconds / 6000);
    const seconds = Math.floor(centiseconds / 100) % 60;
    const hundredths = centiseconds % 100;
    return (
      String(minutes).padStart(2, '0') + ':' +
      String(seconds).padStart(2, '0') + '.' +
      String(hundredths).padStart(2, '0')
    );
  }

  function currentElapsed() {
    return state === 'running' ? Math.max(0, now() - startedAt) : elapsedMs;
  }

  function announceState() {
    const ms = currentElapsed();
    window.dispatchEvent(new CustomEvent('runner-timer-state', {
      detail: { state, elapsedMs: ms, formatted: formatted(ms), reason: stoppedBy },
    }));
  }

  function draw() {
    if (!panel) return;
    labelNode.textContent = (
      state === 'running' ? 'RUN TIME' :
      state === 'finished' ? (stoppedBy === 'coin' ? 'COIN PICKED UP' :
        stoppedBy === 'hoverboard' ? 'HOVERBOARD USED' : 'FINAL TIME') : 'NO-COIN TIMER'
    );
    timeNode.textContent = formatted(currentElapsed());
    panel.dataset.state = state;
  }

  function tick() {
    frameId = null;
    if (state !== 'running') return;
    draw();
    frameId = requestAnimationFrame(tick);
  }

  function start() {
    if (state === 'running') return;
    if (frameId !== null) cancelAnimationFrame(frameId);
    elapsedMs = 0;
    startedAt = now();
    state = 'running';
    stoppedBy = null;
    draw();
    announceState();
    frameId = requestAnimationFrame(tick);
  }

  function stop(reason = 'game-over') {
    if (state !== 'running') return;
    elapsedMs = Math.max(0, now() - startedAt);
    state = 'finished';
    stoppedBy = reason;
    if (frameId !== null) cancelAnimationFrame(frameId);
    frameId = null;
    draw();
    announceState();
  }

  // Signals originate only from the local patched Unity bridge.
  // Original game/SDK events still govern regular death and run resets.
  window.addEventListener('runner-game-event', event => {
    const kind = event.detail?.kind;
    if (kind === 'coin' || kind === 'hoverboard') stop(kind);
  });

  function record(event, args) {
    // Ignore unrelated SDK rounds if the provider passes a round label.
    if ((event === 'roundStart' || event === 'roundEnd') &&
        args.length && args[0] !== 'run') return;

    if (event === 'gameplayStart' || event === 'roundStart') start();
    else if (event === 'gameplayStop' || event === 'roundEnd') stop();

    // The optional bridge inspector listens to this instead of separately
    // wrapping the same SDK methods (which would cause competing wrappers).
    window.dispatchEvent(new CustomEvent('runner-sdk-lifecycle', {
      detail: { name: event, args: Array.from(args) },
    }));
  }

  function observeSdk() {
    const sdk = window.PokiSDK;
    if (!sdk) return;
    for (const event of LIFECYCLE_EVENTS) {
      const original = sdk[event];
      if (typeof original !== 'function' || original[WRAPPED]) continue;
      const wrapped = function (...args) {
        record(event, args);
        return original.apply(this, args);
      };
      Object.defineProperty(wrapped, WRAPPED, { value: true });
      try {
        sdk[event] = wrapped;
      } catch (error) {
        console.warn('[No-coin timer] Cannot observe', event, error);
      }
    }
  }

  function createOverlay() {
    if (panel || !document.body) return;
    panel = document.createElement('div');
    panel.id = 'no-coin-timer';
    panel.setAttribute('aria-label', 'No-Coin Challenge run timer');
    panel.style.cssText = [
      'position:absolute',
      'top:12px',
      'left:50%',
      'transform:translateX(-50%)',
      'z-index:2147483000',
      'pointer-events:none',
      'user-select:none',
      'min-width:138px',
      'padding:8px 15px 10px',
      'box-sizing:border-box',
      'border:1px solid rgba(255,255,255,.24)',
      'border-radius:12px',
      'background:rgba(12,20,30,.84)',
      'box-shadow:0 4px 16px rgba(0,0,0,.22)',
      'color:#fff',
      'text-align:center',
      'font-family:system-ui,-apple-system,Segoe UI,sans-serif',
      'font-variant-numeric:tabular-nums',
    ].join(';');
    labelNode = document.createElement('div');
    labelNode.style.cssText = 'font-size:10px;font-weight:750;letter-spacing:1.5px;color:#a8e7ef';
    timeNode = document.createElement('div');
    timeNode.style.cssText = 'font-size:28px;font-weight:800;line-height:1.2;white-space:nowrap';
    panel.append(labelNode, timeNode);
    // Keep the timer attached to the game: scrolling to records should
    // not leave a floating timer covering the statistics section.
    const stage = typeof document.getElementById === 'function'
      ? document.getElementById('challenge-stage') : null;
    (stage || document.body).appendChild(panel);
    draw();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', createOverlay, { once: true });
  } else {
    createOverlay();
  }

  // PokiSDK is created asynchronously by master-loader.js and may later be
  // replaced by poki-sdk-core. Re-observe replacements without stacking hooks.
  observeSdk();
  setInterval(observeSdk, 100);
  document.addEventListener('visibilitychange', draw);

  window.RunnerRunTimer = Object.freeze({
    snapshot: () => ({ state, elapsedMs: currentElapsed(), formatted: formatted(currentElapsed()), reason: stoppedBy }),
  });
})();
