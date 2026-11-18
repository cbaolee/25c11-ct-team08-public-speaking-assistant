import { chart, hideTip, showTip } from '../charts.js';
import { ADR, adviceList, fx, hasBase, paceWindows, progressDelta, sh } from '../data.js';
import { T } from '../i18n.js';
import { go, moveSegPills } from '../nav.js';
import { deltaPill } from '../screens/home.js';
import { CONFIG, RENDER, S } from '../state.js';
import { openWordCoach, openSentenceCoach, closeWordCoach } from './word_coach.js';
import { openModal } from '../ui.js';
import { $, $$, IC, esc, fmtTime, plain } from '../utils.js';

/* ---------- Report ---------- */
export const FILLERS = ['um', 'uh', 'er'];
export const fillerOf = w => w.fillerText || FILLERS[w.i % 3];
export function wordHtml(w) {
  const cls = { wrong: 'w-wrong', near: 'w-near', missing: 'w-missing' }[w.status];
  let h = cls
    ? '<button type="button" class="w ' + cls + '" data-i="' + w.i + '" aria-label="' + esc(plain(w.raw) + ', ' + T({ wrong: 'tip.wrongT', near: 'tip.nearT', missing: 'tip.missT' }[w.status])) + '">' + esc(w.raw) + '</button>'
    : '<span class="w" data-i="' + w.i + '">' + esc(w.raw) + '</span>';
  if (w.fillerAfter) h += ' <span class="fillerchip" data-wi="' + w.i + '" data-k="filler">' + fillerOf(w) + '</span>';
  if (w.pauseAfter && w.pauseAfter.kind !== 'natural') {
    const forgot = w.pauseAfter.kind === 'forgot', d = w.pauseAfter.dur.toFixed(1);
    h += ' <span class="pausechip ' + (forgot ? 'bad' : 'warn') + '" data-wi="' + w.i + '" data-k="pause" role="img" aria-label="' + esc(T(forgot ? 'report.pauseForgot' : 'report.pauseHes')) + ', ' + d + ' s">' + d + ' s</span>';
  }
  return h;
}
export function buildTranscript(an) {
  const stats = window.EvaluateClient.sentenceErrorStats(an.words);
  return an.sentences.map((_, si) => {
    const ws = an.words.filter(w => w.si === si), first = ws.find(w => w.start != null), t0 = first ? first.start : 0;
    const practice = window.EvaluateClient.needsSentencePractice(stats.find(x => x.si === si), CONFIG.RETRY.minRatio) ? ' <button type="button" class="wc-sent-btn" data-si="' + si + '" aria-label="' + esc(T('wc.practiceSentence')) + '">&#8635; ' + esc(T('wc.practiceSentence')) + '</button>' : '';
    return '<div class="tx-row"><button type="button" class="tx-time" data-t0="' + t0.toFixed(2) + '" aria-label="' + esc(T('report.playFrom', { t: fmtTime(t0) })) + '">' + fmtTime(t0) + '</button><div class="tx-text">' + ws.map(wordHtml).join(' ') + practice + '</div></div>';
  }).join('');
}

/* ---- hover notes: what went wrong at this exact spot (replaces the old legend + caption under the transcript) ---- */
export function tipWord(w) {
  const L = ['• ' + T({ wrong: 'tip.wrong', near: 'tip.near', missing: 'tip.missing' }[w.status])];
  if (w.fillerAfter) L.push('• ' + T('tip.fillerAfter', { f: fillerOf(w) }));
  if (w.pauseAfter && w.pauseAfter.kind !== 'natural') L.push('• ' + T(w.pauseAfter.kind === 'forgot' ? 'tip.forgotAfter' : 'tip.hesAfter', { d: w.pauseAfter.dur.toFixed(1) }));
  return '“' + plain(w.raw) + '”\n' + L.join('\n');
}
export function tipFor(el) {
  const an = S.currentSession && S.currentSession.an; if (!an) return null;
  const k = el.getAttribute('data-k');
  if (k) {
    const w = an.words[+el.getAttribute('data-wi')]; if (!w) return null;
    const head = T('tip.after', { w: plain(w.raw) });
    return k === 'filler' ? head + '\n• ' + T('tip.filler', { f: fillerOf(w) })
      : head + '\n• ' + T(w.pauseAfter.kind === 'forgot' ? 'tip.forgot' : 'tip.hes', { d: w.pauseAfter.dur.toFixed(1) });
  }
  const w = an.words[+el.getAttribute('data-i')];
  return w && w.status !== 'ok' ? tipWord(w) : null;
}
export function bindTxTips() {
  const tx = $('#transcriptView'), sel = '.w[data-i], .pausechip[data-k], .fillerchip[data-k]';
  const at = e => { const el = e.target.closest && e.target.closest(sel); return el ? tipFor(el) : null; };
  tx.addEventListener('mouseover', e => { const t = at(e); if (t) showTip(t, e.clientX, e.clientY); else hideTip(); });
  tx.addEventListener('mousemove', e => { if ($('#tip').style.display === 'block') { const t = at(e); if (t) showTip(t, e.clientX, e.clientY); } });
  tx.addEventListener('mouseleave', hideTip);
  tx.addEventListener('focusin', e => { const t = at(e); if (t) { const r = e.target.getBoundingClientRect(); showTip(t, r.left + r.width / 2, r.top); } });
  tx.addEventListener('focusout', hideTip);
  window.addEventListener('scroll', hideTip, { passive: true });
}

