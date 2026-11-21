import { AUTH_ERR, EMAIL_RE, MIN_PASSWORD, api, readJson, storeAuth } from '../api.js';
import { T } from '../i18n.js';
import { loadBaseline, openBaselineGate } from '../modals/baseline_gate.js';
import { go, moveNavPill, moveSegPills, renderAccount, showView, slideIn, syncHeader } from '../nav.js';
import { heroLightsOn } from '../screens/home.js';
import { loadHistory } from '../screens/history.js';
import { setStageAuth } from '../screens/landing.js';
import { loadSavedScripts } from '../screens/saved_scripts.js';
import { applyFollowWpm } from '../screens/practice.js';
import { addBubble, fillTopicSelect, renderChatFile, restoreChat } from '../screens/script_studio.js';
import { CONFIG, RENDER, S } from '../state.js';
import { openModal, toast, withBusy } from '../ui.js';
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
  ['eSuName', 'eSuAge', 'eSuAccent'].forEach(i => $('#' + i).classList.remove('show'));
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
  resetOtpStep();
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
  S.chatHistory = [];
  // The greeting always opens the chat. It is not stored: it is made again here, so a new display name shows.
  addBubble('ai', '<p></p>', false).querySelector('p').textContent = T('script.greeting', { name: S.user.name });
  restoreChat();   // then the latest conversation kept in localStorage, if any
  S.chatFile = null; renderChatFile(); $('#composerInput').value = ''; S.composerFolded = false; clearErr($('#composerError'));
}
export function enterApp(fresh) {
  S.texts = { mine: null, sample: null, own: null }; S.pickerTab = 'mine'; S.audio = null; S.currentSession = null; S.choosing = true;
  S.scrollPos = {}; S.scrollKey = null;   // a new log in starts every screen at the top
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
  S.profile = { displayName: p.display_name || null, gender: p.gender || null, age: p.age != null ? p.age : null, accent: p.target_accent };
  S.consent = !!p.consent_recording;
  S.avatar = p.avatar_url || null;
  applyFollowWpm(p.preferences);
}
/* Full-screen loading screen: from the Log in click (or page load with stored tokens) until Home is
   drawn with everything it needs. Only one loading screen: checking the password is part of it. */
export function showAppLoader(on) {
  const el = $('#appLoader');
  if (on) { el.hidden = false; el.classList.remove('out'); return; }
  if (el.hidden) return;
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) { el.hidden = true; return; }
  el.classList.add('out');   // .out lets clicks and scrolling through while it fades
  setTimeout(() => { el.hidden = true; el.classList.remove('out'); }, 400);
}
/* After log in, and on page load when tokens are stored. Everything Home and the first screens show
   is loaded first, under the loading screen: the profile, history with the latest full scores, the
   baseline, the saved script list and the web fonts. Only then is the app shown, drawn once, and
   Home slides in. Nothing on Home changes afterwards. The Baseline Gate (if needed) opens after. */
