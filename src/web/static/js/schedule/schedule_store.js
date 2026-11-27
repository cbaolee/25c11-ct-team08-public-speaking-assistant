export const STORAGE_PREFIX = 'psa.schedule.v1.';
export const STORE_VERSION = 3;
// Build the per-user storage key.
export function storageKey(userId) { return STORAGE_PREFIX + userId; }
const date = v => typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v);
const plain = v => v !== null && typeof v === 'object' &&
  (Object.getPrototypeOf(v) === Object.prototype || Object.getPrototypeOf(v) === null);

// These values must match DURATIONS_MIN, NOTE_MAX_CHARS, and RECURRENCE_KINDS in schedule_model.js.
function isValidV1Event(e) {
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

// These lists must match schedule_model.js.
function isValidEvent(e) {
  const r = e?.recurrence, end = r?.end, script = e?.script;
  return !!e && typeof e.id === 'string' && date(e.date) && typeof e.all_day === 'boolean' &&
    (e.all_day ? e.time === null : typeof e.time === 'string' && /^([01]\d|2[0-3]):[0-5]\d$/.test(e.time)) &&
    (e.duration_min === null || [5,10,15,20].includes(e.duration_min)) &&
    ['any','cinematography','gender_studies','information_technology','learning_experiences','sports','wildlife'].includes(e.category) &&
    ['lime','blue','green','amber','brown','red','slate','gray','sky'].includes(e.color) &&
    !!script && ['free','saved','ai'].includes(script.kind) &&
    (script.kind !== 'saved' || (typeof script.script_id === 'string' && !!script.script_id.trim() && typeof script.title === 'string')) &&
    (script.kind !== 'ai' || (e.duration_min !== null && e.category !== 'any')) &&
    typeof e.note === 'string' && e.note.length <= 200 && !!r && ['none','daily','weekly','custom'].includes(r.kind) &&
    Array.isArray(r.days) && r.days.every(d => Number.isInteger(d) && d >= 1 && d <= 7) && (r.kind !== 'custom' || r.days.length > 0) &&
    !!end && (end.kind === 'never' || (end.kind === 'until' && date(end.until) && end.until >= e.date) ||
    (end.kind === 'count' && Number.isInteger(end.count) && end.count >= 1 && end.count <= 99)) &&
    Number.isFinite(e.created_at) && (e.details_edited_at === null || Number.isFinite(e.details_edited_at)) && typeof e.sample === 'boolean';
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
export function migrateV1(x) {
  if (!x || x.version !== 1 || !Array.isArray(x.events) || !x.events.every(isValidV1Event) || !plain(x.done) || !Object.values(x.done).every(isValidDone)) return null;
  const result = { version: 2, events: x.events.map(e => {
    const { until, ...recurrence } = e.recurrence;
    return { ...e, all_day: false, category: 'any', color: 'blue', script: { kind: 'free' }, details_edited_at: null,
      recurrence: { ...recurrence, end: until ? { kind: 'until', until } : { kind: 'never' } } };
  }), done: x.done };
  return isValidV2State(result) ? result : null;
}
function isValidV2State(x) {
  return !!x && x.version === 2 && Array.isArray(x.events) &&
    x.events.every(e => isValidEvent(e) && e.color !== 'lime') &&
    plain(x.done) && Object.values(x.done).every(isValidDone);
}
export function migrateV2(x) {
  if (!isValidV2State(x)) return null;
  // V2 cannot distinguish an explicitly selected blue from the old default.
  const result = { ...x, version: STORE_VERSION, events: x.events.map(e => ({ ...e, color: e.color === 'blue' ? 'lime' : e.color })) };
  return isValidState(result) ? result : null;
}
export function migrateState(x) {
  if (x?.version === 1) return migrateV2(migrateV1(x));
  if (x?.version === 2) return migrateV2(x);
  return null;
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
      if (raw !== null) { const state = JSON.parse(raw); if (isValidState(state)) return state; const migrated = migrateState(state); if (migrated) { saveSchedule(userId, migrated, opts.storage); return migrated; } }
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
export function countOccurrencesBefore(event, day) {
  const [y, m, d] = event.date.split('-').map(Number), cursor = new Date(y, m - 1, d), firstWeekday = cursor.getDay() || 7;
  let count = 0;
  while (true) {
    const key = `${String(cursor.getFullYear()).padStart(4, '0')}-${String(cursor.getMonth() + 1).padStart(2, '0')}-${String(cursor.getDate()).padStart(2, '0')}`;
    const end = event.recurrence.end;
    if (key >= day || (end.kind === 'until' && key > end.until) || (end.kind === 'count' && count >= end.count)) return count;
    const weekday = cursor.getDay() || 7, kind = event.recurrence.kind;
    if (kind === 'daily' || (kind === 'none' && key === event.date) || (kind === 'weekly' && weekday === firstWeekday) || (kind === 'custom' && event.recurrence.days.includes(weekday))) count++;
    cursor.setDate(cursor.getDate() + 1);
  }
}
export function remainingCount(event, day) {
  return event.recurrence.end.kind === 'count' ? event.recurrence.end.count - countOccurrencesBefore(event, day) : null;
}
export function deleteFromOccurrence(state, eventId, day) {
  const event = state.events.find(e => e.id === eventId);
  if (!event) return state;
  if (event.recurrence.kind === 'none' || !countOccurrencesBefore(event, day)) return deleteEvent(state, eventId);
  return { ...state, events: state.events.map(e => e.id === eventId ? { ...e, recurrence: { ...e.recurrence, end: { kind: 'until', until: previousDay(day) } } } : e) };
}
export function editOccurrence(state, eventId, day, changes, { now, newId }) {
  const event = state.events.find(e => e.id === eventId);
  if (!event) return state;
  const keys = ['date','time','all_day','duration_min','note','category','color','script','recurrence'];
  const patch = Object.fromEntries(keys.filter(k => changes[k] !== undefined).map(k => [k, changes[k]]));
  if (event.recurrence.kind !== 'none' && patch.date < day) delete patch.date;
  const different = k => k in patch && JSON.stringify(patch[k]) !== JSON.stringify(event[k]);
  const created_at = ['date','time','all_day','recurrence'].some(different) ? now : event.created_at;
  const details_edited_at = ['duration_min','note','category','color','script'].some(different) ? now : event.details_edited_at;
  if (event.recurrence.kind === 'none') return { ...state, events: state.events.map(e => e.id === eventId ? { ...e, ...patch, created_at, details_edited_at } : e) };
  const before = countOccurrencesBefore(event, day);
  const old = { ...event, recurrence: { ...event.recurrence, end: { kind: 'until', until: previousDay(day) } } };
  const end = event.recurrence.end.kind === 'count' ? { kind: 'count', count: event.recurrence.end.count - before } : event.recurrence.end;
  const next = { ...event, ...patch, id: newId, date: patch.date ?? day, recurrence: patch.recurrence ?? { ...event.recurrence, end }, created_at, details_edited_at };
  return { ...state, events: state.events.flatMap(e => e.id === eventId ? (before ? [old, next] : [next]) : [e]) };
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