/* ---- score breakdown (read only); one "View details" button below opens the tabbed detail window ---- */
export function partsHtml(sc) {
  const rows = [
    ['A', 'pA', 'wA', sc.A, T('report.dA', { n: sc.sub + sc.del, total: sc.N })],
    ['F', 'pF', 'wF', sc.F, T('report.dF')],
    ['P', 'pP', 'wP', sc.P, T('report.dP')],
    ['S', 'pS', 'wS', sc.S, T('report.dS', { n: sc.cosOk, total: sc.nSent })]
  ];
  return '<ul class="parts">' + rows.map(r => '<li><div class="top"><span>' + esc(T('report.' + r[1])) + ' <small>' + esc(T('report.' + r[2])) + '</small></span><span>' + esc(sh(r[3])) + '</span></div><div class="bar" aria-hidden="true"><i style="width:' + (Number.isFinite(r[3]) ? Math.round(r[3]) : 0) + '%"></i></div><small>' + esc(r[4]) + '</small></li>').join('') + '</ul>' +
    '<button type="button" class="btn btn-primary rep-details" data-details aria-haspopup="dialog">' + esc(T('part.view')) + IC.chev + '</button>';
}
export const overallLabel = v => (v >= 85 ? 'good' : v >= 70 ? 'fair' : v >= 50 ? 'improve' : 'more');
/* AI coach note: one short, friendly paragraph about the whole take.
   PLACEHOLDER: fixed text until the LLM feedback call is ready. Whoever adds that call replaces the
   body of this function (or fills #repCoachNote later with plain text; it is shown as text, not HTML). */
export function coachNote(s) {
  return T('overview.coachPlaceholder', { name: S.user ? S.user.name : '' });
}
const OV_IC = {
  good: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6L9 17l-5-5"/></svg>',
  warn: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 17l6-6 4 4 8-8M14 7h7v7"/></svg>',
  focus: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/></svg>',
  pace: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 13l4-4M4 18a9 9 0 1 1 16 0"/></svg>',
  pause: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 5v14M15 5v14"/></svg>',
  filler: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v11H9l-5 4z"/></svg>',
  words: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h10M4 18h7"/></svg>',
  pitch: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12c2-5 4-5 6 0s4 5 6 0 4-5 6 0"/></svg>'
};
export function overviewHtml(s) {
  const sc = s.sc;
  const parts = [['pA', sc.A], ['pF', sc.F], ['pP', sc.P], ['pS', sc.S]].map(p => ({ name: T('report.' + p[0]), v: p[1] }));
  const vp = parts.filter(p => Number.isFinite(p.v));
  const hi = vp.length ? vp.reduce((m, p) => (p.v > m.v ? p : m)) : null, lo = vp.length ? vp.reduce((m, p) => (p.v < m.v ? p : m)) : null;
  const adv = adviceList(sc, 1)[0];
  const band = sc.overall != null ? overallLabel(EvaluateClient.displayRound(sc.overall)) : null;
  const verdict = band ? T('overview.verdict_' + band) : T('overview.na');
  // three short cards: what went best, what to improve, what to do next
  const cards = [];
  if (!lo) { /* no part could be scored */ } else if (lo.v >= 85) cards.push(['good', T('overview.strongest'), esc(T('overview.allGood'))]);
  else {
    cards.push(['good', T('overview.strongest'), '<b>' + esc(hi.name) + '</b>']);
    cards.push(['warn', T('overview.improve'), '<b>' + esc(lo.name) + '</b>']);
  }
  cards.push(['focus', T('overview.focus'), adv ? '<b>' + esc(adv.area.charAt(0).toUpperCase() + adv.area.slice(1)) + '.</b> ' + esc(adv.text) : esc(T('part.nothing'))]);
  return '<div class="ov-deco" aria-hidden="true"></div>' +
    '<p class="ov-eyebrow">' + esc(T('overview.title')) + '</p>' +
    '<h2 class="ov-verdict' + (band ? ' ' + band : '') + '">' + esc(verdict) + '</h2>' +
    '<div class="ov-coach"><span class="ov-coach-av" aria-hidden="true">' + IC.ai + '</span><div class="ov-coach-in">' +
      '<p class="ov-coach-who">' + esc(T('overview.coachWho')) + ' <span class="ov-coach-tag">' + esc(T('overview.coachTag')) + '</span></p>' +
      '<p class="ov-coach-text" id="repCoachNote">' + esc(coachNote(s)) + '</p></div></div>' +
    '<ul class="ov-cards">' + cards.map(c => '<li class="ov-card ' + c[0] + '"><span class="ov-ic" aria-hidden="true">' + OV_IC[c[0]] + '</span><div><p class="ov-k">' + esc(c[1]) + '</p><p class="ov-v">' + c[2] + '</p></div></li>').join('') + '</ul>';
}
/* Key numbers (own panel at the top of the right column): one row per measure, with a green
   "on target" or amber "work on it" state from the part score behind it */
