import { T } from '../i18n.js';
import { go } from '../nav.js';
import { S, RENDER } from '../state.js';
import { openModal, closeModal, enhanceSelect, toast } from '../ui.js';
import { openConfirmDialog } from '../modals/confirm.js';
import { dayKey, parseDay, addDays, expandOccurrences, occurrenceStatus, validateEvent, seedSchedule, reminderSkipped, reminderAt, REMINDER_LEAD_MIN, NOTE_MAX_CHARS, DURATIONS_MIN } from '../schedule/schedule_model.js';
import { loadSchedule, saveSchedule, resetSchedule, addEvent, deleteEvent, newEventId } from '../schedule/schedule_store.js';
import { monthGrid, formatCountdown, streakLabel } from '../schedule/schedule_view.js';
import { startOfWeek, todaySummary, motivationKey } from '../schedule/schedule_model.js';

const $ = id => document.getElementById(id);
let cachedUser, cachedState, month = new Date(), selectedDay;
const storage = () => { try { return window.localStorage; } catch (_) { return null; } };
const options = () => ({ storage: storage(), seed: seedSchedule, now: Date.now() });
export function getSchedule() {
  const id = S.user?.id;
  if (cachedUser !== id || !cachedState) { cachedUser = id; cachedState = loadSchedule(id, options()); }
  return cachedState;
}
export function saveScheduleState(state) { cachedUser = S.user?.id; cachedState = state; return saveSchedule(cachedUser, state, storage()); }
export function occurrencesBetween(from, to) { const state = getSchedule(); return expandOccurrences(state.events, { from, to }, state.done); }
const fmt = (value, opts) => new Intl.DateTimeFormat('en-US', opts).format(new Date(value));
const time = value => fmt(value, { hour: 'numeric', minute: '2-digit' });
const shortDate = value => fmt(value, { month: 'short', day: 'numeric' });
const fullDate = value => fmt(value, { weekday: 'long', month: 'long', day: 'numeric' });
const dateTime = value => fmt(value, { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
const node = (tag, text, cls) => { const e = document.createElement(tag); if (text != null) e.textContent = text; if (cls) e.className = cls; return e; };
const button = (text, fn, cls = 'btn btn-sm') => { const b = node('button', text, cls); b.type = 'button'; b.onclick = fn; return b; };
function chip(status, label, compact = false) {
  const el = node('span', null, 'sch-chip sch-' + status + (compact ? ' sch-compact' : ''));
  const icon = node('span', { active: '\u25CF', done: '\u2713', upcoming: '\u25CB', missed: '\u25CC' }[status], 'sch-icon'); icon.setAttribute('aria-hidden', 'true'); el.append(icon);
  if (label) el.append(node('span', label, 'sch-chip-time'));
  el.append(node('span', T('schedule.' + status), 'sch-chip-word'));
  return el;
}
function render() {
  const state = getSchedule(), keys = monthGrid(month.getFullYear(), month.getMonth()), now = Date.now();
  $('schMonth').textContent = fmt(month, { month: 'long', year: 'numeric' });
  const grid = $('schGrid'), focusedDay = document.activeElement?.dataset.schDay; grid.replaceChildren();
  const occs = occurrencesBetween(parseDay(keys[0]), addDays(parseDay(keys[41]), 1));
  keys.forEach(key => {
    const list = occs.filter(o => o.day === key), counts = {};
    list.forEach(o => { const status = occurrenceStatus(o, now); counts[status] = (counts[status] || 0) + 1; });
    const date = fullDate(parseDay(key));
    const description = Object.entries(counts).map(([status, count]) => `${count} ${T('schedule.' + (status === 'active' ? 'activeLegend' : status)).toLowerCase()}`).join(', ');
    const b = button('', () => openDay(key), 'sch-day');
    b.dataset.schDay = key;
    b.setAttribute('aria-label', list.length ? T(list.length === 1 ? 'schedule.sessionOne' : 'schedule.sessionMany', { date, count: list.length, statuses: description }) : T('schedule.noSessions', { date }));
    if (new Date(parseDay(key)).getMonth() !== month.getMonth()) b.classList.add('sch-outside');
    if (key === dayKey(now)) { b.classList.add('sch-today'); b.append(node('span', T('schedule.today'), 'sr-only')); }
    b.append(node('span', String(new Date(parseDay(key)).getDate()), 'sch-day-number'));
    list.slice(0, 2).forEach(o => b.append(chip(occurrenceStatus(o, now), time(o.start), true)));
    if (list.length > 2) b.append(node('span', T('schedule.more', { n: list.length - 2 }), 'sch-more'));
    grid.append(b);
  });
  $('schEmpty').hidden = state.events.length !== 0;
  if (focusedDay) grid.querySelector(`[data-sch-day="${focusedDay}"]`)?.focus();
}
function openDay(key) {
  selectedDay = key; $('schDayTitle').textContent = fullDate(parseDay(key));
  const list = $('schDayList'); list.replaceChildren();
  const occs = occurrencesBetween(parseDay(key), addDays(parseDay(key), 1));
  if (!occs.length) { list.append(node('p', T('schedule.nothing')), button(T('schedule.newEvent'), () => openEvent(key), 'btn btn-primary')); }
  occs.forEach(occ => {
    const event = getSchedule().events.find(e => e.id === occ.event_id), row = node('div', null, 'sch-entry');
    row.append(node('strong', `${time(occ.start)} – ${time(occ.start + occ.duration_min * 60000)} · ${T('schedule.minutes', { n: occ.duration_min })}`));
    row.append(chip(occurrenceStatus(occ, Date.now())));
    if (occ.note) row.append(node('p', occ.note, 'sch-note'));
    if (event.recurrence.kind !== 'none') {
      const kind = T('schedule.' + event.recurrence.kind + 'Lower');
      row.append(node('p', event.recurrence.until ? T('schedule.repeatsUntil', { kind, date: shortDate(parseDay(event.recurrence.until)) }) : T('schedule.repeats', { kind }), 'note'));
    }
    const actions = node('div', null, 'sch-actions');
    actions.append(button(T('schedule.email'), () => openEmail(occ, event)), button(T('schedule.delete'), () => openConfirmDialog(T('schedule.deleteQuestion'), T('schedule.deleteDetail'), T('schedule.delete'), () => { saveScheduleState(deleteEvent(getSchedule(), event.id)); render(); openDay(key); toast(T('schedule.deleted')); })));
    const slot = node('div'); slot.dataset.schCheckin = ''; actions.append(slot); row.append(actions); list.append(row);
  });
  if (!$('schDayDrawer').classList.contains('show')) openModal('schDayDrawer');
}
function openEvent(key) {
  const form = $('schForm'); form.reset(); $('schLength').value = '10'; $('schRepeat').value = 'none';
  $('schDate').min = dayKey(Date.now()); $('schDate').value = key && key >= $('schDate').min ? key : $('schDate').min;
  $('schUntil').min = $('schDate').value; $('schDays').hidden = true;
  ['Start', 'Length', 'Note', 'Repeat', 'Days', 'Until'].forEach(k => { $('sch' + k + 'Error').textContent = ''; $('sch' + k + 'Error').classList.remove('show'); });
  ['schDate', 'schTime', 'schLength', 'schNote', 'schRepeat', 'schUntil'].forEach(id => $(id).removeAttribute('aria-invalid'));
  $('schCount').textContent = T('schedule.count', { n: 0, max: NOTE_MAX_CHARS });
  openModal('schEventModal', { focus: '#schDate' });
}
function openEmail(occ, event) {
  const body = $('schEmailBody'); body.replaceChildren();
  [T('schedule.to', { value: S.user.email }), T('schedule.from'), T('schedule.subject', { lead: REMINDER_LEAD_MIN, length: occ.duration_min, time: time(occ.start) }), S.user.name?.trim() ? T('schedule.greeting', { name: S.user.name }) : T('schedule.greetingNameless'), T('schedule.when', { when: dateTime(occ.start) }), T('schedule.emailLength', { length: occ.duration_min }), ...(occ.note ? [T('schedule.emailNote', { note: occ.note })] : [])].forEach(text => body.append(node('p', text)));
  const disabled = button(T('schedule.openPractice'), () => {}, 'btn btn-primary'); disabled.disabled = true; disabled.setAttribute('aria-disabled', 'true'); body.append(disabled);
  $('schEmailFooter').textContent = reminderSkipped(occ, event.created_at) ? T('schedule.skipped') : T('schedule.wouldSend', { when: dateTime(reminderAt(occ)) });
  openModal('schEmailModal');
}
function init() {
  T('schedule.weekdays').forEach((name, i) => { $('schWeekdays').append(node('span', name)); const label = node('label'); const input = node('input'); input.type = 'checkbox'; input.value = i + 1; label.append(input, document.createTextNode(name)); $('schDayChecks').append(label); });
  ['upcoming', 'active', 'done', 'missed'].forEach(status => { const c = chip(status); if (status === 'active') c.lastChild.textContent = T('schedule.activeLegend'); $('schLegend').append(c); });
  DURATIONS_MIN.forEach(n => $('schLength').add(new Option(T('schedule.minutes', { n }), n))); $('schLength').value = '10';
  ['none', 'daily', 'weekly', 'custom'].forEach(k => $('schRepeat').add(new Option(T('schedule.' + k), k)));
  enhanceSelect($('schLength')); enhanceSelect($('schRepeat'));
  $('schNote').maxLength = NOTE_MAX_CHARS; $('schNote').oninput = () => { $('schCount').textContent = T('schedule.count', { n: $('schNote').value.length, max: NOTE_MAX_CHARS }); };
  $('schRepeat').onchange = () => { $('schDays').hidden = $('schRepeat').value !== 'custom'; };
  $('schDate').onchange = () => { $('schUntil').min = $('schDate').value; };
  $('schReminder').textContent = T('schedule.reminder', { n: REMINDER_LEAD_MIN });
  $('schNew').onclick = $('schEmptyNew').onclick = () => openEvent();
  $('schReset').onclick = () => openConfirmDialog(T('schedule.resetQuestion'), T('schedule.resetDetail'), T('schedule.reset'), () => { cachedState = resetSchedule(S.user.id, options()); cachedUser = S.user.id; render(); toast(T('schedule.resetDone')); });
  $('schPrev').onclick = () => { month = new Date(month.getFullYear(), month.getMonth() - 1, 1); render(); };
  $('schNext').onclick = () => { month = new Date(month.getFullYear(), month.getMonth() + 1, 1); render(); };
  document.querySelector('#screenSchedule #schToday').onclick = () => { month = new Date(); render(); };
  $('schForm').onsubmit = e => {
    e.preventDefault(); const input = { date: $('schDate').value, time: $('schTime').value, duration_min: Number($('schLength').value), note: $('schNote').value, recurrence: { kind: $('schRepeat').value, days: [...$('schDayChecks').querySelectorAll('input:checked')].map(x => Number(x.value)), until: $('schUntil').value || null } };
    const result = validateEvent(input, Date.now()), errors = result.errors;
    const fields = [['start', 'Start', errors.start === 'past' ? 'past' : 'invalid', 'schTime'], ['duration_min', 'Length', 'invalidLength', 'schLength'], ['note', 'Note', 'invalidNote', 'schNote'], ['recurrence', 'Repeat', 'invalidRepeat', 'schRepeat'], ['days', 'Days', 'invalidDays', null], ['until', 'Until', 'invalidUntil', 'schUntil']];
    fields.forEach(([key, target, message, id]) => { $('sch' + target + 'Error').textContent = errors[key] ? T('schedule.' + message) : ''; $('sch' + target + 'Error').classList.toggle('show', !!errors[key]); if (id) $(id).setAttribute('aria-invalid', String(!!errors[key])); });
    $('schDate').setAttribute('aria-invalid', String(!!errors.start));
    if (!result.ok) { const first = fields.find(([key]) => errors[key]); if (first[3]) $(first[3]).focus(); else $('schDayChecks').querySelector('input').focus(); return; }
    saveScheduleState(addEvent(getSchedule(), { ...input, id: newEventId(), created_at: Date.now(), sample: false })); closeModal('schEventModal'); render(); if (S.modal.includes('schDayDrawer')) openDay(selectedDay); toast(T('schedule.created'));
  };
}
let initialized = false;
RENDER.schedule = () => { if (!initialized) { init(); initialized = true; } render(); };
setInterval(() => { if (S.screen === 'schedule') render(); }, 60000);

export function openTodayEvent() { month = new Date(); render(); openEvent(dayKey(Date.now())); }
export function openTodayDrawer() { month = new Date(); render(); openDay(dayKey(Date.now())); }

const todayButton = (text, cls, action) => {
  const el = node('button', text, cls);
  el.type = 'button';
  if (action) el.addEventListener('click', action);
  return el;
};
export function renderTodayPanel() {
  const now = Date.now(), today = parseDay(dayKey(now));
  const summary = todaySummary(occurrencesBetween(addDays(startOfWeek(now), -56), addDays(today, 2)), now);
  const panel = document.getElementById('schTodayPanel');
  panel.replaceChildren();
  const head = node('div', null, 'sch-today-head');
  const heading = node('h2', T('schedule.todayPanel.heading')); heading.id = 'schTodayH';
  const streak = node('span', null, 'sch-streak');
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('aria-hidden', 'true');
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', 'M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.07-2.14-.22-4.05 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.15.43-2.29 1-3a2.5 2.5 0 0 0 2.5 2.5z');
  svg.append(path); streak.append(svg, document.createTextNode(streakLabel(summary.streak, T('schedule.todayPanel.noStreak'), T('schedule.todayPanel.streak'))));
  head.append(heading, node('span', T('schedule.demo'), 'badge-demo'), streak, node('span', T('schedule.todayPanel.weekCount', summary.week), 'sch-week-count'));
  panel.append(head);
  const body = node('div', null, 'sch-today-body'), occ = summary.primary;
  if (occ) {
    const time = new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit' }).format(new Date(occ.start));
    body.append(node('strong', T('schedule.todayPanel.' + summary.status + 'Time', { time, len: occ.duration_min })));
    if (summary.status === 'done' || summary.status === 'missed') body.append(node('span', (summary.status === 'done' ? '\u2713 ' : '\u25CC ') + T('schedule.' + summary.status), 'sch-chip sch-' + summary.status));
    if ((summary.status === 'active' || summary.status === 'upcoming') && occ.note) body.append(node('p', occ.note, 'sch-note'));
    if (summary.status === 'active') {
      body.append(node('p', T('schedule.todayPanel.closes', { time: formatCountdown(summary.closes_in_ms) })));
      const check = todayButton(T('schedule.todayPanel.checkIn'), 'btn btn-primary');
      check.dataset.schCheckin = occ.key; check.dataset.go = 'schedule'; body.append(check);
    }
  } else {
    body.append(node('p', T('schedule.todayPanel.nothing')));
    body.append(todayButton(T('schedule.todayPanel.plan'), 'btn btn-primary', () => { go('schedule'); openTodayEvent(); }));
  }
  if (summary.more) body.append(todayButton(T('schedule.todayPanel.more', { n: summary.more }), 'sch-today-link', () => { go('schedule'); openTodayDrawer(); }));
  panel.append(body);
  const dots = node('div', null, 'sch-week-dots');
  const days = T('schedule.todayPanel.days'), letters = T('schedule.todayPanel.letters'), states = T('schedule.todayPanel.states');
  summary.week.dots.forEach((dot, i) => {
    const item = node('span', null, 'sch-week-dot-item' + (dot.day === dayKey(now) ? ' sch-week-dot-today' : ''));
    item.append(node('span', T('schedule.todayPanel.dot', { day: days[i], state: states[dot.state] }), 'sr-only'));
    const circle = node('span', null, 'sch-week-dot sch-week-dot-' + dot.state); circle.setAttribute('aria-hidden', 'true');
    const letter = node('span', letters[i]); letter.setAttribute('aria-hidden', 'true'); item.append(circle, letter); dots.append(item);
  });
  panel.append(dots);
  const motivation = motivationKey(summary);
  if (motivation) panel.append(node('p', T('schedule.motivation.' + motivation, { n: summary.streak, len: occ?.duration_min }), 'sch-motivation'));
}
