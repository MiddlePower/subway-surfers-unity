/**
 * Site shell and personal-best dashboard.
 *
 * The original Unity loader dynamically appends #game-container and #loader
 * to <body>, while assuming the page cannot scroll. We move those nodes into
 * a viewport-height section without touching the commercial game binary.
 *
 * Personal records are saved only for the separate No-Coin test page.
 * Normal/unmodified gameplay must never inflate a challenge high score.
 */
(() => {
  'use strict';

  const host = document.getElementById('challenge-game');
  const stage = document.getElementById('challenge-stage');
  const fullscreenButton = document.getElementById('challenge-fullscreen');
  const bestNode = document.getElementById('best-score');
  const lastNode = document.getElementById('last-score');
  const runsNode = document.getElementById('total-runs');
  const historyNode = document.getElementById('run-history');
  const storageNote = document.getElementById('storage-message');
  const isChallenge = document.body?.dataset.runMode === 'no-coin';
  const coinMode = document.body?.dataset.coinMode || 'game-over';
  const coinModeTarget = document.body?.dataset.coinModeTarget;
  const blitzMode = document.body?.dataset.blitzMode || 'off';
  const blitzTarget = document.body?.dataset.blitzTarget || '';
  const blitzToggle = document.getElementById('blitz-mode-toggle');
  const challengeSettings = document.getElementById('challenge-settings');
  const coinModeToggle = document.getElementById('coin-mode-toggle');
  const coinModeDescription = document.getElementById('coin-mode-description');
  const recordsIntro = document.getElementById('records-intro-description');
  const hoverboardRule = document.querySelector('.hoverboard-rule');
  if (blitzToggle) {
    blitzToggle.hidden = !isChallenge || !blitzTarget;
    if (!blitzToggle.hidden) {
      blitzToggle.href = blitzTarget;
      blitzToggle.textContent = blitzMode === 'on'
        ? 'Disable Blitz (normal speed)'
        : 'Enable Blitz (2.25× speed)';
    }
  }
  if (recordsIntro && isChallenge && coinMode === 'timer-only') {
    recordsIntro.textContent =
      'One coin freezes the clock, but you can keep playing. Survive as long as you can without coins or hoverboards.';
  }
  if (hoverboardRule && document.body?.dataset.runMode === 'no-coin') {
    hoverboardRule.textContent =
      'Space or double-tap stops the timer during a run (hoverboard input fallback). '
      + 'If the game rejects the board due to cooldown, the attempt still ends.';
  }
  if (hoverboardRule && document.body?.dataset.hoverboardHook === 'unavailable') {
    hoverboardRule.textContent =
      'Native hoverboard hook unavailable. Space or double-tap will stop the timer as an input fallback.';
  }

  // Changing the compiled Unity rule requires loading its companion private
  // test build. Both game pages share the same browser-local records.
  if (challengeSettings && coinModeToggle && coinModeDescription) {
    challengeSettings.hidden = !isChallenge || !coinModeTarget;
    if (isChallenge && coinModeTarget) {
      coinModeToggle.href = coinModeTarget;
      if (coinMode === 'timer-only') {
        coinModeToggle.textContent = 'Restore coin = game over';
        coinModeDescription.textContent =
          'Coin pickup freezes your timer, but the runner keeps going. Your first coin is your final challenge time.';
      } else {
        coinModeToggle.textContent = 'Coin = stop timer only';
        coinModeDescription.textContent =
          'Coin pickup ends the run. Switch modes to let the game continue after your timer stops.';
      }
    }
  }
  const STORAGE_KEY = 'no-coin-challenge.records.v1';
  const HISTORY_LIMIT = 40;
  let runInProgress = false;
  let storageAvailable = true;

  function moveLoaderIntoStage() {
    for (const id of ['loader', 'game-container']) {
      const element = document.getElementById(id);
      if (element && element.parentElement !== host) host.appendChild(element);
    }
  }

  // Unity injects its nodes after its scripts load, so attach the observer
  // before the asynchronous master-loader begins creating them.
  if (stage && host) {
    moveLoaderIntoStage();
    const observer = new MutationObserver(moveLoaderIntoStage);
    observer.observe(document.body, { childList: true });
  }

  // Keep arrow keys and Space from scrolling while the game is in view.
  // preventDefault does not stop Unity from receiving the keyboard event.
  window.addEventListener('keydown', event => {
    if (!stage || !(event.key.startsWith('Arrow') || event.key === ' ')) return;
    const target = event.target;
    if (target && typeof target.closest === 'function' &&
        target.closest('input,textarea,select,[contenteditable],button,a')) return;
    const rect = stage.getBoundingClientRect();
    if (rect.top <= 0 && rect.bottom >= window.innerHeight * 0.5) {
      event.preventDefault();
    }
  }, { capture: true });

  if (fullscreenButton) {
    const updateFullscreen = () => {
      const active = document.fullscreenElement === stage;
      fullscreenButton.querySelector('span:last-child').textContent =
        active ? 'Exit fullscreen' : 'Fullscreen';
      fullscreenButton.setAttribute('aria-label',
        active ? 'Exit game fullscreen' : 'Enter game fullscreen');
    };
    fullscreenButton.addEventListener('click', async () => {
      try {
        if (document.fullscreenElement === stage) {
          await document.exitFullscreen();
        } else if (stage.requestFullscreen) {
          await stage.requestFullscreen();
        }
      } catch (error) {
        console.warn('[No-Coin] Fullscreen unavailable:', error);
      }
      updateFullscreen();
    });
    document.addEventListener('fullscreenchange', updateFullscreen);
    if (typeof stage.requestFullscreen !== 'function') fullscreenButton.hidden = true;
  }

  function blankRecords() {
    return { bestMs: null, lastMs: null, completedRuns: 0, history: [] };
  }

  function validMs(value) {
    return typeof value === 'number' && Number.isFinite(value) &&
      value >= 0 && value <= 86_400_000;
  }

  function loadRecords() {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (!stored) return blankRecords();
      const value = JSON.parse(stored);
      if (!value || typeof value !== 'object') return blankRecords();
      const history = Array.isArray(value.history)
        ? value.history.filter(item => item && validMs(item.ms) &&
          Number.isFinite(item.at) && item.at > 0).slice(0, HISTORY_LIMIT)
        : [];
      return {
        bestMs: validMs(value.bestMs) ? value.bestMs : null,
        lastMs: validMs(value.lastMs) ? value.lastMs : null,
        completedRuns: Number.isSafeInteger(value.completedRuns) && value.completedRuns >= 0
          ? value.completedRuns : history.length,
        history,
      };
    } catch (error) {
      storageAvailable = false;
      return blankRecords();
    }
  }

  const records = loadRecords();

  function formatTime(ms) {
    if (ms === null || ms === undefined || !validMs(ms)) return '--:--.--';
    const centi = Math.floor(ms / 10);
    const minutes = Math.floor(centi / 6000);
    const seconds = Math.floor(centi / 100) % 60;
    const hundredths = centi % 100;
    return String(minutes).padStart(2, '0') + ':' +
      String(seconds).padStart(2, '0') + '.' +
      String(hundredths).padStart(2, '0');
  }

  function appendText(parent, className, content, tagName = 'span') {
    const node = document.createElement(tagName);
    node.className = className;
    node.textContent = content;
    parent.appendChild(node);
  }

  function renderRecords() {
    bestNode.textContent = formatTime(records.bestMs);
    lastNode.textContent = formatTime(records.lastMs);
    runsNode.textContent = records.completedRuns.toLocaleString();
    historyNode.replaceChildren();

    if (!records.history.length) {
      appendText(historyNode, 'history-empty',
        'Finish a No-Coin Challenge run to see your times here.', 'li');
    } else {
      records.history.slice(0, 6).forEach((record, index) => {
        const li = document.createElement('li');
        const left = document.createElement('div');
        appendText(left, 'history-title', 'Attempt #' + (records.completedRuns - index));
        const date = new Date(record.at);
        appendText(left, 'history-detail',
          Number.isNaN(date.getTime()) ? '' : ' · ' + date.toLocaleString());
        li.appendChild(left);
        appendText(li, 'history-time', formatTime(record.ms));
        historyNode.appendChild(li);
      });
    }

    if (!isChallenge) {
      storageNote.textContent =
        'Records only count runs on the No-Coin Challenge page, not the original game.';
    } else if (!storageAvailable) {
      storageNote.textContent =
        'Browser storage is unavailable. These scores will disappear when the page reloads.';
    } else {
      storageNote.textContent =
        'Saved in this browser only. Private/incognito windows may erase records when closed.';
    }
  }

  function saveRun(elapsedMs) {
    if (!validMs(elapsedMs)) return;
    const finalMs = Math.floor(elapsedMs);
    records.completedRuns += 1;
    records.lastMs = finalMs;
    records.bestMs = records.bestMs === null ? finalMs : Math.max(records.bestMs, finalMs);
    records.history.unshift({ ms: finalMs, at: Date.now() });
    records.history.length = Math.min(records.history.length, HISTORY_LIMIT);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(records));
    } catch (error) {
      storageAvailable = false;
      console.warn('[No-Coin] Could not store personal best', error);
    }
    renderRecords();
  }

  window.addEventListener('runner-timer-state', event => {
    const detail = event.detail || {};
    if (detail.state === 'running') {
      runInProgress = true;
    } else if (detail.state === 'finished' && runInProgress) {
      runInProgress = false;
      // The original game has its own scoring; these records measure
      // the confirmed elapsed No-Coin run time, not in-game distance.
      if (isChallenge) saveRun(detail.elapsedMs);
    }
  });

  if (bestNode && lastNode && runsNode && historyNode && storageNote) renderRecords();

  window.NoCoinChallenge = Object.freeze({
    isChallenge,
    getRecords: () => JSON.parse(JSON.stringify(records)),
  });
})();
