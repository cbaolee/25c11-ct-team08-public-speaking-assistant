import { api } from '../api.js';
import { SAMPLE_TEXTS, sh, tokenize } from '../data.js';
import { T } from '../i18n.js';
import { openBaselineGate } from '../modals/baseline_gate.js';
import { openConfirmDialog } from '../modals/confirm.js';
import { go } from '../nav.js';
import { requireConsent, startRecorder } from '../recorder.js';
import { saveScript } from '../screens/script_studio.js';
import { CONFIG, RENDER, S } from '../state.js';
import { closeModal, openModal, toast } from '../ui.js';
import { $, $$, clearErr, esc, fmtClock, fmtTime, showErr, wordsOf } from '../utils.js';

/* ---------- Practice ---------- */
export function goStep(i) {
  if (S.rec || i >= 3) return;
  const go = () => {
    S.choosing = i === 1; S.audio = null; renderPractice();
    const f = i === 1 ? $('[data-src=' + S.pickerTab + ']') : (S.voiceTab === 'rec' ? $('#recBtn') : $('#dropBtn'));
    if (f) { f.focus(); if (f.scrollIntoView) f.scrollIntoView({ block: 'nearest' }); }
  };
  if (S.audio) openConfirmDialog(T('practice.stepBackT'), T('practice.stepBackD'), T('practice.discardOk'), go); else go();
}
export function selectPickerTab(k) { S.pickerTab = k; S.choosing = true; renderPractice(); }
export function pickSample() {
  const n = S.sampleN % SAMPLE_TEXTS.length, text = SAMPLE_TEXTS[n], label = 'Text ' + (n + 1);
  S.sampleN++; S.choosing = true;
  S.texts.sample = { title: T('practice.sampleTitle', { title: label }), short: label, text, topic: null };
  renderPractice();
}
/* Saved scripts (Practice > Mine): GET /api/scripts lists summaries; the text comes from GET /api/scripts/{id}. */
export function pickSavedScript(id, byUser) {   // byUser: picked in the dropdown (back to step 1); the automatic first pick must not move the stepper
  return api('/api/scripts/' + encodeURIComponent(id)).then(r => (r.ok ? r.json() : null)).then(s => {
    if (!s) return;
    S.texts.mine = { id: s.id, title: T('practice.fromScript', { title: s.title }), short: s.title, text: s.body, topic: s.category || null };
    if (S.screen === 'practice') { if (byUser) S.choosing = true; renderPractice(); }
  }).catch(() => {});
}
export function loadSavedScripts(pickId) {
  if (!S.user) return;
  api('/api/scripts?limit=' + CONFIG.HISTORY_PAGE_SIZE).then(r => r.ok ? r.json() : null).then(d => {
    const list = (d && d.items) || [], wrap = $('#mineSaved'), sel = $('#mineSel');
    S.savedScripts = list;
    if (!wrap || !sel) return;
    wrap.hidden = !list.length;
    if (!list.length) return;
    const curId = pickId || (S.texts.mine && S.texts.mine.id) || sel.value || list[0].id;
    sel.innerHTML = list.map(s => '<option value="' + esc(s.id) + '">' + esc(s.title + ' (' + s.word_count + 'w)') + '</option>').join('');
    const chosen = list.find(s => s.id === curId) || list[0];
    sel.value = chosen.id;
    if (pickId || !S.texts.mine) pickSavedScript(chosen.id);
  }).catch(() => {});
}
export function renderPractice() {
  const txt = S.texts[S.pickerTab];
  ['mine', 'sample', 'own'].forEach(k => {
    const tab = $('[data-src=' + k + ']'); tab.setAttribute('aria-selected', String(k === S.pickerTab));
    $('#picker' + k.charAt(0).toUpperCase() + k.slice(1) + 'Pane').hidden = k !== S.pickerTab;
  });
  const au = S.audio;
  // stepper: a real sequence. 1 = choose text (until "Use this script"), 2 = record, 3 = review. Finished steps can be clicked to go back.
  const cur = S.choosing || !txt ? 1 : !au ? 2 : 3, reach = [true, !!txt, !!au];
  $('#pStep1').hidden = cur !== 1; $('#pStep2').hidden = cur === 1; $('#pStep1Go').hidden = cur !== 1;
  $('#useScript').disabled = !txt; $('#useHint').textContent = txt ? '' : T('practice.hintNoText');
  const sh = $('#sheet');
  if (txt) {
    sh.className = 'reader reader-wide'; sh.innerHTML = sentHtml(txt.text);
    $('#sheetTitle').textContent = txt.title;
    const n = wordsOf(txt.text);
    $('#sheetMeta').textContent = T('practice.words', { n, t: fmtTime(n / CONFIG.SPEAKING_WPM_FOR_ESTIMATE * 60) });
  } else {
    sh.className = 'reader reader-wide empty'; sh.textContent = T(S.pickerTab === 'mine' ? 'practice.emptyMineT' : S.pickerTab === 'sample' ? 'practice.emptySampleT' : 'practice.emptyOwnT');
    $('#sheetTitle').textContent = ''; $('#sheetMeta').textContent = '';
  }
  $('#sampleBtn').textContent = T(S.texts.sample ? 'practice.sampleAnother' : 'practice.sampleBtn');
  updateOwnCount();
  $$('[data-src]').forEach(b => { b.disabled = !!S.rec; });        // the text must not change while recording
  $('#sampleBtn').disabled = !!S.rec; $('#ownUse').disabled = !!S.rec;
  if (S.rec && S.follow) paintFollow();
  // voice tabs
  const rec = S.voiceTab === 'rec';
  $('#voiceRecordTab').setAttribute('aria-selected', String(rec)); $('#voiceUploadTab').setAttribute('aria-selected', String(!rec));
  $('#voiceRecordPane').hidden = !rec; $('#voiceUploadPane').hidden = rec;
  $('#recNote').hidden = !rec; $('#prSpeed').hidden = !rec;   // follow-along only exists while recording
  $('#pStep2').classList.toggle('is-upload', !rec);
  // recorder
  $('#recBtn').innerHTML = S.rec ? '<span class="rec-dot" aria-hidden="true"></span>' + esc(T('practice.stop')) : esc(T('practice.start'));
  $('#recBtn').disabled = !S.rec && !!au;
  $('#recClear').disabled = !au || !!S.rec;
  if (!S.rec) $('#recTimer').textContent = au && au.kind === 'rec' ? fmtClock(au.dur) : '00:00';
  $('#recNote').textContent = S.rec ? T('practice.recordingFollow') : au && au.kind === 'rec' ? T('practice.recFinished') : T('practice.recNote');
  $('#dropText').textContent = au && au.kind === 'file' ? au.name : T('practice.dropText');
  $('#audioState').textContent = S.rec ? T('practice.recInProgress') : !au ? T('practice.noAudio') : au.kind === 'rec' ? T('practice.audioReady', { time: fmtTime(au.dur) }) : T('practice.fileReady', { name: au.name });
  const ready = !!txt && !!au && !S.rec;
  $('#evalBtn').disabled = !ready;
  $('#evalHint').textContent = ready ? '' : (!txt ? T('practice.hintNoText') : T('practice.hintNoAudio'));
  [1, 2, 3].forEach(i => {
    const li = $('#st' + i);
    li.className = i < cur ? 'done' : i === cur ? 'cur' : '';
    if (i === cur) li.setAttribute('aria-current', 'step'); else li.removeAttribute('aria-current');
    $('button', li).disabled = !!S.rec || !reach[i - 1] || i === cur;
  });
}
RENDER.practice = function () { loadSavedScripts(); paintFollowWpm(); renderPractice(); };
export function updateOwnCount() {
  const n = $('#ownText').value.length;
  $('#ownCnt').textContent = T('practice.ownCounter', { n, max: CONFIG.OWN_MAX_CHARS });
}
export function useOwn() {
  const v = $('#ownText').value.trim(), err = $('#ownErr');
  if (!v) { showErr(err, T('practice.errOwnEmpty')); $('#ownText').setAttribute('aria-invalid', 'true'); return; }
  if (v.length > CONFIG.OWN_MAX_CHARS) { showErr(err, T('practice.errOwnMax', { max: CONFIG.OWN_MAX_CHARS })); $('#ownText').setAttribute('aria-invalid', 'true'); return; }
  clearErr(err); $('#ownText').removeAttribute('aria-invalid');
  const applyOwn = () => {
    S.choosing = true;
    S.texts.own = { title: T('practice.ownTitle'), short: T('practice.ownTitle'), text: v, topic: null };
    renderPractice();
  };
  saveScript({ title: T('practice.ownTitle'), text: v, source: 'written' }).then(j => {
    applyOwn(); S.texts.own.id = j.id; loadSavedScripts();
  }).catch(e => {
    if (e && e.code === 'content_rejected') { openModal('safetyAlert'); return; }
    if (e && e.code) { showErr(err, e.msg || T('eval.errServer')); return; }
    applyOwn();   // network error: practise without saving
  });
}
/* ---- follow-along (SIM): the highlight moves by TIME, at S.followWpm (slider, default 145; separate from CONFIG.SPEAKING_WPM_FOR_ESTIMATE).
   Following the real voice later needs streaming STT or a local VAD: that is a new ADR ([CAN CHOT]), not part of this demo. ---- */
