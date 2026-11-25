'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const load = name => import('data:text/javascript;base64,' + Buffer.from(fs.readFileSync(path.join(__dirname, '../../src/web/static/js/schedule/' + name + '.js'), 'utf8')).toString('base64'));
const store = load('schedule_store'), model = load('schedule_model');
const now = new Date(2026, 10, 25, 14, 0).getTime();
const memory = () => { const values = new Map(); return { getItem: k => values.get(k) ?? null, setItem: (k, v) => values.set(k, v) }; };

test('corrupt or outdated storage is replaced with a valid seed', async () => {
  const s = await store, m = await model, storage = memory(), opts = { now, storage, seed: m.seedSchedule };
  storage.setItem(s.storageKey('u'), '{'); const seeded = s.loadSchedule('u', opts);
  assert.equal(s.isValidState(seeded), true); assert.deepEqual(JSON.parse(storage.getItem(s.storageKey('u'))), seeded);
  storage.setItem(s.storageKey('u'), JSON.stringify({ ...seeded, version: 2 })); assert.deepEqual(s.loadSchedule('u', opts), seeded);
});

test('storage round trips independently per user and tolerates blocked access', async () => {
  const s = await store, m = await model, storage = memory(), opts = { now, storage, seed: m.seedSchedule };
  assert.equal(s.storageKey('u'), 'psa.schedule.v1.u');
  const first = s.loadSchedule('u', opts); first.events = []; assert.equal(s.saveSchedule('u', first, storage), true);
  assert.deepEqual(s.loadSchedule('u', opts), first); assert.equal(s.loadSchedule('v', opts).events.length, 4);
  const blocked = { getItem() { throw Error('blocked'); }, setItem() { throw Error('blocked'); } };
  assert.equal(s.loadSchedule('u', { ...opts, storage: blocked }).events.length, 4); assert.equal(s.saveSchedule('u', first, blocked), false);
  assert.equal(s.loadSchedule('', opts).events.length, 4); assert.equal(s.loadSchedule('u', { ...opts, storage: null }).events.length, 4);
});

test('immutable event operations remove related completions and preserve first completion', async () => {
  const s = await store, m = await model, original = { version: 1, ...m.seedSchedule(now) }, snapshot = structuredClone(original);
  const added = s.addEvent(original, { ...original.events[0], id: 'extra' }); assert.equal(added.events.length, 5);
  const record = { checkin_at: now, done_at: now + 1 };
  const marked = s.markDone(added, 'extra@2026-11-25', record);
  assert.deepEqual(s.markDone(marked, 'extra@2026-11-25', { checkin_at: now + 2, done_at: now + 3 }).done['extra@2026-11-25'], record);
  const removed = s.deleteEvent(marked, 'extra'); assert.equal(removed.events.length, 4); assert.equal(Object.hasOwn(removed.done, 'extra@2026-11-25'), false); assert.deepEqual(original, snapshot);
  assert.equal(s.newEventId(() => 0.5), 'ev-i');
});

test('reset replaces saved user events with fresh samples', async () => {
  const s = await store, m = await model, storage = memory(), opts = { now, storage, seed: m.seedSchedule };
  s.saveSchedule('u', { version: 1, events: [], done: {} }, storage);
  assert.equal(s.resetSchedule('u', opts).events.length, 4); assert.equal(s.loadSchedule('u', opts).events.length, 4);
});

