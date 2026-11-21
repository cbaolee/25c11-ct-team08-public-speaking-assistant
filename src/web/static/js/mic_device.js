/* Microphone choice (Settings > Audio, ADR-011). Pure helpers, no DOM: loaded as a classic
   script (window.MicDevice) and by node --test (tests/web/mic_device.test.js).
   The chosen deviceId is kept in localStorage per user: a deviceId belongs to one browser
   (and changes when site data is cleared), so it is never sent to the server.
   Only the device is chosen. No echoCancellation / noiseSuppression / autoGainControl
   constraints are added or changed: baseline and practice must go through one capture chain. */
(function (root) {
  'use strict';
  const KEY = 'psa.mic.';
  const store = s => s || (typeof localStorage !== 'undefined' ? localStorage : null);

  /* -> Promise<{ mics: [{ id, label }], unnamed }>. The first entry is always the browser default
     (id ''). Before the mic permission is granted, browsers hide labels (and Firefox also the ids):
     entries without an id cannot be chosen and are left out; entries without a label get
     "Microphone 1, 2, ...". `unnamed` is true when names were hidden, so the UI can hint at the test. */
  function listMics(mediaDevices, labels) {
    const def = { id: '', label: labels.def };
    if (!mediaDevices || typeof mediaDevices.enumerateDevices !== 'function') return Promise.resolve({ mics: [def], unnamed: false });
    return Promise.resolve(mediaDevices.enumerateDevices()).then(devices => {
      const mics = [def], seen = new Set(['', 'default']);   // Chrome's "default" entry is the same as our first option
      let unnamed = false, n = 0;
      (devices || []).filter(d => d && d.kind === 'audioinput').forEach(d => {
        if (!d.label) unnamed = true;
        if (!d.deviceId || seen.has(d.deviceId)) return;
        seen.add(d.deviceId); n += 1;
        mics.push({ id: d.deviceId, label: d.label || labels.nth(n) });
      });
      return { mics, unnamed };
    }, () => ({ mics: [def], unnamed: false }));
  }
  function getSavedMicId(userId, storage) {
    const s = store(storage);
    if (!userId || !s) return '';
    try { return s.getItem(KEY + userId) || ''; } catch (e) { return ''; }
  }
  function saveMicId(userId, id, storage) {          // '' (default microphone) removes the entry
    const s = store(storage);
    if (!userId || !s) return;
    try { if (id) s.setItem(KEY + userId, id); else s.removeItem(KEY + userId); } catch (e) { /* storage blocked */ }
  }
  function audioConstraints(id) { return id ? { deviceId: { exact: id } } : true; }
  /* The saved device is gone (unplugged, or ids reset with the site data). */
  function isMissingDevice(err) { const n = err && err.name; return n === 'OverconstrainedError' || n === 'NotFoundError'; }
  /* Open the mic on `id`. If that device is missing, call onMissing() and try once more with the
     default microphone (only when fallback is true). Other errors (denied, ...) are passed on. */
  function openMic(mediaDevices, id, opts) {
    const o = opts || {};
    return mediaDevices.getUserMedia({ audio: audioConstraints(id) }).catch(err => {
      if (!id || !isMissingDevice(err)) throw err;
      if (o.onMissing) o.onMissing(err);
      if (!o.fallback) throw err;
      return mediaDevices.getUserMedia({ audio: true });
    });
  }
  const api = { listMics, getSavedMicId, saveMicId, audioConstraints, isMissingDevice, openMic };
  root.MicDevice = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