export function startSession(fresh) {
  showAppLoader(true);
  const fail = msg => {
    showAppLoader(false);
    if (fresh) showErr($('#authError'), msg || T('auth.errServer')); else toast(T('auth.errServer'), true);
  };
  return api('/api/profile').then(readJson).then(({ ok, status, j }) => {
    if (!ok) {
      if (status === 401) { showAppLoader(false); return; }   // sessionEnded() already ran
      if (status === 404) storeAuth(null);                     // account without a profile row: cannot continue
      fail(j && j.message);
      return;
    }
    applyProfile(j);
    S.sessions = []; S.baseline = null; S.savedScripts = null;
    S.screen = null;   // no screen is drawn by the loaders below; enterApp draws Home once, with all the data
    const user = S.user;
    const capped = (p, ms) => Promise.race([Promise.resolve(p).catch(() => {}), new Promise(r => setTimeout(r, ms))]);
    const fonts = document.fonts ? document.fonts.ready : null;
    return Promise.all([capped(loadHistory(), 10000), capped(loadBaseline(false), 10000), capped(loadSavedScripts(), 10000), capped(fonts, 3000)]).then(([, needGate]) => {
      if (S.user !== user) { showAppLoader(false); return; }
      enterApp(fresh);
      syncHeader(); moveNavPill(false);
      // two frames: the browser has laid out and painted the final Home before the loader fades.
      // A hidden tab runs no frames, so a timer reveals it anyway.
      let shown = false;
      const reveal = () => {
        if (shown) return;
        shown = true;
        showAppLoader(false);
        const cur = $('.screen.active');
        if (cur) slideIn(cur, 1, 120);
        if (S.screen === 'home') heroLightsOn();
        if (fresh) toast(T('auth.okLogin'));
        if (needGate === true) openBaselineGate();
      };
      requestAnimationFrame(() => requestAnimationFrame(reveal));
      setTimeout(reveal, 200);
    });
  }).catch(() => fail());
}
export function readSignupProfile() {
  const name = $('#signupExtraDisplayName').value.trim();
  const age = $('#signupExtraAge').value.trim(), acc = $('input[name=signupExtraAccent]:checked');
  const n = age === '' ? null : Number(age);
  const okAge = n === null || (Number.isInteger(n) && n >= 1 && n <= 120);
  $('#eSuName').classList.toggle('show', !name); $('#signupExtraDisplayName').setAttribute('aria-invalid', String(!name));
  $('#eSuAge').classList.toggle('show', !okAge); $('#signupExtraAge').setAttribute('aria-invalid', String(!okAge));
  $('#eSuAccent').classList.toggle('show', !acc);
  if (!name) { $('#signupExtraDisplayName').focus(); return null; }
  if (!okAge) { $('#signupExtraAge').focus(); return null; }
  if (!acc) { $('input[name=signupExtraAccent]').focus(); return null; }
  return { displayName: name, gender: $('#signupExtraGender').value || null, age: n, accent: acc.value };
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
  withBusy(api('/api/auth/signup', { method: 'POST', json: { email: d.email, password: d.password, display_name: d.profile.displayName, target_accent: d.profile.accent, age: d.profile.age, gender: d.profile.gender, consent_recording: consent } }), T('busy.signingUp'))
    .then(readJson).then(({ ok, j }) => {
      setAuthBusy(false);
      const code = j && j.error_code;
      if (!ok) {
        showErr(err, AUTH_ERR[code] ? T(AUTH_ERR[code]) : (j && j.message) || T('auth.errServer'));
        if (code === 'email_taken' || code === 'invalid_email') { $('#authEmail').setAttribute('aria-invalid', 'true'); $('#authEmail').focus(); }
        return;
      }
      if (j && j.verification_required === true) {
        $('#authPassword').value = ''; $('#authPassword2').value = '';
        openOtpStep(d.email, { from: 'up', consent, draft: d });   // the form goes with the code: a repeat sign-up keeps its new password
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
  showAppLoader(true);   // the same loading screen stays up until Home is ready
  fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) })
    .then(readJson).then(({ ok, j }) => {
      if (!ok) {
        setAuthBusy(false); showAppLoader(false);
        const code = j && j.error_code;
        if (code === 'email_not_confirmed') {
          $('#authPassword').value = '';
          openOtpStep(email, { from: 'in', resend: true });
          return;
        }
        showErr(err, AUTH_ERR[code] ? T(AUTH_ERR[code]) : (j && j.message) || T('auth.errServer'));
        $('#authPassword').setAttribute('aria-invalid', 'true'); $('#authPassword').focus();
        return;
      }
      $('#authPassword').value = '';
      storeAuth(j);
      return startSession(true).finally(() => setAuthBusy(false));
    }).catch(() => { setAuthBusy(false); showAppLoader(false); showErr(err, T('auth.errServer')); });
}


const OTP_ERR = { otp_invalid: 'auth.errOtpInvalid', otp_expired: 'auth.errOtpExpired', rate_limited: 'auth.errRateLimited', invalid_email: 'auth.errEmail' };
let otp = null, otpMotion = null, otpBusy = false, otpInitialized = false;
const otpConfig = () => ({ otp_length: CONFIG.auth?.otp_length ?? 6, resend_cooldown_s: CONFIG.auth?.resend_cooldown_s ?? 60, unconfirmed_ttl_min: CONFIG.auth?.unconfirmed_ttl_min ?? 60 });

