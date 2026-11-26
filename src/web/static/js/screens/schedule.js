import { api } from '../api.js';
import { readAiCache, writeAiCache, pruneAiCache } from '../schedule/schedule_script.js';
import { T, TOPICS } from '../i18n.js';
import { go } from '../nav.js';
import { S, RENDER } from '../state.js';
import { openModal, closeModal, toast } from '../ui.js';
import { openConfirmDialog } from '../modals/confirm.js';
import { dayKey, parseDay, addDays, expandOccurrences, occurrenceStatus, validateEvent, normalizeRecurrence, seedSchedule, reminderState, reminderAt, REMINDER_LEAD_MIN, NOTE_MAX_CHARS, DURATIONS_MIN, previewOccurrenceDays, seriesSummary, ALL_DAY_REMINDER_HOUR, SCHEDULE_CATEGORIES, SCHEDULE_COLORS, DEFAULT_COLOR } from '../schedule/schedule_model.js';
import { loadSchedule, saveSchedule, resetSchedule, addEvent, editOccurrence, deleteFromOccurrence, newEventId, remainingCount } from '../schedule/schedule_store.js';
import { monthGrid, formatDurationWords, closesTone, carouselStep, edgeFades, streakLabel, to12h, to24h, MINUTE_STEPS, moveDay, defaultTime, sessionsSummary, resultLink, wrapWheel, clampWheel, wheelWindow, occurrenceStyle, styleVars, sessionTimeLabel, lengthLabel, chipsThatFit, weekDays, weekForMonthView, monthForWeekView, weekRangeLabel, layoutDayBlocks, blockGeometry, initialScrollHour, WEEK_MIN_BLOCK_MIN } from '../schedule/schedule_view.js';
import { startCheckIn, configureCheckIn } from '../schedule/schedule_checkin.js';
import { canCheckIn, canEditSchedule, canEditDetails } from '../schedule/schedule_model.js';
import { startOfWeek, todaySummary, motivationKey, windowClosesAt } from '../schedule/schedule_model.js';

