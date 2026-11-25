import { chart } from '../charts.js';
import { ADR, adviceList, fx, progressDelta, sh } from '../data.js';
import { T } from '../i18n.js';
import { renderTodayPanel } from './schedule.js';
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
/* Hero: the first full screen of Home. One greeting, one summary line, one main action that
   depends on the latest result, and a hint to scroll down to progress and history.
   (A baseline is always there: the Baseline Gate asks for it right after log in.) */
function greeting(name) {
  const h = new Date().getHours();
  return T(h < 12 ? 'home.greetMorning' : h < 18 ? 'home.greetAfternoon' : 'home.greetEvening', { name });
}
function renderHero(ss) {
  $('#homeH').textContent = greeting(S.user.name);
  const script = '<button class="btn btn-lg" type="button" data-go="scriptStudio">' + esc(T('home.ctaScript')) + '</button>';
  if (!ss.length) {
    $('#homeSummary').textContent = T('home.summaryNew');
    $('#homeCta').innerHTML = '<button class="btn btn-primary btn-lg" type="button" data-go="practice">' + esc(T('home.ctaFirst')) + '</button>' + script;
    $('#homeMoreText').textContent = T('home.moreNew');
    return;
  }
  const last = ss[ss.length - 1], weekAgo = Date.now() - 7 * 24 * 3600 * 1000;
  const week = S.sessions.filter(s => s.ts >= weekAgo).length, score = sh(last.sc.overall);
  $('#homeSummary').textContent = T(week === 0 ? 'home.summaryIdle' : week === 1 ? 'home.summaryWeekOne' : 'home.summaryWeek', { n: week, score });
  const adv = adviceList(last.sc, 1, 101)[0];
  $('#homeCta').innerHTML = '<button class="btn btn-primary btn-lg" type="button" data-go="practice">' + esc(T('home.ctaFocus', { area: adv.area.toLowerCase() })) + '</button>' + script;
  $('#homeMoreText').textContent = T('home.more');
}
/* Lights off while scrolling down to the progress section: 0 at the top of Home, 1 after
   about half of the hero has scrolled away. CSS reads --hero-p (see .hero-glow). */
function syncHeroLight() {
  const hero = document.getElementById('homeHero');
  if (!hero || S.screen !== 'home') return;
  // short pages (no history yet) still reach "lights off" at the very bottom
  const room = document.documentElement.scrollHeight - window.innerHeight;
  const span = Math.max(1, Math.min(hero.offsetHeight * 0.55, room));
  const p = Math.min(1, Math.max(0, window.scrollY / span));
  hero.style.setProperty('--hero-p', p.toFixed(3));
}
window.addEventListener('scroll', syncHeroLight, { passive: true });   // one style write per event, cheap
/* Coming back to Home: start from "lights off" and play the "lights on" motion (same as scrolling up) */
export function heroLightsOn() {
  const hero = document.getElementById('homeHero');
  if (!hero) return;
  hero.classList.remove('hero-anim');
  hero.classList.add('hero-off');
  void hero.offsetWidth;   // apply "off" first, without a transition
  hero.classList.add('hero-anim');
  hero.classList.remove('hero-off');
  clearTimeout(hero._animT);
  hero._animT = setTimeout(() => hero.classList.remove('hero-anim'), 1300);
}
/* "Scroll for more": smooth unless the user asked for less motion */
export function scrollHomeDown() {
  const target = $('#homeData').hidden ? $('#homeEmpty') : $('#homeData');
  const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const top = target.getBoundingClientRect().top + window.scrollY - (parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--hh')) || 64) - 16;
  window.scrollTo({ top: Math.max(0, top), behavior: calm ? 'auto' : 'smooth' });
}
RENDER.home = function () {
  const ss = scored();
  renderHero(ss);
  renderTodayPanel();
  syncHeroLight();
  const empty = !ss.length;
  $('#homeEmpty').hidden = !empty; $('#homeData').hidden = empty;
  if (empty) { $('#homeEmpty').textContent = T('home.later'); return; }
  const last = ss[ss.length - 1], pd = progressDelta(S.sessions);
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
