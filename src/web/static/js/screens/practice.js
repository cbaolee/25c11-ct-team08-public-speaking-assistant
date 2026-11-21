import { api } from '../api.js';
import { SAMPLE_TEXTS, sh, tokenize } from '../data.js';
import { T } from '../i18n.js';
import { openBaselineGate } from '../modals/baseline_gate.js';
import { openConfirmDialog } from '../modals/confirm.js';
import { go } from '../nav.js';
import { requireConsent, startRecorder } from '../recorder.js';
import { loadSavedScripts, patchSavedScript, renderSavedLists, saveScriptAs } from '../screens/saved_scripts.js';
import { CONFIG, RENDER, S } from '../state.js';
import { caretToStart, closeModal, editedText, fillParagraphs, guardTitle, openModal, popIn, popOut, setEditable, showSavedTick, toast, withBusy } from '../ui.js';
import { $, $$, clearErr, esc, fmtClock, fmtTime, showErr, wordsOf } from '../utils.js';

/* ---------- Practice ---------- */
const STOP_ICON = '<svg class="rec-ic" viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>';
const PAUSE_ICON = '<svg class="rec-ic" viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>';
const PLAY_ICON = '<svg class="rec-ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>';
/* Pause keeps the recording: time, the level bars' meaning and the follow-along highlight wait for Resume. */
export function togglePause() {
  if (!S.rec) return;
  if (S.rec.paused) S.rec.resume(); else S.rec.pause();
  renderPractice();
  $('#recNote').textContent = T(S.rec && S.rec.paused ? 'practice.pausedNote' : 'practice.recordingFollow');
}
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
/* Saved scripts (Practice > Mine): the list on the left, the picked script's text on the right.
   The list comes from GET /api/scripts (saved_scripts.js); the text from GET /api/scripts/{id}. */
export function pickSavedScript(id, byUser) {   // byUser: clicked in the list (stays on step 1); the automatic first pick must not move the stepper
  const req = api('/api/scripts/' + encodeURIComponent(id));
  return (byUser ? withBusy(req, T('busy.loading')) : req).then(r => (r.ok ? r.json() : null)).then(s => {
    if (!s) return;
    if (mineEditId && mineEditId !== s.id) cancelMineEdit();   // another script picked: the open edit is dropped
    S.texts.mine = { id: s.id, title: s.title, short: s.title, text: s.body, topic: s.category || null, duration_min: s.duration_min || null };
    renderSavedLists();
    if (S.screen === 'practice') { if (byUser) S.choosing = true; renderPractice(); }
  }).catch(() => {});
}
/* "Write my own": the text in the box, as the script to practise. Null (with the error shown) when it cannot be used. */
function ownTextOrError() {
  const v = $('#ownText').value.trim(), err = $('#ownErr');
  if (!v) { showErr(err, T('practice.errOwnEmpty')); $('#ownText').setAttribute('aria-invalid', 'true'); return null; }
  if (wordsOf(v) > CONFIG.OWN_MAX_WORDS) { showErr(err, T('practice.errOwnMax', { max: CONFIG.OWN_MAX_WORDS })); $('#ownText').setAttribute('aria-invalid', 'true'); return null; }
  clearErr(err); $('#ownText').removeAttribute('aria-invalid');
  return v;
}
/* Use this script: Mine and Sample already hold their text; Own takes the box as it is now.
   With an unsaved edit on My script, the last saved version is used (after a notice). */