export function sentHtml(text) {
  return tokenize(text).sentences.map((s, i) => '<span class="sent" data-si="' + i + '">' + esc(s) + '</span>').join(' ');
}
export function followCounts(text) {
  const { sentences, words } = tokenize(text);
  return sentences.map((_, si) => words.filter(w => w.si === si).length);
}
export function buildFollow(counts) {
  return EvaluateClient.followSchedule({ wordCounts: counts, wpm: S.followWpm, leadS: CONFIG.FOLLOW_LEAD_S, gapS: CONFIG.FOLLOW_GAP_S });
}
/* Highlight speed slider. It only moves the demo highlight: nothing here is sent to /api/* or used by score() (ADR-003 scores 130-160 WPM, unrelated). */
export const FOLLOW_WPM_KEY = 'psc.followWpm';
export function loadFollowWpm() {
  try { S.followWpm = EvaluateClient.parseFollowWpm(localStorage.getItem(FOLLOW_WPM_KEY)); } catch (e) { S.followWpm = EvaluateClient.FOLLOW_WPM.def; }
}
export function paintFollowWpm() {
  const sl = $('#followWpm'); if (!sl) return;
  sl.value = String(S.followWpm);
  sl.setAttribute('aria-valuetext', T('practice.followWpmVal', { n: S.followWpm }));
  $('#followWpmVal').textContent = T('practice.followWpmShort', { n: S.followWpm });
}
export function onFollowWpm() {
  S.followWpm = EvaluateClient.parseFollowWpm(Number($('#followWpm').value));
  try { localStorage.setItem(FOLLOW_WPM_KEY, String(S.followWpm)); } catch (e) { /* private mode: lasts until reload */ }
  paintFollowWpm();
  const f = S.follow;
  if (S.rec && f) {   // keep the current sentence and the part already read; only the rest speeds up or slows down
    f.segs = EvaluateClient.followRetime(f.segs, f.idx, f.now || 0, { wordCounts: f.counts, wpm: S.followWpm, leadS: CONFIG.FOLLOW_LEAD_S, gapS: CONFIG.FOLLOW_GAP_S });
  }
}
export function followTick(s) {
  const f = S.follow; if (!f) return;
  f.now = s;
  let idx = -1;
  f.segs.forEach((g, i) => { if (s >= g.start) idx = i; });
  if (idx !== f.idx) { f.idx = idx; paintFollow(); }
}
export function paintFollow() {
  const f = S.follow, sh = $('#sheet');
  if (!f || !sh) return;
  sh.classList.add('following');
  $$('.sent', sh).forEach((el, i) => { el.classList.toggle('done', i < f.idx); el.classList.toggle('cur', i === f.idx); });
  const cur = $('.sent.cur', sh);
  if (cur && sh.scrollTo) {
    const calm = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    sh.scrollTo({ top: Math.max(0, cur.offsetTop - (sh.clientHeight - cur.offsetHeight) / 2), behavior: calm ? 'auto' : 'smooth' });
  }
}
export function toggleRecording() {
  if (S.rec) { S.rec.stop(false); return; }
  requireConsent(() => {
    const txt = S.texts[S.pickerTab];
    S.audio = null; S.choosing = false;
    const counts = txt ? followCounts(txt.text) : null;
    S.follow = txt ? { counts, segs: buildFollow(counts), idx: -2, now: 0 } : null;
    S.rec = startRecorder({
      lvl: $('#recLvl'), onTick: s => { $('#recTimer').textContent = fmtClock(s); followTick(s); },
      onEnd: (sec, auto, rec) => {
        S.rec = null; S.follow = null;
        if (rec && rec.blob) S.audio = { kind: 'rec', dur: sec, blob: rec.blob, mime: rec.mime };
        renderPractice();
      },
      onError: code => {
        S.rec = null; S.follow = null; S.voiceTab = 'up'; renderPractice();
        showErr($('#upErr'), T('practice.mic' + code.charAt(0).toUpperCase() + code.slice(1)));
      }
    });
    renderPractice();
    $('#sheet').scrollTop = 0;
  });
}
export function onAudioFile(e) {
  const f = e.target.files && e.target.files[0], err = $('#upErr');
  e.target.value = '';
  if (!f) return;
  if (!(f.type || '').startsWith('audio/') && !/\.(mp3|wav|webm|m4a)$/i.test(f.name)) { showErr(err, T('practice.errAudio')); return; }
  clearErr(err); S.audio = { kind: 'file', name: f.name, dur: null, file: f, mime: f.type || '' }; S.choosing = false; renderPractice();
}

