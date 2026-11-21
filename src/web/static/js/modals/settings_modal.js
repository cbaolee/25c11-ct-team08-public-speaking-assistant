import { MIN_PASSWORD, api, deleteAccount, readJson } from '../api.js';
import { T } from '../i18n.js';
import { logout } from './baseline_gate.js';
import { saveConsent } from './profile_modal.js';
import { levelAnim } from '../recorder.js';
import { dropFollowWpm, fitFollowWpm, followLimits, paintFollowWpm } from '../screens/practice.js';
import { clearChatHistory } from '../screens/script_studio.js';
import { CONFIG, S } from '../state.js';
import { openModal, toast, withBusy } from '../ui.js';
import { $, $$, clearErr, esc, showErr } from '../utils.js';

/* ---------- Settings Modal ----------
   One window: the first screen lists Permissions, Audio, Change password and Delete account.
   Choosing one slides its screen in from the right inside the same box; Back slides the list
   back. The screen that is off to the side is inert, so Tab never lands in it. */
const PANES = ['permissions', 'audio', 'speed', 'password', 'delete'];
let current = null;   // open detail screen, or null when the list is shown

export function openSettings() {
  showList(false);
  openModal('settingsModal');
}

function showList(focus) {
  stopAudioTest();
  $('.settings-box').classList.remove('detail');
  $('#settingsList').inert = false;
  $('#settingsDetail').inert = true;
  const from = current;
  current = null;
  if (focus && from) $('[data-settings="' + from + '"]').focus();
}

function showPane(name) {
  current = name;
  PANES.forEach(k => { $('[data-pane="' + k + '"]').hidden = k !== name; });
  if (name === 'permissions') $('#pmChk').checked = S.consent;
  else if (name === 'audio') fillAudio();
  else if (name === 'speed') fillSpeed();
  else if (name === 'password') fillPassword();
  else if (name === 'delete') fillDelete();
  $('#settingsList').inert = true;
  $('#settingsDetail').inert = false;
  $('.settings-box').classList.add('detail');
  const h = $('[data-pane="' + name + '"] h3');
  h.tabIndex = -1;
  h.focus({ preventScroll: true });
}

/* ---- Permissions ---- */
function savePermissions() {
  const on = $('#pmChk').checked, changed = on !== S.consent;
  S.consent = on;
  if (changed) saveConsent(on);
  toast(T(S.consent ? 'consent.toastOn' : 'consent.toastOff'));
  showList(true);
}

/* ---- Reading speed: the user's own slider range, kept in profiles.preferences ---- */
function speedOptions(sel, value) {
  const opts = [];
  for (let v = CONFIG.FOLLOW_WPM_MIN; v <= CONFIG.FOLLOW_WPM_MAX; v += CONFIG.FOLLOW_WPM_STEP) opts.push(v);
  sel.innerHTML = opts.map(v => '<option value="' + v + '"' + (v === value ? ' selected' : '') + '>' + esc(T('speed.wpm', { n: v })) + '</option>').join('');
}
function fillSpeed() {
  const l = followLimits();
  $('#speedSub').textContent = T('speed.sub', { lo: CONFIG.FOLLOW_WPM_MIN, hi: CONFIG.FOLLOW_WPM_MAX });
  speedOptions($('#speedMin'), l.min); speedOptions($('#speedMax'), l.max);
  $('#speedAuto').checked = !!S.autoSpeed;
  clearErr($('#speedErr'));
}
function saveSpeed() {
  const lo = Number($('#speedMin').value), hi = Number($('#speedMax').value), err = $('#speedErr');
  if (!(lo < hi)) { showErr(err, T('speed.errOrder')); $('#speedMin').focus(); return; }
  clearErr(err);
  const auto = $('#speedAuto').checked, before = S.wpmRange;
  S.wpmRange = { min: lo, max: hi };
  const wpm = fitFollowWpm(S.followWpm);
  S.wpmRange = before;
  withBusy(api('/api/profile', { method: 'PATCH', json: { preferences: { follow_wpm_min_choose: lo, follow_wpm_max_choose: hi, follow_wpm: wpm, follow_auto_speed: auto } } }), T('busy.saving')).then(r => {
    if (!r.ok) throw new Error('speed ' + r.status);
    S.wpmRange = { min: lo, max: hi }; S.followWpm = wpm; S.autoSpeed = auto; paintFollowWpm();
    toast(T('speed.ok')); showList(true);
  }).catch(() => showErr(err, T('speed.err')));
}
function resetSpeed() {
  speedOptions($('#speedMin'), CONFIG.FOLLOW_WPM_MIN_CHOOSE); speedOptions($('#speedMax'), CONFIG.FOLLOW_WPM_MAX_CHOOSE);
  clearErr($('#speedErr'));
}

