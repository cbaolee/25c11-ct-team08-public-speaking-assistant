'use strict';
// Fixture data is SYNTHETIC (tests/fixtures/README.md), not measured results.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { mapResult, displayRound, pickBaselineProfile, expandCompact, clampFollowWpm, parseFollowWpm, followSchedule, followRetime } = require('../../src/web/static/js/evaluate_client.js');

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

test('expandCompact: words from the script, mistakes marked, sentences split, no timings', () => {
  const summary = { status: 'ok', overall: 80, components: { accuracy: 90 }, audio: { duration_s: 12, voiced_ratio: 0.8 } };
  const mistakes = [
    { type: 'alignment', status: 'sub', ref_index: 1, ref_word: 'quick', hyp_word: 'quack', sentence_index: 0 },
    { type: 'alignment', status: 'del', ref_index: 4, ref_word: 'very', hyp_word: null, sentence_index: 1 },
    { type: 'filler', after_ref_index: 2, text: 'um', source: 'stt', start_s: 1.0, end_s: 1.2 },
    { type: 'pause', kind: 'hesitation', after_ref_index: 2, start_s: 1.2, end_s: 2.4 }
  ];
  const script = 'The quick fox. It is very fast!';
  const json = expandCompact(summary, mistakes, script);
  assert.equal(json.alignment.length, 7);
  assert.deepEqual(json.sentences.map(x => x.ref_text), ['The quick fox.', 'It is very fast!']);
  assert.deepEqual(json.alignment.map(a => a.sentence_index), [0, 0, 0, 1, 1, 1, 1]);
  assert.equal(json.overall, 80);                                   // summary fields kept

  const { an, sc } = mapResult(json, script);
  assert.deepEqual(an.words.map(w => w.status), ['ok', 'wrong', 'ok', 'ok', 'missing', 'ok', 'ok']);
  assert.ok(an.words.every(w => w.start === null && w.end === null));
  assert.equal(an.words[2].fillerAfter, true);
  assert.equal(an.words[2].pauseAfter.kind, 'hesitation');
  assert.equal(sc.overall, 80);
  assert.equal(an.dur, 12);
});

test('expandCompact: empty mistakes and empty script do not crash', () => {
  const json = expandCompact({ status: 'ok' }, null, '');
  assert.deepEqual(json.alignment, []);
  assert.deepEqual(json.sentences, []);
  assert.doesNotThrow(() => mapResult(json, ''));
});

// ---- follow-along schedule (demo highlight, not scored) ----
const near = (a, b, m) => assert.ok(Math.abs(a - b) < 1e-9, `${m || ''} ${a} != ${b}`);

test('followSchedule: hand-computed (120 wpm = 0.5 s/word, lead 1, gap 0.5)', () => {
  const r = followSchedule({ wordCounts: [4, 2], wpm: 120, leadS: 1, gapS: 0.5 });
  assert.deepEqual(r, [{ start: 1, end: 3 }, { start: 3.5, end: 4.5 }]);
});

test('followSchedule: wpm 145 equals the old buildFollow formula', () => {
  const counts = [7, 3, 12, 1], per = 60 / 145;
  let t = 1.0; const old = counts.map(n => { const seg = { start: t, end: t + n * per }; t = seg.end + 0.5; return seg; });
  assert.deepEqual(followSchedule({ wordCounts: counts, wpm: 145, leadS: 1.0, gapS: 0.5 }), old);
});

test('followSchedule: 100 wpm lasts 1.8x of 180 wpm (word time only)', () => {
  const end = w => followSchedule({ wordCounts: [10, 20, 30], wpm: w, leadS: 0, gapS: 0 }).at(-1).end;
  near(end(180), 20); near(end(100), 36); near(end(100) / end(180), 1.8);
});

test('followSchedule: empty input and out-of-range wpm', () => {
  assert.deepEqual(followSchedule({ wordCounts: [], wpm: 145, leadS: 1, gapS: 0.5 }), []);
  assert.deepEqual(followSchedule({ wpm: 145 }), []);
  const one = w => followSchedule({ wordCounts: [60], wpm: w, leadS: 0, gapS: 0 })[0].end;
  near(one(50), 36); near(one(999), 20); near(one(NaN), 60 * 60 / 145); near(one('abc'), 60 * 60 / 145);   // clamp to [100,180], not a number -> 145
});