export function keyNumbersHtml(sc) {
  const state = v => (v == null ? '' : v >= 85 ? 'ok' : 'warn');
  const tiles = [
    ['pace', sc.wpm == null ? esc(T('common.na')) : Math.round(sc.wpm) + '<small>' + esc(T('report.unitWpm')) + '</small>', T('overview.gPace'), sc.Fwpm],
    ['pause', esc(fx(sc.H, 1)), T('overview.gHes'), sc.Fpause],
    ['filler', sc.R == null ? esc(T('common.na')) : fx(sc.R, 1) + '<small>%</small>', T('overview.gFiller'), sc.Ffiller],
    ['words', sc.sub == null || sc.del == null ? esc(T('common.na')) : esc(T('overview.gWords', { n: sc.sub + sc.del, total: sc.N })), T('overview.gWrong'), sc.A],
    ['pitch', sc.Rst == null ? esc(T('common.na')) : fx(sc.Rst, 1) + '<small>' + esc(T('report.unitSt')) + '</small>', T('overview.gPitch'), sc.Ppitch]
  ];
  return '<h3>' + esc(T('overview.keyNumbers')) + '</h3>' +
    '<ul class="kn-list">' + tiles.map(x => {
      const st = state(x[3]), stTxt = st ? T(st === 'ok' ? 'overview.onTarget' : 'overview.workOn') : '';
      // the icon's colour is the state (green on target, amber work on it); the words stay for screen readers and on hover
      return '<li class="kn ' + st + '"' + (st ? ' title="' + esc(stTxt) + '"' : '') + '><span class="kn-ic" aria-hidden="true">' + OV_IC[x[0]] + '</span><span class="kn-txt"><span class="kn-lab">' + esc(x[2]) + '</span><b>' + x[1] + '</b>' + (st ? '<span class="sr-only">' + esc(stTxt) + '</span>' : '') + '</span></li>';
    }).join('') + '</ul>';
}
RENDER.report = function () {
  const s = S.currentSession;
  if (!s) { go('home'); return; }
  const sc = s.sc, an = s.an;
  $('#repMeta').textContent = T('report.meta', { title: s.title, accent: s.accent ? T('report.accentPart', { accent: s.accent }) : '' }) + (s.compact ? ' · ' + T('report.compactNote') : '');
  $('#player').hidden = !!s.remote && !s.audioUrl;   // compact session or audio file not available
  const bad = sc.status !== 'ok';
  $('#repState').hidden = !bad; $('#repMain').hidden = bad;
  $('#repHeadActions').hidden = !bad;   // normally the two buttons sit at the top of the pinned right column
  hideTip();
  if (bad) {
    $('#repState').innerHTML = '<div class="panel state"><span class="pill bad">' + IC.alert + esc(T('common.na')) + '</span><h2>' + esc(T('report.stInsT')) + '</h2><p>' + esc(sc.reason === 'empty_transcript' ? T('eval.insEmpty') : T('report.stInsD', { p: Math.round((sc.voicedRatio || 0) * 100) })) + '</p><button class="btn btn-primary" type="button" data-go="practice">' + esc(T('report.stInsCta')) + '</button></div>';
    return;
  }
  $('#repOverview').innerHTML = overviewHtml(s);
  $('#repKeyNumbers').innerHTML = keyNumbersHtml(sc);
  $('#transcriptView').innerHTML = buildTranscript(an);
  S.play = { t: 0, on: false, iv: null };
  bindPlayerAudio(s);
  const pd = progressDelta(S.sessions.filter(x => x.ts <= s.ts));
  $('#repScoreCard').innerHTML = '<h3>' + esc(T('report.overall')) + '</h3>' +
    '<div class="rep-score-row">' +   // score and progress share one line (the progress note wraps under it when long)
    (sc.overall != null ? '<div class="hero-score"><b class="num">' + sh(sc.overall) + '</b><span>' + esc(T('report.outOf')) + '</span></div>' : '<div class="hero-score"><b>' + esc(T('common.na')) + '</b></div>') +
    (pd.d == null ? '<p class="note">' + esc(T('report.deltaNeed', { n: pd.n })) + '</p>' : deltaPill(pd, false)) + '</div>' +
    '<h3 style="margin-top:16px">' + esc(T('report.parts')) + '</h3>' + partsHtml(sc) +
    (hasBase(sc) ? '' : '<p class="note" style="margin-top:12px">' + esc(T('report.noBaseline')) + '</p>');
  drawVolume(s);
  updatePlayer();
  fitReportAside();
};
/* The right column stays pinned just under the top bar while the page scrolls, and must fit the
   screen there (never under the top bar, never its own scrollbar). When it is too tall it gets
   tighter step by step: 1. hide the small line under each part score (the details window has it),
   2. hide the "no baseline" note, 3. scale the whole column down until it fits. */
