import { T } from '../i18n.js';
import { go } from '../nav.js';
import { S, RENDER } from '../state.js';
import { openModal, closeModal, toast } from '../ui.js';
import { openConfirmDialog } from '../modals/confirm.js';
import { dayKey, parseDay, addDays, expandOccurrences, occurrenceStatus, validateEvent, seedSchedule, reminderSkipped, reminderAt, REMINDER_LEAD_MIN, NOTE_MAX_CHARS, DURATIONS_MIN, previewOccurrenceDays } from '../schedule/schedule_model.js';
import { loadSchedule, saveSchedule, resetSchedule, addEvent, editOccurrence, deleteFromOccurrence, newEventId } from '../schedule/schedule_store.js';
import { monthGrid, formatCountdown, streakLabel, to12h, to24h, MINUTE_STEPS, moveDay, defaultTime, sessionsSummary, resultLink } from '../schedule/schedule_view.js';
import { startCheckIn, configureCheckIn } from '../schedule/schedule_checkin.js';
import { canCheckIn, canEdit } from '../schedule/schedule_model.js';
import { startOfWeek, todaySummary, motivationKey } from '../schedule/schedule_model.js';

const $ = id => document.getElementById(id);
let cachedUser, cachedState, month = new Date(), selectedDay, editing = null, datePicker, timePicker, untilPicker;
let openPopover = null;
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
function pickerShell(container, paint) {
  const trigger = container.querySelector('button'), popup = container.querySelector('.sch-popover');
  const close = (restore = true) => { popup.hidden = true; trigger.setAttribute('aria-expanded', 'false'); if (openPopover === close) openPopover = null; if (restore) trigger.focus(); };
  trigger.onclick = () => {
    if (!popup.hidden) { close(); return; }
    if (openPopover) openPopover(false);
    paint(); popup.hidden = false; trigger.setAttribute('aria-expanded', 'true'); openPopover = close;
    popup.classList.remove('sch-flip');
    const box = container.closest('.box').getBoundingClientRect();
    if (popup.getBoundingClientRect().bottom > box.bottom) popup.classList.add('sch-flip');
    popup.querySelector('[tabindex="0"], button:not(:disabled)')?.focus();
  };
  popup.addEventListener('keydown', e => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(); } });
  document.addEventListener('pointerdown', e => { if (!popup.hidden && !container.contains(e.target)) close(false); });
  return { trigger, popup, close };
}
function makeDatePicker(container, { min, value, onChange, markDays = () => [], allowEmpty = false }) {
  let minimum = min, current = value, cursor = value || min;
  const shell = pickerShell(container, paint);
  function update() { shell.trigger.value = current; shell.trigger.textContent = current ? fmt(parseDay(current), { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' }) : T('schedule.noEndDate'); }
  function paint() {
    const popup = shell.popup; popup.replaceChildren();
    const date = new Date(parseDay(cursor)), header = node('div', null, 'sch-picker-header');
    const changeMonth = action => { cursor = moveDay(cursor, action); if (cursor < minimum) cursor = minimum; paint(); popup.querySelector('[tabindex="0"]')?.focus(); };
    const prev = button('\u2039', () => changeMonth('PageUp'), 'sch-picker-control'); prev.setAttribute('aria-label', T('schedule.previous'));
    const next = button('\u203A', () => changeMonth('PageDown'), 'sch-picker-control'); next.setAttribute('aria-label', T('schedule.nextMonth'));
    header.append(prev, node('strong', fmt(date, { month: 'long', year: 'numeric' })), next); popup.append(header);
    const grid = node('div', null, 'sch-mini-grid');
    T('schedule.weekdays').forEach(day => grid.append(node('span', day)));
    const marked = markDays(date.getFullYear(), date.getMonth());
    monthGrid(date.getFullYear(), date.getMonth()).forEach(key => {
      const b = button(String(new Date(parseDay(key)).getDate()), () => { current = key; update(); onChange(key); shell.close(); }, 'sch-picker-control');
      b.disabled = key < minimum; b.tabIndex = key === cursor ? 0 : -1;
      b.setAttribute('aria-label', fmt(parseDay(key), { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' }));
      if (key === dayKey(Date.now())) b.classList.add('sch-picker-today');
      if (key === current) b.classList.add('sch-picker-selected');
      if (new Date(parseDay(key)).getMonth() !== date.getMonth()) b.classList.add('sch-picker-outside');
      if (marked.includes(key)) { b.classList.add('sch-picker-marked'); b.append(node('span', ' ' + T('schedule.sessionMarker'), 'sr-only')); b.setAttribute('aria-label', b.getAttribute('aria-label') + ', ' + T('schedule.sessionMarker')); }
      b.onkeydown = e => { if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End'].includes(e.key)) { e.preventDefault(); cursor = moveDay(key, e.key); if (cursor < minimum) cursor = minimum; paint(); popup.querySelector('[tabindex="0"]')?.focus(); } };
      grid.append(b);
    }); popup.append(grid);
    if (allowEmpty) popup.append(button(T('schedule.noEndDate'), () => { current = ''; update(); onChange(''); shell.close(); }, 'btn btn-sm'));
  }
  update(); return { set(value, minValue) { minimum = minValue; current = value; cursor = value || minValue; update(); }, close: shell.close };
}
function makeTimePicker(container, getDate, onChange = () => {}) {
  let current = '', parts;
  const shell = pickerShell(container, paint);
  const valid = value => { const [h, m] = value.split(':').map(Number), d = new Date(parseDay(getDate())); d.setHours(h, m, 0, 0); return d.getTime() > Date.now(); };
  function update() { shell.trigger.value = current; shell.trigger.textContent = current ? fmt(new Date(2000, 0, 1, ...current.split(':').map(Number)), { hour: 'numeric', minute: '2-digit' }) : T('schedule.pickerNoTime'); }
  function paint() {
    parts = to12h(current || '19:00'); const popup = shell.popup; popup.replaceChildren();
    const columns = node('div', null, 'sch-time-columns'); popup.append(columns);
    function draw() {
      columns.replaceChildren();
      const candidates = (column, value) => to24h(column === 0 ? value : parts.h, column === 1 ? value : parts.m, column === 2 ? value : parts.pm);
      [[T('schedule.pickerHour'), Array.from({ length: 12 }, (_, i) => i + 1)], [T('schedule.pickerMinute'), MINUTE_STEPS], [T('schedule.pickerPeriod'), [false, true]]].forEach(([label, values], column) => {
        const wrap = node('div', null, 'sch-time-column'), title = node('span', label); wrap.append(title);
        const list = node('div', null, 'sch-time-list'); list.setAttribute('role', 'listbox'); list.setAttribute('aria-label', label);
        values.forEach(value => {
          const text = column === 1 ? String(value).padStart(2, '0') : column === 2 ? T(value ? 'schedule.pickerPM' : 'schedule.pickerAM') : String(value);
          const selected = value === [parts.h, parts.m, parts.pm][column];
          const b = button(text, () => { if (column === 0) parts.h = value; else if (column === 1) parts.m = value; else parts.pm = value; draw(); columns.children[column].querySelector('[aria-selected="true"]')?.focus(); }, 'sch-picker-control');
          b.setAttribute('role', 'option'); b.setAttribute('aria-selected', String(selected)); b.tabIndex = selected ? 0 : -1;
          b.disabled = column === 1 ? !valid(candidates(column, value)) : column === 0 ? !MINUTE_STEPS.some(m => valid(to24h(value, m, parts.pm))) : !Array.from({ length: 12 }, (_, i) => i + 1).some(h => MINUTE_STEPS.some(m => valid(to24h(h, m, value))));
          b.onkeydown = e => { if (e.key === 'ArrowUp' || e.key === 'ArrowDown') { e.preventDefault(); const enabled = [...list.querySelectorAll('button:not(:disabled)')], index = enabled.indexOf(b), next = enabled[(index + (e.key === 'ArrowDown' ? 1 : -1) + enabled.length) % enabled.length]; next?.click(); } else if (e.key === 'Enter') { e.preventDefault(); apply(); } }; list.append(b);
        }); wrap.append(list); columns.append(wrap);
        const selected = list.querySelector('[aria-selected="true"]'); if (selected?.disabled) { selected.tabIndex = -1; const first = list.querySelector('button:not(:disabled)'); if (first) first.tabIndex = 0; }
      });
    }
    function apply() { const value = to24h(parts.h, parts.m, parts.pm); if (valid(value)) { current = value; update(); onChange(value); shell.close(); } }
    draw(); popup.append(button(T('schedule.pickerApply'), apply, 'btn btn-sm btn-primary'));
  }
  update(); return { set(value) { current = value; update(); }, close: shell.close };
}
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
  const current = new Date(now);
  $('schToday').hidden = month.getFullYear() === current.getFullYear() && month.getMonth() === current.getMonth();
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
  if (!occs.length) list.append(node('p', T('schedule.nothing'), 'sch-day-empty'));
  occs.forEach(occ => {
    const event = getSchedule().events.find(e => e.id === occ.event_id), row = node('div', null, 'sch-entry');
    row.append(node('strong', `${time(occ.start)} \u2013 ${time(occ.start + occ.duration_min * 60000)} \u00B7 ${T('schedule.minutes', { n: occ.duration_min })}`));
    row.append(chip(occurrenceStatus(occ, Date.now())));
    if (occ.note) row.append(node('p', occ.note, 'sch-note'));
    if (event.recurrence.kind !== 'none') {
      const kind = T('schedule.' + event.recurrence.kind + 'Lower');
      row.append(node('p', event.recurrence.until ? T('schedule.repeatsUntil', { kind, date: shortDate(parseDay(event.recurrence.until)) }) : T('schedule.repeats', { kind }), 'note'));
    }
    const actions = node('div', null, 'sch-actions');
    actions.append(button(T('schedule.email'), () => openEmail(occ, event)));
    if (occurrenceStatus(occ, Date.now()) === 'done') {
      const id = resultLink(getSchedule().done[occ.key], S.sessions);
      if (id) {
        const result = button(T('schedule.viewResult'), () => closeModal('schDayDrawer'));
        result.dataset.open = id; actions.append(result);
      } else row.append(node('p', T('schedule.resultUnavailable'), 'note'));
    }
    if (canEdit(occ, Date.now())) actions.append(button(T('schedule.edit'), () => openEvent(key, occ, event)));
    const slot = node('div'); slot.dataset.schCheckin = ''; if (canCheckIn(occ, Date.now()) && occurrenceStatus(occ, Date.now()) === 'active') slot.append(button(T('schedule.todayPanel.checkIn'), () => { closeModal('schDayDrawer'); startCheckIn(occ); }, 'btn btn-primary')); actions.append(slot); row.append(actions); list.append(row);
  });
  $('schDayNew').hidden = key < dayKey(Date.now());
  $('schDayNew').onclick = () => openEvent(key);
  if (!$('schDayDrawer').classList.contains('show')) openModal('schDayDrawer');
}
function setSegment(id, value) {
  const group = $(id); group.value = String(value);
  group.querySelectorAll('[role="radio"]').forEach(b => { const selected = b.value === group.value; b.setAttribute('aria-checked', String(selected)); b.tabIndex = selected ? 0 : -1; });
}
function makeSegments(id, values, label, changed) {
  const group = $(id);
  values.forEach(value => {
    const b = button(label(value), () => { setSegment(id, value); changed(); }, 'sch-segment');
    b.value = String(value); b.setAttribute('role', 'radio');
    b.onkeydown = e => { const delta = { ArrowLeft: -1, ArrowUp: -1, ArrowRight: 1, ArrowDown: 1 }[e.key]; if (delta) { e.preventDefault(); const items = [...group.querySelectorAll('[role="radio"]')]; const next = items[(items.indexOf(b) + delta + items.length) % items.length]; next.click(); next.focus(); } };
    group.append(b);
  });
}
function currentInput() {
  return { date: $('schDate').value, time: $('schTime').value, duration_min: Number($('schLength').value), note: $('schNote').value, recurrence: { kind: $('schRepeat').value, days: [...$('schDayChecks').querySelectorAll('[aria-pressed="true"]')].map(x => Number(x.value)), until: $('schUntil').value || null } };
}
function updateRecurrence() {
  const input = currentInput(), repeating = input.recurrence.kind !== 'none';
  $('schDays').hidden = input.recurrence.kind !== 'custom';
  $('schUntilField').hidden = !repeating;
  if (!repeating) { untilPicker.set('', input.date); return; }
  const until = input.recurrence.until;
  if (!until) $('schUntilSummary').textContent = T('schedule.noEndSummary');
  else { const result = sessionsSummary(previewOccurrenceDays(input, input.date, until)); $('schUntilSummary').textContent = result.last ? T('schedule.sessionsSummary', { n: result.n, date: shortDate(parseDay(result.last)) }) : T('schedule.noSessionsSummary'); }
}
function openEvent(key, occ = null, event = null) {
  if (openPopover) openPopover(false);
  editing = occ ? { occ, event } : null;
  const form = $('schForm'); form.reset(); setSegment('schLength', '10'); setSegment('schRepeat', 'none'); $('schDayChecks').querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', 'false'));
  const minimum = dayKey(Date.now()), chosen = key && key >= minimum ? key : minimum;
  datePicker.set(chosen, minimum); timePicker.set(defaultTime(Date.now(), chosen));
  untilPicker.set('', chosen); $('schDays').hidden = true;
  ['Start', 'Length', 'Note', 'Repeat', 'Days', 'Until'].forEach(k => { $('sch' + k + 'Error').textContent = ''; $('sch' + k + 'Error').classList.remove('show'); });
  ['schDate', 'schTime', 'schLength', 'schNote', 'schRepeat', 'schUntil'].forEach(id => $(id).removeAttribute('aria-invalid'));
  $('schEventTitle').textContent = T(editing ? 'schedule.editEvent' : 'schedule.newEvent');
  $('schDelete').hidden = !editing;
  $('schRepeatFields').hidden = !!editing && event.recurrence.kind !== 'none';
  $('schRepeat').querySelectorAll('button').forEach(b => { b.disabled = !!editing; });
  $('schDate').disabled = !!editing && event.recurrence.kind !== 'none';
  $('schEditRepeat').hidden = !editing || event.recurrence.kind === 'none';
  if (editing) {
    datePicker.set(occ.day, minimum); timePicker.set(event.time); setSegment('schLength', event.duration_min);
    $('schNote').value = event.note; setSegment('schRepeat', event.recurrence.kind);
    untilPicker.set(event.recurrence.until || '', occ.day);
    $('schDayChecks').querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(event.recurrence.days.includes(Number(b.value)))));
  }
  updateRecurrence();
  $('schCount').textContent = T('schedule.count', { n: $('schNote').value.length, max: NOTE_MAX_CHARS });
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
  T('schedule.weekdays').forEach((name, i) => { $('schWeekdays').append(node('span', name)); const b = button(name, () => { b.setAttribute('aria-pressed', String(b.getAttribute('aria-pressed') !== 'true')); updateRecurrence(); }, 'sch-day-toggle'); b.value = i + 1; b.setAttribute('aria-pressed', 'false'); $('schDayChecks').append(b); });
  ['upcoming', 'active', 'done', 'missed'].forEach(status => { const c = chip(status); if (status === 'active') c.lastChild.textContent = T('schedule.activeLegend'); $('schLegend').append(c); });
  makeSegments('schLength', DURATIONS_MIN, n => T('schedule.minutes', { n }), updateRecurrence);
  makeSegments('schRepeat', ['none', 'daily', 'weekly', 'custom'], k => T('schedule.' + (k === 'custom' ? 'customOption' : k)), updateRecurrence);
  setSegment('schLength', '10'); setSegment('schRepeat', 'none');
  $('schNote').maxLength = NOTE_MAX_CHARS; $('schNote').oninput = () => { $('schCount').textContent = T('schedule.count', { n: $('schNote').value.length, max: NOTE_MAX_CHARS }); };
  datePicker = makeDatePicker($('schDatePicker'), { min: dayKey(Date.now()), value: dayKey(Date.now()), onChange: value => { const until = $('schUntil').value; untilPicker.set(until && until >= value ? until : '', value); timePicker.set(defaultTime(Date.now(), value)); updateRecurrence(); } });
  timePicker = makeTimePicker($('schTimePicker'), () => $('schDate').value, updateRecurrence);
  untilPicker = makeDatePicker($('schUntilPicker'), { min: dayKey(Date.now()), value: '', allowEmpty: true, onChange: updateRecurrence, markDays: (year, month) => { const input = currentInput(), end = dayKey(new Date(year, month + 1, 0).getTime()), limit = input.recurrence.until && input.recurrence.until < end ? input.recurrence.until : end; return previewOccurrenceDays(input, input.date, limit); } });
  $('schReminder').textContent = T('schedule.reminder', { n: REMINDER_LEAD_MIN });
  $('schDelete').onclick = () => {
    if (!editing) return;
    const { occ, event } = editing;
    openConfirmDialog(T(event.recurrence.kind === 'none' ? 'schedule.deleteSingleQuestion' : 'schedule.deleteFollowingQuestion'), '', T('schedule.delete'), () => {
      if (!canEdit(occ, Date.now())) { $('schStartError').textContent = T('schedule.editTooLate'); $('schStartError').classList.add('show'); return; }
      saveScheduleState(deleteFromOccurrence(getSchedule(), event.id, occ.day)); closeModal('schEventModal'); render(); openDay(selectedDay); toast(T('schedule.deleted'));
    });
  };
  $('schReset').onclick = () => openConfirmDialog(T('schedule.resetQuestion'), T('schedule.resetDetail'), T('schedule.reset'), () => { cachedState = resetSchedule(S.user.id, options()); cachedUser = S.user.id; render(); toast(T('schedule.resetDone')); });
  const picker = $('schMonthPicker'), label = $('schMonth');
  let pickedMonth;
  const closePicker = () => { picker.hidden = true; label.setAttribute('aria-expanded', 'false'); label.focus(); };
  const paintPicker = () => {
    picker.replaceChildren();
    [['pickerMonth', 'previous', 'nextMonth', 0], ['pickerYear', 'previousYear', 'nextYear', 1]].forEach(([title, prev, next, column]) => {
      const section = node('span', null, 'sch-month-column');
      section.append(node('span', T('schedule.' + title)));
      const change = delta => { pickedMonth = new Date(pickedMonth.getFullYear() + (column ? delta : 0), pickedMonth.getMonth() + (column ? 0 : delta), 1); paintPicker(); picker.querySelectorAll('.sch-month-value')[column].focus(); };
      const up = button('\u2303', () => change(1), 'sch-picker-arrow'); up.setAttribute('aria-label', T('schedule.' + next));
      const value = button(column ? String(pickedMonth.getFullYear()) : fmt(pickedMonth, { month: 'long' }), () => {}, 'sch-month-value');
      value.setAttribute('aria-label', T('schedule.' + title));
      value.onkeydown = e => { if (e.key === 'ArrowUp' || e.key === 'ArrowDown') { e.preventDefault(); change(e.key === 'ArrowUp' ? 1 : -1); } else if (e.key === 'Enter') { e.preventDefault(); apply(); } };
      const down = button('\u2304', () => change(-1), 'sch-picker-arrow'); down.setAttribute('aria-label', T('schedule.' + prev));
      section.append(up, value, down); picker.append(section);
    });
    picker.append(button(T('schedule.pickerGo'), apply, 'btn btn-sm btn-primary'));
  };
  const apply = () => { month = pickedMonth; render(); closePicker(); };
  label.onclick = () => { if (!picker.hidden) { closePicker(); return; } pickedMonth = new Date(month.getFullYear(), month.getMonth(), 1); paintPicker(); picker.hidden = false; label.setAttribute('aria-expanded', 'true'); picker.querySelector('.sch-month-value').focus(); };
  picker.onkeydown = e => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closePicker(); } };
  document.addEventListener('pointerdown', e => { if (!picker.hidden && !picker.parentElement.contains(e.target)) closePicker(); });
  $('schPrev').onclick = () => { month = new Date(month.getFullYear(), month.getMonth() - 1, 1); render(); };
  $('schNext').onclick = () => { month = new Date(month.getFullYear(), month.getMonth() + 1, 1); render(); };
  document.querySelector('#screenSchedule #schToday').onclick = () => { month = new Date(); render(); $('schGrid').querySelector(`[data-sch-day="${dayKey(Date.now())}"]`)?.focus(); };
  $('schForm').onsubmit = e => {
    e.preventDefault(); const input = currentInput();
    if (editing) input.recurrence = editing.event.recurrence;
    const result = validateEvent(input, Date.now()), errors = result.errors;
    if (editing && !canEdit(editing.occ, Date.now())) errors.start = 'too_late';
    const fields = [['start', 'Start', errors.start === 'too_late' ? 'editTooLate' : errors.start === 'past' ? 'past' : 'invalid', 'schTime'], ['duration_min', 'Length', 'invalidLength', 'schLength'], ['note', 'Note', 'invalidNote', 'schNote'], ['recurrence', 'Repeat', 'invalidRepeat', 'schRepeat'], ['days', 'Days', 'invalidDays', 'schDayChecks'], ['until', 'Until', 'invalidUntil', 'schUntil']];
    fields.forEach(([key, target, message, id]) => { $('sch' + target + 'Error').textContent = errors[key] ? T('schedule.' + message) : ''; $('sch' + target + 'Error').classList.toggle('show', !!errors[key]); if (id) $(id).setAttribute('aria-invalid', String(!!errors[key])); });
    $('schDate').setAttribute('aria-invalid', String(!!errors.start));
    if (Object.keys(errors).length) { const first = fields.find(([key]) => errors[key]); if (first[0] === 'start' && !$('schDate').disabled) $('schDate').focus(); else if (['schLength', 'schRepeat'].includes(first[3])) $(first[3]).querySelector('[aria-checked="true"]').focus(); else if (first[3] === 'schDayChecks') $('schDayChecks').querySelector('button').focus(); else if (first[3]) $(first[3]).focus(); return; }
    const wasEditing = !!editing;
    saveScheduleState(editing ? editOccurrence(getSchedule(), editing.event.id, editing.occ.day, input, { now: Date.now(), newId: newEventId() }) : addEvent(getSchedule(), { ...input, id: newEventId(), created_at: Date.now(), sample: false })); if (openPopover) openPopover(false); closeModal('schEventModal'); render(); if (S.modal.includes('schDayDrawer')) openDay(selectedDay); toast(T(wasEditing ? 'schedule.updated' : 'schedule.created'));
  };
}
let initialized = false;
RENDER.schedule = () => { if (!initialized) { init(); initialized = true; } render(); };
setInterval(() => { if (S.screen === 'schedule' && !S.modal.length) render(); else if (S.screen === 'home' && S.user) renderTodayPanel(); }, 60000);   // keeps the countdown and status changes fresh

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
      const check = todayButton(T('schedule.todayPanel.checkIn'), 'btn btn-primary', () => startCheckIn(occ));
      check.dataset.schCheckin = occ.key; body.append(check);
    }
  } else {
    body.append(node('p', T('schedule.todayPanel.nothing')));
    body.append(todayButton(T('schedule.todayPanel.plan'), 'btn btn-primary', () => { go('schedule'); openTodayDrawer(); }));
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

configureCheckIn({ getSchedule, saveScheduleState, rerender: () => { if (S.screen === 'home') renderTodayPanel(); if (S.screen === 'schedule') { render(); if (S.modal.includes('schDayDrawer')) openDay(selectedDay); } } });
