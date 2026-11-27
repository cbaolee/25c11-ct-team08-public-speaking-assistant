import { MIN_PASSWORD, RESET_ERR, api, deleteAccount, readJson, resetPassword, sendResetCode } from '../api.js';
import { T } from '../i18n.js';
import { openAuth } from './auth_panel.js';
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
  if (navigator.mediaDevices && navigator.mediaDevices.removeEventListener) navigator.mediaDevices.removeEventListener('devicechange', onDeviceChange);
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
  if (name === 'permissions') { $('#pmChk').checked = S.consent; showPermWarning(); }
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
/* Turning recording off locks practice and recording; say so before it is saved. */
function showPermWarning() { $('#pmOffWarning').classList.toggle('show', !$('#pmChk').checked); }
function savePermissions() {
  const on = $('#pmChk').checked;
  if (on === S.consent) { showList(true); return; }
  const btn = $('#permSave');
  btn.disabled = true;
  saveConsent(on).then(ok => {
    btn.disabled = false;
    if (!ok) { toast(T('pm.saveErr'), true); return; }
    S.consent = on;
    toast(T(on ? 'consent.toastOn' : 'consent.toastOff'));
    showList(true);
  });
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

/* ---- Audio: choose the real microphone (mic_device.js, ADR-011); Save keeps it in this browser ---- */
export let audioTestStop = null;
const micLabels = () => ({ def: T('audio.micDefault'), nth: n => T('audio.micN', { n }) });
function audioPaneOpen() { return current === 'audio' && $('#settingsModal').classList.contains('show'); }
/* Fill the list; keep the device picked in the list if it is still there, else the saved one, else the default. */
function fillMics(keepPick) {
  const sel = $('#audioMic'), M = window.MicDevice, want = keepPick ? sel.value : M.getSavedMicId(S.user && S.user.id);
  return M.listMics(navigator.mediaDevices, micLabels()).then(({ mics, unnamed }) => {
    if (current !== 'audio') return;
    sel.innerHTML = mics.map(m => '<option value="' + esc(m.id) + '">' + esc(m.label) + '</option>').join('');
    sel.value = mics.some(m => m.id === want) ? want : '';
    $('#audioMicHint').textContent = unnamed ? T('audio.micHint') : '';
  });
}
function onDeviceChange() {
  if (!audioPaneOpen()) { navigator.mediaDevices.removeEventListener('devicechange', onDeviceChange); return; }
  fillMics(true);
}
function fillAudio() {
  $('#audioTestNote').textContent = '';
  fillMics(false);
  if (navigator.mediaDevices && navigator.mediaDevices.addEventListener) {
    navigator.mediaDevices.removeEventListener('devicechange', onDeviceChange);
    navigator.mediaDevices.addEventListener('devicechange', onDeviceChange);   // removed when the pane is left
  }
}
export function testMic() {
  if (audioTestStop) return;
  $('#audioTestNote').textContent = T('audio.testing');
  audioTestStop = levelAnim($('#audioLevel'), null, e => {   // mic could not be opened: stop the test and say why (no "working" message)
    if (audioTestStop) { audioTestStop(); audioTestStop = null; }
    const n = e && e.name;
    $('#audioTestNote').textContent = T('practice.mic' + (n === 'NotAllowedError' || n === 'SecurityError' ? 'Denied' : n === 'unsupported' ? 'Unsupported' : 'Nodevice'));
    if (window.MicDevice.isMissingDevice(e)) fillMics(false);   // the picked device was unplugged
  }, { micId: $('#audioMic').value, onOpen: () => { if (audioPaneOpen()) fillMics(true); } });   // permission given: names can now be shown
  setTimeout(() => { if (audioTestStop) { audioTestStop(); audioTestStop = null; $('#audioTestNote').textContent = T('audio.testOk'); } }, 1800);
}
function saveAudio() {
  stopAudioTest();
  window.MicDevice.saveMicId(S.user && S.user.id, $('#audioMic').value);
  toast(T('audio.ok')); showList(true);
}
/* Stop the microphone test if it is running (also used by the Baseline Gate). */
export function stopAudioTest() { if (audioTestStop) { audioTestStop(); audioTestStop = null; } }

/* ---- Change password: needs the current password (re-auth, ADR-011); the session stays ---- */
const PASS_ERR = { wrong_password: 'pass.errWrong', same_password: 'pass.errSame', rate_limited: 'pass.errRate', weak_password: 'auth.errWeak' };
function clearPassFields() { ['#mpCurrent', '#mpNew', '#mpNew2'].forEach(id => { $(id).value = ''; }); }
function fillPassword() {
  $('#mpUser').value = S.user.email || ''; clearPassFields(); clearErr($('#mpErr'));
  showCodeForm(false);
}

/* ---- Change password > Forgot your current password?: a code to the account's email, then a new
   password. The reset ends every session (this one too), so the user logs in again. ---- */
let codeSentAt = null, codeTimer = null, codeBusy = false;
const otpLength = () => CONFIG.auth?.otp_length ?? 6;
const cooldownS = () => CONFIG.auth?.resend_cooldown_s ?? 60;
function stopCodeCountdown() { clearInterval(codeTimer); codeTimer = null; }
function updateCodeCountdown() {
  const left = window.OtpUtils.cooldownLeft(codeSentAt, Date.now(), cooldownS()), button = $('#mpCodeResend');
  button.disabled = left > 0;
  button.textContent = left ? T('auth.otpResendIn', { t: window.OtpUtils.formatCountdown(left) }) : T('auth.otpResend');
  if (!left || $('#mpWithCode').hidden) stopCodeCountdown();
}
function showCodeForm(on) {
  $('#mpWithCurrent').hidden = on; $('#mpWithCode').hidden = !on;
  ['#mpCode', '#mpCodeNew', '#mpCodeNew2'].forEach(id => { $(id).value = ''; });
  clearErr($('#mpCodeErr'));
  if (!on) { stopCodeCountdown(); codeSentAt = null; }
}
async function sendCode() {
  if (codeBusy || !S.user) return;
  codeBusy = true; $('#mpForgot').disabled = true; $('#mpCodeResend').disabled = true;
  try {
    const { ok, status } = await withBusy(sendResetCode(S.user.email), T('busy.sending'));
    if (!ok && status !== 429) { showErr($($('#mpWithCode').hidden ? '#mpErr' : '#mpCodeErr'), T('auth.errServer')); $('#mpCodeResend').disabled = false; return; }
    if ($('#mpWithCode').hidden) showCodeForm(true);
    $('#mpCodeSentTo').textContent = T('reset.settingsSent', { email: S.user.email, n: otpLength() });
    $('#mpCode').maxLength = otpLength();
    if (!ok) showErr($('#mpCodeErr'), T('auth.errRateLimited'));
    codeSentAt = Date.now(); stopCodeCountdown(); updateCodeCountdown(); codeTimer = setInterval(updateCodeCountdown, 1000);
    $('#mpCode').focus();
  } catch (_) { showErr($('#mpErr'), T('auth.errServer')); }
  finally { codeBusy = false; $('#mpForgot').disabled = false; }
}
async function saveWithCode() {
  if (codeBusy || !S.user) return;
  const err = $('#mpCodeErr'), email = S.user.email;
  const form = { code: $('#mpCode').value, password: $('#mpCodeNew').value, password2: $('#mpCodeNew2').value };
  const problem = window.ResetForm.resetFormError(form, otpLength(), MIN_PASSWORD);
  if (problem) { showErr(err, T(problem, { n: otpLength() })); $(problem === 'reset.errCode' ? '#mpCode' : '#mpCodeNew').focus(); return; }
  codeBusy = true; $('#mpCodeSave').disabled = true; clearErr(err);
  try {
    const { ok, j } = await withBusy(resetPassword(email, form.code, form.password), T('busy.saving'));
    if (!ok) { const code = j && j.error_code; showErr(err, RESET_ERR[code] ? T(RESET_ERR[code]) : (j && j.message) || T('auth.errServer')); return; }
    showCodeForm(false);
    logout(true);   // the server already ended this session
    openAuth('in');
    $('#authEmail').value = email;
    $('#loginHint').textContent = T('reset.done'); $('#loginHint').hidden = false;
    $('#authPassword').focus();
    toast(T('reset.done'));
  } catch (_) { showErr(err, T('auth.errServer')); }
  finally { codeBusy = false; $('#mpCodeSave').disabled = false; }
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
    window.MicDevice.saveMicId(S.user && S.user.id, '');
    logout(true);
    toast(T('del.done'));
  }).catch(() => { $('#delConfirm').disabled = !$('#delPassword').value; showErr(err, T('del.failed')); });
}