export function fitReportAside() {
  const a = $('.rep-aside'); if (!a || !a.offsetParent) return;
  const acts = $('.rep-actions', a), head = $('#screenReport > .head');
  a.classList.remove('tight', 'tighter'); a.style.zoom = ''; a.style.top = ''; a.style.marginTop = ''; acts.style.height = ''; acts.style.marginBottom = '';
  if (getComputedStyle(a).position !== 'sticky') return;   // narrow screens: the column sits above the report, no pinning
  // At first the buttons sit on the title's row: the column is pulled up by the title block, its button row
  // is as tall as that block, so the panels below start level with the Overview on the left. Scrolling
  // down, the whole column (buttons included) stays pinned under the top bar.
  const headH = head.offsetHeight, headGap = parseFloat(getComputedStyle(head).marginBottom) || 0, colGap = parseFloat(getComputedStyle(a).rowGap) || 0;
  const align = z => {
    a.style.marginTop = (-(headH + headGap) / z) + 'px';
    acts.style.height = (headH / z) + 'px';
    acts.style.marginBottom = ((headGap - colGap) / z) + 'px';
  };
  align(1);
  const hh = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--hh')) || 64;
  const room = window.innerHeight - hh - 32;
  if (a.offsetHeight <= room) return;
  a.classList.add('tight');
  if (a.offsetHeight <= room) return;
  a.classList.add('tighter');
  if (a.offsetHeight > room) {
    const z = Math.max(0.6, room / a.offsetHeight);
    a.style.zoom = String(z);
    a.style.top = ((hh + 16) / z) + 'px';   // zoom scales the sticky offset too: keep the real gap under the top bar at 16px
    align(z);                               // and the pull-up and button row, so they still line up with the title
  }
}
window.addEventListener('resize', () => { if (S.screen === 'report') fitReportAside(); });
// the column's own height can change after drawing too (fonts, long progress note)
if (window.ResizeObserver && $('.rep-aside')) new ResizeObserver(() => { if (S.screen === 'report') fitReportAside(); }).observe($('.rep-aside'));

/* ---- detail windows. Assessments and suggestions are deterministic templates over the scores (the LLM never grades). ---- */
export const PART_KEYS = { A: 'pA', F: 'pF', P: 'pP', S: 'pS' };
export const bandOf = v => (v >= 85 ? 'good' : v >= 70 ? 'mid' : 'low');
export const BAND_PILL = { good: 'ok', mid: 'warn', low: 'bad' };
export const secHtml = (title, inner) => '<section class="dsec"><h3>' + esc(title) + '</h3>' + inner + '</section>';
export function tipsHtml(list) {
  return list.length ? '<ul class="todo">' + list.map(t => '<li><span>' + esc(t) + '</span></li>').join('') + '</ul>' : '<p class="note">' + esc(T('part.nothing')) + '</p>';
}
export function statRows(head, rows) {
  return '<table class="stbl"><thead><tr>' + head.map(h => '<th scope="col">' + esc(h) + '</th>').join('') + '</tr></thead><tbody>' +
    rows.map(r => '<tr><th scope="row">' + esc(r[0]) + '</th>' + r.slice(1, -1).map(c => '<td class="mute">' + esc(c) + '</td>').join('') + '<td>' + esc(r[r.length - 1]) + '</td></tr>').join('') + '</tbody></table>';
}
export function wordChips(ws, max) {
  return '<div class="chipwrap">' + ws.slice(0, max).map(w => '<button type="button" class="chipw ' + w.status + '" data-wi="' + w.i + '">' + esc(plain(w.raw)) + '</button>').join('') +
    (ws.length > max ? '<span class="note">' + esc(T('part.more', { n: ws.length - max })) + '</span>' : '') + '</div>';
}
export const chartBox = (title, capId, chId, extra) => '<div class="chartbox dchart"><h3>' + esc(title) + '</h3><p class="cap" id="' + capId + '"></p><div class="chart" id="' + chId + '"></div>' + (extra ? '<p class="note read">' + esc(extra) + '</p>' : '') + '</div>';