/* ---- Audio ---- */
export let audioTestStop = null;
function fillAudio() {
  $('#audioMic').innerHTML = T('audio.mics').map((m, i) => '<option value="' + i + '">' + esc(m) + '</option>').join('');
  $('#audioTestNote').textContent = '';
}
export function testMic() {
  if (audioTestStop) return;
  $('#audioTestNote').textContent = T('audio.testing');
  audioTestStop = levelAnim($('#audioLevel'), null, e => {   // mic could not be opened: stop the test and say why (no "working" message)
    if (audioTestStop) { audioTestStop(); audioTestStop = null; }
    const n = e && e.name;
    $('#audioTestNote').textContent = T('practice.mic' + (n === 'NotAllowedError' || n === 'SecurityError' ? 'Denied' : n === 'unsupported' ? 'Unsupported' : 'Nodevice'));
  });
  setTimeout(() => { if (audioTestStop) { audioTestStop(); audioTestStop = null; $('#audioTestNote').textContent = T('audio.testOk'); } }, 1800);
}
/* Stop the microphone test if it is running (also used by the Baseline Gate). */
export function stopAudioTest() { if (audioTestStop) { audioTestStop(); audioTestStop = null; } }

/* ---- Change password: needs the current password (re-auth, ADR-011); the session stays ---- */
const PASS_ERR = { wrong_password: 'pass.errWrong', same_password: 'pass.errSame', rate_limited: 'pass.errRate', weak_password: 'auth.errWeak' };
function clearPassFields() { ['#mpCurrent', '#mpNew', '#mpNew2'].forEach(id => { $(id).value = ''; }); }
function fillPassword() {
  $('#mpUser').value = S.user.email || ''; clearPassFields(); clearErr($('#mpErr'));
}
export function savePass() {
  const cur = $('#mpCurrent').value, a = $('#mpNew').value, b = $('#mpNew2').value, err = $('#mpErr');
  if (!cur || !a || !b) { showErr(err, T('pass.errEmpty')); $(!cur ? '#mpCurrent' : !a ? '#mpNew' : '#mpNew2').focus(); return; }
  if (a !== b) { showErr(err, T('pass.errMismatch')); $('#mpNew2').focus(); return; }
  if (a.length < MIN_PASSWORD) { showErr(err, T('auth.errWeak')); $('#mpNew').focus(); return; }
  if (a === cur) { showErr(err, T('pass.errSame')); $('#mpNew').focus(); return; }
  $('#passSave').disabled = true;
  withBusy(api('/api/auth/password', { method: 'PUT', json: { current_password: cur, new_password: a } }), T('busy.saving')).then(readJson).then(({ ok, status, j }) => {
    $('#passSave').disabled = false;
    if (status === 401) return;   // session ended: api() already logged out
    if (!ok) {
      const code = j && j.error_code;
      showErr(err, T(PASS_ERR[code] || 'auth.errServer'));
      if (code === 'wrong_password') { $('#mpCurrent').value = ''; $('#mpCurrent').focus(); }
      return;
    }
    clearPassFields();
    toast(T('pass.ok'));
    showList(true);
  }).catch(() => { $('#passSave').disabled = false; showErr(err, T('auth.errServer')); });
}

/* ---- Delete account: re-auth with the current password (ADR-011); Agree unlocks once it is typed ---- */
const DEL_ERR = { wrong_password: 'del.errWrong', rate_limited: 'del.errRate' };   // storage_unavailable, auth_unavailable -> del.failed
function fillDelete() {
  $('#delUser').value = S.user.email || '';   // hidden username field so password managers pick the right account
  $('#delPassword').value = '';
  $('#delConfirm').disabled = true;
  clearErr($('#delErr'));
}
function cancelDelete() { $('#delPassword').value = ''; showList(true); }
function confirmDelete() {
  const err = $('#delErr'), pw = $('#delPassword').value;
  if (!pw) return;
  $('#delConfirm').disabled = true;
  deleteAccount(pw).then(readJson).then(({ ok, status, j }) => {
    if (status === 401) return;   // session ended: api() already logged out
    if (!ok) {
      const code = j && j.error_code;
      showErr(err, T(DEL_ERR[code] || 'del.failed'));
      if (code === 'wrong_password') { $('#delPassword').value = ''; $('#delPassword').focus(); }
      else $('#delConfirm').disabled = !$('#delPassword').value;
      return;
    }
    $('#delPassword').value = '';
    clearChatHistory(S.user && S.user.id);   // logout(true) keeps the chat, a deleted account must not
    dropFollowWpm(S.user && S.user.id);
    logout(true);
    toast(T('del.done'));
  }).catch(() => { $('#delConfirm').disabled = !$('#delPassword').value; showErr(err, T('del.failed')); });
}

export function setupSettings() {
  $$('[data-settings]').forEach(b => { b.onclick = () => showPane(b.getAttribute('data-settings')); });
  $$('[data-settings-back]').forEach(b => { b.onclick = () => showList(true); });
  $('#permSave').onclick = savePermissions;
  $('#passSave').onclick = savePass;
  $('#speedSave').onclick = saveSpeed;
  $('#speedReset').onclick = resetSpeed;
  $('#audioTest').onclick = testMic;
  $('#audioSave').onclick = () => { stopAudioTest(); toast(T('audio.ok')); showList(true); };
  $('#delPassword').addEventListener('input', () => { $('#delConfirm').disabled = !$('#delPassword').value; clearErr($('#delErr')); });
  $('#delPassword').addEventListener('keydown', e => { if (e.key === 'Enter' && $('#delPassword').value) confirmDelete(); });
  $('#delCancel').onclick = cancelDelete;
  $('#delConfirm').onclick = confirmDelete;
}
