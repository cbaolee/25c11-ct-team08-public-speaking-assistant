import { readAiCache, writeAiCache, removeAiScript, getAiScript, putAiScript, pickTopic } from './schedule_script.js';
import { api, readJson } from '../api.js';
import { openConfirmDialog } from '../modals/confirm.js';
import { runScriptAction } from '../screens/script_reader.js';
import { setPracticeSourceLock } from '../screens/practice.js';
import { T, TOPICS } from '../i18n.js';
import { go } from '../nav.js';
import { CONFIG, S } from '../state.js';
import { toast, openModal, closeModal } from '../ui.js';
import { canCheckIn, occurrenceStatus, windowClosesAt } from './schedule_model.js';
import { markDone } from './schedule_store.js';
import { shouldCompleteCheckIn, shouldClearOnLeave, lengthLabel } from './schedule_view.js';

let context = null, callbacks, previousPractice = null, generation = null, loading = new Set();
const POLL_MAX_MS = 5 * 60 * 1000;
const pollIntervalMs = () => Number(CONFIG.SCRIPT_POLL_INTERVAL_MS) || 650;
export function configureCheckIn(value) { callbacks = value; }
export function currentCheckIn() { return context; }
function paintBanner() {
  const banner = document.getElementById('schBanner');
  banner.hidden = !context || S.screen !== 'practice';
  banner.replaceChildren();
  if (banner.hidden) return;
  const text = document.createElement('span');
  text.textContent = T('schedule.scheduledPractice') + ' \u00B7 ' + (context.all_day ? T('schedule.allDay') + ' \u00B7 ' : '') + lengthLabel(context.duration_min, T('schedule')) + (context.category && context.category !== 'any' ? ' \u00B7 ' + TOPICS[context.category] : '') + (context.note ? ' \u00B7 ' + context.note : '') + (context.script?.kind === 'ai' ? ' \u00B7 ' + T('schedule.aiReadOnly') : context.script?.kind === 'saved' ? ' \u00B7 ' + T('schedule.scheduledScript', { title: context.script.title }) : '') + ' \u00B7';
  const badge = document.createElement('span');
  badge.className = 'badge-demo'; badge.textContent = T('schedule.demo');
  banner.append(text, badge);
}
export function clearCheckIn() {
  context = null; setPracticeSourceLock(null);
  if (previousPractice) { S.texts.mine = previousPractice.mine; S.pickerTab = previousPractice.tab; previousPractice = null; if (S.audio) { S.audio = null; S.choosing = true; } }
  paintBanner();
}
function begin(occ, at, script) {
  context = { occKey: occ.key, event_id: occ.event_id, start: occ.start, duration_min: occ.duration_min, all_day: occ.all_day, category: occ.category, note: occ.note, script: occ.script, checkin_at: at };
  if (script) {
    if (previousPractice === null) previousPractice = { mine: S.texts.mine, tab: S.pickerTab };
    // Use the Studio handoff so issue #123 can validate unsaved generated scripts.
    runScriptAction(script, 'practice');
    setPracticeSourceLock({ kind: occ.script.kind, message: T('schedule.fixedScript') });
    // The handoff renders before the lock is installed.
    document.querySelectorAll('[data-src]').forEach(b => { b.disabled = true; });
    document.querySelector('[data-step="1"]').disabled = true;
  } else go('practice');
  paintBanner();
}
function cacheStorage() { try { return window.localStorage; } catch (_) { return null; } }
function showGeneration(occ, at) {
  if (generation) generation.abort();
  const ctl = new AbortController(); generation = ctl; ctl.occKey = occ.key;
  const progress = document.getElementById('schGenProgress'), cancel = document.getElementById('schGenCancel'), retry = document.getElementById('schGenRetry'), close = document.getElementById('schGenClose');
  progress.textContent = T('schedule.genProgress'); cancel.hidden = false; retry.hidden = true; close.hidden = true;
  const stop = () => { ctl.abort(); if (generation === ctl) generation = null; closeModal('schGenModal'); };
  cancel.onclick = stop; close.onclick = stop;
  retry.onclick = () => { stop(); showGeneration(occ, at); };
  openModal('schGenModal', { focus: '#schGenCancel', lock: true });
  const fail = (message, canRetry = true) => { if (ctl.signal.aborted) return; progress.textContent = T(message); cancel.hidden = true; retry.hidden = !canRetry; close.hidden = false; (canRetry ? retry : close).focus(); };
  const request = (url, opts = {}) => api(url, { ...opts, signal: ctl.signal }).then(readJson).then(r => { if (!r.ok || !r.j) throw new Error('request'); return r.j; });
  const wait = () => new Promise((resolve, reject) => { const timer = setTimeout(resolve, pollIntervalMs()); ctl.signal.addEventListener('abort', () => { clearTimeout(timer); reject(new Error('abort')); }, { once: true }); });
  (async () => {
    try {
      const data = await request('/api/topics?category=' + encodeURIComponent(occ.category));
      const topic = pickTopic(data.topics || [], occ.duration_min);
      if (!topic) { fail('schedule.genNoTopic', false); return; }
      const fd = new FormData(); fd.append('topic', topic.topic); fd.append('category', occ.category); fd.append('duration_min', String(occ.duration_min));
      const job = await request('/api/generate-script', { method: 'POST', body: fd });
      if (!job.job_id) throw new Error('request');
      let tries = 0, result;
      while (!ctl.signal.aborted) {
        if (++tries > Math.ceil(POLL_MAX_MS / pollIntervalMs())) { fail('schedule.genTimeout'); return; }
        const j = await request('/api/generate-script/' + encodeURIComponent(job.job_id));
        if (j.status === 'failed') throw new Error('failed');
        progress.textContent = (j.status === 'extracting' ? T('script.extracting') : j.status === 'moderating' ? T('script.checking') : T('script.generating')) + ' (' + (j.progress || 0) + '%)';
        if (j.status === 'completed') { result = j.result; break; }
        await wait();
      }
      if (ctl.signal.aborted) return;
      if (!result || typeof result.script !== 'string' || !result.script.trim()) throw new Error('result');
      const entry = { title: typeof result.title === 'string' && result.title.trim() ? result.title.trim() : topic.topic, text: result.script, topic: occ.category, category: occ.category, duration_min: occ.duration_min, closes_at: windowClosesAt(occ), created_at: Date.now() };
      const storage = cacheStorage(); writeAiCache(storage, S.user.id, putAiScript(readAiCache(storage, S.user.id), occ.key, entry));
      stop(); handoffAi(occ, at, entry);
    } catch (_) { if (!ctl.signal.aborted) fail('schedule.genError'); }
  })();
}
function handoffAi(occ, at, entry) {
  begin(occ, at, { text: entry.text, title: entry.title, cardName: entry.title, savedId: null, topic: occ.category, duration_min: occ.duration_min, source: 'generated' });
}
export function startCheckIn(occ) {
  if (context?.occKey === occ.key || loading.has(occ.key) || generation?.occKey === occ.key) return;
  const now = Date.now();
  if (!canCheckIn(occ, now) || occurrenceStatus(occ, now) !== 'active') { toast(T('schedule.checkInClosed')); callbacks.rerender(); return; }
  if (S.evaluation?.background) { go('practice'); return; }
  if (occ.script?.kind === 'saved') {
    loading.add(occ.key);
    api('/api/scripts/' + encodeURIComponent(occ.script.script_id)).then(readJson).then(({ ok, status, j }) => {
      if (status === 404) { openConfirmDialog(T('schedule.savedUnavailable'), T('schedule.savedUnavailableDetail'), T('schedule.practiceFree'), () => begin({ ...occ, script: { kind: 'free' } }, now), { primary: true }); return; }
      if (!ok || !j || typeof j.body !== 'string') throw new Error('request');
      begin(occ, now, { text: j.body, title: j.title, cardName: j.title, savedId: occ.script.script_id, topic: null, duration_min: occ.duration_min });
    }).catch(() => {
      toast(T('schedule.checkInRetry'), true);
      const retry = document.createElement('button'); retry.type = 'button'; retry.className = 'btn btn-sm'; retry.textContent = T('schedule.genRetry');
      retry.onclick = () => { document.getElementById('toast').classList.remove('show'); startCheckIn(occ); };
      document.getElementById('toast').append(retry);
    }).finally(() => loading.delete(occ.key));
  } else if (occ.script?.kind === 'ai') {
    const storage = cacheStorage(), cached = getAiScript(readAiCache(storage, S.user.id), occ.key, now);
    if (cached) handoffAi(occ, now, cached); else showGeneration(occ, now);
  } else begin(occ, now);
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
    try { const storage = window.localStorage; writeAiCache(storage, S.user.id, removeAiScript(readAiCache(storage, S.user.id), context.occKey)); } catch (_) {}
    clearCheckIn(); callbacks.rerender();
    setTimeout(() => toast(T('schedule.checkInComplete')), 4000);
  } else if (S.screen !== 'practice') clearCheckIn();
});