export function partA(s) {
  const sc = s.sc, an = s.an, bad = sc.sub + sc.del;
  const rev = an.words.filter(w => w.status === 'wrong' || w.status === 'missing');
  const tips = [];
  if (sc.sub) tips.push(T('part.A_tipWrong', { n: sc.sub }));
  if (sc.del) tips.push(T('part.A_tipMiss', { n: sc.del }));
  return secHtml(T('part.assess'), '<p>' + esc(T('part.A_' + bandOf(sc.A), { bad, total: sc.N, ok: sc.N - bad })) + '</p>') +
    secHtml(T('part.measured'), statRows([T('part.colMeasure'), T('part.colNote'), T('part.colCount')], [
      [T('part.A_total'), T('part.A_totalH'), sc.N], [T('part.A_wrong'), T('part.A_wrongH'), sc.sub],
      [T('part.A_miss'), T('part.A_missH'), sc.del], [T('part.A_near'), T('part.A_nearH'), sc.near]
    ]) + '<p class="note" style="margin-top:8px">' + esc(T('part.A_formula', { bad, total: sc.N, a: sh(sc.A) })) + '</p>') +
    (rev.length ? secHtml(T('part.review'), '<p class="note" style="margin-bottom:8px">' + esc(T('part.reviewHint')) + '</p>' + wordChips(rev, 16)) : '') +
    secHtml(T('part.suggest'), tipsHtml(tips));
}
export function partF(s) {
  const sc = s.sc, an = s.an, areas = [], tips = [];
  if (sc.Fwpm != null && sc.Fwpm < 85) areas.push(T('report.areaWpm'));
  if (sc.Fpause != null && sc.Fpause < 85) areas.push(T('report.areaPause'));
  if (sc.Ffiller != null && sc.Ffiller < 85) areas.push(T('report.areaFiller'));
  if (sc.Fwpm != null && sc.Fwpm < 85) tips.push(T(sc.wpm < ADR.wpmLo ? 'part.F_tipSlow' : 'part.F_tipFast', { v: Math.round(sc.wpm) }));
  if (sc.Fpause != null && sc.Fpause < 85) tips.push(T('part.F_tipPause', { v: fx(sc.H, 1) }));
  if (sc.Ffiller != null && sc.Ffiller < 85) tips.push(T('part.F_tipFiller', { v: fx(sc.R, 1) }));
  const win = paceWindows(an), inBand = win.filter(w => w.wpm >= ADR.wpmLo && w.wpm <= ADR.wpmHi).length;
  const longest = an.pauses.reduce((m, p) => (!m || p.dur > m.dur ? p : m), null), hes = an.pauses.filter(p => p.kind !== 'natural').length;
  return secHtml(T('part.assess'), '<p>' + esc(T('part.F_' + bandOf(sc.F)) + (areas.length ? ' ' + T('part.F_watch', { areas: areas.join(', ') }) : '')) + '</p>') +
    secHtml(T('part.measured'), statRows([T('part.colMeasure'), T('part.colResult'), T('part.colTarget'), T('part.colScore')], [
      [T('part.F_pace'), (sc.wpm == null ? T('common.na') : Math.round(sc.wpm)) + ' ' + T('report.unitWpm'), T('part.F_paceT'), sh(sc.Fwpm)],
      [T('part.F_pause'), fx(sc.H, 1) + ' / min', T('part.F_pauseT'), sh(sc.Fpause)],
      [T('part.F_filler'), fx(sc.R, 1) + '%', T('part.F_fillerT'), sh(sc.Ffiller)]
    ]) + '<p class="note" style="margin-top:8px">' + esc(T('part.F_avg')) + '</p>') +
    chartBox(T('report.cPace'), 'capPace', 'chPace', T('part.F_paceRead', { n: inBand, total: win.length })) +
    chartBox(T('report.cPause'), 'capPause', 'chPause', longest ? T('part.F_pauseRead', { d: longest.dur.toFixed(1), t: fmtTime(longest.start), h: hes, n: an.pauses.length }) : '') +
    secHtml(T('part.suggest'), tipsHtml(tips));
}
export function partP(s) {
  const sc = s.sc, an = s.an, near = an.words.filter(w => w.status === 'near'), areas = [], tips = [];
  if (sc.Pclar != null && sc.Pclar < 85) areas.push(T('report.areaClarity'));
  if (sc.Ppitch != null && sc.Ppitch < 85) areas.push(T('report.areaPitch'));
  if (near.length) tips.push(T('part.P_tipNear', { n: near.length }));
  if (sc.Rst != null && sc.Rst < ADR.monotone) tips.push(T('part.P_tipMono', { v: fx(sc.Rst, 1) }));
  else if (sc.Ppitch != null && sc.Ppitch < 85) tips.push(T('part.P_tipRange', { v: fx(sc.Rst, 1) }));
  return secHtml(T('part.assess'), '<p>' + esc(T('part.P_' + bandOf(sc.P)) + (areas.length ? ' ' + T('part.P_watch', { areas: areas.join(', ') }) : '')) + '</p>' +
      '<div class="callout">' + esc(T('report.lgNote')) + '</div>') +
    secHtml(T('part.measured'), statRows([T('part.colMeasure'), T('part.colResult'), T('part.colTarget'), T('part.colScore')], [
      [T('part.P_clar'), sc.near == null || sc.N == null ? T('common.na') : sc.near + ' / ' + sc.N, T('part.P_clarT'), sh(sc.Pclar)],
      [T('part.P_pitch'), fx(sc.Rst, 1) + ' ' + T('report.unitSt'), T('part.P_pitchT'), sh(sc.Ppitch)]
    ]) + '<p class="note" style="margin-top:8px">' + esc(T('part.P_avg')) + '</p>' + (hasBase(sc) ? '' : '<p class="note" style="margin-top:6px">' + esc(T('report.noBaseline')) + '</p>')) +
    chartBox(T('report.cPitch'), 'capRepPitch', 'chRepPitch', '') +
    (near.length ? secHtml(T('part.review'), '<p class="note" style="margin-bottom:8px">' + esc(T('part.reviewHint')) + '</p>' + wordChips(near, 16)) : '') +
    secHtml(T('part.suggest'), tipsHtml(tips));
}
export function partS(s) {
  const sc = s.sc, an = s.an, drift = sc.nSent - sc.cosOk, tips = [];
  if (drift) tips.push(T('part.S_tipDrift', { n: drift }));
  return secHtml(T('part.assess'), '<p>' + esc(T('part.S_' + bandOf(sc.S), { n: drift, total: sc.nSent })) + '</p>') +
    secHtml(T('part.measured'), statRows([T('part.colMeasure'), T('part.colTarget'), T('part.colResult')], [
      [T('part.S_ok'), T('part.S_okT'), sc.cosOk + ' / ' + sc.nSent]
    ])) +
    secHtml(T('part.S_listTitle'), '<p class="note" style="margin-bottom:8px">' + esc(T('part.S_listHint')) + '</p><ul class="sentlist">' +
      an.sentences.map((t, i) => { const ok = an.cos[i] != null && an.cos[i] >= ADR.cosine; return '<li><span class="pill ' + (ok ? 'ok' : 'bad') + '">' + fx(an.cos[i], 2) + '</span><span>' + esc(t) + '</span></li>'; }).join('') + '</ul>') +
    secHtml(T('part.suggest'), tipsHtml(tips));
}
export const PART_BODY = { A: partA, F: partF, P: partP, S: partS };
export const PART_CHARTS = { F: s => { drawPace(s); drawPause(s); }, P: s => { drawPitch(s); } };
/* "View details": opens on the weakest scored part (the one most worth reading), Accuracy if none */
export function openDetails() {
  const sc = S.currentSession && S.currentSession.sc; if (!sc) return;
  const scored = Object.keys(PART_KEYS).filter(k => Number.isFinite(sc[k]));
  openPart(scored.length ? scored.reduce((m, k) => (sc[k] < sc[m] ? k : m)) : 'A');
}
/* Show one part in the detail window (opens it if closed). The tabs at the top switch parts. */
export function openPart(key) {
  const s = S.currentSession;
  if (!s || s.sc.status !== 'ok' || !PART_BODY[key]) return;
  hideTip();
  const v = s.sc[key], b = bandOf(v);   // v null: part not scored -> N/A pill, no body, no charts
  $$('#mpartTabs [role=tab]').forEach(t => { const on = t.getAttribute('data-part') === key; t.setAttribute('aria-selected', String(on)); t.tabIndex = on ? 0 : -1; });
  $('#mpartPanel').setAttribute('aria-labelledby', 'mpartTab' + key);
  const m = $('#componentDetail'), wasOpen = m.classList.contains('show'), panel = $('#mpartPanel');
  stopPartMotion(panel);
  const h0 = panel.offsetHeight;                                   // height of the part shown until now (switching tabs)
  const pill = $('#mpartPill'); pill.className = 'pill ' + (v == null ? 'warn' : BAND_PILL[b]); pill.textContent = v == null ? T('common.na') : sh(v) + ' / 100 · ' + T('part.band_' + b);
  $('#mpartSub').textContent = T('part.weight', { w: T('report.w' + key) });
  $('#mpartBody').innerHTML = v == null ? '<p class="note">' + esc(T('eval.naPart')) + '</p>' : PART_BODY[key](s);
  if (!wasOpen) openModal('componentDetail', { focus: '#mpartTab' + key });
  moveSegPills(wasOpen, m);
  $('#componentDetail .box').scrollTop = 0;
  if (v != null && PART_CHARTS[key]) PART_CHARTS[key](s);          // draw after the window is visible, so the charts get their width
  if (wasOpen) playPartSwitch(panel, h0);
}
/* Switching tabs: the panel grows or shrinks smoothly from the old part's height to the new one's while
   the new content fades in and settles. The steps end on a timer, so a hidden tab (no animation frames)
   can never leave the panel half-open or see-through. Off with "reduce motion". */