export function setupSettings() {
  $$('[data-settings]').forEach(b => { b.onclick = () => showPane(b.getAttribute('data-settings')); });
  $$('[data-settings-back]').forEach(b => { b.onclick = () => showList(true); });
  $('#permSave').onclick = savePermissions;
  $('#mpForgot').onclick = sendCode;
  $('#mpCodeResend').onclick = sendCode;
  $('#mpCodeSave').onclick = saveWithCode;
  $('#mpCodeCancel').onclick = () => showCodeForm(false);
  $('#mpCode').addEventListener('input', () => { $('#mpCode').value = window.OtpUtils.normalizeOtp($('#mpCode').value, otpLength()); });
  $('#pmChk').addEventListener('change', showPermWarning);
  $('#passSave').onclick = savePass;
  $('#speedSave').onclick = saveSpeed;
  $('#speedReset').onclick = resetSpeed;
  $('#audioTest').onclick = testMic;
  $('#audioSave').onclick = saveAudio;
  $('#delPassword').addEventListener('input', () => { $('#delConfirm').disabled = !$('#delPassword').value; clearErr($('#delErr')); });
  $('#delPassword').addEventListener('keydown', e => { if (e.key === 'Enter' && $('#delPassword').value) confirmDelete(); });
  $('#delCancel').onclick = cancelDelete;
  $('#delConfirm').onclick = confirmDelete;
}
