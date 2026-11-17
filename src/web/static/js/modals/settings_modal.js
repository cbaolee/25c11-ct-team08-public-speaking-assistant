import { MIN_PASSWORD, api, readJson } from '../api.js';
import { T } from '../i18n.js';
import { levelAnim } from '../recorder.js';
import { S } from '../state.js';
import { closeModal, openModal, toast } from '../ui.js';
import { $, clearErr, esc, showErr } from '../utils.js';

/* ---------- other modals ---------- */
export function openPassModal() {
  $('#mpUser').value = S.user.email || ''; $('#mpNew').value = ''; $('#mpNew2').value = ''; clearErr($('#mpErr'));
  openModal('passwordModal', { focus: '#mpNew' });
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
    closeModal('passwordModal'); toast(T('pass.ok'));
  }).catch(() => { $('#passSave').disabled = false; showErr(err, T('auth.errServer')); });
}
export let audioTestStop = null;
export function openAudioModal() {
  $('#audioMic').innerHTML = T('audio.mics').map((m, i) => '<option value="' + i + '">' + esc(m) + '</option>').join('');
  $('#audioTestNote').textContent = '';
  openModal('audioSettingsModal');
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
