import { api, readJson } from '../api.js';
import { T, TOPICS } from '../i18n.js';
import { postBaseline } from '../modals/baseline_gate.js';
import { paintAvatar } from '../nav.js';
import { practiceLocked } from '../screens/practice.js';
import { startRecorder } from '../recorder.js';
import { CONFIG, RENDER, S } from '../state.js';
import { closeModal, openModal, toast, withBusy } from '../ui.js';
import { $, esc, fmtDayLong, fmtTime } from '../utils.js';

/* ---------- Profile ---------- */
RENDER.profile = function () {
  paintAvatar($('#avBig')); $('#avRemove').disabled = !S.avatar;
  const p = S.profile || {}, ns = T('profile.rowNotSet');
  const rows = [
    [T('profile.rowName'), S.user.name], [T('profile.rowGender'), p.gender || ns], [T('profile.rowAge'), p.age != null ? p.age : ns],
    [T('profile.rowAccent'), p.accent || ns], [T('profile.rowTopics'), p.topics && p.topics.length ? p.topics.map(k => TOPICS[k]).join(', ') : ns]
  ];
  $('#pfBaseline').textContent = S.baseline ? T('profile.rowBaselineDone', { date: fmtDayLong(S.baseline.ts) }) : T('profile.none');
  $('#pfSummary').innerHTML = rows.map(r => '<tr><th scope="row">' + esc(r[0]) + '</th><td>' + esc(r[1]) + '</td></tr>').join('');
  renderBaseline();
};
export function renderBaseline(sec, msg) {
  const rec = !!S.brec, s = sec || 0;
  $('#profileBaselineTimer').textContent = fmtTime(s) + T('profile.timerSuffix', { t: fmtTime(CONFIG.BASELINE_SECONDS) });
  const pct = Math.min(100, Math.round(s / CONFIG.BASELINE_SECONDS * 100));
  $('#profileBaselineBar').style.width = pct + '%'; $('#profileBaselineBarWrap').setAttribute('aria-valuenow', String(pct));
  const lb = $('#profileBaselineListen');
  lb.hidden = !S.baseline; lb.disabled = rec || !!S.bbusy || !!S.blLoad;
  // the recorder window cannot be closed while it records or uploads
  const busy = rec || !!S.bbusy;
  $('#baselineRecorder')._lock = busy; $('#baselineRecorderClose').disabled = busy; $('#profileBaselineAgain').disabled = busy;
  if (!S.baseline) resetBaselineAudio();
  $('#profileBaselineStart').innerHTML = rec ? '<span class="rec-dot" aria-hidden="true"></span>' + esc(T('profile.stop')) : esc(T('profile.start'));
  const st = $('#profileBaselineStatus');
  if (rec) { st.className = 'pill'; st.textContent = T('profile.recording'); }
  else if (msg) { st.className = 'pill warn'; st.textContent = msg; }
  else if (S.baseline) { st.className = 'pill ok'; st.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12l5 5 9-10"/></svg><span></span>'; $('span', st).textContent = T('profile.saved', { date: fmtDayLong(S.baseline.ts) }); }
  else { st.className = 'pill'; st.textContent = T('profile.none'); }
}
/* Baseline playback: GET /api/baseline/audio returns a short-lived signed URL; ask again after a new recording or an expired link. */
export function resetBaselineAudio() {
  const a = $('#profileBaselineAudio'), m = $('#profileBaselineListenMessage');
  if (!a) return;
  S.blTok = {}; S.blLoad = null;   // a fetch still in flight is now stale and must not set src
  a.pause(); a.removeAttribute('src'); a.load(); a.hidden = true; m.hidden = true; m.textContent = '';
}
export function onBaselineAudioError() {   // expired or broken URL: drop it, the next click fetches a new one
  const a = $('#profileBaselineAudio');
  if (!a.getAttribute('src')) return;
  a.removeAttribute('src'); a.hidden = true;
  $('#profileBaselineListenMessage').textContent = T('profile.errListen'); $('#profileBaselineListenMessage').hidden = false;
}
export function listenBaseline() {
  if (S.blLoad || S.brec || S.bbusy || S.grec) return;
  resetBaselineAudio();
  const a = $('#profileBaselineAudio'), m = $('#profileBaselineListenMessage'), user = S.user, tok = S.blTok, lb = $('#profileBaselineListen');
  S.blLoad = tok; lb.disabled = true;
  const stale = () => S.user !== user || S.blTok !== tok || S.brec || S.bbusy || S.grec;
  const fail = k => { a.hidden = true; m.textContent = T(k); m.hidden = false; };
  m.hidden = true;
  return withBusy(api('/api/baseline/audio'), T('busy.loading')).then(readJson).then(({ ok, status, j }) => {
    if (stale() || status === 401) return;
    if (status === 404) { fail('profile.errListenNone'); return; }
    if (!ok || !j || !j.url) { fail('profile.errListen'); return; }
    a.src = j.url; a.hidden = false;
    a.play().catch(() => { /* autoplay blocked: the controls stay visible */ });
  }).catch(() => { if (!stale()) fail('profile.errListen'); })
    .finally(() => { if (S.blLoad === tok) { S.blLoad = null; lb.disabled = !!S.brec || !!S.bbusy; } });
}
/* Profile > Record again: opens the Baseline Recorder. No consent step here: the account already
   agreed to recording when it recorded its first baseline in the Baseline Gate. */
export function openBaselineRecorder() {
  if (S.brec || S.bbusy) return;
  resetBaselineAudio();
  renderBaseline(0);
  openModal('baselineRecorder', { focus: '#profileBaselineStart' });
}
export function toggleBaseline() {
  if (S.brec) { S.brec.stop(false); return; }
  if (S.bbusy || practiceLocked()) return;   // no new recording while an evaluation runs in the background
  {
    resetBaselineAudio();   // stop playback and drop any pending URL before the mic opens
    S.brec = startRecorder({
      lvl: $('#profileBaselineLevel'), max: CONFIG.BASELINE_SECONDS, onTick: s => renderBaseline(s),
      onEnd: (sec, auto, rec) => {
        S.brec = null;
        const min = CONFIG.BASELINE_MIN_SECONDS;
        if (sec < min || !rec || !rec.blob) { renderBaseline(0, T('profile.tooShort', { n: min })); return; }
        const tok = S.bbusy = {}, user = S.user;
        renderBaseline(0, T('profile.analysing'));
        postBaseline(rec, r => {
          if (S.bbusy !== tok || S.user !== user) return;   // logged out meanwhile
          S.bbusy = null;
          if (!r.profile) { renderBaseline(0, r.msg); return; }   // nothing saved; an older baseline (if any) stays
          resetBaselineAudio();   // old signed URL points at the replaced file
          S.baseline = { ts: Date.now(), profile: r.profile }; renderBaseline(sec); toast(T('profile.toastSaved'));
          closeModal('baselineRecorder'); if (S.screen === 'profile') RENDER.profile();
        });
      },
      onError: code => { S.brec = null; renderBaseline(0, T('practice.mic' + code.charAt(0).toUpperCase() + code.slice(1))); }
    });
    renderBaseline(0);
  }
}