const $ = id => document.getElementById(id);
let cachedUser, cachedState, month = new Date(), selectedDay, editing = null, datePicker, timePicker, untilPicker;
let openPopover = null, gridObserver, gridFrame = 0, view = 'month', viewUser, weekScrollKey = '';
const WEEK_HOUR_PX = 60;
function loadView() { if (viewUser !== S.user?.id) { viewUser = S.user?.id; try { view = storage()?.getItem('psa.schedule.view.v1.' + viewUser) === 'week' ? 'week' : 'month'; } catch (_) { view = 'month'; } weekScrollKey = ''; } }
const storage = () => { try { return window.localStorage; } catch (_) { return null; } };
const options = () => ({ storage: storage(), seed: seedSchedule, now: Date.now() });
function pruneCache() { if (S.user?.id) { const store = storage(), cache = readAiCache(store, S.user.id), pruned = pruneAiCache(cache, Date.now()); if (Object.keys(pruned).length !== Object.keys(cache).length) writeAiCache(store, S.user.id, pruned); } }
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
  const escape = e => { if (e.key === 'Escape' && !popup.hidden) { e.preventDefault(); e.stopPropagation(); close(); } };
  trigger.addEventListener('keydown', escape);
  popup.addEventListener('keydown', escape);
  window.addEventListener('resize', () => { if (!popup.hidden) close(false); });
  document.addEventListener('scroll', e => { if (!popup.hidden && !container.contains(e.target)) close(false); }, true);
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
      const candidates = (column, value) => to24h(column === 0 ? value : parts.h, column === 1 ? value : parts.m, column === 2 ? value : parts.pm);
      [[T('schedule.pickerHour'), Array.from({ length: 12 }, (_, i) => i + 1)], [T('schedule.pickerMinute'), MINUTE_STEPS], [T('schedule.pickerPeriod'), [false, true]]].forEach(([label, values], column) => {
        const wrap = columns.children[column] || node('div', null, 'sch-time-column'), title = node('span', label);
        const list = wrap.querySelector('.sch-time-list') || node('div', null, 'sch-time-list');
        if (!wrap.isConnected) { wrap.append(title); list.setAttribute('role', 'listbox'); list.setAttribute('aria-label', label); wrap.append(list); columns.append(wrap); }
        values.forEach((value, index) => {
          const text = column === 1 ? String(value).padStart(2, '0') : column === 2 ? T(value ? 'schedule.pickerPM' : 'schedule.pickerAM') : String(value);
          const selected = value === [parts.h, parts.m, parts.pm][column];
          const b = list.children[index] || button(text, () => { if (column === 0) parts.h = value; else if (column === 1) parts.m = value; else parts.pm = value; draw(); b.focus({ preventScroll: true }); const top = b.offsetTop - list.offsetTop; if (top < list.scrollTop) list.scrollTop = top; else if (top + b.offsetHeight > list.scrollTop + list.clientHeight) list.scrollTop = top + b.offsetHeight - list.clientHeight; }, 'sch-picker-control');
          b.setAttribute('role', 'option'); b.setAttribute('aria-selected', String(selected)); b.tabIndex = selected ? 0 : -1;
          b.disabled = column === 1 ? !valid(candidates(column, value)) : column === 0 ? !MINUTE_STEPS.some(m => valid(to24h(value, m, parts.pm))) : !Array.from({ length: 12 }, (_, i) => i + 1).some(h => MINUTE_STEPS.some(m => valid(to24h(h, m, value))));
          b.onkeydown = e => { if (e.key === 'ArrowUp' || e.key === 'ArrowDown') { e.preventDefault(); const enabled = [...list.querySelectorAll('button:not(:disabled)')], index = enabled.indexOf(b), next = enabled[(index + (e.key === 'ArrowDown' ? 1 : -1) + enabled.length) % enabled.length]; next?.click(); } else if (e.key === 'Enter') { e.preventDefault(); apply(); } }; if (!b.isConnected) list.append(b);
        });
        const selected = list.querySelector('[aria-selected="true"]'); if (selected?.disabled) { selected.tabIndex = -1; const first = list.querySelector('button:not(:disabled)'); if (first) first.tabIndex = 0; }
      });
    }
    function apply() { const value = to24h(parts.h, parts.m, parts.pm); if (valid(value)) { current = value; update(); onChange(value); shell.close(); } }
    draw(); popup.append(button(T('schedule.pickerApply'), apply, 'btn btn-sm btn-primary'));
    requestAnimationFrame(() => { if (!popup.hidden && columns.isConnected) columns.querySelectorAll('.sch-time-list').forEach(list => { const selected = list.querySelector('[aria-selected="true"]'); if (selected) list.scrollTop = selected.offsetTop - list.offsetTop; }); });
  }
  update(); return { set(value) { current = value; update(); }, close: shell.close };
}
const labelWords = () => T('schedule');
const scriptLabel = occ => occ.script?.kind === 'saved' ? T('schedule.scriptTitle', { title: occ.script.title }) : T(occ.script?.kind === 'ai' ? 'schedule.scriptAiLine' : 'schedule.scriptFree');
const categoryLabel = occ => occ.category && occ.category !== 'any' ? TOPICS[occ.category] : '';
const applyEventStyle = (el, status, color) => Object.entries(styleVars(occurrenceStyle(status, color))).forEach(([key, value]) => el.style.setProperty(key, value));
function chip(status, label, compact = false, colorKey = DEFAULT_COLOR) {
  const el = node('span', null, 'sch-chip sch-' + status + (compact ? ' sch-compact' : ''));
  applyEventStyle(el, status, colorKey);
  const icon = node('span', { active: '\u25CF', done: '\u2713', upcoming: '\u25CB', missed: '\u25CC' }[status], 'sch-icon'); icon.setAttribute('aria-hidden', 'true'); el.append(icon);
  if (label) el.append(node('span', label, 'sch-chip-time'));
  el.append(node('span', T('schedule.' + status), 'sch-chip-word'));
  return el;
}
function monthChip(status, label, color) {
  const el = chip(status, label, true, color);
  el.querySelector('.sch-chip-word').classList.add('sr-only');
  el.title = T('schedule.' + status) + ' \u2013 ' + label;
  return el;
}
function renderWeek(now) {
  const root = $('schWeek'), keys = weekDays(dayKey(month)), today = dayKey(now), oldScroll = root.querySelector('.sch-week-scroll')?.scrollTop, focusKey = root.contains(document.activeElement) ? document.activeElement.dataset.occKey : null;
  const focusDay = root.contains(document.activeElement) ? document.activeElement.dataset.schDay : null;
  const occs = occurrencesBetween(parseDay(keys[0]), addDays(parseDay(keys[6]), 1));
  root.replaceChildren();
  const wide = node('div', null, 'sch-week-wide'), headers = node('div', null, 'sch-week-row sch-week-headers'), all = node('div', null, 'sch-week-row sch-week-all');
  headers.append(node('span')); all.append(node('span', T('schedule.allDay'), 'sch-week-axis'));
  const scroll = node('div', null, 'sch-week-scroll'), body = node('div', null, 'sch-week-row sch-week-body');
  body.setAttribute('role', 'list'); body.setAttribute('aria-label', T('schedule.weekTimeGrid'));
  const axis = node('div', null, 'sch-week-hours'); axis.setAttribute('role', 'presentation'); axis.setAttribute('aria-hidden', 'true');
  for (let h = 0; h < 24; h++) { const label = node('span', fmt(new Date(2000, 0, 1, h), { hour: 'numeric' })); label.style.top = (h * WEEK_HOUR_PX) + 'px'; axis.append(label); }
  body.append(axis);
  keys.forEach(key => {
    const date = fullDate(parseDay(key)), header = node('div', null, 'sch-week-header sch-cell');
    const day = button(fmt(parseDay(key), { weekday: 'short', day: 'numeric' }), () => openDay(key), 'sch-week-day'); day.dataset.schDay = key; day.setAttribute('aria-label', date);
    if (key === today) day.classList.add('sch-week-today'); header.append(day);
    if (key >= today) { const add = button('+', () => openEvent(key), 'sch-add'); add.dataset.schDay = key; add.setAttribute('aria-label', T('schedule.addPracticeOn', { date })); header.append(add); }
    headers.append(header);
    const allCell = node('div', null, 'sch-week-all-cell');
    occs.filter(o => o.day === key && o.all_day).forEach(o => { const status = occurrenceStatus(o, now), b = button('', () => openDay(key, o.key), 'sch-week-all-button'); b.dataset.occKey = o.key; b.setAttribute('aria-label', [date, T('schedule.allDay'), lengthLabel(o.duration_min, labelWords()), T('schedule.' + status)].join(', ')); b.append(monthChip(status, T('schedule.allDay'), o.color)); allCell.append(b); }); all.append(allCell);
    const column = node('div', null, 'sch-week-column'); column.setAttribute('role', 'listitem'); column.setAttribute('aria-label', date);
    const items = occs.filter(o => o.day === key && !o.all_day).map(o => { const d = new Date(o.start), startMin = d.getHours() * 60 + d.getMinutes(); return { key: o.key, startMin, endMin: Math.min(1440, startMin + Math.max(WEEK_MIN_BLOCK_MIN, o.duration_min || 0)), occ: o }; });
    layoutDayBlocks(items).forEach(item => { const o = item.occ, status = occurrenceStatus(o, now), length = lengthLabel(o.duration_min, labelWords()), geom = blockGeometry(item.startMin, o.duration_min, WEEK_HOUR_PX);
      const b = button('', () => openDay(key, o.key), 'sch-week-block'); b.dataset.occKey = o.key; b.setAttribute('aria-label', [date, time(o.start), length, T('schedule.' + status)].join(', ')); applyEventStyle(b, status, o.color);
      b.style.top = geom.top + 'px'; b.style.height = geom.height + 'px'; b.style.left = (item.col * 100 / item.cols) + '%'; b.style.width = (100 / item.cols) + '%';
      const icon = node('span', { active: '\u25CF', done: '\u2713', upcoming: '\u25CB', missed: '\u25CC' }[status]); icon.setAttribute('aria-hidden', 'true'); b.title = T('schedule.' + status); b.append(icon, node('span', time(o.start) + (o.duration_min == null ? '' : ' \u00B7 ' + length), 'sch-week-block-label'), node('span', T('schedule.' + status), 'sr-only')); column.append(b); });
    if (key === today) { const d = new Date(now), line = node('div', null, 'sch-now-line'); line.setAttribute('aria-hidden', 'true'); line.style.top = ((d.getHours() * 60 + d.getMinutes()) * WEEK_HOUR_PX / 60) + 'px'; column.append(line); }
    body.append(column);
  });
  scroll.append(body); wide.append(headers, all, scroll); root.append(wide);
  wide.style.setProperty('--sch-scrollbar-width', (scroll.offsetWidth - scroll.clientWidth) + 'px');
  const newKey = keys[0]; scroll.scrollTop = newKey === weekScrollKey && oldScroll != null ? oldScroll : Math.max(0, initialScrollHour(keys, today, new Date(now).getHours()) * WEEK_HOUR_PX - 8); weekScrollKey = newKey;
  if (focusKey) [...root.querySelectorAll('[data-occ-key]')].find(el => el.dataset.occKey === focusKey)?.focus();
  else if (focusDay) [...root.querySelectorAll('[data-sch-day]')].find(el => el.dataset.schDay === focusDay)?.focus();
}
function render() {
  loadView();
  const panel = $('schGrid').closest('.sch-panel'); panel.style.setProperty('--sch-panel-top', (panel.getBoundingClientRect().top + window.scrollY) + 'px');
  $('schWeek').hidden = view !== 'week'; $('schGrid').hidden = view === 'week'; $('schWeekdays').hidden = view === 'week';
  $('schViewToggle').querySelectorAll('button').forEach(b => { const selected = b.value === view; b.setAttribute('aria-checked', String(selected)); b.tabIndex = selected ? 0 : -1; });
  $('schPrev').setAttribute('aria-label', T(view === 'week' ? 'schedule.previousWeek' : 'schedule.previous')); $('schNext').setAttribute('aria-label', T(view === 'week' ? 'schedule.nextWeek' : 'schedule.nextMonth'));
  if (view === 'week') { $('schMonth').textContent = weekRangeLabel(dayKey(month), fmt); $('schMonthLive').textContent = $('schMonth').textContent; $('schEmpty').hidden = true; renderWeek(Date.now()); return; }
  const state = getSchedule(), keys = monthGrid(month.getFullYear(), month.getMonth()), now = Date.now();
  $('schMonth').textContent = fmt(month, { month: 'long', year: 'numeric' });
  $('schMonthLive').textContent = $('schMonth').textContent;
  const grid = $('schGrid'), focusedDay = document.activeElement?.dataset.schDay, focusedAdd = document.activeElement?.classList.contains('sch-add');
  grid.replaceChildren();
  const cells = [];
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
    const cell = node('div', null, 'sch-cell'); cell.append(b);
    if (key >= dayKey(now)) {
      const add = button('+', () => { selectedDay = key; openEvent(key); }, 'sch-add');
      add.dataset.schDay = key; add.setAttribute('aria-label', T('schedule.addPracticeOn', { date })); cell.append(add);
    }
    grid.append(cell); cells.push({ b, list });
  });
  $('schEmpty').hidden = state.events.length !== 0;
  const sample = monthChip('upcoming', '12:00 PM'), moreSample = node('span', T('schedule.more', { n: 1 }), 'sch-more');
  cells[0].b.append(sample, moreSample);
  const day = cells[0].b, styles = getComputedStyle(day);
  const headerHeight = day.querySelector('.sch-day-number').getBoundingClientRect().height;
  const chipHeight = sample.getBoundingClientRect().height, moreHeight = moreSample.getBoundingClientRect().height, gap = parseFloat(styles.rowGap) || 0;
  sample.remove(); moreSample.remove();
  const compact = matchMedia('(max-width: 720px)').matches;
  cells.forEach(({ b, list }) => {
    const innerHeight = b.clientHeight - parseFloat(styles.paddingTop) - parseFloat(styles.paddingBottom);
    const fit = compact ? { shown: Math.min(2, list.length), more: Math.max(0, list.length - 2) } : chipsThatFit(innerHeight, headerHeight, chipHeight, moreHeight, gap, list.length);
    list.slice(0, fit.shown).forEach(o => b.append(monthChip(occurrenceStatus(o, now), sessionTimeLabel(o, time, labelWords()), o.color)));
    if (fit.more) b.append(node('span', T('schedule.more', { n: fit.more }), 'sch-more'));
  });
  if (focusedDay) grid.querySelector(`[data-sch-day="${focusedDay}"].${focusedAdd ? 'sch-add' : 'sch-day'}`)?.focus();
}
function openDay(key, highlightKey = null) {
  selectedDay = key; $('schDayTitle').textContent = fullDate(parseDay(key));
  const list = $('schDayList'); list.replaceChildren();
  const occs = occurrencesBetween(parseDay(key), addDays(parseDay(key), 1));
  if (!occs.length) list.append(node('p', T('schedule.nothing'), 'sch-day-empty'));
  occs.forEach(occ => {
    const event = getSchedule().events.find(e => e.id === occ.event_id), row = node('div', null, 'sch-entry');
    if (occ.key === highlightKey) { row.classList.add('sch-entry-highlight'); }
    const status = occurrenceStatus(occ, Date.now()), start = sessionTimeLabel(occ, time, labelWords()), length = lengthLabel(occ.duration_min, labelWords());
    applyEventStyle(row, status, occ.color);
    const end = !occ.all_day && occ.duration_min != null ? ` \u2013 ${time(occ.start + occ.duration_min * 60000)}` : '';
    row.append(node('strong', `${start}${end} \u00B7 ${length}`));
    row.append(chip(status, null, false, occ.color));
    if (categoryLabel(occ)) row.append(node('p', categoryLabel(occ)));
    row.append(node('p', scriptLabel(occ)));
    if (occ.note) row.append(node('p', occ.note, 'sch-note'));
    if (event.recurrence.kind !== 'none') {
      const kind = T('schedule.' + event.recurrence.kind + 'Lower');
      row.append(node('p', (event.recurrence.end.kind === 'until' ? event.recurrence.end.until : null) ? T('schedule.repeatsUntil', { kind, date: shortDate(parseDay((event.recurrence.end.kind === 'until' ? event.recurrence.end.until : null))) }) : T('schedule.repeats', { kind }), 'note'));
    }
    const actions = node('div', null, 'sch-actions');
    actions.append(button(T('schedule.email'), () => openEmail(occ, event)));
    if (occurrenceStatus(occ, Date.now()) === 'done') {
      const id = resultLink(getSchedule().done[occ.key], S.sessions);
      if (id) {
        const result = button(T('schedule.viewResult'), () => closeModal('schDayDrawer'));
        result.dataset.open = id; result.dataset.todayRole = 'result'; actions.append(result);
      } else row.append(node('p', T('schedule.resultUnavailable'), 'note'));
    }
    if (canEditDetails(occ, Date.now())) actions.append(button(T('schedule.edit'), () => openEvent(key, occ, event)));
    const slot = node('div'); slot.dataset.schCheckin = ''; if (canCheckIn(occ, Date.now()) && occurrenceStatus(occ, Date.now()) === 'active') slot.append(button(T('schedule.todayPanel.checkIn'), () => { closeModal('schDayDrawer'); startCheckIn(occ); }, 'btn btn-primary')); actions.append(slot); row.append(actions); list.append(row);
  });
  $('schDayNew').hidden = key < dayKey(Date.now());
  $('schDayNew').onclick = () => openEvent(key);
  if (!$('schDayDrawer').classList.contains('show')) openModal('schDayDrawer');
  if (highlightKey) { const highlighted = list.querySelector('.sch-entry-highlight'); highlighted?.scrollIntoView({ block: 'nearest' }); if (highlighted) setTimeout(() => highlighted.classList.remove('sch-entry-highlight'), 2000); }
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
let savedItems = [], savedSelection = null, savedRequest = 0;
function currentScript() {
  const kind = $('schScript').value;
  return kind === 'saved' ? { kind, script_id: savedSelection?.id || '', title: savedSelection?.title || '' } : { kind };
}
function updateScriptErrors() {
  const input = currentInput(), errors = validateEvent(input, Date.now()).errors;
  [['duration_min', 'Length', 'aiNeedsLength'], ['category', 'Category', 'aiNeedsCategory']].forEach(([key, field, message]) => {
    const show = errors[key] === (key === 'category' ? 'ai_needs_category' : 'ai_needs_length');
    $('sch' + field + 'Error').textContent = show ? T('schedule.' + message) : '';
    $('sch' + field + 'Error').classList.toggle('show', show);
    $( 'sch' + field).setAttribute('aria-invalid', String(show));
  });
}
function updateScript() {
  const kind = $('schScript').value;
  $('schSavedField').hidden = kind !== 'saved'; $('schScriptHelp').hidden = kind !== 'ai';
  $('schScriptError').textContent = ''; $('schScriptError').classList.remove('show');
  updateScriptErrors();
}
async function fetchSavedScripts() {
  const request = ++savedRequest, userId = S.user?.id;
  $('schSavedStatus').textContent = T('schedule.savedLoading'); $('schSavedRetry').hidden = true; $('schSavedSelect').disabled = true;
  try {
    const response = await api('/api/scripts'); if (!response.ok) throw new Error('scripts');
    const data = await response.json(); if (request !== savedRequest || userId !== S.user?.id) return;
    if (!Array.isArray(data.items)) throw new Error('scripts');
    savedItems = data.items; const select = $('schSavedSelect'); select.replaceChildren(new Option(T('schedule.savedPlaceholder'), ''));
    savedItems.forEach(item => select.add(new Option(item.title, item.id)));
    if (savedSelection && !savedItems.some(item => item.id === savedSelection.id)) select.add(new Option(T('schedule.savedUnavailable', { title: savedSelection.title }), savedSelection.id));
    select.value = savedSelection?.id || ''; select.disabled = false;
    $('schSavedStatus').textContent = savedItems.length ? '' : T('schedule.savedEmpty');
  } catch (_) { if (request !== savedRequest || userId !== S.user?.id) return; $('schSavedStatus').textContent = T('schedule.savedError'); $('schSavedRetry').hidden = false; }
}
function currentInput() {
  const allDay = $('schAllDay').getAttribute('aria-checked') === 'true', endKind = $('schEnds').value;
  const end = endKind === 'until' ? { kind: 'until', until: $('schUntil').value } : endKind === 'count' ? { kind: 'count', count: Number($('schCount').value) } : { kind: 'never' };
  return { date: $('schDate').value, time: allDay ? null : $('schTime').value, all_day: allDay, duration_min: $('schLength').value === 'any' ? null : Number($('schLength').value), note: $('schNote').value,
    category: $('schCategory').value, color: $('schColor').value, script: currentScript(),
    recurrence: normalizeRecurrence({ kind: $('schRepeat').value, days: [...$('schDayChecks').querySelectorAll('[aria-pressed="true"]')].map(x => Number(x.value)), end }) };
}
function updateRecurrence() {
  const input = currentInput(), repeating = input.recurrence.kind !== 'none', end = input.recurrence.end;
  $('schTimeLabel').hidden = input.all_day; $('schTimePicker').hidden = input.all_day;
  $('schReminder').textContent = input.all_day ? T('schedule.reminderAllDay', { hour: ALL_DAY_REMINDER_HOUR }) : T('schedule.reminder', { n: REMINDER_LEAD_MIN });
  $('schDays').hidden = input.recurrence.kind !== 'custom';
  $('schEndsField').hidden = !repeating; $('schUntilField').hidden = !repeating || end.kind !== 'until'; $('schCountField').hidden = !repeating || end.kind !== 'count';
  if (!repeating) return;
  const result = end.kind === 'count' && (!Number.isInteger(end.count) || end.count < 1 || end.count > 99) ? null : end.kind === 'until' && !end.until ? null : seriesSummary(input);
  $('schUntilSummary').textContent = end.kind === 'never' ? T('schedule.noEndSummary') : result?.last ? T('schedule.sessionsSummary', { n: result.n, date: shortDate(parseDay(result.last)) }) : T('schedule.noSessionsSummary');
}
let lockTimer = null;
function applyScheduleLock() {
  const locked = !!editing && !canEditSchedule(editing.occ, Date.now());
  $('schDate').disabled = locked;
  $('schAllDay').disabled = locked; $('schUntil').disabled = locked; $('schCount').disabled = locked;
  ['schRepeat', 'schDayChecks', 'schEnds'].forEach(id => $(id).querySelectorAll('button').forEach(b => { b.disabled = locked; }));
  $('schTime').disabled = locked;
  $('schLockNote').hidden = !locked;
  $('schLockNote').textContent = T('schedule.scheduleLocked');
}
function openEvent(key, occ = null, event = null) {
  if (openPopover) openPopover(false);
  editing = occ ? { occ, event } : null; savedRequest++; savedItems = []; savedSelection = event?.script?.kind === 'saved' ? { id: event.script.script_id, title: event.script.title } : null;
  const form = $('schForm'); form.reset(); setSegment('schLength', 'any'); setSegment('schCategory', 'any'); setSegment('schScript', event?.script?.kind || 'free'); setSegment('schColor', DEFAULT_COLOR); setSegment('schRepeat', 'none'); setSegment('schEnds', 'never'); $('schAllDay').setAttribute('aria-checked', 'false'); $('schCount').value = '1'; $('schDayChecks').querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', 'false'));
  const minimum = dayKey(Date.now()), chosen = key && key >= minimum ? key : minimum;
  datePicker.set(chosen, minimum); timePicker.set(defaultTime(Date.now(), chosen));
  untilPicker.set('', chosen); $('schDays').hidden = true;
  ['Start', 'Length', 'Category', 'Script', 'Color', 'Note', 'Repeat', 'Days', 'Until', 'Count'].forEach(k => { $('sch' + k + 'Error').textContent = ''; $('sch' + k + 'Error').classList.remove('show'); });
  ['schDate', 'schTime', 'schLength', 'schNote', 'schRepeat', 'schUntil'].forEach(id => $(id).removeAttribute('aria-invalid'));
  $('schEventTitle').textContent = T(editing ? 'schedule.editEvent' : 'schedule.newEvent');
  $('schDelete').hidden = !editing;
  $('schRepeatFields').hidden = !!editing && event.recurrence.kind === 'none';
  applyScheduleLock();
  $('schEditRepeat').hidden = !editing || event.recurrence.kind === 'none';
  if (editing) {
    datePicker.set(occ.day, event.recurrence.kind !== 'none' ? occ.day : minimum); timePicker.set(event.time || defaultTime(Date.now(), occ.day)); setSegment('schLength', event.duration_min ?? 'any');
    $('schAllDay').setAttribute('aria-checked', String(event.all_day)); setSegment('schCategory', event.category); setSegment('schColor', event.color); setSegment('schEnds', event.recurrence.end.kind); $('schCount').value = remainingCount(event, occ.day) ?? 1;
    $('schNote').value = event.note; setSegment('schRepeat', event.recurrence.kind);
    untilPicker.set((event.recurrence.end.kind === 'until' ? event.recurrence.end.until : null) || '', occ.day);
    $('schDayChecks').querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(event.recurrence.days.includes(Number(b.value)))));
  }
  if (editing) editing.initialRecurrence = JSON.stringify(event.recurrence.kind === 'none' ? event.recurrence : currentInput().recurrence);
  updateRecurrence(); updateScript(); if ($('schScript').value === 'saved') fetchSavedScripts();
  $("schNoteCount").textContent = T('schedule.count', { n: $('schNote').value.length, max: NOTE_MAX_CHARS });
  clearInterval(lockTimer); lockTimer = setInterval(() => { if (!$('schEventModal').classList.contains('show')) { clearInterval(lockTimer); lockTimer = null; } else applyScheduleLock(); }, 15000);
  openModal('schEventModal', { focus: !$('schDate').disabled ? '#schDate' : !$('schTime').disabled ? '#schTime' : '#schNote' });
}
function openEmail(occ, event) {
  const body = $('schEmailBody'); body.replaceChildren();
  const length = occ.duration_min == null ? T('schedule.anyLengthLower') : lengthLabel(occ.duration_min, labelWords());
  const subject = occ.all_day ? T('schedule.subjectAllDay', { length }) : T('schedule.subjectWithLength', { lead: REMINDER_LEAD_MIN, length, time: time(occ.start) });
  const when = occ.all_day ? T('schedule.whenAllDay', { date: fmt(occ.start, { weekday: 'short', month: 'short', day: 'numeric' }) }) : T('schedule.when', { when: dateTime(occ.start) });
  [T('schedule.to', { value: S.user.email }), T('schedule.from'), subject, S.user.name?.trim() ? T('schedule.greeting', { name: S.user.name }) : T('schedule.greetingNameless'), when, T('schedule.emailLengthLabel', { length }), ...(occ.note ? [T('schedule.emailNote', { note: occ.note })] : [])].forEach(text => body.append(node('p', text)));
  const disabled = button(T('schedule.openPractice'), () => {}, 'btn btn-primary'); disabled.disabled = true; disabled.setAttribute('aria-disabled', 'true'); body.append(disabled);
  const state = reminderState(occ, event, Date.now());
  $('schEmailFooter').textContent = T('schedule.' + ({ skipped: 'skipped', scheduled: 'wouldSend', sent: 'reminderSent', sent_then_edited: 'reminderSentEdited' }[state]), { when: dateTime(reminderAt(occ)) });
  openModal('schEmailModal');
}
function init() {
  makeSegments('schViewToggle', ['month', 'week'], value => T('schedule.' + value + 'View'), () => {
    const value = $('schViewToggle').value;
    if (value === view) return;
    if (value === 'week') month = new Date(parseDay(weekForMonthView(dayKey(month).slice(0, 7), Date.now())));
    else { const [y, m] = monthForWeekView(dayKey(month), Date.now()).split('-').map(Number); month = new Date(y, m - 1, 1); }
    view = value; weekScrollKey = ''; try { storage()?.setItem('psa.schedule.view.v1.' + S.user?.id, value); } catch (_) {} render();
  });
  T('schedule.weekdays').forEach((name, i) => { $('schWeekdays').append(node('span', name)); const b = button(name, () => { b.setAttribute('aria-pressed', String(b.getAttribute('aria-pressed') !== 'true')); updateRecurrence(); }, 'sch-day-toggle'); b.value = i + 1; b.setAttribute('aria-pressed', 'false'); $('schDayChecks').append(b); });
  ['upcoming', 'active', 'done', 'missed'].forEach(status => { const c = chip(status, null, false, DEFAULT_COLOR); if (status === 'active') c.lastChild.textContent = T('schedule.activeLegend'); $('schLegend').append(c); });
  makeSegments('schLength', ['any', ...DURATIONS_MIN], n => n === 'any' ? T('schedule.any') : T('schedule.minutes', { n }), () => { updateRecurrence(); updateScriptErrors(); });
  makeSegments('schCategory', ['any', ...SCHEDULE_CATEGORIES], k => k === 'any' ? T('schedule.any') : TOPICS[k], () => { updateRecurrence(); updateScriptErrors(); });
  makeSegments('schScript', ['free', 'saved', 'ai'], k => T('schedule.' + ({ free: 'scriptFree', saved: 'scriptSaved', ai: 'scriptAi' }[k])), () => { updateScript(); if ($('schScript').value === 'saved') fetchSavedScripts(); });
  $('schSavedRetry').onclick = fetchSavedScripts;
  $('schSavedSelect').onchange = () => { savedSelection = savedItems.find(item => item.id === $('schSavedSelect').value) || (savedSelection?.id === $('schSavedSelect').value ? savedSelection : null); $('schScriptError').textContent = ''; $('schScriptError').classList.remove('show'); };
  makeSegments('schColor', SCHEDULE_COLORS.map(c => c.key), k => T('schedule.colors.' + k), updateRecurrence);
  $('schColor').querySelectorAll('button').forEach(b => { const color = SCHEDULE_COLORS.find(c => c.key === b.value); b.setAttribute('aria-label', T('schedule.colors.' + b.value)); b.textContent = ''; const swatch = node('span', null, 'sch-swatch'); swatch.style.backgroundColor = color.hex; swatch.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12l5 5L19 7"/></svg>'; swatch.style.color = occurrenceStyle('upcoming', b.value).text; b.append(swatch); });
  makeSegments('schEnds', ['never', 'until', 'count'], k => T('schedule.' + ({ never: 'endNever', until: 'endUntil', count: 'endCount' }[k])), updateRecurrence);
  $('schAllDay').onclick = () => { $('schAllDay').setAttribute('aria-checked', String($('schAllDay').getAttribute('aria-checked') !== 'true')); updateRecurrence(); };
  $('schCount').oninput = updateRecurrence;
  makeSegments('schRepeat', ['none', 'daily', 'weekly', 'custom'], k => T('schedule.' + (k === 'custom' ? 'customOption' : k)), updateRecurrence);
  setSegment('schLength', 'any'); setSegment('schCategory', 'any'); setSegment('schColor', DEFAULT_COLOR); setSegment('schRepeat', 'none'); setSegment('schEnds', 'never');
  $('schNote').maxLength = NOTE_MAX_CHARS; $('schNote').oninput = () => { $('schNoteCount').textContent = T('schedule.count', { n: $('schNote').value.length, max: NOTE_MAX_CHARS }); };
  datePicker = makeDatePicker($('schDatePicker'), { min: dayKey(Date.now()), value: dayKey(Date.now()), onChange: value => { const until = $('schUntil').value; untilPicker.set(until && until >= value ? until : '', value); const current = $('schTime').value, now = Date.now(); if (!/^\d{2}:\d{2}$/.test(current) || Number(current.slice(0, 2)) > 23 || Number(current.slice(3)) > 59 || new Date(value + 'T' + current).getTime() <= now) timePicker.set(defaultTime(now, value)); updateRecurrence(); } });
  timePicker = makeTimePicker($('schTimePicker'), () => $('schDate').value, updateRecurrence);
  untilPicker = makeDatePicker($('schUntilPicker'), { min: dayKey(Date.now()), value: '', allowEmpty: true, onChange: updateRecurrence, markDays: (year, month) => { const input = currentInput(), end = dayKey(new Date(year, month + 1, 0).getTime()), limit = (input.recurrence.end.kind === 'until' ? input.recurrence.end.until : null) && (input.recurrence.end.kind === 'until' ? input.recurrence.end.until : null) < end ? (input.recurrence.end.kind === 'until' ? input.recurrence.end.until : null) : end; return previewOccurrenceDays(input, input.date, limit); } });
  $('schReminder').textContent = T('schedule.reminder', { n: REMINDER_LEAD_MIN });
  $('schDelete').onclick = () => {
    if (!editing) return;
    const { occ, event } = editing;
    openConfirmDialog(T(event.recurrence.kind === 'none' ? 'schedule.deleteSingleQuestion' : 'schedule.deleteFollowingQuestion'), '', T('schedule.delete'), () => {
      if (!canEditDetails(occ, Date.now())) { $('schStartError').textContent = T('schedule.editTooLate'); $('schStartError').classList.add('show'); return; }
      saveScheduleState(deleteFromOccurrence(getSchedule(), event.id, occ.day)); closeModal('schEventModal'); render(); openDay(selectedDay); toast(T('schedule.deleted'));
    });
  };
  $('schReset').onclick = () => openConfirmDialog(T('schedule.resetQuestion'), T('schedule.resetDetail'), T('schedule.reset'), () => { writeAiCache(storage(), S.user.id, {}); cachedState = resetSchedule(S.user.id, options()); cachedUser = S.user.id; render(); toast(T('schedule.resetDone')); });
  const picker = $('schMonthPicker'), label = $('schMonth');
  let pickedMonth, pickedYear, minYear, maxYear;
  const closePicker = () => { picker.hidden = true; label.setAttribute('aria-expanded', 'false'); label.focus(); };
  const apply = () => { month = new Date(pickedYear, pickedMonth, 1); render(); closePicker(); };
  const paintPicker = () => {
    picker.replaceChildren();
    const columns = node('span', null, 'sch-wheel-columns');
    const back = button('', () => { const now = Date.now(); month = new Date(now); render(); closePicker(); $('schGrid').querySelector(`[data-sch-day="${dayKey(now)}"]`)?.focus(); }, 'btn btn-sm sch-picker-back');
    const backIcon = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); backIcon.setAttribute('viewBox', '0 0 24 24'); backIcon.setAttribute('aria-hidden', 'true');
    const backPath = document.createElementNS('http://www.w3.org/2000/svg', 'path'); backPath.setAttribute('d', 'M19 12H5M12 19l-7-7 7-7'); backIcon.append(backPath); back.append(backIcon, node('span', T('schedule.backToday')));
    const updateBack = () => { const today = new Date(); back.disabled = pickedYear === today.getFullYear() && pickedMonth === today.getMonth() && month.getFullYear() === today.getFullYear() && month.getMonth() === today.getMonth() && (view !== 'week' || weekDays(dayKey(month)).includes(dayKey(today))); };
    updateBack();
    [['pickerMonth', 'previous', 'nextMonth', false], ['pickerYear', 'previousYear', 'nextYear', true]].forEach(([title, prev, next, year]) => {
      const section = node('span', null, 'sch-month-column');
      section.append(node('span', T('schedule.' + title), 'sch-wheel-title'));
      const up = button(null, () => change(-1), 'sch-picker-arrow');
      const down = button(null, () => change(1), 'sch-picker-arrow');
      const icon = direction => {
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('aria-hidden', 'true');
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', direction < 0 ? 'M6 15l6-6 6 6' : 'M6 9l6 6 6-6'); svg.append(path); return svg;
      };
      up.append(icon(-1)); down.append(icon(1));
      up.setAttribute('aria-label', T('schedule.' + prev)); down.setAttribute('aria-label', T('schedule.' + next));
      const wheel = node('span', null, 'sch-wheel'); wheel.tabIndex = 0; wheel.setAttribute('role', 'spinbutton');
      wheel.setAttribute('aria-label', T('schedule.' + title));
      wheel.setAttribute('aria-valuemin', String(year ? minYear : 1)); wheel.setAttribute('aria-valuemax', String(year ? maxYear : 12));
      const list = node('span', null, 'sch-wheel-list'); wheel.append(list);
      const paint = () => {
        const value = year ? pickedYear : pickedMonth;
        const values = wheelWindow(value, year ? minYear : 0, year ? maxYear : 11, !year);
        list.replaceChildren(...values.map((item, i) => node('span', item === null ? '' : year ? String(item) : fmt(new Date(2020, item, 1), { month: 'long' }), i === 1 ? 'sch-wheel-current' : 'sch-wheel-adjacent')));
        wheel.setAttribute('aria-valuenow', String(year ? value : value + 1));
        wheel.setAttribute('aria-valuetext', list.children[1].textContent);
        up.disabled = year && value === minYear; down.disabled = year && value === maxYear;
      };
      const change = delta => {
        const before = year ? pickedYear : pickedMonth;
        if (year) pickedYear = clampWheel(pickedYear + delta, minYear, maxYear);
        else pickedMonth = wrapWheel(pickedMonth + delta, 0, 11);
        if (before === (year ? pickedYear : pickedMonth)) return;
        list.getAnimations().forEach(animation => animation.cancel()); paint(); updateBack();
        if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
          list.animate([{ transform: `translateY(${delta * 36}px)`, opacity: 0.55 }, { transform: 'translateY(0)', opacity: 1 }], { duration: 200, easing: 'ease-out' });
        }
      };
      wheel.onkeydown = e => { if (e.key === 'ArrowUp' || e.key === 'ArrowDown') { e.preventDefault(); change(e.key === 'ArrowUp' ? -1 : 1); } };
      let lastWheelStep = -Infinity;
      section.addEventListener('wheel', e => { if (e.deltaY) { e.preventDefault(); const now = performance.now(); if (now - lastWheelStep >= 120) { lastWheelStep = now; change(e.deltaY < 0 ? -1 : 1); } } }, { passive: false });
      paint(); section.append(up, wheel, down); columns.append(section);
    });
    const actions = node('span', null, 'sch-picker-actions'); actions.append(back, button(T('schedule.pickerGo'), apply, 'btn btn-sm btn-primary sch-picker-go'));
    picker.append(columns, actions);
  };
  label.onclick = () => {
    if (!picker.hidden) { closePicker(); return; }
    const currentYear = new Date().getFullYear(); minYear = currentYear - 5; maxYear = currentYear + 5;
    pickedMonth = month.getMonth(); pickedYear = clampWheel(month.getFullYear(), minYear, maxYear);
    paintPicker(); picker.hidden = false; label.setAttribute('aria-expanded', 'true');
    const rect = label.getBoundingClientRect(), width = picker.offsetWidth;
    picker.style.left = Math.max(12, Math.min(window.innerWidth - width - 12, rect.left + rect.width / 2 - width / 2)) + 'px';
    picker.style.top = rect.bottom + 6 + 'px'; picker.querySelector('.sch-wheel').focus();
  };
  const escapePicker = e => { if (e.key === 'Escape' && !picker.hidden) { e.preventDefault(); e.stopPropagation(); closePicker(); } else if (e.key === 'Enter' && !picker.hidden && (e.target.classList.contains('sch-wheel') || e.target.classList.contains('sch-picker-go'))) { e.preventDefault(); apply(); } };
  label.onkeydown = escapePicker;
  picker.onkeydown = escapePicker;
  window.addEventListener('resize', () => { if (!picker.hidden) closePicker(); });
  document.addEventListener('scroll', e => { if (!picker.hidden && !picker.contains(e.target)) closePicker(); }, true);
  document.addEventListener('pointerdown', e => { if (!picker.hidden && !picker.parentElement.contains(e.target)) closePicker(); });
  $('schPrev').onclick = () => { month = view === 'week' ? new Date(addDays(month, -7)) : new Date(month.getFullYear(), month.getMonth() - 1, 1); render(); };
  $('schNext').onclick = () => { month = view === 'week' ? new Date(addDays(month, 7)) : new Date(month.getFullYear(), month.getMonth() + 1, 1); render(); };
  $('schForm').onsubmit = e => {
    e.preventDefault(); const input = currentInput();
    if (editing && editing.event.recurrence.kind === 'none') input.recurrence = editing.event.recurrence;
    const recurrenceChanged = editing && JSON.stringify(input.recurrence) !== editing.initialRecurrence;
    const result = validateEvent(input, Date.now()), errors = result.errors;
    if (editing && !canEditDetails(editing.occ, Date.now())) errors.start = 'too_late';
    else if (editing && !canEditSchedule(editing.occ, Date.now()) && (input.date !== editing.occ.day || input.time !== editing.event.time || input.all_day !== editing.event.all_day || recurrenceChanged)) errors.start = 'locked';
    const fields = [['start', 'Start', errors.start === 'locked' ? 'scheduleLockedError' : errors.start === 'too_late' ? 'editTooLate' : errors.start === 'past' ? 'past' : errors.start === 'all_day_today' ? 'allDayToday' : 'invalid', 'schTime'], ['duration_min', 'Length', errors.duration_min === 'ai_needs_length' ? 'aiNeedsLength' : 'invalidLength', 'schLength'], ['category', 'Category', errors.category === 'ai_needs_category' ? 'aiNeedsCategory' : 'invalidCategory', 'schCategory'], ['script', 'Script', 'savedMissing', 'schScript'], ['color', 'Color', 'invalidColor', 'schColor'], ['count', 'Count', 'invalidCount', 'schCount'], ['note', 'Note', 'invalidNote', 'schNote'], ['recurrence', 'Repeat', 'invalidRepeat', 'schRepeat'], ['days', 'Days', 'invalidDays', 'schDayChecks'], ['until', 'Until', 'invalidUntil', 'schUntil']];
    fields.forEach(([key, target, message, id]) => { $('sch' + target + 'Error').textContent = errors[key] ? T('schedule.' + message) : ''; $('sch' + target + 'Error').classList.toggle('show', !!errors[key]); if (id) $(id).setAttribute('aria-invalid', String(!!errors[key])); });
    $('schDate').setAttribute('aria-invalid', String(!!errors.start));
    if (Object.keys(errors).length) { const first = fields.find(([key]) => errors[key]); if (first[0] === 'start' && !$('schDate').disabled) $('schDate').focus(); else if (['schLength', 'schRepeat', 'schCategory', 'schColor', 'schScript'].includes(first[3])) $(first[3]).querySelector('[aria-checked="true"]').focus(); else if (first[3] === 'schDayChecks') $('schDayChecks').querySelector('button').focus(); else if (first[3]) $(first[3]).focus(); return; }
    if (editing && editing.event.recurrence.kind !== 'none') { if (input.date === editing.occ.day) delete input.date; if (!recurrenceChanged) delete input.recurrence; }
    const wasEditing = !!editing;
    saveScheduleState(editing ? editOccurrence(getSchedule(), editing.event.id, editing.occ.day, input, { now: Date.now(), newId: newEventId() }) : addEvent(getSchedule(), { ...input, id: newEventId(), created_at: Date.now(), details_edited_at: null, sample: false })); if (openPopover) openPopover(false); closeModal('schEventModal'); render(); if (S.modal.includes('schDayDrawer')) openDay(selectedDay); toast(T(wasEditing ? 'schedule.updated' : 'schedule.created'));
  };
}
let initialized = false;
RENDER.schedule = () => {
  pruneCache();
  if (!initialized) {
    init(); initialized = true;
    gridObserver = new ResizeObserver(() => {
      cancelAnimationFrame(gridFrame);
      gridFrame = requestAnimationFrame(() => { if (S.screen === 'schedule') render(); });
    });
    new MutationObserver(() => {
      if (!$('screenSchedule').classList.contains('active')) { gridObserver.disconnect(); cancelAnimationFrame(gridFrame); }
    }).observe($('screenSchedule'), { attributes: true, attributeFilter: ['class'] });
    window.addEventListener('resize', () => {
      if (S.screen === 'schedule') { cancelAnimationFrame(gridFrame); gridFrame = requestAnimationFrame(render); }
    });
  }
  weekScrollKey = ''; render(); gridObserver.observe($('schGrid'));
};
setInterval(() => { if (S.screen === 'schedule' && !S.modal.length) render(); else if (S.screen === 'home' && S.user) renderTodayPanel(); }, 60000);   // keeps the countdown and status changes fresh