export function runEval() {
  const txt = S.texts[S.pickerTab];
  if (!txt || !S.audio) return;
  runEvalReal(txt);
}
export function cancelEval() {
  if (S.evaluation && S.evaluation.ctrl) S.evaluation.ctrl.abort();   // user cancel: S.evaluation is cleared below, so the fetch catch stays silent
  if (S.evaluation) { S.evaluation.timers.forEach(clearTimeout); S.evaluation = null; }
  closeModal('evaluatingOverlay');
}

/* ---- real evaluation: POST /api/evaluate. S.audio is kept until a scored result is saved, so Retry re-sends the same audio. ---- */
export const EXT_BY_MIME = { 'audio/webm': '.webm', 'audio/ogg': '.ogg', 'audio/mp4': '.m4a' };
export const EVAL_ERR = { too_long: 'errTooLong', too_large: 'errTooLarge', stt_unavailable: 'errStt', no_audio_stream: 'errNoStream', unsupported_format: 'errFormat', corrupt: 'errCorrupt', invalid_baseline: 'errBaseline',
  baseline_required: 'errBaselineRequired', baseline_unavailable: 'errBaselineUnavailable', baseline_not_saved: 'errBaselineNotSaved',
  script_not_found: 'errScriptNotFound', invalid_script_id: 'errScriptNotFound', script_storage_unavailable: 'errScriptStorage', script_empty: 'errScriptEmpty', script_too_long: 'errScriptTooLong' };