test('followSchedule: startIndex/startTime moves the tail, keeps prev', () => {
  const prev = [{ start: 1, end: 3 }, { start: 3.5, end: 4.5 }];
  const r = followSchedule({ wordCounts: [4, 2, 6], wpm: 120, leadS: 1, gapS: 0.5, startIndex: 2, startTime: 10, prev });
  assert.deepEqual(r.slice(0, 2), prev);
  assert.deepEqual(r[2], { start: 10, end: 13 });
});

test('followRetime: mid-sentence speed change keeps earlier sentences and read fraction', () => {
  const o = { wordCounts: [4, 2, 6], leadS: 1, gapS: 0.5 };
  const segs = followSchedule({ ...o, wpm: 120 });            // [1,3] [3.5,4.5] [5,8]
  const r = followRetime(segs, 1, 4, { ...o, wpm: 180 });     // halfway through sentence 1 at t=4; 180 wpm = 1/3 s/word
  assert.deepEqual(r[0], segs[0]);
  near(r[1].start, 4 - 1 / 3); near(r[1].end, 4 + 1 / 3);     // half of 2/3 s already read, half left
  near(r[2].start, 4 + 1 / 3 + 0.5); near(r[2].end - r[2].start, 2);
  assert.ok(r[1].start <= 4 && r[2].start > 4);                // current index stays 1
});

test('followRetime: still in the lead-in keeps the first start; empty segs', () => {
  const o = { wordCounts: [4, 2], leadS: 1, gapS: 0.5 };
  const r = followRetime(followSchedule({ ...o, wpm: 120 }), -1, 0.4, { ...o, wpm: 180 });
  near(r[0].start, 1); near(r[0].end, 1 + 4 / 3);
  assert.deepEqual(followRetime([], 0, 1, { ...o, wpm: 120 }), []);
});

test('clampFollowWpm / parseFollowWpm', () => {
  assert.equal(clampFollowWpm(100), 100); assert.equal(clampFollowWpm(99), 100); assert.equal(clampFollowWpm(181), 180); assert.equal(clampFollowWpm(null), 145);
  for (const ok of ['100', '145', '180', 150]) assert.equal(parseFollowWpm(ok), Number(ok));
  for (const bad of [null, undefined, '', 'abc', '97', '146', '95', '185', '145.5', NaN, 1e9]) assert.equal(parseFollowWpm(bad), 145, String(bad));
});

test('followRetime: edge cases (gap, last sentence, empty sentence, now past old end)', () => {
  const o = { wordCounts: [4, 2, 6], leadS: 1, gapS: 0.5 };
  const segs = followSchedule({ ...o, wpm: 120 });            // [1,3] [3.5,4.5] [5,8]
  // (a) now inside the gap after sentence 1 (4.5..5): frac clamps to 1 -> sentence ends exactly at now
  let r = followRetime(segs, 1, 4.75, { ...o, wpm: 180 });
  near(r[1].end, 4.75); near(r[1].start, 4.75 - 2 / 3); near(r[2].start, 4.75 + 0.5);
  // (d) now a bit after the old end of the last sentence (8.2): same clamp, nothing breaks
  r = followRetime(segs, 2, 8.2, { ...o, wpm: 100 });         // 100 wpm = 0.6 s/word, d = 3.6
  assert.deepEqual(r.slice(0, 2), segs.slice(0, 2));
  near(r[2].end, 8.2); near(r[2].start, 8.2 - 3.6); assert.equal(r.length, 3);
  // (b) last sentence, halfway (6.5 of [5,8]) at 180 wpm: d_new = 2, start = 6.5 - 1 = 5.5
  r = followRetime(segs, 2, 6.5, { ...o, wpm: 180 });
  near(r[2].start, 5.5); near(r[2].end, 7.5);
  // (c) empty sentence (n = 0): zero length, frac 0, no NaN
  const z = { wordCounts: [3, 0, 2], leadS: 0, gapS: 0.5 };
  const zs = followSchedule({ ...z, wpm: 120 });              // [0,1.5] [2,2] [2.5,3.5]
  assert.deepEqual(zs[1], { start: 2, end: 2 });
  r = followRetime(zs, 1, 2.2, { ...z, wpm: 180 });
  for (const g of r) { assert.ok(Number.isFinite(g.start) && Number.isFinite(g.end)); }
  near(r[1].start, 2.2); near(r[1].end, 2.2); near(r[2].start, 2.7);
});

test('followSchedule(undefined) does not throw', () => {
  assert.deepEqual(followSchedule(undefined), []);
  assert.deepEqual(followSchedule(null), []);
});
