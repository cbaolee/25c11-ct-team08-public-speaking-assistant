import { EMAIL_RE, MIN_PASSWORD, RESET_ERR, resetPassword, sendResetCode } from '../api.js';
import { T } from '../i18n.js';
import { moveSegPills } from '../nav.js';
import { CONFIG } from '../state.js';
import { withBusy } from '../ui.js';
import { $, clearErr, showErr } from '../utils.js';
import { applyAuthMode, morphAuthCard } from './auth_panel.js';

/* Reset password step in the Auth Panel (Log in > Forgot password?).
   Stage 1: the email -> POST /api/auth/forgot-password. Stage 2: the code, a new password and a
   repeat -> POST /api/auth/reset-password. The server ends every session of the account. */
let reset = null;   // { email, sentAt, timer } once a code was asked for
let resetBusy = false, resetInitialized = false;
const otpLength = () => CONFIG.auth?.otp_length ?? 6;
const cooldownS = () => CONFIG.auth?.resend_cooldown_s ?? 60;

const seg = () => $('#lAuth').querySelector('.seg');
function showStage(stage) {
  $('#resetEmailForm').hidden = stage !== 'email';
  $('#resetCodeForm').hidden = stage !== 'code';
}
function stopCountdown() { if (reset && reset.timer) { clearInterval(reset.timer); reset.timer = null; } }
function updateCountdown() {
  const button = $('#resetResend');
  if (!reset || $('#resetStep').hidden) { stopCountdown(); return; }
  const left = window.OtpUtils.cooldownLeft(reset.sentAt, Date.now(), cooldownS());
  button.disabled = left > 0;
  button.textContent = left ? T('auth.otpResendIn', { t: window.OtpUtils.formatCountdown(left) }) : T('auth.otpResend');
  if (!left) stopCountdown();
}
function startCountdown() {
  stopCountdown(); updateCountdown();
  if (reset && window.OtpUtils.cooldownLeft(reset.sentAt, Date.now(), cooldownS()) > 0) reset.timer = setInterval(updateCountdown, 1000);
}
function clearCodeForm() {
  ['#resetCode', '#resetNew', '#resetNew2'].forEach(id => { $(id).value = ''; $(id).removeAttribute('aria-invalid'); });
  clearErr($('#resetError')); $('#resetHint').hidden = true; $('#resetHint').textContent = '';
}

export function openResetStep() {
  initReset();
  stopCountdown(); reset = null; resetBusy = false;
  const step = $('#resetStep');
  $('#resetEmail').value = $('#authEmail').value.trim(); $('#resetEmail').removeAttribute('aria-invalid');
  clearErr($('#resetEmailError')); clearCodeForm();
  $('#resetCode').maxLength = otpLength(); $('#resetCode').style.setProperty('--otp-len', otpLength());
  showStage('email');
  morphAuthCard([seg(), $('#authForm')], () => { seg().hidden = true; $('#authForm').hidden = true; step.hidden = false; }, [step])
    .then(() => { if (!step.hidden) $('#resetEmail').focus(); });
}
function closeResetStep() {
  stopCountdown(); reset = null;
  const a = $('#lAuth');
  return morphAuthCard([$('#resetStep')], () => {
    $('#resetStep').hidden = true; seg().hidden = false; $('#authForm').hidden = false;
    applyAuthMode('in'); moveSegPills(false, a);
  }, [seg(), $('#authForm')]).then(() => moveSegPills(false, a));
}

