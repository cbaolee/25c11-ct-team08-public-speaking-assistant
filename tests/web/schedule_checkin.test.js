'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const load = name => import('data:text/javascript;base64,' + Buffer.from(fs.readFileSync(path.join(__dirname, '../../src/web/static/js/schedule', name), 'utf8')).toString('base64'));

test('completion requires a context and a scored successful evaluation', async () => {
  const { shouldCompleteCheckIn, shouldClearOnLeave } = await load('schedule_view.js');
  assert.equal(shouldCompleteCheckIn({}, { status: 'ok', overall: 0 }), true);
  assert.equal(shouldCompleteCheckIn({}, { status: 'ok', overall: null }), false);
  assert.equal(shouldCompleteCheckIn({}, { status: 'insufficient_audio', overall: 50 }), false);
  assert.equal(shouldCompleteCheckIn(null, { status: 'ok', overall: 50 }), false);
  assert.equal(shouldClearOnLeave(false, true), false);
  assert.equal(shouldClearOnLeave(false, false), true);
  assert.equal(shouldClearOnLeave(true, false), false);
});
test('on-time check-in remains done when evaluation finishes after midnight', async () => {
  const model = await load('schedule_model.js'), store = await load('schedule_store.js');
  const event = { id: 'late', date: '2026-11-25', time: '22:00', duration_min: 10, note: '', recurrence: { kind: 'none', days: [], until: null }, sample: false };
  const start = new Date(2026, 10, 25).getTime();
  const state = store.markDone({ version: 1, events: [event], done: {} }, 'late@2026-11-25', { checkin_at: new Date(2026, 10, 25, 23, 50).getTime(), done_at: new Date(2026, 10, 26, 0, 20).getTime() });
  const [occ] = model.expandOccurrences(state.events, { from: start, to: model.addDays(start, 1) }, state.done);
  assert.equal(model.occurrenceStatus(occ, state.done[occ.key].done_at), 'done');
});
