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

// Kept local because this pure module is also loaded from a data URL in tests.
const STYLE_COLORS = { blue: '#1D4ED8', green: '#047857', amber: '#D97706', brown: '#92400E', red: '#B91C1C', slate: '#1B2433', gray: '#5B6475', sky: '#BBD0FB' };
export const DONE_FILL_OPACITY = 0.5;
export const MISSED_BORDER_OPACITY = 0.6;
const channels = hex => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
export function blendOver(hex, opacity, baseHex) {
  const base = channels(baseHex);
  return '#' + channels(hex).map((value, i) => Math.round(value * opacity + base[i] * (1 - opacity)).toString(16).padStart(2, '0')).join('').toUpperCase();
}
export function contrastRatio(hexA, hexB) {
  const luminance = hex => channels(hex).map(value => value / 255).map(value => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4).reduce((sum, value, i) => sum + value * [0.2126, 0.7152, 0.0722][i], 0);
  const a = luminance(hexA), b = luminance(hexB);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}
export function occurrenceStyle(status, colorKey) {
  const color = STYLE_COLORS[colorKey] || STYLE_COLORS.blue;
  const missed = status === 'missed', opacity = status === 'done' ? DONE_FILL_OPACITY : 1;
  const background = missed ? '#FFFFFF' : blendOver(color, opacity, '#FFFFFF');
  const text = contrastRatio('#FFFFFF', background) > contrastRatio('#1B2433', background) ? '#FFFFFF' : '#1B2433';
  return { fill: missed ? null : color, fillOpacity: missed ? 0 : opacity, border: color, borderOpacity: missed ? MISSED_BORDER_OPACITY : 1, borderStyle: missed ? 'dashed' : 'solid', ring: status === 'active', text };
}

export function rgba(hex, opacity) { return `rgba(${channels(hex).join(', ')}, ${opacity})`; }
export function styleVars(style) {
  return { '--sch-ev-fill': style.fill ? rgba(style.fill, style.fillOpacity) : 'transparent', '--sch-ev-border': rgba(style.border, style.borderOpacity), '--sch-ev-border-style': style.borderStyle, '--sch-ev-text': style.text, '--sch-ev-ring': style.ring ? style.border : 'transparent' };
}
export function sessionTimeLabel(occ, fmtTime, words) { return occ.all_day ? words.allDay : fmtTime(occ.start); }
export function lengthLabel(min, words) { return min == null ? words.anyLength : words.minutes.replace('{n}', String(min)); }

export function chipsThatFit(cellInnerHeight, headerHeight, chipHeight, moreHeight, gap, total) {
  const count = Math.max(0, Math.floor(total));
  if (!count) return { shown: 0, more: 0 };
  const available = Math.max(0, cellInnerHeight - headerHeight);
  if (chipHeight > 0 && count * (chipHeight + gap) <= available) return { shown: count, more: 0 };
  const shown = chipHeight > 0 ? Math.max(0, Math.min(count - 1, Math.floor((available - moreHeight - gap) / (chipHeight + gap)))) : 0;
  return { shown, more: count - shown };
}
