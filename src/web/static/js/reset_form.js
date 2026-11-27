/* Reset password form rules (code + new password), kept apart from the DOM so tests/web can check
   them. resetFormError() returns the i18n key of the first problem, or null when it can be sent. */
(function (root) {
  'use strict';
  function resetFormError(form, otpLength, minPassword) {
    const f = form || {};
    const code = String(f.code ?? '');
    if (code.length !== otpLength || !/^[0-9]+$/.test(code)) return 'reset.errCode';
    if (!f.password || !f.password2) return 'reset.errNew';
    if (String(f.password).length < minPassword) return 'auth.errWeak';
    if (f.password !== f.password2) return 'pass.errMismatch';
    return null;
  }
  const api = { resetFormError };
  root.ResetForm = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
