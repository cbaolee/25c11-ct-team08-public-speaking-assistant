export const ALL_DAY_REMINDER_HOUR = 8;
export const COUNT_MIN = 1, COUNT_MAX = 99;
export const SCHEDULE_CATEGORIES = ['cinematography', 'gender_studies', 'information_technology', 'learning_experiences', 'sports', 'wildlife'];
export const SCHEDULE_COLORS = [{key:'blue',hex:'#1D4ED8'},{key:'green',hex:'#047857'},{key:'amber',hex:'#D97706'},{key:'brown',hex:'#92400E'},{key:'red',hex:'#B91C1C'},{key:'slate',hex:'#1B2433'},{key:'gray',hex:'#5B6475'},{key:'sky',hex:'#BBD0FB'}];
export const DEFAULT_COLOR = 'blue';
export const CHECKIN_WINDOW_H = 6;
export const REMINDER_LEAD_MIN = 30;
export const NOTE_MAX_CHARS = 200;
export const DURATIONS_MIN = [5, 10, 15, 20];
export const RECURRENCE_KINDS = ['none', 'daily', 'weekly', 'custom'];

// Format a timestamp as a local calendar date.
const pad = (value, width = 2) => String(value).padStart(width, '0');
const byStart = (a, b) => a.start - b.start || Number(!!b.all_day) - Number(!!a.all_day) || (a.key < b.key ? -1 : a.key > b.key ? 1 : 0);

