export const STORAGE_PREFIX = 'psa.schedule.v1.';
export const STORE_VERSION = 1;
// Build the per-user storage key.
export function storageKey(userId) { return STORAGE_PREFIX + userId; }
const date = v => typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v);
const plain = v => v !== null && typeof v === 'object' &&
  (Object.getPrototypeOf(v) === Object.prototype || Object.getPrototypeOf(v) === null);

// These values must match DURATIONS_MIN, NOTE_MAX_CHARS, and RECURRENCE_KINDS in schedule_model.js.
function isValidEvent(e) {
  return !!e &&
    typeof e.id === 'string' &&
    date(e.date) &&
    typeof e.time === 'string' &&
    /^\d{2}:\d{2}$/.test(e.time) &&
    [5, 10, 15, 20].includes(e.duration_min) &&
    typeof e.note === 'string' &&
    e.note.length <= 200 &&
    !!e.recurrence &&
    ['none', 'daily', 'weekly', 'custom'].includes(e.recurrence.kind) &&
    Array.isArray(e.recurrence.days) &&
    e.recurrence.days.every(d => Number.isInteger(d) && d >= 1 && d <= 7) &&
    (e.recurrence.until === null || date(e.recurrence.until)) &&
    typeof e.sample === 'boolean';
}

function isValidDone(record) {
  return plain(record) &&
    Number.isFinite(record.checkin_at) &&
    Number.isFinite(record.done_at) &&
    record.done_at >= record.checkin_at &&
    (record.session_id == null || typeof record.session_id === 'string');
}

// Reject invalid stored data before using it in schedule calculations.
export function isValidState(x) {
  return !!x &&
    x.version === STORE_VERSION &&
    Array.isArray(x.events) &&
    x.events.every(isValidEvent) &&
    plain(x.done) &&
    Object.values(x.done).every(isValidDone);
}
// Save a schedule when storage is available.
export function saveSchedule(userId, state, storage) {
  if (!userId || !storage) return false;
  try { storage.setItem(storageKey(userId), JSON.stringify(state)); return true; } catch (e) { return false; }
}
// Replace stored data with fresh samples.
export function resetSchedule(userId, opts) {
  const state = { version: STORE_VERSION, ...opts.seed(opts.now) };
  saveSchedule(userId, state, opts.storage);
  return state;
}
// Load valid data or fall back to samples.
export function loadSchedule(userId, opts) {
  if (userId && opts.storage) {
    try {
      const raw = opts.storage.getItem(storageKey(userId));
      if (raw !== null) { const state = JSON.parse(raw); if (isValidState(state)) return state; }
    } catch (e) { /* A blocked or damaged store starts with samples. */ }
  }
  return resetSchedule(userId, opts);
}
// Return a schedule with an added event.
export function addEvent(state, event) { return { ...state, events: [...state.events, event] }; }
// Remove an event and its completion records.
export function deleteEvent(state, eventId) {
  return {
    ...state,
    events: state.events.filter(e => e.id !== eventId),
    done: Object.fromEntries(Object.entries(state.done).filter(([key]) => !key.startsWith(eventId + '@'))),
  };
}
// Small local-date helpers are duplicated here to keep the store independent of imports.
function previousDay(day) {
  const [y, m, d] = day.split('-').map(Number), value = new Date(y, m - 1, d);
  value.setDate(value.getDate() - 1);
  return `${String(value.getFullYear()).padStart(4, '0')}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`;
}
function hasEarlierOccurrence(event, day) {
  const [y, m, d] = event.date.split('-').map(Number), cursor = new Date(y, m - 1, d);
  while (true) {
    const key = `${String(cursor.getFullYear()).padStart(4, '0')}-${String(cursor.getMonth() + 1).padStart(2, '0')}-${String(cursor.getDate()).padStart(2, '0')}`;
    if (key >= day || (event.recurrence.until && key > event.recurrence.until)) return false;
    const weekday = cursor.getDay() || 7;
    if (event.recurrence.kind === 'daily' ||
        (event.recurrence.kind === 'weekly' && key === event.date) ||
        (event.recurrence.kind === 'custom' && event.recurrence.days.includes(weekday))) return true;
    cursor.setDate(cursor.getDate() + 1);
  }
}
export function deleteFromOccurrence(state, eventId, day) {
  const event = state.events.find(e => e.id === eventId);
  if (!event) return state;
  if (event.recurrence.kind === 'none' || !hasEarlierOccurrence(event, day)) return deleteEvent(state, eventId);
  return { ...state, events: state.events.map(e => e.id === eventId ?
    { ...e, recurrence: { ...e.recurrence, until: previousDay(day) } } : e) };
}
export function editOccurrence(state, eventId, day, changes, { now, newId }) {
  const event = state.events.find(e => e.id === eventId);
  if (!event) return state;
  const { time, duration_min, note } = changes;
  const patch = Object.fromEntries(Object.entries({ time, duration_min, note }).filter(([, value]) => value !== undefined));
  if (event.recurrence.kind === 'none') {
    if (changes.date !== undefined) patch.date = changes.date;
    return { ...state, events: state.events.map(e => e.id === eventId ? { ...e, ...patch, created_at: now } : e) };
  }
  const keepOld = hasEarlierOccurrence(event, day);
  const old = { ...event, recurrence: { ...event.recurrence, until: previousDay(day) } };
  const next = { ...event, ...patch, id: newId, date: day, recurrence: { ...event.recurrence, days: [...event.recurrence.days] }, created_at: now };
  return { ...state, events: state.events.flatMap(e => e.id === eventId ? (keepOld ? [old, next] : [next]) : [e]) };
}
// Record the first completion without changing the input.
export function markDone(state, occKey, record) {
  return {
    ...state,
    done: { ...state.done, [occKey]: Object.hasOwn(state.done, occKey) ? state.done[occKey] : record },
  };
}
// Generate an event identifier.
export function newEventId(rand = Math.random) { return 'ev-' + (rand().toString(36).slice(2) || '0'); }
