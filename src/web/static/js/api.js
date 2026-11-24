import { T } from './i18n.js';
import { logout } from './modals/baseline_gate.js';
import { S } from './state.js';
import { openModal, toast } from './ui.js';

/* ---------- API calls + login session ----------
   The tokens from POST /api/auth/login are kept in localStorage, so F5 keeps the person logged in.
   api() adds `Authorization: Bearer`, and on a 401 swaps the refresh token for a new session once. */
export const AUTH_KEY = 'psa.auth';
export const MIN_PASSWORD = 8;   // same rule as the backend (src/app/auth.py)
export const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
export const AUTH_ERR = { email_taken: 'auth.errTaken', invalid_email: 'auth.errEmail', weak_password: 'auth.errWeak', invalid_credentials: 'auth.errLogin' };
export function loadAuth() {
  try { const a = JSON.parse(localStorage.getItem(AUTH_KEY) || 'null'); return a && a.access_token ? a : null; } catch (e) { return null; }
}
export function storeAuth(a) {
  S.auth = a;
  try { if (a) localStorage.setItem(AUTH_KEY, JSON.stringify(a)); else localStorage.removeItem(AUTH_KEY); } catch (e) { /* private mode: login lasts until reload */ }
}
export let authRefresh = null;
export function refreshAuth() {   // resolves true (new tokens), false (session over); rejects when the server cannot be reached
  if (!S.auth || !S.auth.refresh_token) return Promise.resolve(false);
  if (!authRefresh) {
    authRefresh = fetch('/api/auth/refresh', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh_token: S.auth.refresh_token }) })
      .then(r => r.ok ? r.json().then(j => { storeAuth(j); return true; }) : (r.status === 401 ? false : Promise.reject(new Error('auth'))))
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

/* Settings > Delete account: DELETE /api/auth/account with the current password (ADR-011).
   A wrong password is 403 wrong_password, so api() does not treat it as a session that ended. */
export function deleteAccount(password) {
  return api('/api/auth/account', { method: 'DELETE', json: { password } });
}
