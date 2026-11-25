'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../src/web/static/js/schedule/schedule_model.js'), 'utf8');
const model = import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const t = (d, h = 0, min = 0) => new Date(2026, 10, d, h, min).getTime();
const now = t(25, 14);
const event = (overrides = {}) => ({ id: 'a', date: '2026-11-25', time: '15:00', duration_min: 10, note: '', recurrence: { kind: 'none', days: [], until: null }, sample: false, ...overrides });
const occ = (start, checkin_at = null, key = 'x', done_at = checkin_at) => ({
  start, day: `${new Date(start).getFullYear()}-${String(new Date(start).getMonth() + 1).padStart(2, '0')}-${String(new Date(start).getDate()).padStart(2, '0')}`,
  checkin_at, done_at, key,
});

test('status and completion use inclusive start and exclusive six hour end', async () => {
  const m = await model, start = t(25, 15), o = occ(start);
  for (const [at, status] of [[start - 1, 'upcoming'], [start, 'active'], [start + 21600000 - 1, 'active'], [start + 21600000, 'missed']]) assert.equal(m.occurrenceStatus(o, at), status);
  assert.equal(m.occurrenceStatus(occ(start, start + 1), now), 'done');
  assert.equal(m.occurrenceStatus(occ(start, start - 1), now), 'upcoming');
  assert.equal(m.occurrenceStatus(occ(start, start + 21600000), start + 21600000), 'missed');
  assert.equal(m.canCheckIn(o, start), true); assert.equal(m.canCheckIn(o, start + 21600000), false);
  assert.equal(m.reminderAt(o), start - 1800000); assert.equal(m.reminderSkipped(o, start - 1200000), true); assert.equal(m.reminderSkipped(o, start - 2700000), false);
});

test('recurrences respect local days, range, until, done and sorting', async () => {
  const m = await model, range = { from: t(23), to: t(30) };
  const expand = e => m.expandOccurrences([e], range);
  assert.deepEqual(expand(event()).map(o => o.day), ['2026-11-25']);
  assert.deepEqual(expand(event({ recurrence: { kind: 'daily', days: [], until: '2026-11-27' } })).map(o => o.day), ['2026-11-25', '2026-11-26', '2026-11-27']);
  assert.deepEqual(expand(event({ date: '2026-11-18', recurrence: { kind: 'weekly', days: [], until: null } })).map(o => o.day), ['2026-11-25']);
  assert.deepEqual(expand(event({ date: '2026-11-23', recurrence: { kind: 'custom', days: [1, 3, 5], until: null } })).map(o => o.day), ['2026-11-23', '2026-11-25', '2026-11-27']);
  const sorted = m.expandOccurrences([event({ id: 'z' }), event({ id: 'a' }), event({ id: 'b', time: '12:00' })], range, { 'a@2026-11-25': { checkin_at: now, done_at: now + 1 } });
  assert.deepEqual(sorted.map(o => o.event_id), ['b', 'a', 'z']); assert.equal(sorted[1].checkin_at, now); assert.equal(sorted[1].done_at, now + 1);
  assert.equal(m.isoWeekday(now), 3); assert.equal(m.dayKey(m.startOfWeek(now)), '2026-11-23'); assert.equal(m.dayKey(m.addDays(t(30), 1)), '2026-12-01');
});

test('validation reports invalid fields and accepts a future event', async () => {
  const m = await model;
  assert.equal(m.validateEvent(event(), now).ok, true);
  for (const [change, field, code] of [[{ time: '13:00' }, 'start', 'past'], [{ date: '2026-02-30' }, 'start', 'invalid'], [{ duration_min: 7 }, 'duration_min', 'invalid'], [{ note: 'x'.repeat(201) }, 'note', 'too_long'], [{ recurrence: { kind: 'custom', days: [], until: null } }, 'days', 'empty'], [{ recurrence: { kind: 'daily', days: [], until: '2026-11-24' } }, 'until', 'before_start']]) assert.equal(m.validateEvent(event(change), now).errors[field], code);
});

test('streak counts consecutive prior weeks and adds current week', async () => {
  const m = await model, done = d => occ(t(d, 10), t(d, 10, 5));
  assert.equal(m.weeklyStreak([done(17), done(10)], now), 2);
  assert.equal(m.weeklyStreak([done(24)], now), 1);
  assert.equal(m.weeklyStreak([done(24), done(17), done(3)], now), 2);
  assert.equal(m.weeklyStreak([], now), 0);
});

