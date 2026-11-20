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

  /* A compacted (older) session keeps its scores and `mistakes` (src/app/db/session_helpers.py
     compact_session) but no alignment, sentences or timings. Rebuild what mapResult needs from the
     saved script: every script.split() token is one word (ref_index = its position, as on the
     backend), marked with its saved mistake when it has one. Sentence breaks follow end punctuation,
     a close copy of text_norm.split_sentences. Timings stay null, so nothing is drawn on a time axis. */
  const SENTENCE_END = /[.!?]["'\u201d\u2019)\]]*$/;
  function expandCompact(result, mistakes, scriptText) {
    const tokens = String(scriptText || '').split(/\s+/).filter(Boolean), list = mistakes || [];
    const byRef = {};
    list.forEach(m => { if (m.type === 'alignment' && m.ref_index != null) byRef[m.ref_index] = m; });
    const sentences = [];
    let start = 0;
    const alignment = tokens.map((tok, k) => {
      const m = byRef[k];
      const item = { ref_index: k, ref_word: tok, hyp_word: m ? nn(m.hyp_word) : tok, status: m ? m.status : 'equal',
        sentence_index: sentences.length, start_s: null, end_s: null };
      if (SENTENCE_END.test(tok) || k === tokens.length - 1) {
        sentences.push({ ref_text: tokens.slice(start, k + 1).join(' '), cosine: null, passed: null });
        start = k + 1;
      }
      return item;
    });
    const pauses = list.filter(m => m.type === 'pause')
      .map(m => ({ start_s: m.start_s, end_s: m.end_s, after_ref_index: m.after_ref_index, kind: m.kind }));
    const fillers = list.filter(m => m.type === 'filler')
      .map(m => ({ after_ref_index: m.after_ref_index, start_s: m.start_s, end_s: m.end_s, text: m.text, source: m.source }));
    return Object.assign({}, result, { alignment, sentences, pauses, fillers });
  }

  /* ---- Practice follow-along schedule (demo: highlight moves by TIME, not by the real voice; NOT part of scoring) ---- */
  // Fallback slider limits, used only when /api/config fails. Real values: app_constants.toml [web] follow_wpm_*.
  const FOLLOW_WPM = { min: 100, max: 180, step: 5, def: 145 };
  function followLimitsOr(limits) {                // fill the limits not given from FOLLOW_WPM
    const l = limits || {};
    return {
      min: l.min != null ? l.min : FOLLOW_WPM.min, max: l.max != null ? l.max : FOLLOW_WPM.max,
      step: l.step != null ? l.step : FOLLOW_WPM.step, def: l.def != null ? l.def : FOLLOW_WPM.def
    };
  }
  function clampFollowWpm(w, limits) {             // out of range -> clamp; not a finite number -> default
    const l = followLimitsOr(limits);
    const n = typeof w === 'number' ? w : (w == null || w === '' ? NaN : Number(w));   // Number(null) would be 0
    if (!Number.isFinite(n)) return l.def;
    return Math.min(l.max, Math.max(l.min, n));
  }
  function parseFollowWpm(raw, limits) {           // stored value (string/number): must be an integer multiple of step in range, else default
    const l = followLimitsOr(limits);
    const n = typeof raw === 'string' && raw.trim() !== '' ? Number(raw) : raw;
    if (typeof n !== 'number' || !Number.isInteger(n) || n < l.min || n > l.max || n % l.step !== 0) return l.def;
    return n;
  }
  /* wordCounts[i] = words in sentence i. Sentence i lasts n_i * 60 / wpm seconds; leadS before the first, gapS after each.
     startIndex/startTime (optional): sentence startIndex begins at startTime and later ones follow; earlier ones are copied from prev
     (or, without prev, from the schedule at this wpm). Returns [{start, end}] in seconds. */
  function followSchedule(o) {
    o = o || {};
    const counts = Array.isArray(o.wordCounts) ? o.wordCounts : [];
    const per = 60 / clampFollowWpm(o.wpm, o.limits), lead = o.leadS == null ? 0 : o.leadS, gap = o.gapS == null ? 0 : o.gapS;
    const k = Number.isInteger(o.startIndex) ? o.startIndex : -1, prev = o.prev || [];
    let t = lead;
    return counts.map((n, i) => {
      if (i === k && typeof o.startTime === 'number') t = o.startTime;
      const seg = i < k && prev[i] ? { start: prev[i].start, end: prev[i].end } : { start: t, end: t + n * per };
      t = seg.end + gap;
      return seg;
    });
  }
  /* Change speed in the middle of a recording: sentences before idx stay; the current sentence keeps the fraction already read
     (so the highlight does not jump back), later ones are recomputed. idx < 0 (still in the lead-in): only the sentences move. */
  function followRetime(segs, idx, now, o) {
    if (!segs || !segs.length) return [];
    if (idx < 0) return followSchedule({ wordCounts: o.wordCounts, wpm: o.wpm, limits: o.limits, leadS: o.leadS, gapS: o.gapS, startIndex: 0, startTime: segs[0].start });
    const old = segs[idx], dOld = old.end - old.start, frac = dOld > 0 ? Math.min(1, Math.max(0, (now - old.start) / dOld)) : 0;
    const dNew = (o.wordCounts[idx] || 0) * 60 / clampFollowWpm(o.wpm, o.limits);
    return followSchedule({ wordCounts: o.wordCounts, wpm: o.wpm, limits: o.limits, leadS: o.leadS, gapS: o.gapS, startIndex: idx, startTime: now - frac * dNew, prev: segs });
  }

  /* Jump to sentence k at time now: it starts now, later ones follow at this wpm, earlier ones count as already read. */
  function followJump(segs, k, now, o) {
    const fresh = followSchedule({ wordCounts: o.wordCounts, wpm: o.wpm, limits: o.limits, leadS: o.leadS, gapS: o.gapS, startIndex: k, startTime: now });
    return fresh.map((g, i) => (i < k ? { start: Math.min(g.start, now - (k - i) * 1e-3), end: Math.min(g.end, now) } : g));
  }

  /* Auto speed. Two taps (sentence fromK at fromT, then toK at toT, seconds): the speed the user really read at,
     in wpm, or null when the taps say nothing reliable (backwards, a skip, too close). A speed outside
     [lo, hi] is taken as lo or hi: reading very fast still pushes the slider to its fastest end.
     o: { gapS, minS, minWords, maxAhead, lo, hi } */
  function followMeasureWpm(counts, fromK, fromT, toK, toT, o) {
    const ahead = toK - fromK;
    if (!(ahead >= 1) || ahead > o.maxAhead) return null;
    let words = 0;
    for (let i = fromK; i < toK; i++) words += counts[i] || 0;
    const secs = toT - fromT - ahead * (o.gapS || 0);
    if (toT - fromT < o.minS || words < o.minWords || secs <= 0) return null;
    const wpm = words * 60 / secs;
    return Math.min(o.hi, Math.max(o.lo, wpm));
  }
  /* The slider value after one measurement: part of the way to it, on the step, inside [min, max]. */
  function followBlendWpm(cur, measured, weight, limits) {
    const v = (1 - weight) * cur + weight * measured, step = limits.step || 5;
    return Math.min(limits.max, Math.max(limits.min, Math.round(v / step) * step));
  }

  const api = { mapResult, displayRound, pickBaselineProfile, expandCompact, FOLLOW_WPM, clampFollowWpm, parseFollowWpm, followSchedule, followRetime, followJump, followMeasureWpm, followBlendWpm };
  root.EvaluateClient = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
