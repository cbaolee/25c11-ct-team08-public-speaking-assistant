'use strict';
// Dữ liệu fixture là TỔNG HỢP (tests/fixtures/README.md), không phải kết quả đo.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { mapResult, displayRound, pickBaselineProfile } = require('../../src/web/static/js/evaluate_client.js');

const load = n => JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'fixtures', n), 'utf8'));
const clone = o => JSON.parse(JSON.stringify(o));

test('displayRound: vectors from tests/audio_processing/test_scoring.py', () => {
  assert.equal(displayRound(89.85), 89.9);            // float 89.8499..., Math.round(x*10)/10 gives 89.8
  assert.equal(displayRound(null), null);
  assert.equal(displayRound(undefined), null);
  assert.equal(displayRound(NaN), null);
  assert.equal(displayRound(0), 0);
  assert.equal(displayRound(100), 100);
  assert.equal(displayRound(70.04), 70);
  assert.equal(displayRound(84.9499), 84.9);
  // compute_overall(83.5, 98.5, 70, 80) = 84.94999999999999 in float -> 85.0
  assert.equal(displayRound(0.4 * 83.5 + 0.3 * 98.5 + 0.2 * 70 + 0.1 * 80), 85);
  for (const [a, e] of [[83.5, 85], [88.5, 87], [93.5, 89]]) {
    assert.equal(displayRound(0.4 * a + 0.3 * 98.5 + 0.2 * 70 + 0.1 * 80), e, String(a));
  }
  for (const x of [84.96, 69.95, 49.95]) assert.equal(displayRound(x), Math.round(x * 10 + 1e-9) / 10);
  assert.equal(displayRound(84.96), 85);
  assert.equal(displayRound(49.94), 49.9);
});

test('displayRound: scan every x.x5 from 0.05 to 99.95 rounds half-up', () => {
  for (let n = 0; n < 1000; n++) {
    const x = (10 * n + 5) / 100;
    assert.equal(displayRound(x), (n + 1) / 10, String(x));
  }
});

test('mapResult ok_mixed: words, statuses, ins, pauses, filler', () => {
  const j = load('evaluation_ok_mixed.json'), { an, sc } = mapResult(j, 'Good morning my friends are here today.');
  assert.deepEqual(an.words.map(w => w.status), ['ok', 'ok', 'missing', 'near', 'ok', 'wrong', 'ok']);
  assert.deepEqual(an.words.map(w => w.i), [0, 1, 2, 3, 4, 5, 6]);
  assert.equal(an.words[2].start, null); assert.equal(an.words[2].end, null);
  assert.equal(an.words[3].start, 1.2);
  assert.equal(an.words[6].raw, 'today.');
  assert.equal(an.ins, 1);
  assert.equal(an.words.length, 7);                    // ins is counted, not drawn
  assert.deepEqual(an.sentences, ['Good morning my friends are here today.']);
  assert.deepEqual(an.cos, [1.0]);
  assert.equal(an.dur, 6.8);
  assert.deepEqual(an.pauses.map(p => p.kind), ['hesitation', 'forgot']);
  assert.ok(Math.abs(an.pauses[1].dur - 1.7) < 1e-9);
  assert.equal(an.pauses[0].afterIdx, 3);
  assert.equal(an.words[3].pauseAfter.kind, 'hesitation');
  assert.equal(an.words[5].pauseAfter.kind, 'forgot');
  assert.equal(an.fillers.length, 1);
  assert.equal(an.words[1].fillerAfter, true); assert.equal(an.words[1].fillerText, 'um');
  // f0 / vol sampled at word centre: "Good" mid 0.2 -> idx 2 (null); "morning" mid 0.7 -> idx 7 (null)
  assert.equal(an.words[0].f0, null);
  assert.equal(an.words[3].f0, null);                                   // mid 1.6 -> idx 16: sample is null in this fixture
  assert.equal(an.words[4].vol, null);                                  // mid 2.95 -> idx 29: null sample
  assert.equal(an.words[3].vol, j.display_only.loudness_db.values[16]); // 58.5 -> a number
  assert.equal(an.words[2].f0, null); assert.equal(an.words[2].vol, null);   // del: no time
  assert.ok(an.words.some(w => typeof w.vol === 'number') && an.words.some(w => w.vol === null));
  assert.equal(sc.status, 'ok');
  assert.equal(sc.A, 57.14285714285714); assert.equal(sc.F, 0); assert.equal(sc.P, 64.28571428571428); assert.equal(sc.S, 100);
  assert.equal(sc.overall, j.overall); assert.equal(sc.label, 'Need practice more');
  assert.equal(sc.wpm, j.fluency_detail.wpm); assert.equal(sc.H, j.fluency_detail.hesitations_per_min);
  assert.equal(sc.R, j.fluency_detail.filler_pct); assert.equal(sc.hes, 2);
  assert.equal(sc.Fwpm, 0); assert.equal(sc.Pclar, j.subscores.p_clarity); assert.equal(sc.Ppitch, 100);
  assert.deepEqual([sc.N, sc.sub, sc.del, sc.near, sc.ins], [7, 1, 1, 1, 1]);
  assert.equal(sc.Rst, j.pitch_detail.range_semitones);
  assert.deepEqual([sc.cosOk, sc.nSent], [1, 1]);
  assert.deepEqual(sc.flags, ['no_baseline']); assert.deepEqual(sc.warnings, ['wpm_slow', 'filler_high']);
});

