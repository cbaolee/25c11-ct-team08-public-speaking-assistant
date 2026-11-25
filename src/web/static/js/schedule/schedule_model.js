export const CHECKIN_WINDOW_H = 6;
export const REMINDER_LEAD_MIN = 30;
export const NOTE_MAX_CHARS = 200;
export const DURATIONS_MIN = [5, 10, 15, 20];
export const RECURRENCE_KINDS = ['none', 'daily', 'weekly', 'custom'];

// Format a timestamp as a local calendar date.
const pad = (value, width = 2) => String(value).padStart(width, '0');
const byStart = (a, b) => a.start - b.start || (a.key < b.key ? -1 : a.key > b.key ? 1 : 0);

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
  const [h, min] = event.time.split(':').map(Number);
  return new Date(y, m - 1, d, h, min).getTime();
}
// Return Monday as 1 and Sunday as 7.
export function isoWeekday(ms) { return new Date(ms).getDay() || 7; }
// Local days are not always 24 hours, so advance the calendar with setDate.
export function addDays(ms, n) { const d = new Date(ms); d.setDate(d.getDate() + n); return d.getTime(); }
// Find the local Monday for a timestamp.
export function startOfWeek(ms) { return addDays(parseDay(dayKey(ms)), 1 - isoWeekday(ms)); }

// Expand recurring events within the requested range.
export function expandOccurrences(events, range, done = {}) {
  const result = [];
  for (const event of events) {
    const first = parseDay(event.date);
    // Start at the range's local day so long-running repeats stay bounded.
    let day = Math.max(first, parseDay(dayKey(range.from)));
    const end = parseDay(dayKey(range.to));
    while (day <= end && (!event.recurrence.until || dayKey(day) <= event.recurrence.until)) {
      const keyDay = dayKey(day), kind = event.recurrence.kind;
      const matches = kind === 'daily' || (kind === 'none' && keyDay === event.date) ||
        (kind === 'weekly' && isoWeekday(day) === isoWeekday(first)) ||
        (kind === 'custom' && event.recurrence.days.includes(isoWeekday(day)));
      if (matches) {
        const start = eventStart({ date: keyDay, time: event.time });
        const key = `${event.id}@${keyDay}`;
        if (start >= range.from && start < range.to) {
          result.push({ key, event_id: event.id, day: keyDay, start,
            duration_min: event.duration_min, note: event.note, sample: event.sample,
            checkin_at: done[key]?.checkin_at ?? null, done_at: done[key]?.done_at ?? null });
        }
      }
      day = addDays(day, 1);
    }
  }
  return result.sort(byStart);
}
// Find the exclusive end of the check-in window.
export function windowClosesAt(occ) {
  // A session belongs to its own day, so its window never crosses midnight.
  return Math.min(occ.start + CHECKIN_WINDOW_H * 60 * 60 * 1000, addDays(parseDay(occ.day), 1));
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
export function reminderAt(occ) { return occ.start - REMINDER_LEAD_MIN * 60000; }
// Check whether there is enough lead time for a reminder.
export function reminderSkipped(occ, createdAt) { return occ.start - createdAt < REMINDER_LEAD_MIN * 60000; }
// Validate event fields and their start time.
const validDate = date => typeof date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(date) &&
  dayKey(parseDay(date)) === date;
const validTime = time => typeof time === 'string' && /^\d{2}:\d{2}$/.test(time) &&
  Number(time.slice(0, 2)) < 24 && Number(time.slice(3)) < 60;

export function validateEvent(input, now) {
  const errors = {};
  const dateValid = validDate(input.date);
  const timeValid = validTime(input.time);
  if (!dateValid || !timeValid) errors.start = 'invalid';
  else if (eventStart(input) <= now) errors.start = 'past';
  if (!DURATIONS_MIN.includes(input.duration_min)) errors.duration_min = 'invalid';
  if (typeof input.note !== 'string' || input.note.length > NOTE_MAX_CHARS) errors.note = 'too_long';
  const recurrence = input.recurrence;
  if (!recurrence || !RECURRENCE_KINDS.includes(recurrence.kind)) errors.recurrence = 'invalid';
  else {
    if (recurrence.kind === 'custom' &&
        (!Array.isArray(recurrence.days) ||
         !recurrence.days.some(d => Number.isInteger(d) && d >= 1 && d <= 7))) errors.days = 'empty';
    if (recurrence.until && dateValid && recurrence.until < input.date) errors.until = 'before_start';
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
    time: `${pad(h)}:${pad(min)}`,
    duration_min: duration,
    note,
    recurrence: { kind: 'none', days: [], until: null },
    created_at: now - 14 * 24 * 60 * 60 * 1000,
    sample: true,
  }));
  const first = events[0], start = eventStart(first);
  return { events, done: { [`${first.id}@${first.date}`]: {
    checkin_at: start + 5 * 60000, done_at: start + 20 * 60000,
  } } };
}
