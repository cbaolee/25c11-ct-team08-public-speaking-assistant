import { AUTH_ERR, EMAIL_RE, MIN_PASSWORD, api, readJson, storeAuth } from '../api.js';
import { T, TOPICS } from '../i18n.js';
import { loadBaseline } from '../modals/baseline_gate.js';
import { go, moveSegPills, renderAccount, showView } from '../nav.js';
import { loadHistory } from '../screens/history.js';
import { setStageAuth } from '../screens/landing.js';
import { addBubble, fillTopicSelect, renderChatFile } from '../screens/script_studio.js';
import { S } from '../state.js';
import { openModal, toast } from '../ui.js';
import { $, $$, clearErr, esc, showErr } from '../utils.js';

export function fillSignupForm(reset) {
  const sel = $('#signupExtraGender');
  if (!reset && sel.options.length) return;
  const p = {};
  sel.innerHTML = '<option value="">' + esc(T('pm.genderPh')) + '</option>' + T('pm.genders').map(g => '<option value="' + esc(g) + '">' + esc(g) + '</option>').join('');
  sel.value = p.gender || '';
  $('#signupExtraDisplayName').value = ''; $('#signupExtraDisplayName').removeAttribute('aria-invalid');
  $('#signupExtraAge').value = p.age != null ? p.age : ''; $('#signupExtraAge').removeAttribute('aria-invalid');
  $('#signupExtraAccents').innerHTML = T('pm.accents').map(a => '<label><input type="radio" name="signupExtraAccent" value="' + esc(a) + '"' + (p.accent === a ? ' checked' : '') + '> ' + esc(a) + '</label>').join('');
  $('#signupExtraTopics').innerHTML = Object.keys(TOPICS).map(k => '<label><input type="checkbox" name="signupExtraTopic" value="' + k + '"' + (p.topics && p.topics.indexOf(k) >= 0 ? ' checked' : '') + '> ' + esc(TOPICS[k]) + '</label>').join('');
  ['eSuName', 'eSuAge', 'eSuAccent', 'eSuTopics'].forEach(i => $('#' + i).classList.remove('show'));
}
/* Log in <-> Sign up on the open panel: the card blurs, shrinks and swipes out, the form changes while it is
   invisible (so the size jump never shows), then it swipes in from the other side. Sign up moves left, log in moves right. */
