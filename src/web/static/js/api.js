import { T } from './i18n.js';
import { logout } from './modals/baseline_gate.js';
import { S } from './state.js';
import { openModal, toast } from './ui.js';

/* ---------- API calls + login session ----------
   The access token lives only in memory (S.auth). The refresh token is an HttpOnly cookie that
   JavaScript never sees, sent by the browser only to /api/auth/*. A page load (F5) and every 401
   ask POST /api/auth/refresh for a new access token; api() adds `Authorization: Bearer`. */
export const MIN_PASSWORD = 8;   // same rule as the backend (src/app/auth.py)
export const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
export const AUTH_ERR = { email_taken: 'auth.errTaken', invalid_email: 'auth.errEmail', weak_password: 'auth.errWeak', invalid_credentials: 'auth.errLogin' };
const OLD_AUTH_KEY = 'psa.auth';   // where older versions kept both tokens; removed on load
const REFRESH_RETRY_MS = 300;
export function dropOldStoredTokens() {
  try { localStorage.removeItem(OLD_AUTH_KEY); } catch (e) { /* storage blocked: nothing stored either */ }
}
export function storeAuth(a) {
  S.auth = a && a.access_token ? { access_token: a.access_token, expires_in: a.expires_in, user_id: a.user_id } : null;
}
function postRefresh() {
  return fetch('/api/auth/refresh', { method: 'POST', credentials: 'same-origin' });
}
export let authRefresh = null;
/* Resolves true (new access token), false (session over); rejects when the server cannot be reached.
   A refresh token works once, so two tabs refreshing together can make one of them get 401: that
   tab tries once more after a short wait, when the other tab has already set the new cookie. */
export function refreshAuth() {
  if (!authRefresh) {
    const asJson = r => r.json().then(j => { storeAuth(j); return true; });
    authRefresh = postRefresh()
      .then(r => r.status !== 401 ? r : new Promise(done => setTimeout(done, REFRESH_RETRY_MS)).then(postRefresh))
      .then(r => r.ok ? asJson(r) : (r.status === 401 ? false : Promise.reject(new Error('auth'))))
      .finally(() => { authRefresh = null; });
  }
  return authRefresh;
}
export function api(url, opts) {
  const o = Object.assign({}, opts || {}), json = o.json;
  delete o.json;
  if (json !== undefined) o.body = JSON.stringify(json);
  const send = () => {
    const h = Object.assign({}, o.headers || {});
    if (S.auth) h.Authorization = 'Bearer ' + S.auth.access_token;
    if (json !== undefined) h['Content-Type'] = 'application/json';
    return fetch(url, Object.assign({}, o, { headers: h }));
  };
  return send().then(res => {
    if (res.status === 403) checkConsentLost(res);
    if (res.status !== 401 || !S.auth) return res;
    return refreshAuth().then(ok => { if (ok) return send(); sessionEnded(); return res; }, () => res);
  });
}
export const readJson = res => res.json().catch(() => null).then(j => ({ res, ok: res.ok, status: res.status, j }));
/* 403 consent_required: recording was turned off (for example in another tab). The caller still
   gets the response; the Consent Modal opens so the user can turn recording on again. */
function checkConsentLost(res) {
  res.clone().json().then(j => {
    if (!j || j.error_code !== 'consent_required' || !S.user) return;
    S.consent = false;
    openModal('consentModal', { focus: '#mcAllow' });
  }).catch(() => {});
}
export function sessionEnded() {
  storeAuth(null);
  if (S.user) { logout(true); toast(T('auth.expired'), true); }
}

/* Forgot password (Log in and Settings): POST without the access token, so a 401 never logs out.
   Both resolve to readJson's { res, ok, status, j }. */
function postJson(url, body) {
  return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(readJson);
}
export const sendResetCode = email => postJson('/api/auth/forgot-password', { email });
export const resetPassword = (email, token, newPassword) => postJson('/api/auth/reset-password', { email, token, new_password: newPassword });
export const RESET_ERR = { otp_invalid: 'auth.errOtpInvalid', otp_expired: 'auth.errOtpExpired', rate_limited: 'auth.errRateLimited', invalid_email: 'auth.errEmail', weak_password: 'auth.errWeak' };

/* Settings > Delete account: DELETE /api/auth/account with the current password (ADR-011).
   A wrong password is 403 wrong_password, so api() does not treat it as a session that ended. */
export function deleteAccount(password) {
  return api('/api/auth/account', { method: 'DELETE', json: { password } });
}
