import { api } from '../api.js';
import { sh } from '../data.js';
import { T } from '../i18n.js';
import { go } from '../nav.js';
import { revokeAudio } from '../screens/report.js';
import { CONFIG, RENDER, S } from '../state.js';
import { busy, toast, withBusy } from '../ui.js';
import { $, esc, fmtDay, fmtDayLong, fmtTime, scored } from '../utils.js';

/* ---------- History from the server (F2): GET /api/sessions, /api/sessions/{id}, DELETE ---------- */
export const DETAIL_TTL_MS = 5 * 60 * 1000;  // signed audio URLs last signed_url_ttl_s (600 s): reload the detail before that
export const numOrNull = v => (typeof v === 'number' && Number.isFinite(v) ? v : null);
/* One /api/sessions item -> the session object Home and History draw. The full report (an) loads on open. */
export function sessionFromSummary(it) {
  const c = it.components || {};
  return {
    id: it.id, ts: Date.parse(it.created_at), title: it.topic || T('history.untitled'), topicKey: null,
    sc: { status: it.status, overall: it.overall, label: it.label, flags: null, warnings: [],
      A: numOrNull(c.accuracy), F: numOrNull(c.fluency), P: numOrNull(c.pronunciation), S: numOrNull(c.semantic),
      wpm: numOrNull(it.wpm), Rst: numOrNull(it.pitch_range_st), Pclar: numOrNull(it.p_clarity) },
    an: null, dur: numOrNull(it.audio_duration_s) || 0, accent: null, compact: !!it.is_compact, remote: true, demo: false
  };
}
/* Resolves when the list and the latest session's full scores are in (Home's hero needs both). */
export function loadHistory() {
  const user = S.user, items = [];
  const page = (cursor, n) => api('/api/sessions?limit=' + CONFIG.HISTORY_PAGE_SIZE + (cursor ? '&cursor=' + encodeURIComponent(cursor) : ''))
    .then(r => (r.ok ? r.json() : Promise.reject(new Error('history ' + r.status)))).then(d => {
      if (S.user !== user) return null;
      items.push.apply(items, d.items || []);
      return d.next_cursor && n + 1 < CONFIG.HISTORY_MAX_PAGES ? page(d.next_cursor, n + 1) : items;
    });
  return page(null, 0).then(list => {
    if (!list || S.user !== user) return;
    const known = new Set(list.map(x => x.id));
    S.sessions = list.map(sessionFromSummary).concat(S.sessions.filter(s => !known.has(s.id)));   // keep sessions saved while loading
    if (S.screen === 'home') RENDER.home();
    const last = scored().slice(-1)[0];   // Home's "next step" advice needs the latest full scores
    if (last && !last.an) return loadSessionDetail(last).then(() => { if (S.user === user && S.screen === 'home') RENDER.home(); }).catch(() => {});
  }).catch(() => { if (S.user === user) toast(T('history.loadErr'), true); });
}
/* GET /api/sessions/{id}: full result (+ signed audio URL), or a compact one rebuilt from its mistakes. */
export function loadSessionDetail(s) {
  if (s.an && (s.fresh || (s.detailAt && Date.now() - s.detailAt < DETAIL_TTL_MS))) return Promise.resolve(s);
  return api('/api/sessions/' + encodeURIComponent(s.id)).then(r => (r.ok ? r.json() : Promise.reject(new Error('session ' + r.status)))).then(d => {
    const json = d.is_compact ? EvaluateClient.expandCompact(d.result, d.mistakes, d.script_snapshot) : d.result;
    const m = EvaluateClient.mapResult(json, d.script_snapshot);
    if (d.is_compact) { m.sc.nSent = null; m.sc.cosOk = null; }   // sentence checks are not kept in compact sessions
    Object.assign(s, { an: m.an, sc: m.sc, dur: m.an.dur != null ? m.an.dur : s.dur, accent: d.accent || null, compact: !!d.is_compact,
      audioUrl: d.media_available && d.audio_url ? d.audio_url : null, detailAt: Date.now() });
    if (d.topic) s.title = d.topic;
    return s;
  });
}
export function deleteSession(id) {
  return withBusy(api('/api/sessions/' + encodeURIComponent(id), { method: 'DELETE' }), T('busy.deleting')).then(r => {
    if (!r.ok && r.status !== 404) throw new Error('delete ' + r.status);   // 404: already gone
    S.sessions.filter(x => x.id === id).forEach(revokeAudio);
    S.sessions = S.sessions.filter(x => x.id !== id);
    if (S.currentSession && S.currentSession.id === id) S.currentSession = null;
  });
}


/* ---------- History (bottom of Home; called from RENDER.home) ---------- */
export function renderHistory() {
  const ss = scored();
  $('#historyBody').innerHTML = ss.slice().reverse().map(s => {
    const lab = fmtDay(s.ts) + ', ' + s.title;
    return '<tr><td>' + esc(fmtDayLong(s.ts)) + '</td><td>' + esc(s.title) + '</td><td class="num">' + fmtTime(s.dur) + '</td><td class="num">' + esc(sh(s.sc.overall)) + '</td><td><div class="row" style="flex-wrap:nowrap;justify-content:flex-end"><button class="btn btn-ghost btn-sm" type="button" data-open="' + s.id + '" aria-label="' + esc(T('history.open') + ': ' + lab) + '">' + esc(T('history.open')) + '</button><button class="btn btn-danger-ghost btn-sm" type="button" data-del="' + s.id + '" aria-label="' + esc(T('history.delete') + ': ' + lab) + '">' + esc(T('history.delete')) + '</button></div></td></tr>';
  }).join('');
}
let opening = false;   // a second click while one report is loading is ignored
export function openReport(id) {
  const s = S.sessions.find(x => x.id === id); if (!s || opening) return;
  opening = true;
  const done = busy(T('history.opening'), 150);   // dim + loading bars while the full report downloads
  loadSessionDetail(s)
    .then(() => { done(); S.currentSession = s; go('report'); }, () => { done(); toast(T('history.openErr'), true); })
    .finally(() => { opening = false; });
}
