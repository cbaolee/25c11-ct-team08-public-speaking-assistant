import { T, TOPICS } from '../i18n.js';
import { go } from '../nav.js';
import { S } from '../state.js';
import { toast } from '../ui.js';
import { canCheckIn, occurrenceStatus } from './schedule_model.js';
import { markDone } from './schedule_store.js';
import { shouldCompleteCheckIn, shouldClearOnLeave, lengthLabel } from './schedule_view.js';

let context = null, callbacks;
export function configureCheckIn(value) { callbacks = value; }
export function currentCheckIn() { return context; }
function paintBanner() {
  const banner = document.getElementById('schBanner');
  banner.hidden = !context || S.screen !== 'practice';
  banner.replaceChildren();
  if (banner.hidden) return;
  const text = document.createElement('span');
  text.textContent = T('schedule.scheduledPractice') + ' \u00B7 ' + (context.all_day ? T('schedule.allDay') + ' \u00B7 ' : '') + lengthLabel(context.duration_min, T('schedule')) + (context.category && context.category !== 'any' ? ' \u00B7 ' + TOPICS[context.category] : '') + (context.note ? ' \u00B7 ' + context.note : '') + ' \u00B7';
  const badge = document.createElement('span');
  badge.className = 'badge-demo'; badge.textContent = T('schedule.demo');
  banner.append(text, badge);
}
export function clearCheckIn() { context = null; paintBanner(); }
export function startCheckIn(occ) {
  const now = Date.now();
  if (!canCheckIn(occ, now) || occurrenceStatus(occ, now) !== 'active') {
    toast(T('schedule.checkInClosed')); callbacks.rerender(); return;
  }
  if (S.evaluation?.background) { go('practice'); return; }
  context = { occKey: occ.key, event_id: occ.event_id, start: occ.start, duration_min: occ.duration_min, all_day: occ.all_day, category: occ.category, note: occ.note, checkin_at: now };
  go('practice'); paintBanner();
}
new MutationObserver(() => {
  if (context && shouldClearOnLeave(S.screen === 'practice', !!S.evaluation?.background)) clearCheckIn();
  else paintBanner();
}).observe(document.getElementById('screenPractice'), { attributes: true, attributeFilter: ['class'] });
// Cancellation and errors can end a background job without a completion event.
new MutationObserver(() => {
  if (context && shouldClearOnLeave(S.screen === 'practice', !!S.evaluation?.background) && document.getElementById('evDock').hidden) clearCheckIn();
}).observe(document.getElementById('evDock'), { attributes: true, attributeFilter: ['hidden'] });
document.addEventListener('psc:evaluation-complete', event => {
  if (!context) return;
  if (shouldCompleteCheckIn(context, event.detail)) {
    callbacks.saveScheduleState(markDone(callbacks.getSchedule(), context.occKey, { checkin_at: context.checkin_at, done_at: Date.now(), session_id: event.detail.session_id }));
    clearCheckIn(); callbacks.rerender();
    setTimeout(() => toast(T('schedule.checkInComplete')), 4000);
  } else if (S.screen !== 'practice') clearCheckIn();
});
