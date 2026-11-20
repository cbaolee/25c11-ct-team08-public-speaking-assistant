import { api } from '../api.js';
import { SAMPLE_TEXTS, sh, tokenize } from '../data.js';
import { T } from '../i18n.js';
import { openBaselineGate } from '../modals/baseline_gate.js';
import { openConfirmDialog } from '../modals/confirm.js';
import { go } from '../nav.js';
import { requireConsent, startRecorder } from '../recorder.js';
import { saveScript } from '../screens/script_studio.js';
import { CONFIG, RENDER, S } from '../state.js';
import { closeModal, openModal, toast, withBusy } from '../ui.js';
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
  const req = api('/api/scripts/' + encodeURIComponent(id));
  return (byUser ? withBusy(req, T('busy.loading')) : req).then(r => (r.ok ? r.json() : null)).then(s => {
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
  // from step 2: script on the left (the page scrolls it), Voice Input + speed pinned on the right
  $('#practiceWork').classList.toggle('split', cur !== 1);
  $('#useScript').disabled = !txt; $('#useHint').textContent = txt ? '' : T('practice.hintNoText');
  const sh = $('#sheet');
  if (txt) {
    sh.className = 'reader reader-wide'; sh.innerHTML = sentHtml(txt.text);
    if (!S.rec) sh.style.paddingBottom = '';   // the room added for following along goes when recording stops
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
  $('#prSpeed').hidden = !rec;   // follow-along only exists while recording
  $('#pStep2').classList.toggle('is-upload', !rec);
  // recorder
  $('#recBtn').innerHTML = S.rec ? '<span class="rec-dot" aria-hidden="true"></span>' + esc(T('practice.stop')) : esc(T('practice.start'));
  $('#recBtn').disabled = !S.rec && !!au;
  $('#recClear').disabled = !au || !!S.rec;
  if (!S.rec) $('#recTimer').textContent = au && au.kind === 'rec' ? fmtClock(au.dur) : '00:00';
  $('#dropText').textContent = au && au.kind === 'file' ? au.name : T('practice.dropText');
  const ready = !!txt && !!au && !S.rec;
  $('#evalBtn').disabled = !ready;
  // one status line under the recorder (both tabs): what is happening, or what is still missing
  $('#recNote').textContent = S.rec ? T('practice.recordingFollow')
    : !txt ? T('practice.hintNoText')
    : !au ? T('practice.noAudio') + ' ' + T('practice.hintNoAudio')
    : au.kind === 'rec' ? T('practice.audioReady', { time: fmtTime(au.dur) })
    : T('practice.fileReady', { name: au.name });
  [1, 2, 3].forEach(i => {
    const li = $('#st' + i);
    li.className = i < cur ? 'done' : i === cur ? 'cur' : '';
    if (i === cur) li.setAttribute('aria-current', 'step'); else li.removeAttribute('aria-current');
    $('button', li).disabled = !!S.rec || !reach[i - 1] || i === cur;
  });
  const changed = shownStep !== null && shownStep !== cur;
  moveStepPill(changed);
  if (changed) animateStepContent(cur > shownStep ? 1 : -1);
  shownStep = cur;
}
/* Stepper: one blue pill glides to the current step (like the main nav). The step contents
   slide in from the side of travel, the same motion as a page change. */
let shownStep = null;
export function moveStepPill(animate) {
  const ol = $('#steps'), li = $('#steps li.cur');
  if (!ol || !li || !li.offsetWidth) return;
  const still = !animate || !ol.classList.contains('pill-on');
  ol.classList.toggle('pill-still', still);
  ol.style.setProperty('--pill-x', li.offsetLeft + 'px'); ol.style.setProperty('--pill-y', li.offsetTop + 'px');
  ol.style.setProperty('--pill-w', li.offsetWidth + 'px'); ol.style.setProperty('--pill-h', li.offsetHeight + 'px');
  ol.classList.add('pill-on');
  if (still) { getComputedStyle(ol, '::before').transform; ol.classList.remove('pill-still'); }
}
function animateStepContent(dir) {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  $$('#practicePanel > :not([hidden])').forEach(el => {
    if (!el.animate) return;
    el.animate([{ opacity: 0, transform: 'translateX(' + (40 * dir) + 'px)', filter: 'blur(6px)' }, { opacity: 1, transform: 'none', filter: 'none' }],
      { duration: 450, easing: 'cubic-bezier(.2, .7, .3, 1)' });
  });
}
window.addEventListener('resize', () => moveStepPill(false));
RENDER.practice = function () { loadSavedScripts(); paintFollowWpm(); renderPractice(); };
export function updateOwnCount() {
  const n = wordsOf($('#ownText').value);
  $('#ownCnt').textContent = T('practice.ownCounter', { n, max: CONFIG.OWN_MAX_WORDS });
}
export function useOwn() {
  const v = $('#ownText').value.trim(), err = $('#ownErr');
  if (!v) { showErr(err, T('practice.errOwnEmpty')); $('#ownText').setAttribute('aria-invalid', 'true'); return; }
  if (wordsOf(v) > CONFIG.OWN_MAX_WORDS) { showErr(err, T('practice.errOwnMax', { max: CONFIG.OWN_MAX_WORDS })); $('#ownText').setAttribute('aria-invalid', 'true'); return; }
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
/* The reading text: one span per sentence (the follow-along highlight moves over them, in order), grouped
   into the text's own paragraphs (split at blank lines, like the Script reader). tokenize() cuts the
   text into consecutive pieces, so each sentence's start in the text tells which paragraph it is in.
   If the counts ever disagree, everything stays in one paragraph (the highlight still works). */
const SENT_PIECE = /[^.!?]+[.!?]*["')]*\s*/g;
export function sentHtml(text) {
  const sentences = tokenize(text).sentences;
  const breaks = Array.from(text.matchAll(/\n\s*\n/g), m => m.index);
  const starts = [];
  for (const m of text.matchAll(SENT_PIECE)) if (m[0].trim()) starts.push(m.index + m[0].length - m[0].trimStart().length);
  const sameCount = starts.length === sentences.length;
  const paras = [];
  sentences.forEach((s, i) => {
    const p = sameCount ? breaks.filter(b => b < starts[i]).length : 0;
    (paras[p] = paras[p] || []).push('<span class="sent" data-si="' + i + '">' + esc(s) + '</span>');
  });
  return paras.filter(Boolean).map(g => '<p class="para">' + g.join(' ') + '</p>').join('');
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
  if (!cur) return;
  const r = cur.getBoundingClientRect();
  if ($('#practiceWork').classList.contains('split')) {
    // the whole page scrolls so the middle of the bold sentence sits in the middle of the visible
    // area (the screen below the header)
    const hh = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--hh')) || 64;
    const mid = hh + (window.innerHeight - hh) / 2;
    const want = window.scrollY + r.top + r.height / 2 - mid;
    // A text that fits the screen stays as it is (no extra room, no scrolling). A longer one gets just
    // enough room under it, added only when needed, for the last sentences to reach the middle too.
    const fits = sh.getBoundingClientRect().height <= window.innerHeight - hh - 32;
    if (!fits) {
      // the page does not always grow by exactly the room added (layout around the text): measure again
      for (let k = 0; k < 3; k++) {
        const short = want - (document.documentElement.scrollHeight - window.innerHeight);
        if (short <= 0.5) break;
        sh.style.paddingBottom = ((parseFloat(sh.style.paddingBottom) || 0) + short) + 'px';
      }
    }
    const max = document.documentElement.scrollHeight - window.innerHeight;
    glideScroll(window, Math.min(max, Math.max(0, want)));
  } else {
    const box = sh.getBoundingClientRect();
    const target = sh.scrollTop + (r.top - box.top) + r.height / 2 - sh.clientHeight / 2;
    glideScroll(sh, Math.min(sh.scrollHeight - sh.clientHeight, Math.max(0, target)));
  }
}
/* Slow, soft scroll for the follow-along: about 1.1 s with a gentle start and finish (the browser's own
   "smooth" is quicker and more abrupt). A new sentence takes over from the running glide without a
   jump. If the reader scrolls by hand (wheel, touch, keys) the glide stops and leaves them in control. */
const GLIDE_MS = 1100;
let glide = null;
function glideScroll(el, to) {
  const isWin = el === window;
  const get = () => (isWin ? window.scrollY : el.scrollTop);
  const set = y => { if (isWin) window.scrollTo(0, y); else el.scrollTop = y; };
  if (glide) { cancelAnimationFrame(glide.raf); glide.stop(); glide = null; }
  const from = get();
  if (Math.abs(to - from) < 2) return;
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) { set(to); return; }
  const t0 = performance.now(), ease = p => 0.5 - Math.cos(Math.PI * p) / 2;   // ease in-out (sine)
  const hand = () => { if (glide) { cancelAnimationFrame(glide.raf); glide.stop(); glide = null; } };
  const evs = ['wheel', 'touchstart', 'keydown'];
  evs.forEach(e => window.addEventListener(e, hand, { passive: true }));
  const g = { raf: 0, stop: () => evs.forEach(e => window.removeEventListener(e, hand)) };
  const step = now => {
    const p = Math.min(1, (now - t0) / GLIDE_MS);
    set(from + (to - from) * ease(p));
    if (p < 1) g.raf = requestAnimationFrame(step); else { g.stop(); if (glide === g) glide = null; }
  };
  glide = g;
  g.raf = requestAnimationFrame(step);
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
  const ev = S.evaluation;
  if (ev) {
    S.evaluation = null;
    ev.timers.forEach(clearTimeout);
    ev.ctrl.abort();
    if (ev.jobId) api('/api/evaluate/' + encodeURIComponent(ev.jobId), { method: 'DELETE', keepalive: true }).catch(() => {});
  }
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
  const ctrl = new AbortController(), ev = S.evaluation = { timers: [], ctrl, jobId: null, shown: 0, sttStarted: null };
  const active = () => S.evaluation === ev;
  const end = () => { ev.timers.forEach(clearTimeout); if (active()) S.evaluation = null; closeModal('evaluatingOverlay', false); };
  const fail = j => {
    end();
    if (j && j.error_code === 'baseline_required') { S.baseline = null; toast(T('eval.errBaselineRequired'), true); openBaselineGate(); return; }
    showEvalError(j && j.error_code && EVAL_ERR[j.error_code] ? T('eval.' + EVAL_ERR[j.error_code]) : ((j && j.message) || T('eval.errServer')));
  };
  const paint = job => {
    const stages = job.stages || [];
    const stt = stages.find(stage => stage.key === 'stt' && stage.state === 'running');
    if (stt && ev.sttStarted === null) ev.sttStarted = Date.now();
    if (!stt) ev.sttStarted = null;
    ev.shown = EvaluateClient.displayProgress(ev.shown, job.progress || 0, stages, CONFIG.EVAL_JOB.weights, ev.sttStarted === null ? 0 : (Date.now() - ev.sttStarted) / 1000, CONFIG.EVAL_JOB.tauS);
    $('#evPercent').textContent = T('eval.percentLabel', { n: ev.shown });
    $('#evBar').setAttribute('aria-valuenow', ev.shown);
    $('#evBar .ev-fill').style.width = ev.shown + '%';
    $$('.ev-step', $('#evaluatingOverlay')).forEach(el => {
      const stage = stages.find(item => item.key === el.dataset.key), state = stage ? stage.state : 'pending';
      el.dataset.state = state;
      $('.ev-icon', el).textContent = state === 'done' ? '✓' : state === 'running' ? '●' : '○';
      $('.ev-status', el).textContent = state === 'skipped' ? T('eval.stepSkipped') : '';
    });
    const bucket = Math.floor(ev.shown / CONFIG.EVAL_JOB.announcePct), stage = job.stage || '';
    if (bucket !== ev.liveBucket || stage !== ev.liveStage) {
      $('#evLive').textContent = [stage ? T('eval.stages.' + stage) : '', T('eval.percentLabel', { n: ev.shown })].filter(Boolean).join(' - ');
      ev.liveBucket = bucket; ev.liveStage = stage;
    }
    $('#ovStep').textContent = stt ? T('eval.estimateNote') : '';
    $('#ovStep').hidden = !stt;
    $('#ovText').textContent = ''; 
  };
  const timeout = () => {
    if (!active()) return;
    if (ev.jobId) api('/api/evaluate/' + encodeURIComponent(ev.jobId), { method: 'DELETE' }).catch(() => {});
    ctrl.abort(); end(); showEvalError(T('eval.errTimeout'));
  };
  ev.timers.push(setTimeout(timeout, CONFIG.EVAL_JOB.maxWaitS * 1000));
  paint({ progress: 0, stages: [] });
  openModal('evaluatingOverlay', { lock: true, focus: '#ovCancel' });
  const poll = () => {
    api('/api/evaluate/' + encodeURIComponent(ev.jobId), { signal: ctrl.signal }).then(res => res.json().catch(() => null).then(job => {
      if (!active()) return;
      if (res.status === 401) { end(); return; }
      if (res.status === 404) { end(); showEvalError(T('eval.errServer')); return; }
      if (!res.ok || !job) { fail(job); return; }
      paint(job);
      if (job.status === 'done') {
        ev.timers.push(setTimeout(() => { if (active()) { end(); finishEvalReal(job.result, txt); } }, matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : CONFIG.EVAL_JOB.closeDelayMs));
      } else if (job.status === 'failed') fail(job);
      else if (job.status === 'cancelled') end();
      else ev.timers.push(setTimeout(poll, CONFIG.EVAL_JOB.pollMs));
    })).catch(() => { if (active()) { end(); showEvalError(T('eval.errNet')); } });
  };
  api('/api/evaluate', { method: 'POST', body: fd, signal: ctrl.signal }).then(res => res.json().catch(() => null).then(job => {
    if (!active()) return;
    if (res.status === 202 && job && job.job_id) { ev.jobId = job.job_id; poll(); return; }
    if (res.status === 401) { end(); return; }
    fail(job);
  })).catch(() => { if (active()) { end(); showEvalError(T('eval.errNet')); } });
}
export function finishEvalReal(j, txt) {
  const m = EvaluateClient.mapResult(j, txt.text), base = { ts: Date.now(), title: txt.short, topicKey: txt.topic, an: m.an, sc: m.sc, dur: m.an.dur, accent: S.profile ? S.profile.accent : null, demo: false, raw: j };
  if (m.sc.status !== 'ok') { S.audio = null; S.currentSession = Object.assign(j.saved && j.session_id ? { id: j.session_id, remote: true } : { id: 'local-' + S.nextId++ }, base); go('report'); return; }   // insufficient_audio: shown, not in History
  const ses = Object.assign({ id: j.saved && j.session_id ? j.session_id : 'local-' + S.nextId++, audioUrl: URL.createObjectURL(S.audio.blob || S.audio.file), fresh: true, remote: !!j.saved }, base);
  S.audio = null; S.currentSession = ses;
  if (j.saved) S.sessions.push(ses);   // D-06: only saved sessions are in History (they come back after F5)
  go('report');
  toast(T(j.saved ? 'eval.saved' : 'eval.notSaved'), !j.saved);
}