test('week progress and today summary choose the correct session and day states', async () => {
  const m = await model, items = [occ(t(23, 10), t(23, 10, 5), 'a'), occ(t(24, 10), null, 'b'), occ(t(25, 10), null, 'c'), occ(t(25, 12), null, 'd'), occ(t(25, 18), null, 'e'), occ(t(26, 10), null, 'f')];
  const week = m.weekProgress(items, now); assert.equal(week.done, 1); assert.equal(week.total, 6);
  assert.deepEqual(week.dots.map(d => d.state), ['done', 'missed', 'active', 'upcoming', 'none', 'none', 'none']);
  const s = m.todaySummary(items, now); assert.equal(s.status, 'active'); assert.equal(s.primary.key, 'c'); assert.equal(s.more, 2); assert.equal(s.closes_in_ms, 7200000); assert.equal(s.missed_yesterday, true);
  assert.equal(m.todaySummary([items[4]], now).status, 'upcoming'); assert.equal(m.todaySummary([occ(t(25, 10), t(25, 10, 5))], now).status, 'done'); assert.equal(m.todaySummary([], now).status, 'none');
});

test('motivation follows done, streak, open window, missed day and empty plan priority', async () => {
  const m = await model, base = { status: 'active', primary: occ(t(25, 12)), missed_yesterday: false, streak: 0, week: { done: 0, dots: [{ day: '2026-11-25', state: 'none' }] } };
  assert.equal(m.motivationKey({ ...base, status: 'done' }), 'doneToday');
  assert.equal(m.motivationKey({ ...base, week: { done: 1, dots: [{ day: '2026-11-25', state: 'done' }] } }), 'doneToday');
  assert.equal(m.motivationKey({ ...base, streak: 1 }), 'keepStreak'); assert.equal(m.motivationKey(base), 'windowOpen');
  assert.equal(m.motivationKey({ ...base, status: 'none', missed_yesterday: true }), 'pickUp'); assert.equal(m.motivationKey({ ...base, status: 'none' }), 'plan'); assert.equal(m.motivationKey({ ...base, status: 'upcoming' }), null);
});

test('sample schedule shows all four states relative to now', async () => {
  const m = await model, seed = m.seedSchedule(now), occurrences = m.expandOccurrences(seed.events, { from: t(1), to: t(30) }, seed.done);
  assert.equal(seed.events.every(e => e.sample), true);
  assert.deepEqual(occurrences.map(o => m.occurrenceStatus(o, now)), ['done', 'missed', 'active', 'upcoming']);
  assert.equal(occurrences[2].day, '2026-11-25'); assert.equal(occurrences[3].day, '2026-11-26');
});

