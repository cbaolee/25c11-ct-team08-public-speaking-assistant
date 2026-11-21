import { api, readJson, storeAuth } from '../api.js';
import { hideTip } from '../charts.js';
import { T } from '../i18n.js';
import { stopAudioTest } from '../modals/settings_modal.js';
import { renderAccount, showView } from '../nav.js';
import { requireConsent, startRecorder } from '../recorder.js';
import { setStageAuth } from '../screens/landing.js';
import { EVAL_ERR, EXT_BY_MIME, clearFollowWpm, dropEval } from '../screens/practice.js';
import { resetBaselineAudio } from '../screens/profile.js';
import { clearChatHistory } from '../screens/script_studio.js';
import { revokeAudio, stopPlayback } from '../screens/report.js';
import { CONFIG, RENDER, S } from '../state.js';
import { closeModal, focusHeading, openModal, toast } from '../ui.js';
import { $, esc, fmtDayLong, fmtTime } from '../utils.js';

/* F1: the server decides if the Baseline Gate opens (GET /api/baseline returns null = no baseline yet).
   Resolves true only when the server said "no baseline", so a caller with openGate=false can open
   the gate later (after the loading screen). Errors resolve undefined: no gate. */
export function loadBaseline(openGate) {
  const user = S.user;
  return api('/api/baseline').then(readJson).then(({ ok, status, j }) => {
    if (S.user !== user || status === 401) return;
    if (!ok) { toast(T('eval.errBaselineUnavailable'), true); return; }
    S.baseline = j ? { ts: Date.parse(j.recorded_at) || Date.now(), profile: j } : null;
    if (S.screen === 'home' || S.screen === 'profile') RENDER[S.screen]();
    if (openGate && !S.baseline) openBaselineGate();
    return !S.baseline;
  }).catch(() => { if (S.user === user) toast(T('eval.errNet'), true); });
}

/* POST the baseline recording to /api/baseline. cb({profile}) on success, cb({msg}) on any failure (nothing is saved on failure). */
export function postBaseline(rec, cb) {
  const fd = new FormData();
  fd.append('audio', rec.blob, 'baseline' + (EXT_BY_MIME[(rec.mime || '').split(';')[0]] || '.webm'));
  const ctrl = new AbortController();
  let timedOut = false;
  const tm = setTimeout(() => { timedOut = true; ctrl.abort(); }, 60000);
  api('/api/baseline', { method: 'POST', body: fd, signal: ctrl.signal }).then(res => res.json().catch(() => null).then(j => {
    clearTimeout(tm);
    if (res.ok && j && j.status === 'insufficient_audio') { cb({ msg: T('profile.errInsufficient') }); return; }
    if (res.ok && j && j.status === 'ok') { const pr = EvaluateClient.pickBaselineProfile(j); cb(pr ? { profile: pr } : { msg: T('eval.errServer') }); return; }
    if (j && j.error_code) { cb({ msg: EVAL_ERR[j.error_code] ? T('eval.' + EVAL_ERR[j.error_code]) : (j.message || T('eval.errServer')) }); return; }
    cb({ msg: T('eval.errServer') });
  })).catch(() => { clearTimeout(tm); cb({ msg: T(timedOut ? 'eval.errTimeout' : 'eval.errNet') }); });
}
/* ---------- baseline window (opens after log in) ---------- */
export function openBaselineGate() {
  S.baselineGate = { saved: false };
  renderGate();
  openModal('baselineGate', { lock: true, focus: '#baselineGateAgree' });
}
export function renderGate(sec, msg) {
  const rec = !!S.grec, g = S.baselineGate || {}, s = sec || 0;
  $('#baselineGateTimer').textContent = fmtTime(s) + T('profile.timerSuffix', { t: fmtTime(CONFIG.BASELINE_SECONDS) });
  const pct = Math.min(100, Math.round(s / CONFIG.BASELINE_SECONDS * 100));
  $('#baselineGateBar').style.width = pct + '%'; $('#baselineGateBarWrap').setAttribute('aria-valuenow', String(pct));
  const ag = $('#baselineGateAgree');
  ag.innerHTML = rec ? '<span class="rec-dot" aria-hidden="true"></span>' + esc(T('profile.stop')) : esc(T(g.saved ? 'gate.done' : 'gate.agree'));
  ag.classList.toggle('btn-record', rec); ag.classList.toggle('btn-primary', !rec);
  $('#baselineGateLogout').hidden = !!g.saved; $('#baselineGateLogout').disabled = rec;
  const st = $('#baselineGateStatus');
  if (rec) { st.className = 'pill'; st.textContent = T('profile.recording'); }
  else if (msg) { st.className = 'pill warn'; st.textContent = msg; }
  else if (g.saved) { st.className = 'pill ok'; st.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12l5 5 9-10"/></svg><span></span>'; $('span', st).textContent = T('profile.saved', { date: fmtDayLong(S.baseline.ts) }); }
  else { st.className = 'pill'; st.textContent = T('profile.none'); }
}
export function onGateAgree() {
  if (S.grec) { S.grec.stop(false); return; }
  if (S.baselineGate && S.baselineGate.busy) return;
  if (S.baselineGate && S.baselineGate.saved) { closeModal('baselineGate', false); focusHeading(); return; }
  requireConsent(() => {
    S.grec = startRecorder({
      lvl: $('#baselineGateLevel'), max: CONFIG.BASELINE_SECONDS, onTick: s => renderGate(s),
      onEnd: (sec, auto, rec) => {
        S.grec = null;
        const min = CONFIG.BASELINE_MIN_SECONDS;
        if (sec < min || !rec || !rec.blob) { renderGate(0, T('profile.tooShort', { n: min })); return; }
        const g = S.baselineGate, user = S.user;
        g.busy = true; renderGate(0, T('profile.analysing'));
        postBaseline(rec, r => {
          if (S.baselineGate !== g || S.user !== user) return;   // logged out meanwhile
          g.busy = false;
          if (!r.profile) { renderGate(0, r.msg); return; }   // gate stays locked, nothing saved
          S.baseline = { ts: Date.now(), profile: r.profile }; g.saved = true; renderGate(sec); toast(T('profile.toastSaved'));
        });
      },
      onError: code => { S.grec = null; renderGate(0, T('practice.mic' + code.charAt(0).toUpperCase() + code.slice(1))); }
    });
    renderGate(0);
  });
}
export function logout(expired) {
  if (!expired) clearChatHistory(S.user && S.user.id);   // session expiry keeps the chat for the next login
  if (!expired && S.auth) api('/api/auth/logout', { method: 'POST' }).catch(() => {});   // best effort: revoke on the server
  storeAuth(null);
  clearFollowWpm(S.user && S.user.id);
  hideTip(); stopPlayback(); resetBaselineAudio();   // no signed URL of this user may survive for the next one
  [S.rec, S.brec, S.grec].forEach(r => { if (r) r.cancel(); });
  stopAudioTest();
  S.sessions.forEach(revokeAudio); revokeAudio(S.currentSession);
  S.rec = S.brec = S.grec = null; S.bbusy = null; S.follow = null; S.baselineGate = null; S.afterConsent = null; S.onDeny = null;
  dropEval();
  S.modal.slice().forEach(id => closeModal(id, false));
  S.user = null; S.profile = null; S.sessions = []; S.audio = null; S.currentSession = null; S.baseline = null; S.consent = false; S.avatar = null; S.savedScripts = null; S.savedScriptTotal = 0; S.ownSaved = null; S.readerScript = null; S.chatHistory = [];
  renderAccount(); setStageAuth(false); showView('landing'); window.scrollTo(0, 0);
}
