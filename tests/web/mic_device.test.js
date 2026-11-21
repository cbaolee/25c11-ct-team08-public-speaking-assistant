'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { listMics, getSavedMicId, saveMicId, audioConstraints, isMissingDevice, openMic } = require('../../src/web/static/js/mic_device.js');

const LABELS = { def: 'Default microphone', nth: n => 'Microphone ' + n };
const devices = list => ({ enumerateDevices: () => Promise.resolve(list) });
const memStore = () => { const m = new Map(); return { m, getItem: k => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: k => m.delete(k) }; };

test('listMics keeps audio inputs, default first, no duplicates', async () => {
  const r = await listMics(devices([
    { kind: 'audioinput', deviceId: 'default', label: 'Default - USB mic' },
    { kind: 'audioinput', deviceId: 'usb', label: 'USB mic' },
    { kind: 'audiooutput', deviceId: 'spk', label: 'Speakers' },
    { kind: 'videoinput', deviceId: 'cam', label: 'Camera' },
    { kind: 'audioinput', deviceId: 'usb', label: 'USB mic' },
    { kind: 'audioinput', deviceId: 'bt', label: 'Bluetooth headset' }
  ]), LABELS);
  assert.deepEqual(r.mics, [{ id: '', label: 'Default microphone' }, { id: 'usb', label: 'USB mic' }, { id: 'bt', label: 'Bluetooth headset' }]);
  assert.equal(r.unnamed, false);
});
test('listMics names unlabelled devices and flags them', async () => {
  const r = await listMics(devices([{ kind: 'audioinput', deviceId: 'a', label: '' }, { kind: 'audioinput', deviceId: 'b', label: '' }]), LABELS);
  assert.deepEqual(r.mics.map(m => m.label), ['Default microphone', 'Microphone 1', 'Microphone 2']);
  assert.equal(r.unnamed, true);
});
test('listMics drops entries without an id (Firefox before permission)', async () => {
  const r = await listMics(devices([{ kind: 'audioinput', deviceId: '', label: '' }]), LABELS);
  assert.deepEqual(r.mics, [{ id: '', label: 'Default microphone' }]);
  assert.equal(r.unnamed, true);
});
test('listMics without enumerateDevices or on error gives only the default', async () => {
  assert.deepEqual((await listMics(undefined, LABELS)).mics, [{ id: '', label: 'Default microphone' }]);
  const bad = { enumerateDevices: () => Promise.reject(new Error('no')) };
  assert.deepEqual((await listMics(bad, LABELS)).mics, [{ id: '', label: 'Default microphone' }]);
});
test('saved mic id is per user and "" removes it', () => {
  const s = memStore();
  assert.equal(getSavedMicId('u1', s), '');
  saveMicId('u1', 'usb', s); saveMicId('u2', 'bt', s);
  assert.equal(getSavedMicId('u1', s), 'usb'); assert.equal(getSavedMicId('u2', s), 'bt');
  saveMicId('u1', '', s);
  assert.equal(getSavedMicId('u1', s), ''); assert.equal(s.m.size, 1);
  assert.equal(getSavedMicId(null, s), '');
});
test('blocked storage never throws', () => {
  const s = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); }, removeItem() { throw new Error('blocked'); } };
  assert.equal(getSavedMicId('u1', s), ''); saveMicId('u1', 'x', s); saveMicId('u1', '', s);
});
test('audioConstraints only picks the device', () => {
  assert.equal(audioConstraints(''), true); assert.equal(audioConstraints(null), true);
  assert.deepEqual(audioConstraints('usb'), { deviceId: { exact: 'usb' } });
});
test('isMissingDevice', () => {
  assert.equal(isMissingDevice({ name: 'OverconstrainedError' }), true); assert.equal(isMissingDevice({ name: 'NotFoundError' }), true);
  assert.equal(isMissingDevice({ name: 'NotAllowedError' }), false); assert.equal(isMissingDevice(null), false);
});
const fakeMedia = fail => { const calls = []; return { calls, getUserMedia: c => { calls.push(c); return fail(c) ? Promise.reject(fail(c)) : Promise.resolve('stream'); } }; };
test('openMic falls back once to the default when the saved device is gone', async () => {
  const md = fakeMedia(c => (c.audio === true ? null : { name: 'OverconstrainedError' }));
  let missing = 0;
  assert.equal(await openMic(md, 'usb', { fallback: true, onMissing: () => { missing += 1; } }), 'stream');
  assert.deepEqual(md.calls, [{ audio: { deviceId: { exact: 'usb' } } }, { audio: true }]);
  assert.equal(missing, 1);
});
test('openMic without fallback reports the missing device', async () => {
  const md = fakeMedia(() => ({ name: 'NotFoundError' }));
  let missing = 0;
  await assert.rejects(openMic(md, 'usb', { onMissing: () => { missing += 1; } }), { name: 'NotFoundError' });
  assert.equal(md.calls.length, 1); assert.equal(missing, 1);
});
test('openMic passes other errors on and never retries the default device', async () => {
  const denied = fakeMedia(() => ({ name: 'NotAllowedError' }));
  await assert.rejects(openMic(denied, 'usb', { fallback: true }), { name: 'NotAllowedError' });
  assert.equal(denied.calls.length, 1);
  const none = fakeMedia(() => ({ name: 'NotFoundError' }));
  await assert.rejects(openMic(none, '', { fallback: true }), { name: 'NotFoundError' });
  assert.deepEqual(none.calls, [{ audio: true }]);
});
