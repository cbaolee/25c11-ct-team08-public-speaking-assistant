(function (root) {
  'use strict';
  function normalizeOtp(raw, len) {
    return String(raw ?? '').replace(/[０-９]/g, c => String.fromCharCode(c.charCodeAt(0) - 0xFEE0)).replace(/[^0-9]/g, '').slice(0, len);
  }
  function isCompleteOtp(code, len) { return typeof code === 'string' && code.length === len && /^[0-9]+$/.test(code); }
  function cooldownLeft(sentAtMs, nowMs, cooldownS) { return sentAtMs == null ? 0 : Math.max(0, Math.ceil((sentAtMs + cooldownS * 1000 - nowMs) / 1000)); }
  function formatCountdown(s) { return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); }
  const api = { normalizeOtp, isCompleteOtp, cooldownLeft, formatCountdown };
  root.OtpUtils = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
