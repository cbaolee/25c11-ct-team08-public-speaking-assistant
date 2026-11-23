import { api } from '../api.js';
import { userName } from './auth_panel.js';
import { renderAccount } from '../nav.js';
import { T } from '../i18n.js';
import { fillTopicSelect } from '../screens/script_studio.js';
import { RENDER, S } from '../state.js';
import { closeModal, openModal, toast, withBusy } from '../ui.js';
import { $, esc } from '../utils.js';

/* ---------- profile modal ---------- */
export function openProfileModal(first) {
  S.pmFirst = first;
  const p = S.profile || {};
  $('#mpTitle').textContent = T(first ? 'pm.titleFirst' : 'pm.titleEdit');
  $('#mpSub').textContent = T(first ? 'pm.subFirst' : 'pm.subEdit');
  $('#mpCancel').hidden = first;
  $('#mpDisplayName').value = p.displayName || '';
  $('#mpGender').innerHTML = '<option value="">' + esc(T('pm.genderPh')) + '</option>' + T('pm.genders').map(g => '<option value="' + esc(g) + '">' + esc(g) + '</option>').join('');
  $('#mpGender').value = p.gender || '';
  $('#mpAge').value = p.age != null ? p.age : '';
  $('#mpAccents').innerHTML = T('pm.accents').map(a => '<label><input type="radio" name="pmAccent" value="' + esc(a) + '"' + (p.accent === a ? ' checked' : '') + '> ' + esc(a) + '</label>').join('');
  ['eAge', 'eAccent'].forEach(i => $('#' + i).classList.remove('show'));
  $('#mpAge').removeAttribute('aria-invalid');
  openModal('profileModal', { lock: first, focus: first ? '#mpGender' : undefined });
}
export function saveProfileModal() {
  const age = $('#mpAge').value.trim(), acc = $('input[name=pmAccent]:checked');
  const n = age === '' ? null : Number(age);
  const okAge = n === null || (Number.isInteger(n) && n >= 1 && n <= 120);
  $('#eAge').classList.toggle('show', !okAge); $('#mpAge').setAttribute('aria-invalid', String(!okAge));
  $('#eAccent').classList.toggle('show', !acc);
  if (!okAge) { $('#mpAge').focus(); return; }
  if (!acc) { $('input[name=pmAccent]').focus(); return; }
  const next = { displayName: $('#mpDisplayName').value.trim() || null, gender: $('#mpGender').value || null, age: n, accent: acc.value };
  $('#mpSave').disabled = true;
  withBusy(api('/api/profile', { method: 'PATCH', json: { display_name: next.displayName, gender: next.gender, age: next.age, target_accent: next.accent } }), T('busy.saving'))
    .then(r => {
      $('#mpSave').disabled = false;
      if (!r.ok) { if (r.status !== 401) toast(T('pm.saveErr'), true); return; }
      S.profile = next;
      S.user.name = userName(next.displayName, S.user.email); renderAccount();
      closeModal('profileModal'); toast(T('pm.saved')); fillTopicSelect();
      if (RENDER[S.screen]) RENDER[S.screen]();
    }).catch(() => { $('#mpSave').disabled = false; toast(T('pm.saveErr'), true); });
}
/* Keep profiles.consent_recording in step with the Consent Modal and Permissions. */
export function saveConsent(on) {
  if (!S.user) return;   // during sign up the answer goes with POST /api/auth/signup
  api('/api/profile', { method: 'PATCH', json: { consent_recording: on } }).then(r => { if (!r.ok && r.status !== 401) toast(T('pm.saveErr'), true); }).catch(() => toast(T('pm.saveErr'), true));
}
