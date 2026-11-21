'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../src/web/static/js/screens/coach_mode.js'), 'utf8');
const mode = import('data:text/javascript;base64,' + Buffer.from(source).toString('base64')).then(m => m.coachNoteMode);

test('coach note mode follows session status and availability', async () => {
  const coachNoteMode = await mode;
  for (const [session, expected] of [
    [{ remote: true, sc: { status: 'ok' } }, 'remote'],
    [{ remote: true, sc: { status: 'insufficient_audio' } }, 'remote'],
    [{ sc: { status: 'insufficient_audio' } }, 'client-rule'],
    [{ remote: true, demo: true, sc: { status: 'insufficient_audio' } }, 'client-rule'],
    [{ remote: true, demo: true, sc: { status: 'ok' } }, 'none'],
    [{ sc: { status: 'ok' } }, 'none'],
    [{ remote: true, sc: null }, 'none'],
  ]) assert.equal(coachNoteMode(session), expected);
});

test('insufficient panel explains scoring and retention for each reason and storage mode', () => {
  const report = fs.readFileSync(path.join(__dirname, '../../src/web/static/js/screens/report.js'), 'utf8');
  const line = report.split('\n').find(line => line.includes("$('#repState').innerHTML ="));
  const render = new Function('$', 'IC', 'esc', 'T', 'sc', 's', 'CONFIG', line);
  for (const reason of ['low_voiced_ratio', 'empty_transcript']) {
    for (const remote of [false, true]) {
      const element = {};
      const translations = { 'eval.insEmpty': 'empty', 'report.stInsD': 'low {p}', 'report.stInsNotScored': 'unscored', 'report.stInsKept': 'deleted {n}' };
      const T = (key, params = {}) => (translations[key] || key).replace(/\{(\w+)\}/g, (_, k) => params[k]);
      render(() => element, { alert: '', ai: '' }, x => x, T, { reason, voicedRatio: 0.2 }, { remote }, { RETENTION: { insufficientDays: 7 } });
      assert.match(element.innerHTML, reason === 'empty_transcript' ? /empty unscored/ : /low 20 unscored/);
      assert.equal(element.innerHTML.includes('deleted 7'), remote);
      assert.doesNotMatch(element.innerHTML, /ov-coach-tag|overview\.coachTag/);
    }
  }
});