function morphAuthCard(leavingEls, apply, enteringEls) {
  const a = $('#lAuth');
  otpMotion = null;
  [a, ...leavingEls, ...enteringEls].forEach(el => el.getAnimations().forEach(animation => animation.cancel()));
  a.style.overflow = '';
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || !a.animate || !$('#lStage').classList.contains('is-auth')) {
    apply(); return Promise.resolve();
  }
  const token = {}; otpMotion = token;
  const r0 = a.getBoundingClientRect();
  const fades = leavingEls.map(el => el.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 200, easing: 'ease-in', fill: 'forwards' }));
  return Promise.all(fades.map(f => f.finished)).then(() => {
    if (otpMotion !== token) return;
    apply(); fades.forEach(f => f.cancel());
    const r1 = a.getBoundingClientRect();
    a.style.overflow = 'hidden';
    const grow = a.animate([{ width: r0.width + 'px', height: r0.height + 'px' }, { width: r1.width + 'px', height: r1.height + 'px' }], { duration: 420, easing: 'cubic-bezier(.65, 0, .35, 1)' });
    enteringEls.forEach(el => el.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 340, delay: 160, easing: 'ease-out', fill: 'backwards' }));
    return grow.finished.then(() => { if (otpMotion === token) { a.style.overflow = ''; otpMotion = null; } });
  }).catch(() => {});
}
function resetOtpStep() {
  if (otp) clearInterval(otp.timer);
  otp = null; otpMotion = null; otpBusy = false;
  const a = $('#lAuth');
  [a, a.querySelector('.seg'), $('#authForm'), $('#otpStep')].forEach(el => el.getAnimations().forEach(animation => animation.cancel()));
  a.style.overflow = ''; a.querySelector('.seg').hidden = false; $('#authForm').hidden = false; $('#otpStep').hidden = true;
  $('#otpVerify').disabled = false; $('#otpVerify').removeAttribute('aria-busy');
}
function updateOtpCountdown() {
  if (!otp) return;
  const left = window.OtpUtils.cooldownLeft(otp.sentAt, Date.now(), otpConfig().resend_cooldown_s), button = $('#otpResend');
  button.disabled = left > 0;
  button.textContent = left ? T('auth.otpResendIn', { t: window.OtpUtils.formatCountdown(left) }) : T('auth.otpResend');
  if (!left && otp.timer) { clearInterval(otp.timer); otp.timer = null; }
}
function startOtpCountdown() {
  if (!otp) return;
  clearInterval(otp.timer); otp.timer = null; updateOtpCountdown();
  if (otp && window.OtpUtils.cooldownLeft(otp.sentAt, Date.now(), otpConfig().resend_cooldown_s) > 0) otp.timer = setInterval(updateOtpCountdown, 1000);
}
function openOtpStep(email, { from, consent, resend, draft }) {
  initOtp();
  if (otp) clearInterval(otp.timer);
  otp = { email, from, consent, draft: draft || null, sentAt: resend ? null : Date.now(), timer: null };
  const current = otp, n = otpConfig().otp_length, input = $('#otpCode'), step = $('#otpStep'), a = $('#lAuth');
  $('#otpSentTo').textContent = T(from === 'in' ? 'auth.otpSentLogin' : 'auth.otpSent', { n, email });
  $('#otpExpiry').textContent = T('auth.otpExpiry', { n: otpConfig().unconfirmed_ttl_min });   // purge: ADR-011, SQL 0006
  input.maxLength = n; input.style.setProperty('--otp-len', n); input.value = ''; input.removeAttribute('aria-invalid');
  clearErr($('#otpError')); $('#otpHint').hidden = true; $('#otpHint').textContent = '';
  startOtpCountdown();
  morphAuthCard([a.querySelector('.seg'), $('#authForm')], () => { a.querySelector('.seg').hidden = true; $('#authForm').hidden = true; step.hidden = false; }, [step]).then(() => { if (otp === current) input.focus(); });
  if (resend) resendOtp();
}
function closeOtpStep(mode) {
  const current = otp, a = $('#lAuth');
  if (current) clearInterval(current.timer);
  otp = null;
  return morphAuthCard([$('#otpStep')], () => {
    $('#otpStep').hidden = true; a.querySelector('.seg').hidden = false; $('#authForm').hidden = false;
    moveSegPills(false, a);
    if (S.authMode !== mode) applyAuthMode(mode);
  }, [a.querySelector('.seg'), $('#authForm')]).then(() => { if (!otp) moveSegPills(false, a); });
}
async function resendOtp() {
  const current = otp, button = $('#otpResend');
  if (!current || button.disabled || otpBusy) return;
  $('#otpHint').hidden = true; $('#otpHint').textContent = ''; clearErr($('#otpError'));
  button.disabled = true; button.textContent = T('auth.otpResending');
  try {
    const { ok, status } = await readJson(await fetch('/api/auth/resend-otp', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: current.email }) }));
    if (otp !== current) return;
    if (ok) { $('#otpHint').hidden = false; requestAnimationFrame(() => { $('#otpHint').textContent = T('auth.otpResent'); }); current.sentAt = Date.now(); startOtpCountdown(); $('#otpCode').focus(); }
    else if (status === 429) { showErr($('#otpError'), T('auth.errRateLimited')); current.sentAt = Date.now(); startOtpCountdown(); $('#otpCode').focus(); }
    else { showErr($('#otpError'), T('auth.errServer')); button.disabled = false; button.textContent = T('auth.otpResend'); }
  } catch (_) { if (otp === current) { showErr($('#otpError'), T('auth.errServer')); button.disabled = false; button.textContent = T('auth.otpResend'); } }
}
async function submitOtp(e) {
  e.preventDefault();
  if (!otp || otpBusy) return;
  const current = otp, input = $('#otpCode'), n = otpConfig().otp_length, error = $('#otpError'), button = $('#otpVerify');
  if (!window.OtpUtils.isCompleteOtp(input.value, n)) { showErr(error, T('auth.errOtpFormat', { n })); input.setAttribute('aria-invalid', 'true'); input.focus(); return; }
  otpBusy = true; button.disabled = true; button.setAttribute('aria-busy', 'true'); clearErr(error);
  try {
    /* From Sign up the latest form goes with the code (ADR-010 D3, amended): signing up again with an email that is
       not confirmed yet keeps the first password otherwise. The server applies it only after the code is accepted. */
    const body = { email: current.email, token: input.value }, d = current.draft;
    if (d) Object.assign(body, { password: d.password, profile: { display_name: d.profile.displayName, target_accent: d.profile.accent, age: d.profile.age, gender: d.profile.gender, consent_recording: current.consent === true } });
    const { ok, j } = await readJson(await withBusy(fetch('/api/auth/verify-otp', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }), T('busy.verifying')));
    if (otp !== current) return;
    if (ok) {
      if (current.from === 'up') fillSignupForm(true);
      await closeOtpStep('in');
      if (otp) return;
      $('#authEmail').value = current.email; $('#authPassword').value = ''; $('#authPassword2').value = '';
      $('#loginHint').textContent = T(j && j.password_updated === false ? 'auth.hintVerifiedOldPassword' : 'auth.hintVerified'); $('#loginHint').hidden = false;
      toast(T(current.consent === false ? 'auth.okVerifiedOff' : 'auth.okVerified')); $('#authPassword').focus();
    } else {
      const code = j && j.error_code;
      showErr(error, OTP_ERR[code] ? T(OTP_ERR[code]) : (j && j.message) || T('auth.errServer'));
      input.setAttribute('aria-invalid', 'true'); input.focus(); input.select();
    }
  } catch (_) { if (otp === current) { showErr(error, T('auth.errServer')); input.setAttribute('aria-invalid', 'true'); input.focus(); input.select(); } }
  finally { otpBusy = false; button.disabled = false; button.removeAttribute('aria-busy'); }
}
function initOtp() {
  if (otpInitialized) return;
  otpInitialized = true;
  const input = $('#otpCode');
  input.addEventListener('input', () => { input.value = window.OtpUtils.normalizeOtp(input.value, otpConfig().otp_length); input.removeAttribute('aria-invalid'); clearErr($('#otpError')); });
  input.addEventListener('paste', e => {
    e.preventDefault();
    const value = input.value.slice(0, input.selectionStart) + e.clipboardData.getData('text') + input.value.slice(input.selectionEnd);
    input.value = window.OtpUtils.normalizeOtp(value, otpConfig().otp_length); input.removeAttribute('aria-invalid'); clearErr($('#otpError'));
  });
  $('#otpForm').addEventListener('submit', submitOtp);
  $('#otpResend').addEventListener('click', resendOtp);
  $('#otpBack').addEventListener('click', () => {
    if (!otp || otpBusy) return;
    const mode = otp.from;
    $('#authPassword').value = ''; $('#authPassword2').value = '';
    closeOtpStep(mode).then(() => { if (!otp) $('#authEmail').focus(); });
  });
}