export let authSwipe = null;
export function setAuthMode(mode) {
  const a = $('#lAuth'), calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  /* Log in <-> Sign up: the tab pill slides; fields that leave fade out; the card then grows or shrinks
     (width and height) to its new size while the new fields fade in. Fields shared by both stay put. */
  const extra = [$('#pass2Wrap'), $('#signupExtra')], btn = $('#authSubmit');
  [a, btn].concat(extra).forEach(el => el.getAnimations().forEach(x => x.cancel()));   // a fast second click starts clean
  authSwipe = null;
  if (mode === S.authMode || !$('#lStage').classList.contains('is-auth') || calm || !a.animate) { applyAuthMode(mode); moveSegPills(false, a); return; }
  $('#authLoginTab').setAttribute('aria-selected', String(mode === 'in'));
  $('#authSignupTab').setAttribute('aria-selected', String(mode === 'up'));
  moveSegPills(true, a);   // pill starts at once
  const r0 = a.getBoundingClientRect();
  const leaving = (mode === 'in' ? extra : []).filter(el => !el.hidden).concat(btn);
  const fades = leaving.map(el => el.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 200, easing: 'ease-in', fill: 'forwards' }));
  const token = {}; authSwipe = token;
  Promise.all(fades.map(f => f.finished)).then(() => {
    if (authSwipe !== token) return;
    applyAuthMode(mode);
    fades.forEach(f => f.cancel());
    const r1 = a.getBoundingClientRect();
    moveSegPills(true, a);   // final spot in the resized card
    a.style.overflow = 'hidden';
    const grow = a.animate([{ width: r0.width + 'px', height: r0.height + 'px' }, { width: r1.width + 'px', height: r1.height + 'px' }],
      { duration: 420, easing: 'cubic-bezier(.65, 0, .35, 1)' });
    grow.onfinish = grow.oncancel = () => { a.style.overflow = ''; if (authSwipe === token) authSwipe = null; };
    (mode === 'up' ? extra : []).concat(btn).forEach(el =>
      el.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 340, delay: 160, easing: 'ease-out', fill: 'backwards' }));
  }).catch(() => {});
}
export function applyAuthMode(mode) {
  S.authMode = mode;
  $('#authLoginTab').setAttribute('aria-selected', String(mode === 'in'));
  $('#authSignupTab').setAttribute('aria-selected', String(mode === 'up'));
  $('#authSubmit').textContent = T(mode === 'up' ? 'auth.btnSignup' : 'auth.btnLogin');
  $('#authPassword').setAttribute('autocomplete', mode === 'up' ? 'new-password' : 'current-password');
  $('#signupExtra').hidden = mode !== 'up';
  $('#pass2Wrap').hidden = mode !== 'up'; $('#authPassword2').value = ''; $('#authPassword2').removeAttribute('aria-invalid');
  $('#lAuth').classList.toggle('signup', mode === 'up');
  $('#loginHint').hidden = true;
  clearErr($('#authError'));
}
export function openAuth(mode) {
  fillSignupForm();
  setAuthMode(mode);
  if (S.view !== 'landing') showView('landing');
  setStageAuth(true);
  window.scrollTo(0, 0);
  $('#authEmail').focus({ preventScroll: true });
}
export function resetChat() {
  const feed = $('#chatFeed');
  feed.innerHTML = '';
  addBubble('ai', '<p></p>').querySelector('p').textContent = T('script.greeting', { name: S.user.name });
  S.chatFile = null; renderChatFile(); $('#composerInput').value = ''; clearErr($('#composerError'));
}
export function enterApp(fresh) {
  S.texts = { mine: null, sample: null, own: null }; S.pickerTab = 'mine'; S.audio = null; S.currentSession = null; S.choosing = true;
  renderAccount(); showView('app'); fillTopicSelect(); resetChat();
  go('home', { silent: !fresh });
}
/* How the app addresses the user: display_name, or the part of the email before "@". */
export function userName(displayName, email) {
  return (displayName || '').trim() || (email || '').split('@')[0] || 'you';
}
/* GET /api/profile -> S.user / S.profile / S.consent (the profile row is made at sign up). */
export function applyProfile(p) {
  S.user = { id: p.id, email: p.email, name: userName(p.display_name, p.email) };
  S.profile = { displayName: p.display_name || null, gender: p.gender || null, age: p.age != null ? p.age : null, accent: p.target_accent, topics: p.topics || [] };
  S.consent = !!p.consent_recording;
}
/* After log in, and on page load when tokens are stored: profile -> app -> baseline (F1) + history (F2). */
/* Full-screen loading screen shown between log in and a fully loaded Home. */
export function showAppLoader(on) {
  const el = $('#appLoader');
  if (on) { el.hidden = false; el.classList.remove('out'); return; }
  if (el.hidden) return;
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) { el.hidden = true; return; }
  el.classList.add('out');
  setTimeout(() => { el.hidden = true; el.classList.remove('out'); }, 400);
}
export function startSession(fresh) {
  return api('/api/profile').then(readJson).then(({ ok, status, j }) => {
    if (!ok) {
      if (status === 401) return;                       // sessionEnded() already ran
      if (status === 404) storeAuth(null);              // account without a profile row: cannot continue
      if (fresh) showErr($('#authError'), (j && j.message) || T('auth.errServer')); else toast(T('auth.errServer'), true);
      return;
    }
    applyProfile(j);
    S.sessions = []; S.baseline = null; S.savedScripts = null;
    // Loading screen until history and the latest scores are in, so Home never shows an empty
    // account first and then jumps. The Baseline Gate (if needed) opens after it.
    showAppLoader(true);
    enterApp(fresh);
    const user = S.user, ready = () => { showAppLoader(false); if (S.user !== user) return; if (fresh) toast(T('auth.okLogin')); loadBaseline(true); };
    Promise.race([loadHistory(), new Promise(r => setTimeout(r, 10000))]).then(ready, ready);
  }).catch(() => { showAppLoader(false); if (fresh) showErr($('#authError'), T('auth.errServer')); else toast(T('auth.errServer'), true); });
}
export function readSignupProfile() {
  const name = $('#signupExtraDisplayName').value.trim();
  const age = $('#signupExtraAge').value.trim(), acc = $('input[name=signupExtraAccent]:checked'), tops = $$('input[name=signupExtraTopic]:checked').map(i => i.value);
  const n = age === '' ? null : Number(age);
  const okAge = n === null || (Number.isInteger(n) && n >= 1 && n <= 120);
  $('#eSuName').classList.toggle('show', !name); $('#signupExtraDisplayName').setAttribute('aria-invalid', String(!name));
  $('#eSuAge').classList.toggle('show', !okAge); $('#signupExtraAge').setAttribute('aria-invalid', String(!okAge));
  $('#eSuAccent').classList.toggle('show', !acc); $('#eSuTopics').classList.toggle('show', !tops.length);
  if (!name) { $('#signupExtraDisplayName').focus(); return null; }
  if (!okAge) { $('#signupExtraAge').focus(); return null; }
  if (!acc) { $('input[name=signupExtraAccent]').focus(); return null; }
  if (!tops.length) { $('input[name=signupExtraTopic]').focus(); return null; }
  return { displayName: name, gender: $('#signupExtraGender').value || null, age: n, accent: acc.value, topics: tops };
}
export function onAuthSubmit(e) {
  e.preventDefault();
  if (S.authBusy) return;
  const u = $('#authEmail').value.trim().toLowerCase(), p = $('#authPassword').value, err = $('#authError');
  $('#authEmail').setAttribute('aria-invalid', String(!u)); $('#authPassword').setAttribute('aria-invalid', String(!p));
  if (!u || !p) { showErr(err, T('auth.errEmpty')); (!u ? $('#authEmail') : $('#authPassword')).focus(); return; }
  if (!EMAIL_RE.test(u)) { showErr(err, T('auth.errEmail')); $('#authEmail').setAttribute('aria-invalid', 'true'); $('#authEmail').focus(); return; }
  clearErr(err);
  if (S.authMode === 'up') {
    const p2 = $('#authPassword2').value;
    if (p.length < MIN_PASSWORD) { showErr(err, T('auth.errWeak')); $('#authPassword').setAttribute('aria-invalid', 'true'); $('#authPassword').focus(); return; }
    $('#authPassword2').setAttribute('aria-invalid', String(!p2 || p2 !== p));
    if (!p2) { showErr(err, T('auth.errRepeat')); $('#authPassword2').focus(); return; }
    if (p2 !== p) { showErr(err, T('auth.errMismatch')); $('#authPassword').setAttribute('aria-invalid', 'true'); $('#authPassword2').focus(); return; }
    const prof = readSignupProfile();
    if (!prof) return;
    // Step 2 of sign up: ask for recording permission. The account is created when the person answers.
    S.signupDraft = { email: u, password: p, profile: prof };
    S.consent = false;
    S.afterConsent = () => finishSignup(true);
    S.onDeny = () => finishSignup(false);
    openModal('consentModal', { lock: true, focus: '#mcAllow' });
    return;
  }
  logIn(u, p);
}
export function setAuthBusy(on) { S.authBusy = on; $('#authSubmit').disabled = on; }
/* POST /api/auth/signup: creates the account and its profiles row (with the consent answer). */
export function finishSignup(consent) {
  const d = S.signupDraft; S.signupDraft = null;
  if (!d) return;
  S.consent = false;                  // nobody is logged in yet; the answer is stored on the account
  const err = $('#authError');
  setAuthBusy(true);
  api('/api/auth/signup', { method: 'POST', json: { email: d.email, password: d.password, display_name: d.profile.displayName, target_accent: d.profile.accent, age: d.profile.age, gender: d.profile.gender, topics: d.profile.topics, consent_recording: consent } })
    .then(readJson).then(({ ok, j }) => {
      setAuthBusy(false);
      const code = j && j.error_code;
      if (!ok) {
        showErr(err, AUTH_ERR[code] ? T(AUTH_ERR[code]) : (j && j.message) || T('auth.errServer'));
        if (code === 'email_taken' || code === 'invalid_email') { $('#authEmail').setAttribute('aria-invalid', 'true'); $('#authEmail').focus(); }
        return;
      }
      $('#authPassword').value = ''; $('#authPassword').removeAttribute('aria-invalid'); $('#authEmail').removeAttribute('aria-invalid');
      fillSignupForm(true);
      setAuthMode('in');
      $('#authEmail').value = d.email;
      $('#loginHint').textContent = T('auth.hintSignedUp'); $('#loginHint').hidden = false;
      toast(T(consent ? 'auth.okSignup' : 'auth.okSignupOff'));
      $('#authPassword').focus();
    }).catch(() => { setAuthBusy(false); showErr(err, T('auth.errServer')); });
}
/* POST /api/auth/login, keep the tokens, then load the profile and enter the app. */
export function logIn(email, password) {
  const err = $('#authError');
  setAuthBusy(true);
  fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) })
    .then(readJson).then(({ ok, j }) => {
      if (!ok) {
        setAuthBusy(false);
        const code = j && j.error_code;
        showErr(err, AUTH_ERR[code] ? T(AUTH_ERR[code]) : (j && j.message) || T('auth.errServer'));
        $('#authPassword').setAttribute('aria-invalid', 'true'); $('#authPassword').focus();
        return;
      }
      $('#authPassword').value = '';
      storeAuth(j);
      return startSession(true).finally(() => setAuthBusy(false));
    }).catch(() => { setAuthBusy(false); showErr(err, T('auth.errServer')); });
}