test('seed keeps all four states around midnight and the week boundary', async () => {
  const m = await model;
  for (const instant of [t(23, 0, 2), t(29, 23, 58), t(25, 0, 30)]) {
    const seed = m.seedSchedule(instant), items = m.expandOccurrences(seed.events, { from: m.addDays(m.startOfWeek(instant), -7), to: m.addDays(instant, 2) }, seed.done);
    assert.deepEqual(items.map(o => m.occurrenceStatus(o, instant)), ['done', 'missed', 'active', 'upcoming']);
    assert.equal(items[2].day, m.dayKey(instant));
    assert.ok(items[0].start < m.startOfWeek(instant) && items[1].start < m.startOfWeek(instant));
    assert.ok(items.every(o => o.sample));
  }
});
test('today summary chooses status priority and nearest or last occurrence', async () => {
  const m = await model, missed = occ(t(25, 7), null, 'missed'), done1 = occ(t(25, 8), t(25, 8, 5), 'done1'), done2 = occ(t(25, 9), t(25, 9, 5), 'done2'), active = occ(t(25, 12), null, 'active'), soon = occ(t(25, 15), null, 'soon'), later = occ(t(25, 16), null, 'later');
  assert.equal(m.todaySummary([missed], now).status, 'missed');
  assert.equal(m.todaySummary([done1, soon], now).status, 'upcoming');
  const upcoming = m.todaySummary([later, soon], now);
  assert.equal(upcoming.primary.key, 'soon'); assert.equal(upcoming.closes_in_ms, null);
  assert.equal(m.todaySummary([done1, done2], now).primary.key, 'done2');
  const result = m.todaySummary([soon, active], now);
  assert.equal(result.status, 'active'); assert.ok('streak' in result && 'week' in result);
});
test('week dots prioritize done, active and upcoming on the same day', async () => {
  const m = await model, done = occ(t(25, 8), t(25, 8, 1)), active = occ(t(25, 12)), upcoming = occ(t(25, 18)), missed = occ(t(25, 6));
  for (const [items, expected] of [[[done, active], 'done'], [[active, upcoming], 'active'], [[upcoming, missed], 'upcoming']]) assert.equal(m.weekProgress(items, now).dots[2].state, expected);
});
test('missed-only weeks do not count and the current week does not break a streak', async () => {
  const m = await model;
  assert.equal(m.weeklyStreak([occ(t(17, 10))], now), 0);
  assert.equal(m.weeklyStreak([occ(t(17, 10), t(17, 10, 5)), occ(t(24, 10))], now), 1);
});
test('out of window completion is ignored while the window is active', async () => {
  const m = await model, start = t(25, 12);
  assert.equal(m.occurrenceStatus(occ(start, start + 21600000), now), 'active');
});
test('validation handles invalid times, recurrence and note boundaries', async () => {
  const m = await model;
  for (const time of ['25:00', '']) assert.equal(m.validateEvent(event({ time }), now).errors.start, 'invalid');
  assert.equal(m.validateEvent(event({ recurrence: { kind: 'unknown' } }), now).errors.recurrence, 'invalid');
  assert.equal(m.validateEvent(event({ note: 1 }), now).errors.note, 'too_long');
  assert.ok(m.validateEvent(event({ note: 'x'.repeat(200) }), now).ok);
});
test('recurrence expansion respects until and the first event day', async () => {
  const m = await model, range = { from: t(1), to: new Date(2026, 11, 1).getTime() };
  const daily = m.expandOccurrences([event({ recurrence: { kind: 'daily', days: [], until: '2026-11-27' } })], range);
  assert.deepEqual(daily.map(o => o.day), ['2026-11-25', '2026-11-26', '2026-11-27']);
  const weekly = m.expandOccurrences([event({ recurrence: { kind: 'weekly', days: [], until: null } })], range);
  assert.deepEqual(weekly.map(o => o.day), ['2026-11-25']);
});
test('unbounded daily recurrence remains finite over two years', async () => {
  const m = await model, e = event({ date: '2026-01-01', recurrence: { kind: 'daily', days: [], until: null } });
  assert.equal(m.expandOccurrences([e], { from: new Date(2026, 0, 1).getTime(), to: new Date(2028, 0, 1).getTime() }).length, 730);
});
test('reminder is not skipped exactly thirty minutes before start', async () => {
  const m = await model, start = t(25, 15);
  assert.equal(m.reminderSkipped(occ(start), start - 1800000), false);
});


test('check-in windows end at six hours or local midnight', async () => {
  const m = await model;
  for (const [hour, minute, close] of [[22, 0, t(26)], [0, 0, t(25, 6)],
    [23, 59, t(26)], [15, 0, t(25, 21)]]) {
    assert.equal(m.windowClosesAt(occ(t(25, hour, minute))), close);
  }
  const start = t(25, 22), o = occ(start), close = t(26);
  assert.equal(m.occurrenceStatus(o, close - 1), 'active');
  assert.equal(m.occurrenceStatus(o, close), 'missed');
  assert.equal(m.canCheckIn(o, start - 1), false);
  assert.equal(m.canCheckIn(o, start), true);
  assert.equal(m.canCheckIn(o, close), false);
  assert.equal(m.occurrenceStatus(occ(start, t(25, 23, 50), 'x', t(26, 0, 20)), t(26, 1)), 'done');
  assert.equal(m.occurrenceStatus(occ(start, close, 'x', t(26, 0, 20)), t(26, 1)), 'missed');
  assert.equal(m.occurrenceStatus(occ(start, start - 1, 'x', start), t(26, 1)), 'missed');
});


test('edit lead time and inclusive recurrence previews', async () => {
  const m = await model, start = t(25, 15);
  assert.equal(m.canEdit({ start }, start - 20 * 60000), true);
  assert.equal(m.canEdit({ start }, start - 19 * 60000 - 59000), false);
  const input = event({ date: '2026-11-23' });
  const preview = (kind, days = []) => m.previewOccurrenceDays({ ...input, recurrence: { kind, days } }, '2026-11-24', '2026-11-29');
  assert.deepEqual(preview('none'), []);
  assert.deepEqual(m.previewOccurrenceDays(input, '2026-11-23', '2026-11-23'), ['2026-11-23']);
  assert.deepEqual(preview('daily'), ['2026-11-24', '2026-11-25', '2026-11-26', '2026-11-27', '2026-11-28', '2026-11-29']);
  assert.deepEqual(preview('weekly'), []);
  assert.deepEqual(preview('custom', [1, 3, 7]), ['2026-11-25', '2026-11-29']);
  assert.deepEqual(m.previewOccurrenceDays({ ...input, recurrence: { kind: 'weekly', days: [] } }, '2026-11-23', '2026-11-30'), ['2026-11-23', '2026-11-30']);
});
