'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { normalizeOtp, isCompleteOtp, cooldownLeft, formatCountdown } = require('../../src/web/static/js/otp_utils.js');
test('normalizeOtp filters and converts pasted digits', () => {
  assert.equal(normalizeOtp(null, 6), ''); assert.equal(normalizeOtp(undefined, 6), '');
  assert.equal(normalizeOtp('Code: 123 456', 6), '123456'); assert.equal(normalizeOtp('123-4567', 6), '123456');
  assert.equal(normalizeOtp('０１２３４５６７８９', 10), '0123456789'); assert.equal(normalizeOtp('no digits', 6), '');
});
test('isCompleteOtp requires exactly ASCII digits', () => {
  assert.equal(isCompleteOtp('123456', 6), true); assert.equal(isCompleteOtp('12345', 6), false);
  assert.equal(isCompleteOtp('１２３４５６', 6), false); assert.equal(isCompleteOtp('12345a', 6), false); assert.equal(isCompleteOtp(null, 6), false);
});
test('cooldownLeft rounds up and clamps', () => {
  assert.equal(cooldownLeft(null, 0, 60), 0); assert.equal(cooldownLeft(0, 0, 60), 60);
  assert.equal(cooldownLeft(1000, 59401, 60), 2); assert.equal(cooldownLeft(0, 60000, 60), 0); assert.equal(cooldownLeft(0, 70000, 60), 0);
});
test('formatCountdown pads seconds', () => {
  assert.equal(formatCountdown(42), '0:42'); assert.equal(formatCountdown(60), '1:00'); assert.equal(formatCountdown(5), '0:05'); assert.equal(formatCountdown(0), '0:00');
});