test('mapResult: f0 sampled at word centre (idx = floor((mid - start_s) / step_s))', () => {
  const j = clone(load('evaluation_ok_mixed.json'));
  j.pitch_detail.contour_st.values[16] = 3.5;           // word 3: 1.2..2.0, mid 1.6
  j.pitch_detail.contour_st.values[2] = -1.25;          // word 0: 0.0..0.4, mid 0.2
  const { an } = mapResult(j, 'x');
  assert.equal(an.words[3].f0, 3.5); assert.equal(an.words[0].f0, -1.25);
});

test('mapResult ok: clean read', () => {
  const j = load('evaluation_ok.json'), { an, sc } = mapResult(j, 'x');
  assert.equal(sc.status, 'ok');
  assert.ok(an.words.every(w => w.status === 'ok'));
  assert.equal(an.ins, 0);
  assert.equal(sc.overall, j.overall);
});

test('mapResult insufficient_audio: no crash, nothing invented', () => {
  const { an, sc } = mapResult(load('evaluation_insufficient.json'), 'x');
  assert.equal(sc.status, 'insufficient_audio'); assert.equal(sc.reason, 'low_voiced_ratio');
  assert.equal(sc.overall, null); assert.equal(sc.voicedRatio, 0.1);
  assert.deepEqual(an.words, []); assert.deepEqual(an.sentences, []);
  assert.equal(sc.A, undefined);
});

test('mapResult: null components and overall stay null (no 0 filled in)', () => {
  const j = clone(load('evaluation_ok_mixed.json'));
  j.overall = null; j.label = null; j.components = { accuracy: null, fluency: null, pronunciation: null, semantic: null };
  j.subscores = { f_wpm: null, f_pause: null, f_filler: null, p_clarity: null, p_pitch: null };
  j.fluency_detail.wpm = null; j.fluency_detail.hesitations_per_min = null; j.pitch_detail.range_semitones = null;
  const { sc } = mapResult(j, 'x');
  for (const k of ['overall', 'label', 'A', 'F', 'P', 'S', 'wpm', 'H', 'Fwpm', 'Fpause', 'Ffiller', 'Pclar', 'Ppitch', 'Rst']) assert.equal(sc[k], null, k);
});

test('mapResult: all-null Series -> every word f0/vol null; absent Series too', () => {
  const j = clone(load('evaluation_ok_mixed.json'));
  j.pitch_detail.contour_st.values = j.pitch_detail.contour_st.values.map(() => null);
  j.display_only.loudness_db = null;
  const { an } = mapResult(j, 'x');
  assert.ok(an.words.every(w => w.f0 === null && w.vol === null));
  j.pitch_detail.contour_st = null;
  assert.ok(mapResult(j, 'x').an.words.every(w => w.f0 === null));
});

test('mapResult: zero pauses and zero fillers', () => {
  const j = clone(load('evaluation_ok_mixed.json')); j.pauses = []; j.fillers = [];
  const { an } = mapResult(j, 'x');
  assert.deepEqual(an.pauses, []); assert.deepEqual(an.fillers, []);
  assert.ok(an.words.every(w => !w.pauseAfter && !w.fillerAfter));
});

test('mapResult is pure: input unchanged', () => {
  const j = load('evaluation_ok_mixed.json'), before = JSON.stringify(j);
  mapResult(j, 'x'); assert.equal(JSON.stringify(j), before);
});

test('pickBaselineProfile: ok -> exactly 5 keys', () => {
  const r = pickBaselineProfile({ status: 'ok', profile: { median_pause_s: 0.5, hesitation_threshold_s: 1.0, median_f0_hz: 120, mean_loudness_db: 60.5, flags: ['no_f0'] } });
  assert.deepEqual(r, { median_pause_s: 0.5, hesitation_threshold_s: 1.0, median_f0_hz: 120, mean_loudness_db: 60.5, flags: ['no_f0'] });
});

test('pickBaselineProfile: unknown flags filtered, unknown keys dropped, nulls kept as null', () => {
  const r = pickBaselineProfile({ status: 'ok', profile: { median_pause_s: null, hesitation_threshold_s: 0.7, median_f0_hz: null, extra: 1, flags: ['no_baseline', 'baseline_pause_unreliable', 'x'] } });
  assert.deepEqual(r, { median_pause_s: null, hesitation_threshold_s: 0.7, median_f0_hz: null, mean_loudness_db: null, flags: ['baseline_pause_unreliable'] });
  assert.deepEqual(Object.keys(r), ['median_pause_s', 'hesitation_threshold_s', 'median_f0_hz', 'mean_loudness_db', 'flags']);
});

test('pickBaselineProfile: insufficient / null profile / bad threshold / garbage -> null', () => {
  assert.equal(pickBaselineProfile({ status: 'insufficient_audio', reason: 'low_voiced_ratio', profile: null, flags: [] }), null);
  assert.equal(pickBaselineProfile({ status: 'ok', profile: null }), null);
  assert.equal(pickBaselineProfile({ status: 'ok', profile: { hesitation_threshold_s: null, flags: [] } }), null);
  assert.equal(pickBaselineProfile(null), null);
  assert.equal(pickBaselineProfile({ status: 'insufficient_audio', profile: { hesitation_threshold_s: 0.7, flags: [] } }), null);
});