export function showEvalError(msg) { $('#meMsg').textContent = msg; openModal('errorDialog', { focus: '#meRetry' }); }
export function runEvalReal(txt) {
  const au = S.audio, blob = au.blob || au.file;
  if (!blob) return;
  const fname = au.kind === 'file' ? au.name : 'recording' + (EXT_BY_MIME[(au.mime || '').split(';')[0]] || '.webm');
  const fd = new FormData();
  fd.append('audio', blob, fname); fd.append('script', txt.text);   // the server reads the baseline itself
  if (txt.id) fd.append('script_id', txt.id);
  if (txt.short) fd.append('topic', txt.short);
  const ctrl = new AbortController(), ev = S.evaluation = { timers: [], ctrl, timedOut: false };
  ev.timers.push(setTimeout(() => { ev.timedOut = true; ctrl.abort(); }, 120000));
  $('#ovStep').textContent = T('eval.step1'); $('#ovText').textContent = T('eval.step1Text');
  openModal('evaluatingOverlay', { lock: true, focus: '#ovCancel' });
  const end = () => { ev.timers.forEach(clearTimeout); S.evaluation = null; closeModal('evaluatingOverlay', false); };
  api('/api/evaluate', { method: 'POST', body: fd, signal: ctrl.signal }).then(res => res.json().catch(() => null).then(j => {
    if (S.evaluation !== ev) return;                       // cancelled by the user meanwhile
    end();
    if (res.ok && j && j.status) { finishEvalReal(j, txt); return; }
    if (res.status === 401) return;                // logged out by sessionEnded()
    if (j && j.error_code === 'baseline_required') { S.baseline = null; toast(T('eval.errBaselineRequired'), true); openBaselineGate(); return; }
    if (j && j.error_code) { showEvalError(EVAL_ERR[j.error_code] ? T('eval.' + EVAL_ERR[j.error_code]) : (j.message || T('eval.errServer'))); return; }
    showEvalError(T('eval.errServer'));
  })).catch(() => {
    if (S.evaluation !== ev) return;                       // user cancel -> no error
    end(); showEvalError(T(ev.timedOut ? 'eval.errTimeout' : 'eval.errNet'));
  });
}
export function finishEvalReal(j, txt) {
  const m = EvaluateClient.mapResult(j, txt.text), base = { ts: Date.now(), title: txt.short, topicKey: txt.topic, an: m.an, sc: m.sc, dur: m.an.dur, accent: S.profile ? S.profile.accent : null, demo: false, raw: j };
  if (m.sc.status !== 'ok') { S.audio = null; S.currentSession = Object.assign({ id: 'local-' + S.nextId++ }, base); go('report'); return; }   // insufficient_audio: shown, not in History
  const ses = Object.assign({ id: j.saved && j.session_id ? j.session_id : 'local-' + S.nextId++, audioUrl: URL.createObjectURL(S.audio.blob || S.audio.file), fresh: true, remote: !!j.saved }, base);
  S.audio = null; S.currentSession = ses;
  if (j.saved) S.sessions.push(ses);   // D-06: only saved sessions are in History (they come back after F5)
  go('report');
  toast(T(j.saved ? 'eval.saved' : 'eval.notSaved'), !j.saved);
}
