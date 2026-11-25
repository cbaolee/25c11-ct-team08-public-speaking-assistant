import { T } from '../i18n.js';
import { S, RENDER } from '../state.js';
import { openModal, closeModal, enhanceSelect, toast } from '../ui.js';
import { openConfirmDialog } from '../modals/confirm.js';
import { dayKey, parseDay, addDays, expandOccurrences, occurrenceStatus, validateEvent, seedSchedule, reminderSkipped, reminderAt, REMINDER_LEAD_MIN, NOTE_MAX_CHARS, DURATIONS_MIN } from '../schedule/schedule_model.js';
import { loadSchedule, saveSchedule, resetSchedule, addEvent, deleteEvent, newEventId } from '../schedule/schedule_store.js';
import { monthGrid } from '../schedule/schedule_view.js';

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
  $('schToday').onclick = () => { month = new Date(); render(); };
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
