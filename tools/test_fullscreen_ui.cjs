// Run: node tools/test_fullscreen_ui.cjs
// Static regression checks for fullscreen-only UI behavior.
const assert = require('node:assert/strict');
const fs = require('node:fs');

const css = fs.readFileSync(__dirname + '/challenge-site.css', 'utf8');
const page = fs.readFileSync(__dirname + '/../index.html', 'utf8');

function ruleContaining(selector) {
  const index = css.indexOf(selector);
  assert.ok(index >= 0, 'Missing CSS selector: ' + selector);
  const start = css.indexOf('{', index);
  const end = css.indexOf('}', start + 1);
  return css.substring(start + 1, end);
}

assert.match(page, /class="brand-lockup"/);
assert.match(page, /class="scroll-prompt"/);
assert.match(page, /id="challenge-fullscreen"/);
assert.match(ruleContaining('#challenge-stage:fullscreen .brand-lockup,'), /display:\s*none\s*!important/);
assert.match(ruleContaining('#challenge-stage:fullscreen .fullscreen-button,'), /opacity:\s*0/);
assert.match(ruleContaining('#challenge-stage:fullscreen .fullscreen-button:hover,'), /opacity:\s*1/);
assert.ok(css.includes('#challenge-stage:fullscreen .fullscreen-button:focus-visible'));
assert.ok(css.includes('#challenge-stage:fullscreen .scroll-prompt'));
assert.ok(css.includes('#challenge-stage:fullscreen .stage-header'));
console.log('PASS: fullscreen branding and scroll prompt hidden, exit hover/focus reveal present.');
