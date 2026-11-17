import { S } from '../state.js';
import { $ } from '../utils.js';

export function syncHero() {
  document.body.classList.toggle('landing-view', S.view === 'landing');
  document.body.classList.toggle('app-view', S.view === 'app');
  $('#topbar').classList.toggle('hero', S.view === 'landing' && window.scrollY <= 40);
}
/* Size the scene like background-size: cover (left centre); on narrow screens a 440px-high strip at 18% */
export let stageRef = 0;   // stage height on the intro; the scene keeps this size while the taller sign-up form is open
export let sceneB = 0;     // scene bottom edge inside the stage, before any follow offset
export function syncStage() {
  const st = $('#lStage'), sc = $('#lScene');
  if (!st.offsetWidth) return;
  const W = st.offsetWidth, full = st.offsetHeight, narrow = window.innerWidth <= 900;
  let H = full;
  if (!st.classList.contains('is-auth')) stageRef = full; else if (stageRef) H = Math.min(full, stageRef);
  H = Math.min(H, window.innerHeight);   // the photo covers the first screen; below it the stage fades to dark
  const h = narrow ? 440 : Math.max(H, W * 893 / 1600), w = h * 1600 / 893;
  const top = narrow ? 0 : (H - h) / 2;
  sc.style.width = w + 'px'; sc.style.height = h + 'px';
  sc.style.left = (narrow ? (W - w) * .18 : 0) + 'px';
  sc.style.top = top + 'px';
  st.classList.toggle('tall', !narrow && top + h < full - 1);
  sceneB = top + h;
  st.style.setProperty('--sceneb', Math.round(sceneB + follow.y) + 'px');
  kickFollow();
}
/* Sign-up: the scene trails the scroll on a loose spring, so the mic stays beside the form and overshoots a little;
   while it moves, the live beam fades in over the baked one and sways with the speed */
export const follow = { y: 0, v: 0, raf: 0 };
export function followTarget() {
  const st = $('#lStage');
  if (S.view !== 'landing' || !st.classList.contains('is-auth') || window.innerWidth <= 900) return 0;
  return Math.max(0, Math.min(window.scrollY, st.offsetHeight - sceneB));
}
export function followStep() {
  const t = followTarget(), calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (calm) { follow.y = t; follow.v = 0; }
  else { follow.v += (t - follow.y) * .035 - follow.v * .3; follow.y += follow.v; }   // soft, well-damped spring
  const done = Math.abs(t - follow.y) < .3 && Math.abs(follow.v) < .03;
  if (done) { follow.y = t; follow.v = 0; }
  const st = $('#lStage'), sc = $('#lScene');
  sc.style.translate = '0 ' + follow.y.toFixed(1) + 'px';
  sc.style.setProperty('--fadeT', Math.min(follow.y, 160).toFixed(0) + 'px');
  sc.style.setProperty('--sway', Math.max(-1, Math.min(1, follow.v / 32)).toFixed(3));
  sc.style.setProperty('--bsway', Math.max(-1, Math.min(1, follow.v / 22)).toFixed(3));   // light sways livelier than the mic
  sc.style.setProperty('--live', Math.min(1, Math.abs(follow.v) / 3).toFixed(3));
  st.style.setProperty('--sceneb', Math.round(sceneB + follow.y) + 'px');
  follow.raf = done ? 0 : requestAnimationFrame(followStep);
}
export function kickFollow() { if (!follow.raf) follow.raf = requestAnimationFrame(followStep); }
export function setStageAuth(on) {
  $('#lStage').classList.toggle('is-auth', on);
  if (on) $('#lStage').classList.add('swept');   // lets the light swing back on the way out too
  $('#lIntro').inert = on; $('#lAuth').inert = !on;
  kickFollow();
}
