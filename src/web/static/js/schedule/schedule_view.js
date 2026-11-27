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
// Keep in sync with --event-lime and SCHEDULE_COLORS.
const STYLE_COLORS = { lime: '#84CC16', blue: '#1D4ED8', green: '#047857', amber: '#D97706', brown: '#92400E', red: '#B91C1C', slate: '#1B2433', gray: '#5B6475', sky: '#BBD0FB' };
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
  const color = STYLE_COLORS[colorKey] || STYLE_COLORS.lime;
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
export function cardTags(durationMin, category, words) {
  const anyCategory = category === 'any' || !category;
  return [{ kind: 'length', tone: durationMin == null ? 'any' : 'length', text: lengthLabel(durationMin, words) }, { kind: 'category', tone: anyCategory ? 'any' : 'category', text: anyCategory ? words.anyCategory : words.categoryName(category) }];
}
export function cardScriptLine(script, words) {
  const text = script?.kind === 'saved' ? (script.title ? words.saved.replace('{title}', script.title) : words.savedNoTitle) : script?.kind === 'ai' ? words.ai : words.free;
  return { text, title: text };
}

export function chipsThatFit(cellInnerHeight, headerHeight, chipHeight, moreHeight, gap, total) {
  const count = Math.max(0, Math.floor(total));
  if (!count) return { shown: 0, more: 0 };
  const available = Math.max(0, cellInnerHeight - headerHeight);
  if (chipHeight > 0 && (count === 1 ? chipHeight : count * (chipHeight + gap)) <= available) return { shown: count, more: 0 };
  const shown = chipHeight > 0 ? Math.max(0, Math.min(count - 1, Math.floor((available - moreHeight - gap) / (chipHeight + gap)))) : 0;
  return { shown, more: count - shown };
}

export const WEEK_MIN_BLOCK_MIN = 30;
const localKey = d => `${String(d.getFullYear()).padStart(4, '0')}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const localDate = key => { const [y, m, d] = key.split('-').map(Number); return new Date(y, m - 1, d); };
export function slotStartTime(dayKey, hour, now, stepMin = 5) {
  const start = localDate(dayKey); start.setHours(hour, 0, 0, 0);
  const end = localDate(dayKey); end.setHours(hour + 1, 0, 0, 0);
  if (end.getTime() <= now) return null;
  if (start.getTime() > now) return `${String(hour).padStart(2, '0')}:00`;
  const current = new Date(now), minutes = current.getHours() * 60 + (Math.floor(current.getMinutes() / stepMin) + 1) * stepMin;
  return minutes >= 1440 ? null : `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;
}
export function slotTarget(dayIndex, hour, key, isOpen) {
  if (key === 'Home' || key === 'End') {
    const start = key === 'Home' ? 0 : 23, step = key === 'Home' ? 1 : -1;
    for (let h = start; h >= 0 && h < 24; h += step) if (isOpen(dayIndex, h)) return { dayIndex, hour: h };
  } else if (key === 'ArrowUp' || key === 'ArrowDown') {
    const step = key === 'ArrowUp' ? -1 : 1;
    for (let h = hour + step; h >= 0 && h < 24; h += step) if (isOpen(dayIndex, h)) return { dayIndex, hour: h };
  } else if (key === 'ArrowLeft' || key === 'ArrowRight') {
    const step = key === 'ArrowLeft' ? -1 : 1;
    for (let d = dayIndex + step; d >= 0 && d < 7; d += step) {
      if (isOpen(d, hour)) return { dayIndex: d, hour };
      for (let h = 0; h < 24; h++) if (isOpen(d, h)) return { dayIndex: d, hour: h };
    }
  }
  return null;
}
export function weekDays(key) {
  const date = localDate(key); date.setDate(date.getDate() - (date.getDay() + 6) % 7);
  return Array.from({ length: 7 }, (_, i) => localKey(new Date(date.getFullYear(), date.getMonth(), date.getDate() + i)));
}
export function otherView(view) { return view === 'month' ? 'week' : 'month'; }
export function weekForMonthView(monthKey, now) {
  const today = localKey(new Date(now));
  return weekDays(today.slice(0, 7) === monthKey ? today : monthKey + '-01')[0];
}
export function monthForWeekView(weekStart, now) {
  const days = weekDays(weekStart), today = localKey(new Date(now));
  // The ISO week belongs to the month/year containing Thursday, with at least four days in that month.
  return (days.includes(today) ? today : days[3]).slice(0, 7);
}
export function weekRangeLabel(key, fmt) {
  const days = weekDays(key), a = localDate(days[0]), b = localDate(days[6]);
  const differentYear = a.getFullYear() !== b.getFullYear();
  const first = `${fmt(a, { month: 'short' })} ${a.getDate()}${differentYear ? ', ' + a.getFullYear() : ''}`;
  const last = `${a.getMonth() !== b.getMonth() || differentYear ? fmt(b, { month: 'short' }) + ' ' : ''}${b.getDate()}, ${b.getFullYear()}`;
  return `${first} \u2013 ${last}`;
}
export function blockGeometry(startMin, durationMin, hourPx) {
  const start = Math.max(0, Math.min(1440, startMin));
  return { top: start * hourPx / 60, height: Math.max(0, Math.min(1440 - start, Math.max(WEEK_MIN_BLOCK_MIN, durationMin || 0))) * hourPx / 60 };
}
export function initialScrollHour(days, today, nowHour) { return days.includes(today) ? nowHour : 7; }
export function layoutDayBlocks(items) {
  const sorted = items.map((item, index) => ({ ...item, index })).sort((a, b) => a.startMin - b.startMin || a.endMin - b.endMin || a.index - b.index);
  const output = Array(items.length); let cluster = [], ends = [], clusterEnd = -Infinity;
  const finish = () => { const cols = ends.length; cluster.forEach(item => { output[item.index] = { ...items[item.index], col: item.col, cols }; }); };
  sorted.forEach(item => {
    if (cluster.length && item.startMin >= clusterEnd) { finish(); cluster = []; ends = []; clusterEnd = -Infinity; }
    let col = ends.findIndex(end => end <= item.startMin); if (col < 0) col = ends.length;
    ends[col] = item.endMin; clusterEnd = Math.max(clusterEnd, item.endMin); cluster.push({ ...item, col });
  });
  if (cluster.length) finish(); return output;
}
