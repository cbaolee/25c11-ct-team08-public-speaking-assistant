export function monthGrid(year, month) {
  const first = new Date(year, month, 1);
  first.setDate(1 - ((first.getDay() + 6) % 7));
  return Array.from({ length: 42 }, (_, i) => {
    const d = new Date(first.getFullYear(), first.getMonth(), first.getDate() + i);
    return `${String(d.getFullYear()).padStart(4, '0')}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  });
}

export function formatCountdown(ms) {
  const minutes = Math.max(0, Math.floor(ms / 60000));
  const hours = Math.floor(minutes / 60);
  return hours ? `${hours} h ${minutes % 60} min` : `${minutes} min`;
}
export function streakLabel(n, noStreak, streak) { return n ? streak.replace('{n}', String(n)) : noStreak; }

export function shouldCompleteCheckIn(ctx, detail) { return !!ctx && detail?.status === 'ok' && detail.overall != null; }
export function shouldClearOnLeave(onPractice, background) { return !onPractice && !background; }

export const MINUTE_STEPS = Array.from({ length: 12 }, (_, i) => i * 5);
export function to12h(value) { const [h, m] = value.split(':').map(Number); return { h: h % 12 || 12, m, pm: h >= 12 }; }
export function to24h(h, m, pm) { return `${String(h % 12 + (pm ? 12 : 0)).padStart(2, '0')}:${String(m).padStart(2, '0')}`; }
export const monthMatrix = monthGrid;
export function moveDay(key, action) {
  const [y, m, d] = key.split('-').map(Number), date = new Date(y, m - 1, d);
  const delta = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7, Home: -((date.getDay() + 6) % 7), End: 6 - ((date.getDay() + 6) % 7) }[action];
  if (delta !== undefined) date.setDate(date.getDate() + delta);
  if (action === 'PageUp' || action === 'PageDown') { const day = date.getDate(); date.setDate(1); date.setMonth(date.getMonth() + (action === 'PageUp' ? -1 : 1)); const last = new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate(); date.setDate(Math.min(day, last)); }
  return `${String(date.getFullYear()).padStart(4, '0')}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}
export function defaultTime(nowMs, dateKey) {
  const now = new Date(nowMs), today = `${String(now.getFullYear()).padStart(4, '0')}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  if (dateKey !== today) return '19:00';
  const next = new Date(nowMs); next.setMinutes((Math.floor(now.getMinutes() / 30) + 1) * 30, 0, 0);
  return next.getDate() === now.getDate() ? `${String(next.getHours()).padStart(2, '0')}:${String(next.getMinutes()).padStart(2, '0')}` : '';
}

export function sessionsSummary(days) { return { n: days.length, last: days.length ? days[days.length - 1] : null }; }

export function resultLink(record, sessions) { return typeof record?.session_id === 'string' && record.session_id && sessions.some(session => session.id === record.session_id) ? record.session_id : null; }

export function wrapWheel(value, min, max) { const size = max - min + 1; return ((value - min) % size + size) % size + min; }
export function clampWheel(value, min, max) { return Math.max(min, Math.min(max, value)); }
export function wheelWindow(value, min, max, wrap = false) {
  return [-1, 0, 1].map(offset => { const next = value + offset; return wrap ? wrapWheel(next, min, max) : next < min || next > max ? null : next; });
}

export function formatDurationWords(ms, words = { hour: 'hour', hours: 'hours', minute: 'minute', minutes: 'minutes', lessThanMinute: 'less than a minute' }) {
  const total = Math.max(0, Math.floor(ms / 60000)), hours = Math.floor(total / 60), minutes = total % 60;
  if (total === 0) return words.lessThanMinute;   // "0 minutes" reads like the window has already closed
  return [hours ? `${hours} ${words[hours === 1 ? 'hour' : 'hours']}` : '', minutes || !hours ? `${minutes} ${words[minutes === 1 ? 'minute' : 'minutes']}` : ''].filter(Boolean).join(' ');
}
export function closesTone(ms) { return ms >= 60 * 60000 ? 'ok' : 'danger'; }
export function carouselStep(index, total, visible, step) { return Math.max(0, Math.min(Math.max(0, total - visible), index + step)); }
export function edgeFades(index, total, visible) { return { left: index > 0, right: index + visible < total }; }