export function openTodayEvent() { month = new Date(); render(); openEvent(dayKey(Date.now())); }
export function openTodayDrawer() { month = new Date(); render(); openDay(dayKey(Date.now())); }

let todayCarouselIndex = 0, todayResize = new AbortController();
const todayButton = (text, cls, action) => {
  const el = node('button', text, cls);
  el.type = 'button';
  if (action) el.addEventListener('click', action);
  return el;
};
export function renderTodayPanel() {
  pruneCache();
  const now = Date.now(), today = parseDay(dayKey(now));
  const occurrences = occurrencesBetween(addDays(startOfWeek(now), -56), addDays(today, 2));
  const summary = todaySummary(occurrences, now);
  const items = occurrences.filter(o => o.day === dayKey(now));
  const panel = document.getElementById('schTodayPanel');
  const active = document.activeElement;
  const focusRole = panel.contains(active) ? active.dataset.todayRole : null;
  const focusKey = focusRole ? active.closest('.sch-card')?.dataset.todayKey : null;
  let restoringFocus = false;
  todayResize.abort(); todayResize = new AbortController();
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
  if (items.length) {
    const viewport = node('div', null, 'sch-carousel-viewport');
    const track = node('div', null, 'sch-carousel-track'); track.id = 'schTodayTrack';
    const live = node('span', null, 'sr-only'); live.setAttribute('aria-live', 'polite');
    const carousel = node('div', null, 'sch-carousel-wrap');
    const arrow = (label, direction) => {
      const b = todayButton('', 'sch-carousel-arrow sch-chevron ' + (direction < 0 ? 'sch-carousel-prev' : 'sch-carousel-next'), e => { e.stopPropagation(); move(direction); });
      b.dataset.todayRole = direction < 0 ? 'prev' : 'next';
      b.setAttribute('aria-label', T('schedule.todayPanel.' + label)); b.setAttribute('aria-controls', track.id);
      const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); icon.setAttribute('viewBox', '0 0 24 24'); icon.setAttribute('aria-hidden', 'true');
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'path'); line.setAttribute('d', direction < 0 ? 'M15 18l-6-6 6-6' : 'M9 18l6-6-6-6'); icon.append(line); b.append(icon); return b;
    };
    const prev = arrow('previousPractices', -1), next = arrow('nextPractices', 1);
    carousel.append(prev, viewport, next);
    const words = Object.fromEntries(['hour', 'hours', 'minute', 'minutes', 'lessThanMinute'].map(k => [k, T('schedule.todayPanel.' + k)]));
    items.forEach((item, index) => {
      const status = occurrenceStatus(item, now), card = node('article', null, 'sch-card');
      applyEventStyle(card, status, item.color);
      card.dataset.todayKey = item.key;
      const itemTime = sessionTimeLabel(item, time, labelWords()), itemLength = lengthLabel(item.duration_min, labelWords()), category = categoryLabel(item);
      const open = todayButton('', 'sch-card-open', () => { go('schedule'); openDay(item.day, item.key); });
      open.dataset.todayRole = 'open';
      open.setAttribute('aria-label', T('schedule.todayPanel.details', { time: itemTime, length: itemLength }) + (category ? ', ' + category : ''));
      card.addEventListener('focusin', () => { const before = todayCarouselIndex, visible = visibleCount(); if (index < todayCarouselIndex) todayCarouselIndex = index; else if (index >= todayCarouselIndex + visible) todayCarouselIndex = index - visible + 1; if (before !== todayCarouselIndex) update(!restoringFocus); });
      const top = node('div', null, 'sch-card-top');
      top.append(node('strong', itemTime), node('span', itemLength, 'sch-card-length'));
      if (category) top.append(node('span', category, 'sch-card-length'));
      if (status === 'done' || status === 'missed') top.append(chip(status, null, false, item.color));
      const note = node('p', item.note, 'sch-card-note'); if (item.note) note.title = item.note; else note.setAttribute('aria-hidden', 'true');
      const statusLine = node('p', null, 'sch-card-status');
      if (status === 'active') {
        const remaining = windowClosesAt(item) - now; statusLine.classList.add('sch-tone-' + closesTone(remaining));
        const clock = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); clock.setAttribute('viewBox', '0 0 24 24'); clock.setAttribute('aria-hidden', 'true'); clock.setAttribute('class', 'sch-card-clock'); clock.innerHTML = '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'; statusLine.append(clock, document.createTextNode(T('schedule.todayPanel.closesIn', { time: formatDurationWords(remaining, words) })));
      } else if (status === 'upcoming') statusLine.textContent = T('schedule.todayPanel.startsIn', { time: formatDurationWords(item.start - now, words) });
      else if (status === 'done') statusLine.textContent = T('schedule.todayPanel.completedAt', { time: time(item.done_at) });
      else statusLine.textContent = T('schedule.todayPanel.windowClosed');
      const actions = node('div', null, 'sch-card-actions');
      if (status === 'active' || status === 'upcoming') {
        const check = todayButton(T('schedule.todayPanel.checkIn'), 'btn btn-primary', () => startCheckIn(item)); check.dataset.schCheckin = item.key; check.dataset.todayRole = 'check-in'; check.disabled = status === 'upcoming'; actions.append(check);
        if (status === 'upcoming') actions.append(node('span', T('schedule.todayPanel.opensAt', { time: time(item.start) }), 'sch-card-helper'));
      } else if (status === 'done') {
        const id = resultLink(getSchedule().done[item.key], S.sessions);
        if (id) { const result = todayButton(T('schedule.viewResult'), 'btn', null); result.dataset.open = id; result.dataset.todayRole = 'result'; actions.append(result); }
        else actions.append(node('span', T('schedule.resultUnavailable'), 'sch-card-helper'));
      }
      card.append(open, top, node('p', scriptLabel(item), 'sch-card-note'), note, statusLine, actions); track.append(card);
    });
    viewport.append(track); body.append(carousel, live);
    function visibleCount() { return window.matchMedia('(max-width: 720px)').matches ? 1 : 3; }
    function update(userMove = false) {
      const visible = visibleCount(); todayCarouselIndex = carouselStep(todayCarouselIndex, items.length, visible, 0);
      const fades = edgeFades(todayCarouselIndex, items.length, visible);
      viewport.classList.toggle('sch-fade-left', fades.left); viewport.classList.toggle('sch-fade-right', fades.right);
      prev.hidden = !fades.left; next.hidden = !fades.right;
      const card = track.firstElementChild; const offset = !fades.right ? Math.max(0, track.scrollWidth - viewport.clientWidth) : card ? todayCarouselIndex * (card.getBoundingClientRect().width + 16) : 0;
      viewport.scrollLeft = 0;
      if (!userMove) track.style.transition = 'none';
      track.style.transform = `translateX(-${offset}px)`;
      if (!userMove) { void track.offsetWidth; track.style.removeProperty('transition'); }
      if (userMove) { const message = T('schedule.todayPanel.showing', { start: todayCarouselIndex + 1, end: Math.min(items.length, todayCarouselIndex + visible), total: items.length }); if (live.textContent !== message) live.textContent = message; }
    }
    function move(direction) { const visible = visibleCount(); todayCarouselIndex = carouselStep(todayCarouselIndex, items.length, visible, direction * visible); update(true); const target = direction < 0 ? prev : next; (target.hidden ? (direction < 0 ? next : prev) : target).focus({ preventScroll: true }); }
    update();
    requestAnimationFrame(() => update());
    window.addEventListener('resize', () => { if (panel.contains(viewport)) update(); }, { signal: todayResize.signal });
  } else {
    todayCarouselIndex = 0;
    body.append(node('p', T('schedule.todayPanel.nothing')));
    body.append(todayButton(T('schedule.todayPanel.plan'), 'btn btn-primary', () => { go('schedule'); openTodayDrawer(); }));
  }
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
  if (motivation && !(motivation === 'windowOpen' && occ?.duration_min == null)) panel.append(node('p', T('schedule.motivation.' + motivation, { n: summary.streak, len: occ?.duration_min ?? '' }), 'sch-motivation'));
  if (focusRole) {
    const target = [...panel.querySelectorAll('[data-today-role]')].find(el => el.dataset.todayRole === focusRole && (focusKey == null || el.closest('.sch-card')?.dataset.todayKey === focusKey));
    if (target && !target.disabled && !target.hidden) { restoringFocus = true; target.focus({ preventScroll: true }); restoringFocus = false; }
  }
}

configureCheckIn({ getSchedule, saveScheduleState, rerender: () => { if (S.screen === 'home') renderTodayPanel(); if (S.screen === 'schedule') { render(); if (S.modal.includes('schDayDrawer')) openDay(selectedDay); } } });