const PART_GROW_MS = 320, PART_FADE_MS = 300;
function stopPartMotion(panel) {
  clearTimeout(panel._partT);
  panel.getAnimations().forEach(a => a.cancel());
  panel.style.overflow = '';
}
function playPartSwitch(panel, h0) {
  if (!panel.animate || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const h1 = panel.offsetHeight;
  panel.style.overflow = 'hidden';
  if (Math.abs(h1 - h0) > 1) panel.animate([{ height: h0 + 'px' }, { height: h1 + 'px' }], { duration: PART_GROW_MS, easing: 'cubic-bezier(.4, 0, .2, 1)' });
  panel.animate([{ opacity: 0, transform: 'translateY(8px)' }, { opacity: 1, transform: 'none' }], { duration: PART_FADE_MS, delay: 60, easing: 'ease-out', fill: 'backwards' });
  panel._partT = setTimeout(() => stopPartMotion(panel), Math.max(PART_GROW_MS, PART_FADE_MS + 60) + 40);
}
export function seekWord(i) {
  const words = S.currentSession.an.words, w = words[i];
  let t = w.start;
  if (t == null) { const prev = words.slice(0, w.i).reverse().find(x => x.end != null); t = prev ? prev.end : 0; }
  seekTo(Math.max(0, t - 0.2), w.status !== 'missing');
}

/* ---- charts ---- */
export function drawPace(s) {
  const an = s.an, win = paceWindows(an);
  chart('#chPace', {
    kind: 'line', aria: T('report.cPace'), pts: win.map(w => ({ y: w.wpm, tip: w.label + ' · ' + Math.round(w.wpm) + ' ' + T('report.unitWpm') })), xTick: (p, i) => win[i].label,
    band: { lo: ADR.wpmLo, hi: ADR.wpmHi, label: ADR.wpmLo + '–' + ADR.wpmHi },
    table: { head: [T('chart.time'), T('report.unitWpm')], rows: win.map(w => [w.label, Math.round(w.wpm)]) }
  });
  $('#capPace').textContent = T('report.capPace');
}
export function drawPause(s) {
  const an = s.an, hesN = an.pauses.filter(p => p.kind !== 'natural').length;
  $('#capPause').textContent = T('report.capPause', { n: an.pauses.length, h: hesN });
  const pc = { natural: '#8A94A6', hesitation: 'var(--warn-mark)', forgot: 'var(--bad)' };
  chart('#chPause', {
    kind: 'bar', xNum: true, xMin: 0, xMax: an.dur, barW: 8, yMin: 0, aria: T('report.cPause'), fmtY: v => v.toFixed(1),
    pts: an.pauses.map(p => ({ x: p.start, y: p.dur, color: pc[p.kind], tip: fmtTime(p.start) + ' · ' + p.dur.toFixed(1) + ' s · ' + T(p.kind === 'natural' ? 'report.pauseNatural' : p.kind === 'forgot' ? 'report.pauseForgot' : 'report.pauseHes') })),
    xTick: p => fmtTime(p.x),
    legend: [{ label: T('report.lgNatural'), color: pc.natural }, { label: T('report.lgHesitation'), color: pc.hesitation }, { label: T('report.lgForgot'), color: pc.forgot }],
    table: { head: [T('chart.time'), T('chart.value'), T('chart.type')], rows: an.pauses.map(p => [fmtTime(p.start), p.dur.toFixed(1) + ' s', T(p.kind === 'natural' ? 'report.pauseNatural' : p.kind === 'forgot' ? 'report.pauseForgot' : 'report.pauseHes')]) }
  });
}
export function drawPitch(s) {
  const an = s.an, sc = s.sc, sp = an.words.filter(w => w.start != null && w.f0 != null);
  $('#capRepPitch').textContent = T('report.capPitch', { r: fx(sc.Rst, 1) });
  if (!sp.length) { $('#capRepPitch').textContent = T('eval.noPitch'); $('#chRepPitch').innerHTML = ''; $('#chRepPitch')._spec = null; return; }
  chart('#chRepPitch', {
    kind: 'line', xNum: true, xMin: 0, xMax: an.dur, aria: T('report.cPitch'), endLabel: false, ref: { y: 0 }, fmtY: v => v.toFixed(0),
    pts: sp.map(w => ({ x: w.start, y: w.f0, tip: fmtTime(w.start) + ' · ' + w.f0.toFixed(1) + ' ' + T('report.unitSt') })),
    xTick: (p, i) => (i % 8 === 0 ? fmtTime(p.x) : ''),
    table: { head: [T('chart.time'), T('report.unitSt')], rows: sp.map(w => [fmtTime(w.start), w.f0.toFixed(1)]) }
  });
}
export function drawVolume(s) {
  const an = s.an, sp = an.words.filter(w => w.start != null && w.vol != null);
  if (!sp.length) { $('#volRead').textContent = T('eval.noVol'); $('#chVol').innerHTML = ''; $('#chVol')._spec = null; return; }
  const hiW = sp.reduce((m, w) => (w.vol > m.vol ? w : m)), loW = sp.reduce((m, w) => (w.vol < m.vol ? w : m));
  $('#volRead').textContent = T('report.volRead', { tHi: fmtTime(hiW.start), hi: hiW.vol.toFixed(0), tLo: fmtTime(loW.start), lo: loW.vol.toFixed(0), r: (hiW.vol - loW.vol).toFixed(0) });
  chart('#chVol', {
    kind: 'line', xNum: true, xMin: 0, xMax: an.dur, aria: T('report.cVol'), endLabel: false, fmtY: v => v.toFixed(0),
    pts: sp.map(w => ({ x: w.start, y: w.vol, tip: fmtTime(w.start) + ' · ' + w.vol.toFixed(0) + ' ' + T('report.unitDb') })),
    xTick: (p, i) => (i % 8 === 0 ? fmtTime(p.x) : ''),
    table: { head: [T('chart.time'), T('report.unitDb')], rows: sp.map(w => [fmtTime(w.start), w.vol.toFixed(0)]) }
  });
}
/* playback: real <audio> when the session has audioUrl (evaluated recording), otherwise the old simulated clock (sample sessions) */
export let PA = null;
export const hasAudio = () => !!(PA && S.currentSession && S.currentSession.audioUrl && PA._url === S.currentSession.audioUrl);
export function bindPlayerAudio(s) {
  closeWordCoach(false);
  if (!PA) {
    PA = new Audio(); PA.preload = 'auto';
    PA.addEventListener('loadedmetadata', () => { if (!Number.isFinite(PA.duration)) { PA._fix = true; PA.currentTime = 1e101; } });   // MediaRecorder webm has no duration: force the browser to scan to the end (UNTESTED trick)
    PA.addEventListener('timeupdate', () => {
      if (PA._fix) { PA._fix = false; PA.currentTime = 0; return; }
      if (hasAudio()) { S.play.t = PA.currentTime; updatePlayer(); }
    });
    PA.addEventListener('ended', () => { S.play.on = false; if (hasAudio()) { S.play.t = S.currentSession.an.dur; updatePlayer(); } });
    PA.addEventListener('pause', () => { if (hasAudio()) { S.play.on = false; updatePlayer(); } });
  }
  PA.pause(); PA._fix = false;
  if (s && s.audioUrl) { if (PA._url !== s.audioUrl) { PA._url = s.audioUrl; PA.src = s.audioUrl; } }
  else if (PA._url) { PA._url = null; PA.removeAttribute('src'); PA.load(); }
}
export function revokeAudio(s) {
  if (!s || !s.audioUrl) return;
  if (PA && PA._url === s.audioUrl) { PA.pause(); PA._url = null; PA.removeAttribute('src'); PA.load(); }
  if (s.audioUrl.startsWith('blob:')) URL.revokeObjectURL(s.audioUrl);   // signed URLs from the server are not ours to revoke
  s.audioUrl = null;
}
export function stopPlayback() { if (S.play.iv) clearInterval(S.play.iv); S.play.iv = null; S.play.on = false; if (PA && !PA.paused) PA.pause(); if ($('#playBtn')) updatePlayer(); }
export function updatePlayer() {
  const s = S.currentSession; if (!s || !s.an) return;
  const dur = s.an.dur, t = Math.min(S.play.t, dur);
  $('#seek').max = Math.round(dur * 10); $('#seek').value = Math.round(t * 10);
  $('#seek').setAttribute('aria-valuetext', fmtTime(t) + ' / ' + fmtTime(dur));
  $('#playTime').textContent = fmtTime(t) + ' / ' + fmtTime(dur);
  $('#playBtn').innerHTML = S.play.on ? IC.pause : IC.play;
  $('#playBtn').setAttribute('aria-label', T(S.play.on ? 'common.pause' : 'common.play'));
  const cur = s.an.words.find(w => w.status !== 'missing' && w.start <= t && t < w.end);
  $$('#transcriptView .w.now').forEach(e => e.classList.remove('now'));
  if (cur) { const el = $('#transcriptView [data-i="' + cur.i + '"]'); if (el) { el.classList.add('now'); if (S.play.on && el.scrollIntoView) el.scrollIntoView({ block: 'nearest' }); } }
}
export function startPlayback() {
  const s = S.currentSession; if (!s) return;
  if (hasAudio()) {
    if (S.play.t >= s.an.dur - 0.05) { S.play.t = 0; PA.currentTime = 0; }
    S.play.on = true; PA.play().catch(() => { S.play.on = false; updatePlayer(); }); updatePlayer(); return;
  }
  if (S.play.t >= s.an.dur) S.play.t = 0;
  S.play.on = true;
  S.play.iv = setInterval(() => {
    S.play.t += 0.1;
    if (S.play.t >= s.an.dur) { S.play.t = s.an.dur; stopPlayback(); }
    updatePlayer();
  }, 100);
  updatePlayer();
}
export function seekTo(t, play) { stopPlayback(); S.play.t = Math.max(0, t); if (hasAudio()) PA.currentTime = S.play.t; if (play) startPlayback(); else updatePlayer(); }
export function onTxClick(e) {
  const sb = e.target.closest('.wc-sent-btn'), tb = e.target.closest('.tx-time'), wb = e.target.closest('.w[data-i]');
  if (sb) { openSentenceCoach(+sb.dataset.si, sb); return; }
  if (tb) { seekTo(parseFloat(tb.getAttribute('data-t0')), true); return; }
  if (wb && S.currentSession) { const i = +wb.getAttribute('data-i'); closeWordCoach(false); seekWord(i); openWordCoach(i, wb); }
}
