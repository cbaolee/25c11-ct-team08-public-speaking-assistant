'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { isValidAge, isSignupReady } = require('../../src/web/static/js/signup_form.js');

const READY = { email: 'ana@example.com', password: 'password-1', password2: 'password-1', displayName: 'Ana', age: '21', accent: 'American', consent: true };

test('isValidAge allows an empty age and whole numbers from 1 to 120', () => {
  assert.equal(isValidAge(''), true); assert.equal(isValidAge(null), true); assert.equal(isValidAge(' 30 '), true);
  assert.equal(isValidAge('0'), false); assert.equal(isValidAge('121'), false); assert.equal(isValidAge('2.5'), false); assert.equal(isValidAge('abc'), false);
});
test('isSignupReady is true only when every field is valid and consent is ticked', () => {
  assert.equal(isSignupReady(READY, 8), true);
  assert.equal(isSignupReady({ ...READY, age: '' }, 8), true);
  assert.equal(isSignupReady({ ...READY, consent: false }, 8), false);
  assert.equal(isSignupReady({ ...READY, email: 'ana@example' }, 8), false);
  assert.equal(isSignupReady({ ...READY, password: 'short', password2: 'short' }, 8), false);
  assert.equal(isSignupReady({ ...READY, password2: 'password-2' }, 8), false);
  assert.equal(isSignupReady({ ...READY, displayName: '  ' }, 8), false);
  assert.equal(isSignupReady({ ...READY, age: '200' }, 8), false);
  assert.equal(isSignupReady({ ...READY, accent: null }, 8), false);
  assert.equal(isSignupReady(null, 8), false);
});