export function dayKey(ms) {
  const d = new Date(ms);
  return `${pad(d.getFullYear(), 4)}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
// Parse a local calendar date at midnight.
export function parseDay(day) {
  const [y, m, d] = day.split('-').map(Number);
  return new Date(y, m - 1, d).getTime();
}
// Combine an event's local date and time.
export function eventStart(event) {
  const [y, m, d] = event.date.split('-').map(Number);
  const [h, min] = event.all_day ? [0, 0] : event.time.split(':').map(Number);
  return new Date(y, m - 1, d, h, min).getTime();
}
// Return Monday as 1 and Sunday as 7.
export function isoWeekday(ms) { return new Date(ms).getDay() || 7; }
// Local days are not always 24 hours, so advance the calendar with setDate.
export function addDays(ms, n) { const d = new Date(ms); d.setDate(d.getDate() + n); return d.getTime(); }
// Find the local Monday for a timestamp.
export function startOfWeek(ms) { return addDays(parseDay(dayKey(ms)), 1 - isoWeekday(ms)); }

function matchesDay(event, day) {
  const kind = event.recurrence.kind, first = parseDay(event.date);
  return kind === 'daily' || (kind === 'none' && dayKey(day) === event.date) ||
    (kind === 'weekly' && isoWeekday(day) === isoWeekday(first)) ||
    (kind === 'custom' && event.recurrence.days.includes(isoWeekday(day)));
}
export function seriesUntil(event) {
  if (event.recurrence.kind === 'none') return event.date;
  const end = event.recurrence.end;
  if (end.kind === 'never') return null;
  if (end.kind === 'until') return end.until;
  let day = parseDay(event.date), count = 0;
  for (let i = 0; i < 700 && count < end.count; i++, day = addDays(day, 1)) {
    if (matchesDay(event, day) && ++count === end.count) return dayKey(day);
  }
  return null;
}
export function expandOccurrences(events, range, done = {}) {
  const result = [];
  for (const event of events) {
    const until = seriesUntil(event);
    let day = Math.max(parseDay(event.date), parseDay(dayKey(range.from)));
    const end = parseDay(dayKey(range.to));
    while (day <= end && (!until || dayKey(day) <= until)) {
      const keyDay = dayKey(day);
      if (matchesDay(event, day)) {
        const start = eventStart({ date: keyDay, time: event.time, all_day: event.all_day });
        const key = `${event.id}@${keyDay}`;
        if (start >= range.from && start < range.to) result.push({ key, event_id: event.id, day: keyDay, start,
          all_day: event.all_day, duration_min: event.duration_min, category: event.category, color: event.color,
          script: event.script, note: event.note, sample: event.sample,
          checkin_at: done[key]?.checkin_at ?? null, done_at: done[key]?.done_at ?? null });
      }
      day = addDays(day, 1);
    }
  }
  return result.sort(byStart);
}
export function previewOccurrenceDays(input, fromDay, toDay) {
  if (toDay < fromDay || toDay < input.date) return [];
  const event = { ...input, id: 'preview', recurrence: { ...input.recurrence, end: { kind: 'never' } } };
  return expandOccurrences([event], { from: parseDay(fromDay), to: addDays(parseDay(toDay), 1) }).map(o => o.day);
}
export function seriesSummary(input) {
  const end = input.recurrence.end;
  if (end.kind === 'never') return null;
  if (end.kind === 'count') return { n: end.count, last: seriesUntil(input) };
  const days = previewOccurrenceDays(input, input.date, end.until);
  return { n: days.length, last: days.at(-1) ?? null };
}
// An all-day session starts at midnight, before its 08:00 reminder: starting fully locks it.
export function canEditSchedule(occ, now) { return now < reminderAt(occ) && now < occ.start; }
export function canEditDetails(occ, now) { return now < occ.start; }
// Find the exclusive end of the check-in window.
export function windowClosesAt(occ) {
  // A session belongs to its own day, so its window never crosses midnight.
  return occ.all_day ? addDays(parseDay(occ.day), 1) : Math.min(occ.start + CHECKIN_WINDOW_H * 60 * 60 * 1000, addDays(parseDay(occ.day), 1));
}
// Determine a session's status at the supplied time.
export function occurrenceStatus(occ, now) {
  // A user who started on time should not be punished for a long practice.
  if (typeof occ.done_at === 'number' && canCheckIn(occ, occ.checkin_at)) return 'done';
  if (now < occ.start) return 'upcoming';
  return now < windowClosesAt(occ) ? 'active' : 'missed';
}
// Check whether a session can be checked in at a given time.
export function canCheckIn(occ, at) {
  return typeof at === 'number' && at >= occ.start && at < windowClosesAt(occ);
}
// Find the scheduled reminder time.
export function reminderAt(occ) { return occ.all_day ? new Date(...occ.day.split('-').map((v, i) => Number(v) - (i === 1 ? 1 : 0)), ALL_DAY_REMINDER_HOUR).getTime() : occ.start - REMINDER_LEAD_MIN * 60000; }
// Check whether there is enough lead time for a reminder.
export function reminderSkipped(occ, createdAt) { return createdAt > reminderAt(occ); }
export function reminderState(occ, event, now) {
  const at = reminderAt(occ);
  if (reminderSkipped(occ, event.created_at)) return 'skipped';
  if (now < at) return 'scheduled';
  return event.details_edited_at != null && event.details_edited_at >= at ? 'sent_then_edited' : 'sent';
}
// Validate event fields and their start time.
const validDate = date => typeof date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(date) &&
  dayKey(parseDay(date)) === date;
const validTime = time => typeof time === 'string' && /^\d{2}:\d{2}$/.test(time) &&
  Number(time.slice(0, 2)) < 24 && Number(time.slice(3)) < 60;

export function normalizeRecurrence(recurrence) {
  return { ...recurrence, days: recurrence.kind === 'custom' ? recurrence.days : [], end: recurrence.kind === 'none' ? { kind: 'never' } : recurrence.end };
}
export function validateEvent(input, now) {
  const errors = {}, dateValid = validDate(input.date);
  if (!dateValid || typeof input.all_day !== 'boolean' || (input.all_day ? input.time !== null : !validTime(input.time))) errors.start = 'invalid';
  else if (input.all_day && input.date === dayKey(now)) errors.start = 'all_day_today';
  else if (input.all_day ? input.date < dayKey(now) : eventStart(input) <= now) errors.start = 'past';
  if (input.duration_min !== null && !DURATIONS_MIN.includes(input.duration_min)) errors.duration_min = 'invalid';
  if (!['any', ...SCHEDULE_CATEGORIES].includes(input.category)) errors.category = 'invalid';
  if (!SCHEDULE_COLORS.some(c => c.key === input.color)) errors.color = 'invalid';
  if (!input.script || !['free', 'saved', 'ai'].includes(input.script.kind)) errors.script = 'invalid';
  else if (input.script.kind === 'saved' && (typeof input.script.script_id !== 'string' || !input.script.script_id.trim() || typeof input.script.title !== 'string')) errors.script = 'saved_missing';
  else if (input.script.kind === 'ai') {
    if (input.duration_min == null) errors.duration_min = 'ai_needs_length';
    if (input.category === 'any') errors.category = 'ai_needs_category';
  }
  if (typeof input.note !== 'string' || input.note.length > NOTE_MAX_CHARS) errors.note = 'too_long';
  const r = input.recurrence;
  if (!r || !RECURRENCE_KINDS.includes(r.kind) || !r.end || !['never', 'until', 'count'].includes(r.end.kind)) errors.recurrence = 'invalid';
  else {
    if (r.kind === 'custom' && (!Array.isArray(r.days) || (!r.days.length || !r.days.every(d => Number.isInteger(d) && d >= 1 && d <= 7)))) errors.days = 'empty';
    if (r.end.kind === 'until' && (!validDate(r.end.until) || (dateValid && r.end.until < input.date))) errors.until = 'before_start';
    if (r.end.kind === 'count' && (!Number.isInteger(r.end.count) || r.end.count < COUNT_MIN || r.end.count > COUNT_MAX)) errors.count = 'invalid';
  }
  return { ok: Object.keys(errors).length === 0, errors };
}
// Count consecutive completed weeks.
export function weeklyStreak(occs, now) {
  const weeks = new Set(occs.filter(o => occurrenceStatus(o, now) === 'done')
    .map(o => dayKey(startOfWeek(o.start))));
  const current = startOfWeek(now);
  // The current week never breaks the streak while it is still underway.
  let count = weeks.has(dayKey(current)) ? 1 : 0;
  for (let week = addDays(current, -7); weeks.has(dayKey(week)); week = addDays(week, -7)) count++;
  return count;
}
// Summarize sessions in the current local week.
export function weekProgress(occs, now) {
  const start = startOfWeek(now), end = addDays(start, 7);
  const week = occs.filter(o => o.start >= start && o.start < end);
  const order = ['done', 'active', 'upcoming', 'missed'];
  const dots = Array.from({ length: 7 }, (_, i) => {
    const day = dayKey(addDays(start, i));
    const statuses = week.filter(o => dayKey(o.start) === day).map(o => occurrenceStatus(o, now));
    return { day, state: order.find(s => statuses.includes(s)) || 'none' };
  });
  return { done: week.filter(o => occurrenceStatus(o, now) === 'done').length, total: week.length, dots };
}
// Choose today's primary session and progress.
export function todaySummary(occs, now) {
  const today = dayKey(now), yesterday = dayKey(addDays(parseDay(today), -1));
  // With the midnight cap no window crosses into the next day,
  // so today's sessions are all that can be active.
  const items = occs.filter(o => dayKey(o.start) === today).sort(byStart);
  const byStatus = status => items.filter(o => occurrenceStatus(o, now) === status);
  let status = 'none', primary = null;
  for (const candidate of ['active', 'upcoming', 'done', 'missed']) {
    const matches = byStatus(candidate);
    if (matches.length) {
      status = candidate;
      primary = candidate === 'done' ? matches[matches.length - 1] : matches[0];
      break;
    }
  }
  return {
    status, primary, more: primary ? items.length - 1 : 0,
    closes_in_ms: status === 'active' ? windowClosesAt(primary) - now : null,
    missed_yesterday: occs.some(o => dayKey(o.start) === yesterday && occurrenceStatus(o, now) === 'missed'),
    streak: weeklyStreak(occs, now), week: weekProgress(occs, now),
  };
}
// Select the message matching schedule progress.
export function motivationKey(summary) {
  // A primary occurrence identifies today's dot.
  const today = summary.primary && dayKey(summary.primary.start);
  if (summary.status === 'done' ||
      (today && summary.week.dots.some(d => d.day === today && d.state === 'done'))) return 'doneToday';
  if (summary.status === 'active' && summary.week.done === 0 && summary.streak > 0) return 'keepStreak';
  if (summary.status === 'active') return 'windowOpen';
  if (summary.missed_yesterday) return 'pickUp';
  if (summary.status === 'none') return 'plan';
  return null;
}
// Create sample sessions relative to the supplied time.
export function seedSchedule(now) {
  const today = parseDay(dayKey(now)), lastMonday = addDays(startOfWeek(now), -7);
  // Clamp the active session to 00:00 so it stays today.
  const activeDate = new Date(Math.max(today, now - 60 * 60000));
  activeDate.setMinutes(Math.floor(activeDate.getMinutes() / 5) * 5, 0, 0);
  const active = Math.max(today, activeDate.getTime());
  const specs = [
    [addDays(lastMonday, 1), 19, 0, 10, 'Read the introduction slowly.'],
    [addDays(lastMonday, 3), 19, 0, 15, 'Practice a clear ending.'],
    [active, new Date(active).getHours(), new Date(active).getMinutes(), 10, 'Practice a short opening.'],
    [addDays(today, 1), 19, 0, 20, 'Rehearse the main points.'],
  ];
  const events = specs.map(([day, h, min, duration, note], i) => ({
    id: `sample-${i + 1}`,
    date: dayKey(day),
    time: `${pad(h)}:${pad(min)}`, all_day: false, category: 'any', color: DEFAULT_COLOR, script: { kind: 'free' }, details_edited_at: null,
    duration_min: duration,
    note,
    recurrence: { kind: 'none', days: [], end: { kind: 'never' } },
    created_at: now - 14 * 24 * 60 * 60 * 1000,
    sample: true,
  }));
  const first = events[0], start = eventStart(first);
  return { events, done: { [`${first.id}@${first.date}`]: {
    checkin_at: start + 5 * 60000, done_at: start + 20 * 60000,
  } } };
}
