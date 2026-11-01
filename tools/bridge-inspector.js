/**
 * Optional read-only Unity WebGL diagnostics.
 * Append ?inspect=1 to the local URL. No network requests or game edits.
 */
(() => {
  'use strict';
  if (new URLSearchParams(location.search).get('inspect') !== '1') return;
  const events = [];
  const hooked = Symbol('bridge-probe');
  const methods = ['customEvent', 'sendHighscore', 'gameplayStart', 'gameplayStop', 'roundStart', 'roundEnd'];
  let output;

  function log(name, args = []) {
    const safeArgs = Array.from(args, value =>
      typeof value === 'string' ? value.slice(0, 200) :
      typeof value === 'number' || typeof value === 'boolean' ? value : '[object]');
    events.push({ time: new Date().toISOString(), name, args: safeArgs });
    if (events.length > 80) events.shift();
    console.debug('[Bridge probe]', events[events.length - 1]);
    render();
  }

  function render() {
    if (!output) return;
    output.textContent = [
      'Unity loaded: ' + Boolean(window.unityGame),
      'SendMessage available: ' + (typeof window.unityGame?.SendMessage === 'function'),
      'Poki bridge: ' + String(window.pokiBridge || '(unknown)'),
      'Events observed: ' + events.length,
      'Compare logs before and after collecting a coin.',
      '',
      ...events.slice(-15).map(e => e.time.slice(11, 19) + ' ' + e.name + '(' + e.args.join(', ') + ')')
    ].join('\n');
  }

  function observe() {
    const sdk = window.PokiSDK;
    if (sdk && typeof sdk === 'object') {
      for (const name of methods) {
        const original = sdk[name];
        if (typeof original !== 'function' || original[hooked]) continue;
        try {
          const replacement = function (...args) {
            log('PokiSDK.' + name, args);
            return original.apply(this, args);
          };
          replacement[hooked] = true;
          sdk[name] = replacement;
        } catch (err) { console.warn('[Bridge probe] Could not observe', name, err); }
      }
    }
    render();
  }

  function panel() {
    const box = document.createElement('section');
    box.style.cssText = 'position:fixed;z-index:2147483647;right:12px;top:12px;width:min(430px,calc(100vw - 24px));max-height:50vh;overflow:auto;padding:12px;border:1px solid #45d8ee;border-radius:12px;background:#101923f5;color:#fff;font:12px/1.5 monospace';
    const title = document.createElement('strong');
    title.textContent = 'Unity bridge inspector (read only)';
    output = document.createElement('pre');
    output.style.cssText = 'white-space:pre-wrap;overflow-wrap:anywhere';
    const copy = document.createElement('button');
    copy.textContent = 'Copy log';
    copy.addEventListener('click', () => {
      navigator.clipboard.writeText(JSON.stringify(events, null, 2))
        .then(() => { copy.textContent = 'Copied'; })
        .catch(err => console.warn('Could not copy log', err));
    });
    box.append(title, output, copy);
    document.body.append(box);
    render();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', panel);
  else panel();
  window.RunnerBridgeProbe = Object.freeze({ getEvents: () => events.slice() });
  setInterval(observe, 350);
})();
