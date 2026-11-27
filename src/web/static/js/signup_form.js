/* Sign up form rules, kept apart from the DOM so tests/web can check them.
   isSignupReady() decides when the Create account button turns on; the server checks again. */
(function (root) {
  'use strict';
  const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
  function isValidAge(ageText) {
    const text = String(ageText ?? '').trim();
    if (text === '') return true;   // age is optional
    const age = Number(text);
    return Number.isInteger(age) && age >= 1 && age <= 120;
  }
  function isSignupReady(form, minPassword) {
    const f = form || {};
    return EMAIL_RE.test(String(f.email ?? '').trim())
      && String(f.password ?? '').length >= minPassword
      && f.password2 === f.password
      && String(f.displayName ?? '').trim() !== ''
      && isValidAge(f.age)
      && !!f.accent
      && f.consent === true;
  }
  const api = { isValidAge, isSignupReady };
  root.SignupForm = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
