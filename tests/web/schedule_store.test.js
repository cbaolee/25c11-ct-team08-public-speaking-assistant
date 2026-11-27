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
  storage.setItem(s.storageKey('u'), JSON.stringify({ ...seeded, version: 99 })); assert.deepEqual(s.loadSchedule('u', opts), seeded);
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
  const s = await store, m = await model, original = { version: s.STORE_VERSION, ...m.seedSchedule(now) }, snapshot = structuredClone(original);
  const added = s.addEvent(original, { ...original.events[0], id: 'extra' }); assert.equal(added.events.length, 5);
  const record = { checkin_at: now, done_at: now + 1 };
  const marked = s.markDone(added, 'extra@2026-11-25', record);
  assert.deepEqual(s.markDone(marked, 'extra@2026-11-25', { checkin_at: now + 2, done_at: now + 3 }).done['extra@2026-11-25'], record);
  const removed = s.deleteEvent(marked, 'extra'); assert.equal(removed.events.length, 4); assert.equal(Object.hasOwn(removed.done, 'extra@2026-11-25'), false); assert.deepEqual(original, snapshot);
  assert.equal(s.newEventId(() => 0.5), 'ev-i');
});

test('reset replaces saved user events with fresh samples', async () => {
  const s = await store, m = await model, storage = memory(), opts = { now, storage, seed: m.seedSchedule };
  s.saveSchedule('u', { version: s.STORE_VERSION, events: [], done: {} }, storage);
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
  const s = await store, m = await model, base = { version: s.STORE_VERSION, ...m.seedSchedule(now) };
  const event = base.events[0];
  const invalidEvents = [
    { date: 'bad' }, { duration_min: 7 }, { note: 'x'.repeat(201) },
    { recurrence: { ...event.recurrence, kind: 'unknown' } },
    ...[0, 8, 1.5].map(day => ({ recurrence: { ...event.recurrence, days: [day] } })),
    ...[undefined, 'bad'].map(until => ({ recurrence: { ...event.recurrence, end: { kind: 'until', until } } })),
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
  const s = await store, m = await model, state = { version: s.STORE_VERSION, ...m.seedSchedule(now) }, snapshot = structuredClone(state);
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
  const s = await store, m = await model, base = { version: s.STORE_VERSION, ...m.seedSchedule(now) }, e = base.events[0];
  for (const duration_min of m.DURATIONS_MIN) assert.ok(s.isValidState({ ...base, events: [{ ...e, duration_min }] }));
  for (const kind of m.RECURRENCE_KINDS) assert.ok(s.isValidState({ ...base, events: [{ ...e, recurrence: { ...e.recurrence, kind, days: kind === 'custom' ? [1] : [] } }] }));
  assert.ok(s.isValidState({ ...base, events: [{ ...e, note: 'x'.repeat(m.NOTE_MAX_CHARS) }] }));
  assert.equal(s.isValidState({ ...base, events: [{ ...e, note: 'x'.repeat(m.NOTE_MAX_CHARS + 1) }] }), false);
});


test('completion records require finite ordered timestamps', async () => {
  const s = await store, m = await model, base = { version: s.STORE_VERSION, ...m.seedSchedule(now) };
  for (const record of [5, { done_at: now }, { checkin_at: now, done_at: now - 1 },
    { checkin_at: NaN, done_at: now }, { checkin_at: now, done_at: NaN }]) {
    assert.equal(s.isValidState({ ...base, done: { a: record } }), false);
  }
});


test('editing and deleting occurrences preserve history and inputs', async () => {
  const s = await store, m = await model;
  const event = { id: 'a', date: '2026-11-23', time: '15:00', duration_min: 10, note: '', recurrence: { kind: 'daily', days: [], end: { kind: 'until', until: '2026-11-30' } }, created_at: 1, sample: true };
  const state = { version: s.STORE_VERSION, events: [event], done: { 'a@2026-11-24': { checkin_at: 2, done_at: 3 } } }, snapshot = structuredClone(state);
  const range = { from: m.parseDay('2026-11-23'), to: m.parseDay('2026-11-26') };
  const split = s.editOccurrence(state, 'a', '2026-11-26', { time: '16:00', note: 'new' }, { now, newId: 'b' });
  assert.deepEqual(m.expandOccurrences(split.events, range, split.done), m.expandOccurrences(state.events, range, state.done));
  assert.equal(split.events[0].recurrence.end.until, '2026-11-25');
  assert.equal(split.events[1].date, '2026-11-26'); assert.equal(split.events[1].time, '16:00');
  assert.deepEqual(split.done, state.done);
  assert.deepEqual(s.editOccurrence(state, 'a', '2026-11-23', {}, { now, newId: 'b' }).events.map(e => e.id), ['b']);
  const single = { ...state, events: [{ ...event, recurrence: { kind: 'none', days: [], end: { kind: 'never' } } }] };
  const updated = s.editOccurrence(single, 'a', '2026-11-23', { date: '2026-11-27', time: '17:00' }, { now, newId: 'b' });
  assert.equal(updated.events[0].id, 'a'); assert.equal(updated.events[0].date, '2026-11-27'); assert.equal(updated.events[0].created_at, now);
  assert.equal(s.deleteFromOccurrence(single, 'a', '2026-11-23').events.length, 0);
  assert.deepEqual(s.deleteFromOccurrence(single, 'a', '2026-11-23').done, {});
  assert.equal(s.deleteFromOccurrence(state, 'a', '2026-11-26').events[0].recurrence.end.until, '2026-11-25');
  assert.deepEqual(s.deleteFromOccurrence(state, 'a', '2026-11-23').done, {});
  assert.deepEqual(state, snapshot);
});

test('completion session IDs are optional strings and survive storage', async () => {
  const s = await store, storage = memory(), base = { version: s.STORE_VERSION, events: [], done: {} };
  for (const session_id of [undefined, null, 'session-1']) {
    const record = { checkin_at: now, done_at: now + 1 };
    if (session_id !== undefined) record.session_id = session_id;
    const state = s.markDone(base, 'a', record);
    assert.equal(s.isValidState(state), true);
    s.saveSchedule('u', state, storage);
    assert.deepEqual(JSON.parse(storage.getItem(s.storageKey('u'))), state);
  }
  assert.equal(s.isValidState({ ...base, done: { a: { checkin_at: now, done_at: now, session_id: 42 } } }), false);
});

test('v1 migration persists defaults and count series splits preserve details', async () => {
 const s = await store, m = await model, storage = memory(), seed = m.seedSchedule(now), e = seed.events[0];
 const { all_day, category, color, script, details_edited_at, ...old } = e;
 const v1 = { version: 1, events: [{ ...old, recurrence: { kind: 'daily', days: [], until: null } }], done: seed.done };
 storage.setItem(s.storageKey('u'), JSON.stringify(v1));
 const migrated = s.loadSchedule('u', { storage, seed: m.seedSchedule, now });
 assert.equal(migrated.version, 3); assert.equal(migrated.events[0].color, 'lime'); assert.deepEqual(migrated.done, v1.done);
 assert.deepEqual(JSON.parse(storage.getItem(s.storageKey('u'))), migrated);
 const series = { ...migrated.events[0], date: '2026-11-23', color: 'red', recurrence: { kind: 'daily', days: [], end: { kind: 'count', count: 5 } } };
 const state = { version: s.STORE_VERSION, events: [series], done: {} };
 const split = s.editOccurrence(state, series.id, '2026-11-25', { note: 'changed' }, { now, newId: 'new' });
 assert.equal(split.events[0].recurrence.end.until, '2026-11-24'); assert.equal(split.events[1].recurrence.end.count, 3);
 assert.equal(split.events[1].color, 'red'); assert.equal(split.events[1].details_edited_at, now); assert.equal(split.events[1].created_at, series.created_at);
});

const v1Fixture = () => ({ version: 1, events: [
  { id: 'a', date: '2026-11-25', time: '19:00', duration_min: 10, note: '', recurrence: { kind: 'daily', days: [], until: '2026-11-30' }, created_at: 1, sample: false },
  { id: 'b', date: '2026-11-25', time: '20:00', duration_min: 10, note: '', recurrence: { kind: 'daily', days: [], until: null }, created_at: 1, sample: false },
], done: { 'a@2026-11-25': { checkin_at: 2, done_at: 3 } } });
const countSeries = () => ({ id: 'a', date: '2026-11-25', time: '19:00', all_day: false, duration_min: 10, category: 'any', color: 'red', script: { kind: 'free' }, note: '', recurrence: { kind: 'daily', days: [], end: { kind: 'count', count: 5 } }, created_at: 1, details_edited_at: 2, sample: false });

test('v2 migration preserves records and non-blue colors without mutating input', async () => {
  const s = await store, m = await model, storage = memory();
  const v2 = { version: 2, events: [{ ...countSeries(), color: 'blue' }, { ...countSeries(), id: 'b' }], done: { a: { checkin_at: 2, done_at: 3 } } };
  const snapshot = structuredClone(v2), migrated = s.migrateState(v2);
  assert.equal(migrated.version, 3); assert.deepEqual(migrated.events.map(e => e.color), ['lime', 'red']);
  assert.deepEqual(migrated.done, v2.done); assert.deepEqual(v2, snapshot); assert.ok(s.isValidState(migrated));
  storage.setItem(s.storageKey('u'), JSON.stringify(v2));
  assert.deepEqual(s.loadSchedule('u', { storage, seed: m.seedSchedule, now }), migrated);
  assert.deepEqual(JSON.parse(storage.getItem(s.storageKey('u'))), migrated);
});

test('invalid v2 and unknown v3 colors fall back to the seed', async () => {
  const s = await store, m = await model, storage = memory(), opts = { storage, seed: m.seedSchedule, now };
  const seed = { version: s.STORE_VERSION, ...m.seedSchedule(now) };
  for (const state of [
    { version: 2, events: [{ ...countSeries(), color: 'lime' }], done: {} },
    { version: 2, events: [{ ...countSeries(), time: '99:00' }], done: {} },
    { version: 3, events: [{ ...countSeries(), color: 'unknown' }], done: {} },
  ]) {
    storage.setItem(s.storageKey('u'), JSON.stringify(state));
    assert.deepEqual(s.loadSchedule('u', opts), seed);
  }
});

test('migrateState preserves v1 data and applies defaults', async () => {
  const s = await store, v1 = v1Fixture(), migrated = s.migrateState(v1);
  assert.equal(s.isValidState(migrated), true); assert.deepEqual(migrated.done, v1.done);
  for (let i = 0; i < 2; i++) {
    const e = migrated.events[i]; assert.equal(e.all_day, false); assert.equal(e.time, v1.events[i].time);
    assert.equal(e.category, 'any'); assert.equal(e.color, 'lime'); assert.deepEqual(e.script, { kind: 'free' }); assert.equal(e.details_edited_at, null);
    assert.equal(Object.hasOwn(e.recurrence, 'until'), false);
  }
  assert.deepEqual(migrated.events[0].recurrence.end, { kind: 'until', until: '2026-11-30' });
  assert.deepEqual(migrated.events[1].recurrence.end, { kind: 'never' });
});

test('loading v1 returns and persists the migrated state', async () => {
  const s = await store, m = await model, storage = memory(), v1 = v1Fixture();
  storage.setItem(s.storageKey('u'), JSON.stringify(v1));
  const loaded = s.loadSchedule('u', { storage, seed: m.seedSchedule, now });
  assert.deepEqual(loaded, s.migrateState(v1)); assert.deepEqual(JSON.parse(storage.getItem(s.storageKey('u'))), loaded);
});

test('weekly occurrence counts honor count and until caps', async () => {
  const s = await store, e = { ...countSeries(), recurrence: { kind: 'weekly', days: [], end: { kind: 'never' } } };
  assert.equal(s.countOccurrencesBefore(e, '2026-12-16'), 3);
  assert.equal(s.countOccurrencesBefore({ ...e, recurrence: { ...e.recurrence, end: { kind: 'count', count: 2 } } }, '2026-12-16'), 2);
  assert.equal(s.countOccurrencesBefore({ ...e, recurrence: { ...e.recurrence, end: { kind: 'until', until: '2026-12-02' } } }, '2026-12-16'), 2);
});

test('editing third count occurrence splits remaining sessions and preserves or changes color', async () => {
  const s = await store, state = { version: s.STORE_VERSION, events: [countSeries()], done: {} };
  for (const [changes, color] of [[{}, 'red'], [{ color: 'green' }, 'green']]) {
    const result = s.editOccurrence(state, 'a', '2026-11-27', changes, { now, newId: 'b' });
    assert.equal(result.events.length, 2); assert.deepEqual(result.events[0].recurrence.end, { kind: 'until', until: '2026-11-26' });
    assert.equal(result.events[1].id, 'b'); assert.equal(result.events[1].date, '2026-11-27');
    assert.deepEqual(result.events[1].recurrence.end, { kind: 'count', count: 3 }); assert.equal(result.events[1].color, color);
  }
});

test('deleting third or first count occurrence truncates or removes the series', async () => {
  const s = await store, state = { version: s.STORE_VERSION, events: [countSeries()], done: { 'a@2026-11-25': { checkin_at: 2, done_at: 3 } } };
  const truncated = s.deleteFromOccurrence(state, 'a', '2026-11-27');
  assert.equal(truncated.events.length, 1); assert.deepEqual(truncated.events[0].recurrence.end, { kind: 'until', until: '2026-11-26' });
  const removed = s.deleteFromOccurrence(state, 'a', '2026-11-25'); assert.deepEqual(removed.events, []); assert.deepEqual(removed.done, {});
});

test('edit timestamps track schedule and detail changes independently', async () => {
  const s = await store, e = { ...countSeries(), recurrence: { kind: 'none', days: [], end: { kind: 'never' } } }, state = { version: s.STORE_VERSION, events: [e], done: {} };
  const note = s.editOccurrence(state, 'a', e.date, { note: 'new' }, { now, newId: 'b' }).events[0];
  assert.equal(note.created_at, e.created_at); assert.equal(note.details_edited_at, now);
  const time = s.editOccurrence(state, 'a', e.date, { time: '20:00' }, { now, newId: 'b' }).events[0];
  assert.equal(time.created_at, now); assert.equal(time.details_edited_at, e.details_edited_at);
  const split = s.editOccurrence({ ...state, events: [countSeries()] }, 'a', '2026-11-27', {}, { now, newId: 'b' });
  assert.equal(split.events[1].created_at, e.created_at); assert.equal(split.events[1].details_edited_at, e.details_edited_at);
});

test('remainingCount counts sessions from the selected occurrence', async () => {
  const s = await store;
  const event = { date: '2026-11-25', recurrence: { kind: 'daily', days: [], end: { kind: 'count', count: 5 } } };
  assert.equal(s.remainingCount(event, '2026-11-25'), 5);
  assert.equal(s.remainingCount(event, '2026-11-27'), 3);
  assert.equal(s.remainingCount(event, '2026-11-29'), 1);
  for (const end of [{ kind: 'until', until: '2026-12-01' }, { kind: 'never' }]) {
    assert.equal(s.remainingCount({ ...event, recurrence: { ...event.recurrence, end } }, '2026-11-27'), null);
  }
});

 test('invalid migrated end date falls back to the seed', async () => {
  const s = await store, m = await model, storage = memory(), v1 = v1Fixture();
  v1.events[0].recurrence.until = '2026-11-24';
  storage.setItem(s.storageKey('u'), JSON.stringify(v1));
  assert.equal(s.migrateState(v1), null);
  assert.deepEqual(s.loadSchedule('u', { storage, seed: m.seedSchedule, now }), { version: s.STORE_VERSION, ...m.seedSchedule(now) });
});
