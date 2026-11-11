/* evaluate_client.js: pure helpers for the Report (no DOM, no network).
   - displayRound: same rule as scoring.display_round (Python): quantize 1e-9 HALF_EVEN, then 0.1 HALF_UP.
   - mapResult: EvaluationResultV2 (ADR-004) -> {an, sc}, the shape the Report already consumes (ADR-004 D14).
   UMD-lite: window.EvaluateClient in the browser, module.exports under node. */
(function (root) {
  'use strict';

  /* ---- decimal rounding on the SHORTEST repr string (like Python's Decimal(str(x))) ---- */
  function parseDec(x) {
    let s = String(x);
    if (/e/i.test(s)) s = x.toFixed(15);            // tiny/huge values: not expected for scores in [0, 100]
    const neg = s[0] === '-';
    if (neg || s[0] === '+') s = s.slice(1);
    const dot = s.indexOf('.');
    const frac = dot < 0 ? '' : s.slice(dot + 1);
    return { neg, digits: BigInt((dot < 0 ? s : s.slice(0, dot)) + frac), scale: frac.length };
  }
  function quantize(d, scale, mode) {              // mode: 'even' | 'up' (half-up on magnitude, as Decimal ROUND_HALF_UP)
    if (d.scale <= scale) return { neg: d.neg, digits: d.digits * 10n ** BigInt(scale - d.scale), scale };
    const div = 10n ** BigInt(d.scale - scale), q = d.digits / div, r = d.digits % div, twice = r * 2n;
    const up = twice > div || (twice === div && (mode === 'up' || q % 2n === 1n));
    return { neg: d.neg, digits: up ? q + 1n : q, scale };
  }
  function displayRound(x) {
    if (x === null || x === undefined || typeof x !== 'number' || !Number.isFinite(x)) return null;
    const r = quantize(quantize(parseDec(x), 9, 'even'), 1, 'up');
    return r.digits === 0n ? 0 : (r.neg ? -1 : 1) * Number(r.digits) / 10;
  }

  /* ---- mapResult ---- */
  const nn = v => (v === undefined ? null : v);
  const STATUS = { equal: 'ok', sub: 'wrong', near_miss: 'near', del: 'missing' };
  const PAUSE_KIND = { forgot_word: 'forgot', hesitation: 'hesitation', natural: 'natural', punctuation: 'natural' };

  function sampleSeries(series, t) {               // value of a Series at time t, or null (outside / null sample / no series)
    if (!series || !Array.isArray(series.values) || !(series.step_s > 0) || t == null) return null;
    const idx = Math.floor((t - series.start_s) / series.step_s);
    if (idx < 0 || idx >= series.values.length) return null;
    return nn(series.values[idx]);
  }

  function mapResult(json, scriptText) {
    const aud = json.audio || {}, acc = json.accuracy_detail || {}, flu = json.fluency_detail || {};
    const pit = json.pitch_detail || {}, cmp = json.components || {}, sub = json.subscores || {};
    const sentences = (json.sentences || []).map(s => s.ref_text);
    const cos = (json.sentences || []).map(s => nn(s.cosine));
    const contour = pit.contour_st || null;
    const loud = (json.display_only && json.display_only.loudness_db) || null;

    const words = (json.alignment || []).filter(a => a.ref_index != null)
      .sort((a, b) => a.ref_index - b.ref_index)
      .map(a => {
        const start = nn(a.start_s), end = nn(a.end_s), mid = start != null && end != null ? (start + end) / 2 : null;
        return {
          i: a.ref_index, raw: a.ref_word, norm: (a.ref_word || '').toLowerCase().replace(/[^a-z0-9']/g, ''),
          si: a.sentence_index, status: STATUS[a.status] || 'ok', start, end,
          hypWord: nn(a.hyp_word), homophone: !!a.homophone,
          f0: sampleSeries(contour, mid), vol: sampleSeries(loud, mid)
        };
      });
    const ins = (json.alignment || []).filter(a => a.ref_index == null).length;

    const pauses = (json.pauses || []).map(p => ({
      dur: p.end_s - p.start_s, afterIdx: nn(p.after_ref_index), kind: PAUSE_KIND[p.kind] || 'natural', start: p.start_s
    }));
    const fillers = (json.fillers || []).map(f => ({ afterIdx: nn(f.after_ref_index), t: f.start_s, text: nn(f.text), source: f.source }));
    pauses.forEach(p => {
      const w = p.afterIdx != null ? words[p.afterIdx] : null;
      if (w && w.i === p.afterIdx && !w.pauseAfter) w.pauseAfter = p;
    });
    fillers.forEach(f => {
      const w = f.afterIdx != null ? words[f.afterIdx] : null;
      if (w && w.i === f.afterIdx) { w.fillerAfter = true; if (!w.fillerText) w.fillerText = f.text || '…'; }
    });

    const an = {
      text: scriptText, sentences, words, pauses, fillers, cos, ins,
      dur: nn(aud.duration_s), voicedRatio: nn(aud.voiced_ratio)
    };
    const nSent = (json.sentences || []).length, cosOk = (json.sentences || []).filter(s => s.passed === true).length;
    const sc = {
      status: json.status, reason: nn(json.reason), voicedRatio: an.voicedRatio,
      overall: nn(json.overall), label: nn(json.label), flags: json.flags || [], warnings: json.warnings || []
    };
    if (json.status === 'ok') {
      Object.assign(sc, {
        N: nn(acc.n_ref), sub: nn(acc.n_sub), del: nn(acc.n_del), near: nn(acc.n_near_miss), ins: nn(acc.n_ins),
        homophone: nn(acc.n_homophone), oov: nn(acc.n_oov),
        A: nn(cmp.accuracy), F: nn(cmp.fluency), P: nn(cmp.pronunciation), S: nn(cmp.semantic),
        wpm: nn(flu.wpm), H: nn(flu.hesitations_per_min), R: nn(flu.filler_pct), hes: nn(flu.hesitation_count),
        Fwpm: nn(sub.f_wpm), Fpause: nn(sub.f_pause), Ffiller: nn(sub.f_filler), Pclar: nn(sub.p_clarity), Ppitch: nn(sub.p_pitch),
        Rst: nn(pit.range_semitones), cosOk, nSent
      });
    }
    return { an, sc };
  }

  /* /api/baseline response -> the 5-key object /api/evaluate accepts (main._parse_baseline), or null.
     Explicit keys only (unknown keys dropped); flags limited to the values the backend accepts. */
  const BASELINE_FLAGS = ['baseline_pause_unreliable', 'no_f0'];
  function pickBaselineProfile(json) {
    if (!json || json.status !== 'ok' || !json.profile || typeof json.profile !== 'object') return null;
    const p = json.profile;
    if (typeof p.hesitation_threshold_s !== 'number' || !Number.isFinite(p.hesitation_threshold_s)) return null;
    const num = v => (typeof v === 'number' && Number.isFinite(v) ? v : null);
    return {
      median_pause_s: num(p.median_pause_s), hesitation_threshold_s: p.hesitation_threshold_s,
      median_f0_hz: num(p.median_f0_hz), mean_loudness_db: num(p.mean_loudness_db),
      flags: (Array.isArray(p.flags) ? p.flags : []).filter(f => BASELINE_FLAGS.includes(f))
    };
  }

  const api = { mapResult, displayRound, pickBaselineProfile };
  root.EvaluateClient = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