/* Ask for a code. A 429 means a code was sent a moment ago: it can still be used. */
async function askForCode(email) {
  const { ok, status } = await sendResetCode(email);
  if (!ok && status !== 429) return { ok: false };
  if (!reset || reset.email !== email) { stopCountdown(); reset = { email, sentAt: null, timer: null }; }
  reset.sentAt = Date.now();
  return { ok: true, limited: !ok };
}
async function submitEmail(e) {
  e.preventDefault();
  if (resetBusy) return;
  const input = $('#resetEmail'), err = $('#resetEmailError'), button = $('#resetSend');
  const email = input.value.trim().toLowerCase();
  if (!EMAIL_RE.test(email)) { showErr(err, T('auth.errEmail')); input.setAttribute('aria-invalid', 'true'); input.focus(); return; }
  input.removeAttribute('aria-invalid'); clearErr(err);
  resetBusy = true; button.disabled = true;
  try {
    const r = await withBusy(askForCode(email), T('busy.sending'));
    if (!r.ok) { showErr(err, T('auth.errServer')); return; }
    $('#resetSentTo').textContent = T('reset.sent', { email, n: otpLength() });
    clearCodeForm(); showStage('code'); startCountdown();
    if (r.limited) showErr($('#resetError'), T('auth.errRateLimited'));
    $('#resetCode').focus();
  } catch (_) { showErr(err, T('auth.errServer')); }
  finally { resetBusy = false; button.disabled = false; }
}
function resendFailed() {
  showErr($('#resetError'), T('auth.errServer'));
  $('#resetResend').disabled = false; $('#resetResend').textContent = T('auth.otpResend');
}
async function resendCode() {
  if (!reset || resetBusy || $('#resetResend').disabled) return;
  const current = reset;
  $('#resetResend').disabled = true; $('#resetResend').textContent = T('auth.otpResending');
  clearErr($('#resetError')); $('#resetHint').hidden = true;
  try {
    const r = await askForCode(current.email);
    if (reset !== current) return;
    if (!r.ok) { resendFailed(); return; }
    if (r.limited) showErr($('#resetError'), T('auth.errRateLimited'));
    else { $('#resetHint').hidden = false; $('#resetHint').textContent = T('auth.otpResent'); }
    startCountdown(); $('#resetCode').focus();
  } catch (_) { if (reset === current) resendFailed(); }
}
const FIELD_OF = { 'reset.errCode': '#resetCode', 'pass.errMismatch': '#resetNew2', 'auth.errWeak': '#resetNew' };
async function submitCode(e) {
  e.preventDefault();
  if (!reset || resetBusy) return;
  const current = reset, err = $('#resetError'), button = $('#resetSave');
  const form = { code: $('#resetCode').value, password: $('#resetNew').value, password2: $('#resetNew2').value };
  const problem = window.ResetForm.resetFormError(form, otpLength(), MIN_PASSWORD);
  if (problem) {
    showErr(err, T(problem, { n: otpLength() }));
    const field = FIELD_OF[problem] || (form.password ? '#resetNew2' : '#resetNew');
    $(field).setAttribute('aria-invalid', 'true'); $(field).focus();
    return;
  }
  resetBusy = true; button.disabled = true; button.setAttribute('aria-busy', 'true'); clearErr(err);
  try {
    const { ok, j } = await withBusy(resetPassword(current.email, form.code, form.password), T('busy.saving'));
    if (reset !== current) return;
    if (!ok) {
      const code = j && j.error_code;
      showErr(err, RESET_ERR[code] ? T(RESET_ERR[code]) : (j && j.message) || T('auth.errServer'));
      const field = code === 'weak_password' ? '#resetNew' : '#resetCode';
      $(field).setAttribute('aria-invalid', 'true'); $(field).focus();
      return;
    }
    await closeResetStep();
    $('#authEmail').value = current.email; $('#authPassword').value = '';
    $('#loginHint').textContent = T('reset.done'); $('#loginHint').hidden = false;
    $('#authPassword').focus();
  } catch (_) { if (reset === current) showErr(err, T('auth.errServer')); }
  finally { resetBusy = false; button.disabled = false; button.removeAttribute('aria-busy'); }
}
function initReset() {
  if (resetInitialized) return;
  resetInitialized = true;
  const code = $('#resetCode');
  code.addEventListener('input', () => { code.value = window.OtpUtils.normalizeOtp(code.value, otpLength()); code.removeAttribute('aria-invalid'); clearErr($('#resetError')); });
  ['#resetNew', '#resetNew2'].forEach(id => $(id).addEventListener('input', () => $(id).removeAttribute('aria-invalid')));
  $('#resetEmailForm').addEventListener('submit', submitEmail);
  $('#resetCodeForm').addEventListener('submit', submitCode);
  $('#resetResend').addEventListener('click', resendCode);
  $('#resetBack').addEventListener('click', () => {
    if (resetBusy) return;
    closeResetStep().then(() => $('#authEmail').focus());
  });
}