export function useScript() {
  if (S.pickerTab === 'mine' && mineHasUnsavedEdit()) {
    openConfirmDialog(T('reader.unsavedTitle'), T('reader.unsavedMsg'), T('reader.useLast'), () => { cancelMineEdit(); goStep(2); });
    return;
  }
  if (S.pickerTab === 'mine' && mineEditId) cancelMineEdit();   // nothing changed: leave edit mode quietly
  if (S.pickerTab === 'own') {
    const v = ownTextOrError(); if (!v) return;
    const saved = S.ownSaved && S.ownSaved.text === v ? S.ownSaved : null;   // saved under a name: the session links to it
    const name = saved ? saved.title : T('practice.ownTitle');
    S.texts.own = { id: saved ? saved.id : null, title: name, short: name, text: v, topic: null };
  }
  goStep(2);
}
/* Save script (Own tab): asks for a name, then saves; the text stays in the box. */
export function saveOwn() {
  const v = ownTextOrError(); if (!v) return;
  saveScriptAs({ title: T('practice.ownTitle'), text: v, source: 'written' }).then(j => {
    if (j) S.ownSaved = { id: j.id, title: j.title, text: v };
  });
}
export function renderPractice() {
  const txt = S.texts[S.pickerTab];
  ['mine', 'sample', 'own'].forEach(k => {
    const tab = $('[data-src=' + k + ']'); tab.setAttribute('aria-selected', String(k === S.pickerTab));
    $('#picker' + k.charAt(0).toUpperCase() + k.slice(1) + 'Pane').hidden = k !== S.pickerTab;
  });
  $('#mineCount').hidden = S.pickerTab !== 'mine';
  const au = S.audio;
  // stepper: a real sequence. 1 = choose text (until "Use this script"), 2 = record, 3 = review. Finished steps can be clicked to go back.
  const cur = S.choosing || !txt ? 1 : !au ? 2 : 3, reach = [true, !!txt, !!au];
  $('#pStep1').hidden = cur !== 1; $('#pStep2').hidden = cur === 1; $('#pStep1Go').hidden = cur !== 1;
  // from step 2: script on the left (the page scrolls it), Voice Input + speed pinned on the right
  $('#practiceWork').classList.toggle('split', cur !== 1);
  const own = S.pickerTab === 'own', ready = own ? !!$('#ownText').value.trim() : !!txt;
  $('#useScript').disabled = !ready || !!S.rec;
  // step 1: Mine shows its text beside the list and Own is its own text box, so only Sample uses the big sheet
  $('#practiceWork').hidden = cur === 1 && S.pickerTab !== 'sample';
  if (S.pickerTab === 'mine') paintMinePreview();
  const sh = $('#sheet');
  if (txt) {
    sh.className = 'reader reader-wide'; sh.innerHTML = sentHtml(txt.text);
    if (!S.rec) sh.style.paddingBottom = '';   // the room added for following along goes when recording stops
    $('#sheetTitle').textContent = txt.title;
    const n = wordsOf(txt.text);
    $('#sheetMeta').textContent = T('practice.words', { n, t: fmtTime(n / CONFIG.SPEAKING_WPM_FOR_ESTIMATE * 60) });
  } else {
    sh.className = 'reader reader-wide empty'; sh.textContent = T(S.pickerTab === 'mine' ? 'saved.empty' : S.pickerTab === 'sample' ? 'practice.emptySampleT' : 'practice.emptyOwnT');
    $('#sheetTitle').textContent = ''; $('#sheetMeta').textContent = '';
  }
  $('#sampleBtn').textContent = T(S.texts.sample ? 'practice.sampleAnother' : 'practice.sampleBtn');
  updateOwnCount();
  $$('[data-src]').forEach(b => { b.disabled = !!S.rec; });        // the text must not change while recording
  $('#sampleBtn').disabled = !!S.rec; $('#ownSave').disabled = !!S.rec || !$('#ownText').value.trim();   // like Use this script
  if (S.rec && S.follow) paintFollow();
  // voice tabs
  const rec = S.voiceTab === 'rec';
  $('#voiceRecordTab').setAttribute('aria-selected', String(rec)); $('#voiceUploadTab').setAttribute('aria-selected', String(!rec));
  // Both panes stay in one grid cell (only the other one is made invisible), so switching tabs never changes the panel height.
  setPaneShown($('#voiceRecordPane'), rec); setPaneShown($('#voiceUploadPane'), !rec);
  $('#pStep2').classList.toggle('is-upload', !rec);   // the follow-along slider keeps its room but is invisible
  // recorder
  // While recording: Stop (ends it) and Pause / Resume (the same recording goes on)
  $('#recBtn').innerHTML = S.rec ? STOP_ICON + esc(T('practice.stop')) : esc(T('practice.start'));
  const paused = !!(S.rec && S.rec.paused);
  $('#recPause').hidden = !S.rec;
  $('#recPause').innerHTML = (paused ? PLAY_ICON : PAUSE_ICON) + esc(T(paused ? 'practice.resume' : 'practice.pause'));
  $('#recClear').hidden = !!S.rec;
  $('#recBtn').disabled = !S.rec && !!au;
  $('#recClear').disabled = !au || !!S.rec;
  if (!S.rec) $('#recTimer').textContent = au && au.kind === 'rec' ? fmtClock(au.dur) : '00:00';
  $('#dropText').textContent = au && au.kind === 'file' ? au.name : T('practice.dropText');
  $('#evalBtn').disabled = !(txt && au && !S.rec);
  // one status line under the recorder (both tabs): what is happening, or what is still missing
  $('#recNote').textContent = S.rec ? T(S.rec.paused ? 'practice.pausedNote' : 'practice.recordingFollow')
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
function setPaneShown(pane, shown) {
  pane.hidden = false; pane.classList.toggle('pane-off', !shown);
  pane.setAttribute('aria-hidden', String(!shown)); pane.inert = !shown;
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
let shownMine = null;     // script shown on the right last, so a new pick can animate
/* Mine tab, right side: the picked script (saved, or sent from Script Studio without saving), title on top. */
function paintMinePreview() {
  const mine = S.texts.mine, box = $('#minePreview');
  if (mineEditId) return;                           // the text being edited stays as it is
  const key = mine ? (mine.id || '') + mine.title + mine.text.length : '';
  if (key !== shownMine) { shownMine = key; popIn($('.mine-view')); }
  if (!mine) {
    box.className = 'reader reader-wide empty'; box.textContent = T((S.savedScripts || []).length ? 'saved.pickOne' : 'saved.empty');
    $('#mineTitle').textContent = '';
    return;
  }
  box.className = 'reader reader-wide'; box.innerHTML = sentHtml(mine.text); box.scrollTop = 0;
  $('#mineTitle').textContent = mine.title;
}
/* The fold button tucks the list away so the text gets the whole width. */
export function toggleMineList() {
  const pane = $('#pickerMinePane'), folded = !pane.classList.contains('list-folded'), btn = $('#mineFold');
  pane.classList.toggle('list-folded', folded);
  // unfolding: the cards keep their full width (no squeezed names) and slide in to the right one by one
  if (!folded) $$('#mineList .saved-item').forEach((li, i) => popIn(li, { x: -28, y: 0, duration: 320, delay: 80 + i * 45 }));
  btn.setAttribute('aria-expanded', String(!folded));
  btn.setAttribute('aria-label', T(folded ? 'saved.unfoldList' : 'saved.foldList')); btn.title = btn.getAttribute('aria-label');
}

/* ---- Edit in place (pencil on a saved script): the title and the text keep their look, only a caret appears ---- */
let mineEditId = null;
/* `after` runs once Cancel / Save have faded out (the saved tick appears then). */
function setMineEditing(on, after) {
  const title = $('#mineTitle'), body = $('#minePreview'), tools = $('#mineEditTools');
  setEditable(title, on); setEditable(body, on);
  body.classList.toggle('reader-editing', on);
  clearErr($('#mineEditError'));
  popIn(body, { y: 6, duration: 300 });
  if (on) { tools.hidden = false; popIn(tools, { y: 4, duration: 220 }); } else popOut(tools, after);
}
export function startMineEdit(id) {
  const begin = () => {
    const mine = S.texts.mine;
    if (!mine || mine.id !== id) return;
    mineEditId = id;
    $('#mineTitle').textContent = mine.title;
    fillParagraphs($('#minePreview'), mine.text);
    setMineEditing(true);
    caretToStart($('#minePreview'));
  };
  if (mineEditId) cancelMineEdit();
  if (S.texts.mine && S.texts.mine.id === id) begin(); else pickSavedScript(id, true).then(begin);
}
function mineHasUnsavedEdit() {
  const mine = S.texts.mine;
  if (!mineEditId || !mine) return false;
  return $('#mineTitle').innerText.replace(/\n/g, ' ').trim() !== mine.title || editedText($('#minePreview')) !== mine.text.trim();
}
export function cancelMineEdit() {
  if (!mineEditId) return;
  mineEditId = null; shownMine = null;
  paintMinePreview();
  setMineEditing(false);
}
export function saveMineEdit() {
  const mine = S.texts.mine; if (!mineEditId || !mine) return;
  const title = $('#mineTitle').innerText.replace(/\n/g, ' ').trim(), text = editedText($('#minePreview')), err = $('#mineEditError');
  if (!title) { showErr(err, T('saved.errNameEmpty')); $('#mineTitle').focus(); return; }
  if (!text) { showErr(err, T('saved.errBodyEmpty')); $('#minePreview').focus(); return; }
  const patch = {};
  if (title !== mine.title) patch.title = title;
  if (text !== mine.text.trim()) patch.body = text;
  const id = mineEditId;
  const finish = () => { mineEditId = null; shownMine = mine.id + mine.title + mine.text.length; paintMinePreview(); setMineEditing(false, () => showSavedTick($('#mineSavedTick'))); };
  if (!Object.keys(patch).length) { finish(); return; }
  patchSavedScript(id, patch, err).then(row => { if (row && mineEditId === id) finish(); });
}
export function setupMineTitle() {
  guardTitle($('#mineTitle'), () => CONFIG.SCRIPT_TITLE_MAX_CHARS, () => caretToStart($('#minePreview')));
}
RENDER.practice = function () {
  renderSavedLists(); paintFollowWpm(); renderPractice();
  loadSavedScripts().then(() => { if (S.screen === 'practice' && S.pickerTab === 'mine' && !S.texts.mine) paintMinePreview(); });   // the empty-state text depends on the list
};
export function updateOwnCount() {
  const n = wordsOf($('#ownText').value);
  $('#ownCnt').textContent = T('practice.ownCounter', { n, max: CONFIG.OWN_MAX_WORDS });
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
  return EvaluateClient.followSchedule({ wordCounts: counts, wpm: S.followWpm, limits: followLimits(), leadS: CONFIG.FOLLOW_LEAD_S, gapS: CONFIG.FOLLOW_GAP_S });
}
/* Highlight speed slider. It only moves the demo highlight and is not used by score() (ADR-003 scores 130-160 WPM, unrelated).
   Saved in profiles.preferences.follow_wpm. localStorage keeps a value per user only while it is not on the server yet
   (save failed, or log out / session expiry before the save delay ended); the next log in sends it again. */
export const FOLLOW_WPM_KEY = 'psc.followWpm';    // old key shared by all accounts; read once to move the value to the profile
const followWpmKey = userId => FOLLOW_WPM_KEY + '.' + userId;
let followWpmSaveTimer = null;
/* The user's slider range (Settings > Reading speed), else min_choose/max_choose from app_constants.toml [web].
   The default speed is moved into that range. */
export function followLimits() {
  const r = S.wpmRange || { min: CONFIG.FOLLOW_WPM_MIN_CHOOSE, max: CONFIG.FOLLOW_WPM_MAX_CHOOSE }, step = CONFIG.FOLLOW_WPM_STEP;
  const def = Math.min(r.max, Math.max(r.min, Math.round(CONFIG.FOLLOW_WPM_DEFAULT / step) * step));
  return { min: r.min, max: r.max, step, def };
}
/* A chosen range from the profile, or null when missing or not valid for the allowed range. */
export function readWpmRange(prefs) {
  const lo = prefs && prefs.follow_wpm_min_choose, hi = prefs && prefs.follow_wpm_max_choose, step = CONFIG.FOLLOW_WPM_STEP;
  const ok = v => Number.isInteger(v) && v >= CONFIG.FOLLOW_WPM_MIN && v <= CONFIG.FOLLOW_WPM_MAX && v % step === 0;
  return ok(lo) && ok(hi) && lo < hi ? { min: lo, max: hi } : null;
}
/* Speed moved into the current range (a speed outside a new range goes to its nearest end). */
export function fitFollowWpm(v) {
  const l = followLimits(), n = Number(v);
  return Number.isFinite(n) ? Math.min(l.max, Math.max(l.min, Math.round(n / l.step) * l.step)) : l.def;
}
function readStored(key) {                        // null when missing or storage is blocked
  try { return localStorage.getItem(key); } catch (e) { return null; }
}
function writeStored(key, value) {
  try { if (value == null) localStorage.removeItem(key); else localStorage.setItem(key, value); } catch (e) { /* storage blocked */ }
}
/* Before log in: the default speed. */
export function loadFollowWpm() {
  S.followWpm = EvaluateClient.parseFollowWpm(null, followLimits());
}
/* After log in. Order: a value not saved yet on this device, then the profile, then the old shared key, then the default. */
export function applyFollowWpm(prefs) {
  S.wpmRange = readWpmRange(prefs);
  S.autoSpeed = !!(prefs && prefs.follow_auto_speed === true);
  const userId = S.user && S.user.id, limits = followLimits();
  const pending = userId ? readStored(followWpmKey(userId)) : null;
  const saved = prefs ? prefs.follow_wpm : null;
  const legacy = readStored(FOLLOW_WPM_KEY);
  writeStored(FOLLOW_WPM_KEY, null);              // the old key is never read twice, so another account cannot take it
  if (pending != null) { S.followWpm = fitFollowWpm(pending); saveFollowWpm(); }
  else if (saved != null) S.followWpm = fitFollowWpm(saved);
  else if (legacy != null) { S.followWpm = fitFollowWpm(legacy); saveFollowWpm(); }
  else S.followWpm = limits.def;
}
/* On log out and session expiry: a save still waiting is kept on this device for the next log in of the same user. */
export function clearFollowWpm(userId) {
  if (followWpmSaveTimer !== null && userId) writeStored(followWpmKey(userId), String(S.followWpm));
  clearTimeout(followWpmSaveTimer); followWpmSaveTimer = null;
}
export function dropFollowWpm(userId) {           // Delete account: nothing of that user stays on this device
  clearTimeout(followWpmSaveTimer); followWpmSaveTimer = null;
  if (userId) writeStored(followWpmKey(userId), null);
}
function saveFollowWpm() {
  followWpmSaveTimer = null;
  const userId = S.user && S.user.id, value = S.followWpm;
  if (!userId) return;
  api('/api/profile', { method: 'PATCH', json: { preferences: { follow_wpm: value } } })
    .then(r => {
      if (!r.ok) throw new Error('follow_wpm not saved');
      writeStored(followWpmKey(userId), null);
    })
    .catch(() => writeStored(followWpmKey(userId), String(value)));   // API down: send again at the next log in
}
export function paintFollowWpm() {
  const sl = $('#followWpm'); if (!sl) return;
  const l = followLimits();
  sl.min = String(l.min); sl.max = String(l.max); sl.step = String(l.step);
  sl.value = String(S.followWpm);
  sl.setAttribute('aria-valuetext', T('practice.followWpmVal', { n: S.followWpm }));
  $('#followWpmVal').textContent = T('practice.followWpmShort', { n: S.followWpm });
}
export function onFollowWpm() {
  S.followWpm = EvaluateClient.parseFollowWpm(Number($('#followWpm').value), followLimits());
  paintFollowWpm();                               // the screen updates at once; the save waits for the last move
  clearTimeout(followWpmSaveTimer);
  followWpmSaveTimer = setTimeout(saveFollowWpm, CONFIG.FOLLOW_WPM_SAVE_DELAY_MS);
  const f = S.follow;
  if (S.rec && f) {   // keep the current sentence and the part already read; only the rest speeds up or slows down
    f.segs = EvaluateClient.followRetime(f.segs, f.idx, f.now || 0, { wordCounts: f.counts, wpm: S.followWpm, limits: followLimits(), leadS: CONFIG.FOLLOW_LEAD_S, gapS: CONFIG.FOLLOW_GAP_S });
  }
}
/* Auto speed: the slider thumb slides from `from` to `to` instead of jumping. Only the look moves:
   S.followWpm and the number already hold the new value. A drag by the user stops the slide. */
const SLIDER_GLIDE_MS = 450;   // auto speed: how long the thumb slides
function glideSlider(sl, from, to) {
  if (!sl || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  cancelAnimationFrame(sl._glide);
  const step = sl.step, t0 = performance.now();
  const stop = () => { cancelAnimationFrame(sl._glide); sl._glide = null; sl.step = step; sl.value = String(S.followWpm); sl.removeEventListener('pointerdown', stop); };
  sl.addEventListener('pointerdown', stop, { once: true });
  sl.step = 'any';                                   // in-between positions, not only multiples of the step
  const frame = now => {
    const p = Math.min(1, (now - t0) / SLIDER_GLIDE_MS), ease = 1 - Math.pow(1 - p, 3);   // ease-out
    sl.value = String(from + (to - from) * ease);
    if (p < 1) sl._glide = requestAnimationFrame(frame); else stop();
  };
  sl.value = String(from);
  sl._glide = requestAnimationFrame(frame);
}
/* While recording: a click on a sentence moves the bold highlight there; it starts again from the
   beginning of that sentence, at the current speed. */
export function onSheetClick(e) {
  const f = S.follow, el = e.target.closest('#sheet .sent');
  if (!S.rec || !f || !el) return;
  const k = Number(el.getAttribute('data-si'));
  if (!Number.isInteger(k) || k < 0 || k >= f.counts.length) return;
  const now = f.now || 0;
  // Auto speed: the gap since the last tap tells how fast the user reads; the slider moves part of the way there
  // No tap yet: the recording start is the first mark (sentence 0, after the lead-in), so the first tap already measures
  if (S.autoSpeed && !f.tap) f.tap = { k: 0, t: CONFIG.FOLLOW_LEAD_S || 0 };
  if (S.autoSpeed && f.tap) {
    const l = followLimits();
    const measured = EvaluateClient.followMeasureWpm(f.counts, f.tap.k, f.tap.t, k, now, { gapS: CONFIG.FOLLOW_GAP_S, minS: CONFIG.FOLLOW_AUTO_MIN_S,
      minWords: CONFIG.FOLLOW_AUTO_MIN_WORDS, maxAhead: CONFIG.FOLLOW_AUTO_MAX_AHEAD, lo: CONFIG.FOLLOW_WPM_MIN, hi: CONFIG.FOLLOW_WPM_MAX });
    if (measured != null) {
      const next = EvaluateClient.followBlendWpm(S.followWpm, measured, CONFIG.FOLLOW_AUTO_WEIGHT, l);
      if (next !== S.followWpm) {
        const from = S.followWpm;
        $('#followWpm').value = String(next); onFollowWpm();   // same path as a slider move (saved too); the number changes at once
        glideSlider($('#followWpm'), from, next);              // only the thumb slides there
      }
    }
  }
  // The mark moves on, except when the same sentence is tapped again: a slow reader taps the sentence they are
  // still reading when the highlight has run ahead; keeping the first mark lets the next tap measure the slow pace.
  if (!f.tap || k !== f.tap.k) f.tap = { k, t: now };
  f.segs = EvaluateClient.followJump(f.segs, k, f.now || 0, { wordCounts: f.counts, wpm: S.followWpm, limits: followLimits(), leadS: CONFIG.FOLLOW_LEAD_S, gapS: CONFIG.FOLLOW_GAP_S });
  f.idx = -2;
  followTick(f.now || 0);
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
    stopEvalTimers(ev);
    ev.ctrl.abort();
    if (ev.jobId) api('/api/evaluate/' + encodeURIComponent(ev.jobId), { method: 'DELETE', keepalive: true }).catch(() => {});
  }
  closeModal('evaluatingOverlay');
  hideEvalDock(true);
}
/* Drops a running evaluation without a request (log out): the server job ends on its own. */
export function dropEval() {
  if (S.evaluation) { stopEvalTimers(S.evaluation); S.evaluation.ctrl.abort(); S.evaluation = null; }
  hideEvalDock(true);
}
function stopEvalTimers(ev) {
  ev.timers.forEach(clearTimeout);
  clearInterval(ev.counter);
}

/* ---- progress dock: the small top-right card that shows a background evaluation ---- */
const EVAL_DOCK_SLIDE_MS = 400;   // matches the .ev-dock transform transition
let dock_hide_timer = 0;          // pending slide-out of the dock
function showEvalDock() {
  const dock = $('#evDock');
  clearTimeout(dock_hide_timer);
  $('#evDockSteps').innerHTML = $('#evaluatingOverlay .ev-steps').innerHTML;   // same step states as the overlay
  setDockOpen(false);
  dock.classList.remove('ev-dock-in', 'ev-dock-out');
  dock.hidden = false;
  void dock.offsetWidth;   // start the slide-in from the off-screen position
  dock.classList.add('ev-dock-in');
}
/* now: remove at once (cancel, error, log out); otherwise slide out to the right first, then remove. */
function hideEvalDock(now) {
  const dock = $('#evDock');
  clearTimeout(dock_hide_timer);
  if (dock.hidden) return;
  const remove = () => { dock.hidden = true; dock.classList.remove('ev-dock-in', 'ev-dock-out'); setDockOpen(false); };
  if (now || matchMedia('(prefers-reduced-motion: reduce)').matches) { remove(); return; }
  dock.classList.add('ev-dock-out');
  dock_hide_timer = setTimeout(remove, EVAL_DOCK_SLIDE_MS);
}
function setDockOpen(open) {
  $('#evDock').classList.toggle('open', open);
  $('#evDockHead').setAttribute('aria-expanded', open ? 'true' : 'false');
  $('#evDockBody').hidden = !open;
}
export function toggleEvalDock() { setDockOpen(!$('#evDock').classList.contains('open')); }

/* ---- real evaluation: POST /api/evaluate. S.audio is kept until a scored result is saved, so Retry re-sends the same audio. ---- */
export const EXT_BY_MIME = { 'audio/webm': '.webm', 'audio/ogg': '.ogg', 'audio/mp4': '.m4a' };
export const EVAL_ERR = { too_long: 'errTooLong', too_large: 'errTooLarge', stt_unavailable: 'errStt', no_audio_stream: 'errNoStream', unsupported_format: 'errFormat', corrupt: 'errCorrupt', invalid_baseline: 'errBaseline',
  baseline_required: 'errBaselineRequired', baseline_unavailable: 'errBaselineUnavailable', baseline_not_saved: 'errBaselineNotSaved',
  script_not_found: 'errScriptNotFound', invalid_script_id: 'errScriptNotFound', script_storage_unavailable: 'errScriptStorage', script_empty: 'errScriptEmpty', script_too_long: 'errScriptTooLong' };
export function showEvalError(msg) { $('#meMsg').textContent = msg; openModal('errorDialog', { focus: '#meRetry' }); }
/* The percent counts up one step at a time toward the real progress (ev.target) and the bars follow the
   shown number, so a jump from 3% to 15% plays as 3, 4, 5 ... 15. After EVALUATE_BACKGROUND_AFTER_MS the
   overlay gives way to the dock and the user is sent Home; Practice and recording wait for the report. */
export function runEvalReal(txt) {
  const au = S.audio, blob = au.blob || au.file;
  if (!blob) return;
  const fname = au.kind === 'file' ? au.name : 'recording' + (EXT_BY_MIME[(au.mime || '').split(';')[0]] || '.webm');
  const fd = new FormData();
  fd.append('audio', blob, fname); fd.append('script', txt.text);   // the server reads the baseline itself
  if (txt.id) fd.append('script_id', txt.id);
  if (txt.short) fd.append('topic', txt.short);
  const ctrl = new AbortController(), ev = S.evaluation = { timers: [], counter: 0, ctrl, jobId: null, shown: 0, target: 0, stage: '', sttStarted: null, background: false, result: null };
  const active = () => S.evaluation === ev;
  const end = () => { stopEvalTimers(ev); if (active()) S.evaluation = null; closeModal('evaluatingOverlay', false); };
  const fail = j => {
    end(); hideEvalDock(true);
    if (j && j.error_code === 'baseline_required') { S.baseline = null; toast(T('eval.errBaselineRequired'), true); openBaselineGate(); return; }
    showEvalError(j && j.error_code && EVAL_ERR[j.error_code] ? T('eval.' + EVAL_ERR[j.error_code]) : ((j && j.message) || T('eval.errServer')));
  };
  const paintPercent = () => {
    const label = T('eval.percentLabel', { n: ev.shown });
    $('#evPercent').textContent = label;
    $('#evDockPercent').textContent = ev.shown + '%';
    $$('#evBar, #evDockBar').forEach(bar => { bar.setAttribute('aria-valuenow', ev.shown); $('.ev-fill', bar).style.width = ev.shown + '%'; });
    const bucket = Math.floor(ev.shown / CONFIG.EVAL_JOB.announcePct);
    if (bucket !== ev.liveBucket || ev.stage !== ev.liveStage) {
      $('#evLive').textContent = [ev.stage ? T('eval.stages.' + ev.stage) : '', label].filter(Boolean).join(' - ');
      ev.liveBucket = bucket; ev.liveStage = ev.stage;
    }
  };
  const paint = job => {
    const stages = job.stages || [];
    const stt = stages.find(stage => stage.key === 'stt' && stage.state === 'running');
    if (stt && ev.sttStarted === null) ev.sttStarted = Date.now();
    if (!stt) ev.sttStarted = null;
    ev.target = EvaluateClient.displayProgress(ev.target, job.progress || 0, stages, CONFIG.EVAL_JOB.weights, ev.sttStarted === null ? 0 : (Date.now() - ev.sttStarted) / 1000, CONFIG.EVAL_JOB.tauS);
    ev.stage = job.stage || '';
    $$('.ev-step').forEach(el => {   // the overlay list and the dock list
      const stage = stages.find(item => item.key === el.dataset.key), state = stage ? stage.state : 'pending';
      el.dataset.state = state;
      $('.ev-icon', el).textContent = state === 'done' ? '✓' : state === 'running' ? '●' : '○';
      $('.ev-status', el).textContent = state === 'skipped' ? T('eval.stepSkipped') : '';
    });
    $('#ovStep').textContent = stt ? T('eval.estimateNote') : '';
    $('#ovStep').hidden = !stt;
  };
  const complete = () => {
    const result = ev.result, background = ev.background;
    end();
    finishEvalReal(result, txt, background);
    if (background) dock_hide_timer = setTimeout(() => hideEvalDock(false), CONFIG.EVAL_DOCK_HOLD_MS);   // the dock stays at 100% a moment, then slides out
  };
  const tick = () => {
    if (!active()) return;
    if (ev.shown < ev.target) { ev.shown++; paintPercent(); return; }
    if (!ev.result || ev.shown < 100) return;
    clearInterval(ev.counter);
    if (ev.background) { complete(); return; }
    ev.timers.push(setTimeout(() => { if (active()) complete(); }, matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : CONFIG.EVAL_JOB.closeDelayMs));
  };
  const goBackground = () => {
    if (!active() || ev.result) return;   // already finished: the report opens as usual
    ev.background = true;
    closeModal('evaluatingOverlay', false);
    showEvalDock(); paintPercent();
    safeRun(() => go('home'));   // a Home render error must not hide the notice below
    openConfirmDialog(T('eval.bgT'), T('eval.bgD'), T('eval.busyOk'), null, { noCancel: true, primary: true });
  };
  const timeout = () => {
    if (!active()) return;
    if (ev.jobId) api('/api/evaluate/' + encodeURIComponent(ev.jobId), { method: 'DELETE' }).catch(() => {});
    ctrl.abort(); fail({ message: T('eval.errTimeout') });
  };
  ev.timers.push(setTimeout(timeout, CONFIG.EVAL_JOB.maxWaitS * 1000));
  ev.timers.push(setTimeout(goBackground, CONFIG.EVALUATE_BACKGROUND_AFTER_MS));
  ev.counter = setInterval(tick, CONFIG.EVAL_COUNT_STEP_MS);
  paint({ progress: 0, stages: [] }); paintPercent();
  openModal('evaluatingOverlay', { lock: true, focus: '#ovCancel' });
  const poll = () => {
    api('/api/evaluate/' + encodeURIComponent(ev.jobId), { signal: ctrl.signal }).then(res => res.json().catch(() => null).then(job => {
      if (!active()) return;
      if (res.status === 401) { end(); hideEvalDock(true); return; }
      if (res.status === 404) { fail(null); return; }
      if (!res.ok || !job) { fail(job); return; }
      paint(job);
      if (job.status === 'done') { ev.result = job.result; ev.target = 100; }   // tick() finishes once the count reaches 100
      else if (job.status === 'failed') fail(job);
      else if (job.status === 'cancelled') { end(); hideEvalDock(true); }
      else ev.timers.push(setTimeout(poll, CONFIG.EVAL_JOB.pollMs));
    })).catch(() => { if (active()) fail({ message: T('eval.errNet') }); });
  };
  api('/api/evaluate', { method: 'POST', body: fd, signal: ctrl.signal }).then(res => res.json().catch(() => null).then(job => {
    if (!active()) return;
    if (res.status === 202 && job && job.job_id) { ev.jobId = job.job_id; poll(); return; }
    if (res.status === 401) { end(); hideEvalDock(true); return; }
    fail(job);
  })).catch(() => { if (active()) fail({ message: T('eval.errNet') }); });
}
/* background: the user is elsewhere, so the report is offered in a pop-up instead of opened. */
export function finishEvalReal(j, txt, background) {
  const m = EvaluateClient.mapResult(j, txt.text), base = { ts: Date.now(), title: txt.short, topicKey: txt.topic, an: m.an, sc: m.sc, dur: m.an.dur, accent: S.profile ? S.profile.accent : null, demo: false, raw: j };
  let ses;
  if (m.sc.status !== 'ok') ses = Object.assign(j.saved && j.session_id ? { id: j.session_id, remote: true } : { id: 'local-' + S.nextId++ }, base);   // insufficient_audio: shown, not in History
  else {
    ses = Object.assign({ id: j.saved && j.session_id ? j.session_id : 'local-' + S.nextId++, audioUrl: URL.createObjectURL(S.audio.blob || S.audio.file), fresh: true, remote: !!j.saved }, base);
    if (j.saved) S.sessions.push(ses);   // D-06: only saved sessions are in History (they come back after F5)
  }
  S.audio = null;
  const open = () => { S.currentSession = ses; go('report'); };
  const note = () => { if (m.sc.status === 'ok') toast(T(j.saved ? 'eval.saved' : 'eval.notSaved'), !j.saved); };
  if (!background) { open(); note(); return; }
  S.choosing = true;   // Practice opens on step 1 next time
  openConfirmDialog(T('eval.readyT'), T('eval.readyD', { title: txt.short || '' }), T('eval.readyView'), open, { cancelLabel: T('common.close'), primary: true });
  note();
  if (S.screen === 'home') safeRun(RENDER.home);   // the new session shows in History at once
}
/* Runs a screen render and logs its error, so the pop-up that follows or precedes it still works. */
function safeRun(fn) {
  try { fn(); } catch (e) { console.error(e); }
}
/* Practice and every recorder wait while an evaluation runs in the background: say why instead of opening them. */
export function practiceLocked() {
  if (!S.evaluation || !S.evaluation.background) return false;
  openConfirmDialog(T('eval.busyT'), T('eval.busyD'), T('eval.busyOk'), null, { noCancel: true, primary: true });
  return true;
}
