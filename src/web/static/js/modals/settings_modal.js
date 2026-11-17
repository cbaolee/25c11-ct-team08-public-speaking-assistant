import { MIN_PASSWORD, api, deleteAccount, readJson } from '../api.js';
import { T } from '../i18n.js';
import { logout } from './baseline_gate.js';
import { saveConsent } from './profile_modal.js';
import { levelAnim } from '../recorder.js';
import { S } from '../state.js';
import { openModal, toast } from '../ui.js';
import { $, $$, clearErr, esc, showErr } from '../utils.js';

/* ---------- Settings Modal ----------
   One window: the first screen lists Permissions, Audio, Change password and Delete account.
   Choosing one slides its screen in from the right inside the same box; Back slides the list
   back. The screen that is off to the side is inert, so Tab never lands in it. */
const PANES = ['permissions', 'audio', 'password', 'delete'];
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

/* ---- Change password ---- */
function fillPassword() {
  $('#mpUser').value = S.user.email || ''; $('#mpNew').value = ''; $('#mpNew2').value = ''; clearErr($('#mpErr'));
}
export function savePass() {
  const a = $('#mpNew').value, b = $('#mpNew2').value, err = $('#mpErr');
  if (!a || !b) { showErr(err, T('pass.errEmpty')); return; }
  if (a.length < MIN_PASSWORD) { showErr(err, T('auth.errWeak')); $('#mpNew').focus(); return; }
  if (a !== b) { showErr(err, T('pass.errMismatch')); $('#mpNew2').focus(); return; }
  $('#passSave').disabled = true;
  api('/api/auth/password', { method: 'PUT', json: { password: a } }).then(readJson).then(({ ok, status, j }) => {
    $('#passSave').disabled = false;
    if (status === 401) return;
    if (!ok) { showErr(err, j && j.error_code === 'weak_password' ? T('auth.errWeak') : T('auth.errServer')); return; }
    toast(T('pass.ok'));
    showList(true);
  }).catch(() => { $('#passSave').disabled = false; showErr(err, T('auth.errServer')); });
}

/* ---- Delete account: the button unlocks only when the typed email matches the account ---- */
const emailMatches = () => $('#delConfirmEmail').value.trim().toLowerCase() === (S.user.email || '').toLowerCase();
function fillDelete() {
  $('#delConfirmEmail').value = '';
  $('#delConfirm').disabled = true;
  clearErr($('#delErr'));
}
function confirmDelete() {
  const err = $('#delErr');
  if (!emailMatches()) { showErr(err, T('del.mismatch')); return; }
  $('#delConfirm').disabled = true;
  deleteAccount().then(r => {
    if (r.status === 401) return;
    if (!r.ok) { $('#delConfirm').disabled = false; showErr(err, T('del.failed')); return; }
    logout(true);
    toast(T('del.done'));
  }).catch(() => { $('#delConfirm').disabled = false; showErr(err, T('del.failed')); });
}

export function setupSettings() {
  $$('[data-settings]').forEach(b => { b.onclick = () => showPane(b.getAttribute('data-settings')); });
  $$('[data-settings-back]').forEach(b => { b.onclick = () => showList(true); });
  $('#permSave').onclick = savePermissions;
  $('#passSave').onclick = savePass;
  $('#audioInput').addEventListener('input', e => { $('#audioInputValue').textContent = e.target.value; });
  $('#audioOutput').addEventListener('input', e => { $('#audioOutputValue').textContent = e.target.value; });
  $('#audioTest').onclick = testMic;
  $('#audioSave').onclick = () => { stopAudioTest(); toast(T('audio.ok')); showList(true); };
  $('#delConfirmEmail').addEventListener('input', () => { $('#delConfirm').disabled = !emailMatches(); clearErr($('#delErr')); });
  $('#delConfirm').onclick = confirmDelete;
}
