import { chart } from '../charts.js';
import { ADR, adviceList, fx, progressDelta, sh } from '../data.js';
import { T } from '../i18n.js';
import { renderHistory } from '../screens/history.js';
import { RENDER, S } from '../state.js';
import { $, IC, esc, fmtDay, fmtDayLong, minus, scored } from '../utils.js';

/* ---------- Home ---------- */
export function deltaPill(pd, signed) {
  if (pd.d == null) return '<p class="note">' + esc(T('home.deltaNeed', { n: pd.n })) + '</p>';
  const d = pd.d;
  if (Math.abs(d) < 0.5) return '<span class="pill">' + IC.flat + esc(T('home.deltaFlat')) + '</span>';
  if (d > 0) return '<span class="pill ok">' + IC.up + esc(signed === false ? T('report.deltaUp', { d: d.toFixed(1) }) : T('home.deltaUp', { d: '+' + d.toFixed(1) })) + '</span>';
  return '<span class="pill warn">' + IC.down + esc(signed === false ? T('report.deltaDown', { d: minus(d.toFixed(1)) }) : T('home.deltaDown', { d: minus(d.toFixed(1)) })) + '</span>';
}
export function dayCounts() {
  const days = [], today = new Date(); today.setHours(0, 0, 0, 0);
  for (let i = 13; i >= 0; i--) { const d = new Date(today); d.setDate(d.getDate() - i); days.push({ d, min: 0, key: d.toDateString() }); }
  S.sessions.forEach(s => { const k = new Date(s.ts).toDateString(), row = days.find(x => x.key === k); if (row) row.min += (s.dur || 0) / 60; });
  const set = new Set(days.filter(x => x.min > 0).map(x => x.key));
  let streak = 0, i = days.length - 1;
  if (!set.has(days[i].key)) i--;
  while (i >= 0 && set.has(days[i].key)) { streak++; i--; }
  return { days, practised: set.size, streak };
}
export const lineSpec = (ss0, pick, o) => { const ss = ss0.filter(s => pick(s) != null); return Object.assign({   // null values are left out, not drawn as 0
  kind: 'line',
  pts: ss.map(s => ({ x: 0, y: pick(s), tip: fmtDay(s.ts) + ' · ' + (o.fmtTip || (v => v.toFixed(0)))(pick(s)) })),
  xTick: (p, i) => fmtDay(ss[i].ts),
  table: { head: [T('history.colDate'), o.col], rows: ss.map(s => [fmtDay(s.ts), (o.fmtTip || (v => v.toFixed(0)))(pick(s))]) }
}, o); };
RENDER.home = function () {
  const ss = scored(), n = S.user.name;
  $('#homeH').textContent = T(S.sessions.length ? 'home.welcome' : 'home.welcomeNew', { name: n });
  const empty = !ss.length;
  $('#homeEmpty').hidden = !empty; $('#homeData').hidden = empty;
  if (empty) {
    $('#homeEmpty').innerHTML = '<h2>' + esc(T('home.emptyT')) + '</h2><p class="note">' + esc(T('home.emptyD')) + '</p><div class="row"><button class="btn btn-primary" type="button" data-go="practice">' + esc(T('home.nextFirstCta')) + '</button>' +
      (S.baseline ? '' : '<button class="btn" type="button" data-go="profile">' + esc(T('home.nextBaselineCta')) + '</button>') + '</div>';
    return;
  }
  const last = ss[ss.length - 1], pd = progressDelta(S.sessions);
  let nx;
  if (!S.baseline) {
    nx = '<span class="pill info">' + esc(T('home.nextKicker')) + '</span><h2>' + esc(T('home.nextBaselineT')) + '</h2><p>' + esc(T('home.nextBaselineD')) + '</p><div class="row" style="margin-top:16px"><button class="btn btn-primary" type="button" data-go="profile">' + esc(T('home.nextBaselineCta')) + '</button></div>';
  } else {
    const adv = adviceList(last.sc, 1, 101)[0];
    nx = '<span class="pill info">' + esc(T('home.nextKicker')) + '</span><h2>' + esc(T('home.nextWeakT', { area: adv.area })) + '</h2><p>' + esc(adv.text) + '</p><div class="row" style="margin-top:16px"><button class="btn btn-primary" type="button" data-go="practice">' + esc(T('home.nextWeakCta')) + '</button><button class="btn" type="button" data-go="scriptStudio">' + esc(T('home.nextScriptCta')) + '</button></div>';
  }
  $('#nextStep').innerHTML = nx;
  $('#latestPanel').innerHTML = '<h3>' + esc(T('home.latestTitle')) + '</h3><div class="bigscore"><b class="num">' + sh(last.sc.overall) + '</b><span class="mute">' + esc(T('report.outOf')) + '</span></div><div style="margin-top:10px">' + deltaPill(pd) + '</div><p class="note" style="margin-top:10px">' + esc(fmtDayLong(last.ts) + ' · ' + last.title) + '</p><div class="row" style="margin-top:14px"><button class="btn" type="button" data-open="' + last.id + '">' + esc(T('home.openReport')) + '</button></div>';

  const sn = ss.filter(s => s.sc.overall != null), ov = sn.map(s => s.sc.overall);   // null overall is not 0: left out of min/max and the chart
  $('#capScore').textContent = T('home.capScore', { v: sh(last.sc.overall), lo: sh(Math.min.apply(null, ov)), hi: sh(Math.max.apply(null, ov)) });
  chart('#chScore', lineSpec(sn, s => s.sc.overall, { aria: T('home.cScore'), col: T('history.colScore'), yMax: 100 }));
  const dc = dayCounts();
  $('#capActivity').textContent = T('home.capActivity', { days: dc.practised, n: 14, streak: dc.streak === 0 ? T('home.streakNone') : dc.streak === 1 ? T('home.streakDay') : T('home.streakDays', { n: dc.streak }) });
  chart('#chActivity', {
    kind: 'bar', aria: T('home.cActivity'), yMin: 0, include: [0.5], fmtY: v => v.toFixed(1),
    pts: dc.days.map(x => ({ y: x.min, tip: fmtDay(x.d) + ' · ' + x.min.toFixed(1) + ' min' })),
    xTick: (p, i) => fmtDay(dc.days[i].d),
    table: { head: [T('history.colDate'), T('chart.minutes')], rows: dc.days.map(x => [fmtDay(x.d), x.min.toFixed(1)]) }
  });
  $('#capWpm').textContent = T('home.capWpm', { v: fx(last.sc.wpm, 0) });
  chart('#chWpm', lineSpec(ss, s => s.sc.wpm, { aria: T('home.cWpm'), col: T('report.unitWpm'), band: { lo: ADR.wpmLo, hi: ADR.wpmHi, label: ADR.wpmLo + '–' + ADR.wpmHi }, fmtTip: v => Math.round(v) + ' ' + T('report.unitWpm') }));
  $('#capPitch').textContent = T('home.capPitch', { v: fx(last.sc.Rst, 1) });
  chart('#chPitch', lineSpec(ss, s => s.sc.Rst, { aria: T('home.cPitch'), col: T('report.unitSt'), yMin: 0, ref: { y: ADR.monotone, label: ADR.monotone + ' ' + T('report.unitSt') }, fmtY: v => v.toFixed(0), fmtTip: v => v.toFixed(1) + ' ' + T('report.unitSt') }));
  $('#capClarity').textContent = T('home.capClarity', { v: fx(last.sc.Pclar, 0) });
  chart('#chClarity', lineSpec(ss, s => s.sc.Pclar, { aria: T('home.cClarity'), col: T('history.colScore'), yMax: 100 }));
  renderHistory();
};
