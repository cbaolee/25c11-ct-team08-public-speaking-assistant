'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { resetFormError } = require('../../src/web/static/js/reset_form.js');

const OK = { code: '123456', password: 'password-1', password2: 'password-1' };

test('resetFormError returns null for a complete form', () => {
  assert.equal(resetFormError(OK, 6, 8), null);
});
test('resetFormError names the first problem', () => {
  assert.equal(resetFormError({ ...OK, code: '12345' }, 6, 8), 'reset.errCode');
  assert.equal(resetFormError({ ...OK, code: '12345a' }, 6, 8), 'reset.errCode');
  assert.equal(resetFormError({ ...OK, password2: '' }, 6, 8), 'reset.errNew');
  assert.equal(resetFormError({ ...OK, password: 'short', password2: 'short' }, 6, 8), 'auth.errWeak');
  assert.equal(resetFormError({ ...OK, password2: 'password-2' }, 6, 8), 'pass.errMismatch');
  assert.equal(resetFormError(null, 6, 8), 'reset.errCode');
});