test('missing storage key is seeded and saved', async () => {
  const s = await store, m = await model, storage = memory();
  const result = s.loadSchedule('u', { now, storage, seed: m.seedSchedule });
  assert.deepEqual(JSON.parse(storage.getItem(s.storageKey('u'))), result);
});
test('falsy user IDs do not write storage keys', async () => {
  const s = await store, m = await model;
  for (const user of ['', null, undefined]) {
    const keys = new Map(), storage = { getItem: k => keys.get(k) ?? null, setItem: (k, v) => keys.set(k, v) };
    s.loadSchedule(user, { now, storage, seed: m.seedSchedule });
    assert.equal(keys.size, 0);
  }
});
test('invalid persisted state fields are rejected', async () => {
  const s = await store, m = await model, base = { version: 1, ...m.seedSchedule(now) };
  const event = base.events[0];
  const invalidEvents = [
    { date: 'bad' }, { duration_min: 7 }, { note: 'x'.repeat(201) },
    { recurrence: { ...event.recurrence, kind: 'unknown' } },
    ...[0, 8, 1.5].map(day => ({ recurrence: { ...event.recurrence, days: [day] } })),
    ...[undefined, 'bad'].map(until => ({ recurrence: { ...event.recurrence, until } })),
    { sample: 'true' },
  ];
  for (const patch of invalidEvents) assert.equal(s.isValidState({ ...base, events: [{ ...event, ...patch }] }), false);
  for (const patch of [{ events: {} }, { done: [] }, { done: { a: '5' } }, { done: { a: NaN } }]) assert.equal(s.isValidState({ ...base, ...patch }), false);
});
test('valid JSON with the wrong shape is replaced by a seed', async () => {
  const s = await store, m = await model, storage = memory(), opts = { now, storage, seed: m.seedSchedule };
  for (const raw of ['{}', 'null']) {
    storage.setItem(s.storageKey('u'), raw);
    assert.deepEqual(s.loadSchedule('u', opts), { version: s.STORE_VERSION, ...m.seedSchedule(now) });
  }
});
test('saving an added event for one user leaves the other seed intact', async () => {
  const s = await store, m = await model, storage = memory(), opts = { now, storage, seed: m.seedSchedule };
  const u = s.loadSchedule('u', opts), v = s.loadSchedule('v', opts);
  const changed = s.addEvent(u, { ...u.events[0], id: 'extra' });
  s.saveSchedule('u', changed, storage);
  assert.deepEqual(s.loadSchedule('v', opts), v);
  assert.deepEqual(s.loadSchedule('u', opts), changed);
});
test('addEvent and markDone preserve their inputs', async () => {
  const s = await store, m = await model, state = { version: 1, ...m.seedSchedule(now) }, snapshot = structuredClone(state);
  s.addEvent(state, state.events[0]);
  s.markDone(state, 'extra', { checkin_at: now, done_at: now + 1 });
  assert.deepEqual(state, snapshot);
});
test('event IDs have a prefix and a nonempty zero suffix', async () => {
  const s = await store;
  assert.ok(s.newEventId().startsWith('ev-'));
  assert.equal(s.newEventId(() => 0), 'ev-0');
});
test('store validation matches the model duration, recurrence and note limits', async () => {
  const s = await store, m = await model, base = { version: 1, ...m.seedSchedule(now) }, e = base.events[0];
  for (const duration_min of m.DURATIONS_MIN) assert.ok(s.isValidState({ ...base, events: [{ ...e, duration_min }] }));
  for (const kind of m.RECURRENCE_KINDS) assert.ok(s.isValidState({ ...base, events: [{ ...e, recurrence: { ...e.recurrence, kind } }] }));
  assert.ok(s.isValidState({ ...base, events: [{ ...e, note: 'x'.repeat(m.NOTE_MAX_CHARS) }] }));
  assert.equal(s.isValidState({ ...base, events: [{ ...e, note: 'x'.repeat(m.NOTE_MAX_CHARS + 1) }] }), false);
});


test('completion records require finite ordered timestamps', async () => {
  const s = await store, m = await model, base = { version: 1, ...m.seedSchedule(now) };
  for (const record of [5, { done_at: now }, { checkin_at: now, done_at: now - 1 },
    { checkin_at: NaN, done_at: now }, { checkin_at: now, done_at: NaN }]) {
    assert.equal(s.isValidState({ ...base, done: { a: record } }), false);
  }
});


test('editing and deleting occurrences preserve history and inputs', async () => {
  const s = await store, m = await model;
  const event = { id: 'a', date: '2026-11-23', time: '15:00', duration_min: 10, note: '', recurrence: { kind: 'daily', days: [], until: '2026-11-30' }, created_at: 1, sample: true };
  const state = { version: 1, events: [event], done: { 'a@2026-11-24': { checkin_at: 2, done_at: 3 } } }, snapshot = structuredClone(state);
  const range = { from: m.parseDay('2026-11-23'), to: m.parseDay('2026-11-26') };
  const split = s.editOccurrence(state, 'a', '2026-11-26', { time: '16:00', note: 'new' }, { now, newId: 'b' });
  assert.deepEqual(m.expandOccurrences(split.events, range, split.done), m.expandOccurrences(state.events, range, state.done));
  assert.equal(split.events[0].recurrence.until, '2026-11-25');
  assert.equal(split.events[1].date, '2026-11-26'); assert.equal(split.events[1].time, '16:00');
  assert.deepEqual(split.done, state.done);
  assert.deepEqual(s.editOccurrence(state, 'a', '2026-11-23', {}, { now, newId: 'b' }).events.map(e => e.id), ['b']);
  const single = { ...state, events: [{ ...event, recurrence: { kind: 'none', days: [], until: null } }] };
  const updated = s.editOccurrence(single, 'a', '2026-11-23', { date: '2026-11-27', time: '17:00' }, { now, newId: 'b' });
  assert.equal(updated.events[0].id, 'a'); assert.equal(updated.events[0].date, '2026-11-27'); assert.equal(updated.events[0].created_at, now);
  assert.equal(s.deleteFromOccurrence(single, 'a', '2026-11-23').events.length, 0);
  assert.deepEqual(s.deleteFromOccurrence(single, 'a', '2026-11-23').done, {});
  assert.equal(s.deleteFromOccurrence(state, 'a', '2026-11-26').events[0].recurrence.until, '2026-11-25');
  assert.deepEqual(s.deleteFromOccurrence(state, 'a', '2026-11-23').done, {});
  assert.deepEqual(state, snapshot);
});
