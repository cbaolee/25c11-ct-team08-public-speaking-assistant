import { redrawCharts } from './charts.js';
import { heroLightsOn } from './screens/home.js';
import { practiceLocked } from './screens/practice.js';
import { syncHero, syncStage } from './screens/landing.js';
import { stopPlayback } from './screens/report.js';
import { RENDER, S } from './state.js';
import { closeUserMenu } from './top_bar.js';
import { focusHeading, repaintScrollbar } from './ui.js';
import { $, $$ } from './utils.js';

/* Old screen: pinned where it was (out of the flow) and slid out to the left, then hidden */
/* Left-to-right order of the screens, used for the slide direction: the nav order (Home, Script, Practice),
   then Profile (with the baseline) on the far right. A report sits just right of the screen it was opened from. */
/* Screen name ('scriptStudio') -> element id ('screenScriptStudio'). */
export function screenId(name) { return 'screen' + name.charAt(0).toUpperCase() + name.slice(1); }

export const SCREEN_ORDER = { home: 0, scriptStudio: 1, practice: 2, schedule: 3, profile: 4 };
export function screenPos(name, from) {
  if (name === 'report') return (SCREEN_ORDER[from] !== undefined ? SCREEN_ORDER[from] : 0) + .5;
  return SCREEN_ORDER[name] !== undefined ? SCREEN_ORDER[name] : 0;
}
export function leaveScreen(el, dir) {
  dir = dir || 1;
  /* pinned where it is on screen now; go() then shifts it by the new screen's scroll position
     (keepLeavingInPlace), so the part the user was looking at stays put while it slides out */
  el.style.top = (el.offsetTop - window.scrollY) + 'px'; el.style.left = el.offsetLeft + 'px'; el.style.width = el.offsetWidth + 'px';
  el.classList.add('leaving'); el.setAttribute('aria-hidden', 'true');
  const a = el.animate([
    { opacity: 1, transform: 'none', filter: 'none' },
    { opacity: 0, transform: 'translateX(' + (-56 * dir) + 'px)', filter: 'blur(8px)' }
  ], { duration: 450, easing: 'cubic-bezier(.65, 0, .35, 1)', fill: 'forwards' });
  const done = () => { a.cancel(); el.classList.remove('leaving'); el.removeAttribute('aria-hidden'); el.style.top = el.style.left = el.style.width = ''; };
  a.onfinish = done; el._leaveDone = done;
}
/* The new screen slides in from the side (dir 1: from the right) and comes out of a blur. Also used
   for Home right after the loading screen, so the first look matches coming back from another screen. */
export function slideIn(el, dir, delay) {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  el.animate([
    { opacity: 0, transform: 'translateX(' + (56 * (dir || 1)) + 'px)', filter: 'blur(8px)' },
    { opacity: 1, transform: 'none', filter: 'none' }
  ], { duration: 600, delay: delay || 0, easing: 'cubic-bezier(.65, 0, .35, 1)', fill: 'backwards' });
}
export function endLeaving() { $$('.screen.leaving').forEach(s => { if (s._leaveDone) s._leaveDone(); }); }
/* Slide the white pill of each segmented tab group to its selected button; animate=false jumps there */
export function moveSegPills(animate, root) {
  $$('.seg', root || $('#viewApp')).forEach(seg => {
    const cur = $('button[aria-selected="true"]', seg);
    if (!cur || !cur.offsetWidth) { seg.classList.remove('pill-on'); return; }
    const still = !animate || !seg.classList.contains('pill-on');
    seg.classList.toggle('pill-still', still);
    seg.style.setProperty('--seg-x', cur.offsetLeft + 'px'); seg.style.setProperty('--seg-y', cur.offsetTop + 'px');
    seg.style.setProperty('--seg-w', cur.offsetWidth + 'px'); seg.style.setProperty('--seg-h', cur.offsetHeight + 'px');
    seg.classList.add('pill-on');
    if (still) { getComputedStyle(seg, '::before').transform; seg.classList.remove('pill-still'); }
  });
}
/* Any tab change inside the app (Practice: My script / Sample / Write my own, Record / Upload) slides its pill */
new MutationObserver(() => moveSegPills(true)).observe(document.getElementById('viewApp'), { subtree: true, attributes: true, attributeFilter: ['aria-selected'] });
/* Tab change inside a panel (Practice: My script / Sample / Write my own, Record / Upload):
   the old content fades out, the panel grows or shrinks to the new height, the new content fades in.
   The click is held back during the fade-out, then passed on to the tab's own handler. */
document.getElementById('viewApp').addEventListener('click', e => {
  const b = e.target.closest('.seg button');
  if (!b || b._passing || b.disabled || b.getAttribute('aria-selected') === 'true') return;
  const seg = b.closest('.seg'), panel = b.closest('.panel');
  // data-tab-static: the tab contents share one fixed-size cell and cross-fade in CSS (Practice Record / Upload).
  // Animating the panel height there turns off position: sticky for a moment and the voice box jumps.
  if (!panel || seg._busy || seg.hasAttribute('data-tab-static') || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  e.stopImmediatePropagation(); e.preventDefault();
  seg._busy = true;
  // the content that changes is what follows the tab bar; a bar that holds fixed buttons too
  // (Practice: Generate a script) is marked data-tab-bar, and only what follows the whole bar fades
  const bar = seg.closest('[data-tab-bar]') || seg;
  const after = () => [...bar.parentElement.children].slice([...bar.parentElement.children].indexOf(bar) + 1).filter(el => !el.hidden && el.offsetParent !== null);
  $$('button', seg).forEach(x => x.setAttribute('aria-selected', String(x === b)));   // pill starts sliding now
  const h0 = panel.offsetHeight, old = after();
  Promise.all(old.map(el => el.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 200, easing: 'ease-in', fill: 'forwards' }).finished)).then(() => {
    b._passing = true; b.click(); b._passing = false;
    old.forEach(el => el.getAnimations().forEach(a => a.cancel()));
    const h1 = panel.offsetHeight;
    panel.style.overflow = 'hidden';
    const grow = panel.animate([{ height: h0 + 'px' }, { height: h1 + 'px' }], { duration: 380, easing: 'cubic-bezier(.65, 0, .35, 1)' });
    grow.onfinish = grow.oncancel = () => { panel.style.overflow = ''; };
    after().forEach(el => el.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 320, delay: 140, easing: 'ease-out', fill: 'backwards' }));
    seg._busy = false;
  });
}, true);
/* Slide the blue pill under the current nav button; animate=false jumps there (first show, resize) */
export function moveNavPill(animate) {
  const nav = $('#nav'), cur = $('#nav [aria-current="page"]');
  if (!nav || nav.hidden || !cur || !cur.offsetWidth) { if (nav) nav.classList.remove('pill-on'); return; }
  const still = !animate || !nav.classList.contains('pill-on');
  nav.classList.toggle('pill-still', still);
  nav.style.setProperty('--pill-x', cur.offsetLeft + 'px');
  nav.style.setProperty('--pill-w', cur.offsetWidth + 'px');
  nav.classList.add('pill-on');
  if (still) { getComputedStyle(nav, '::before').transform; nav.classList.remove('pill-still'); }   // apply the jump, then turn the slide back on
}
export function syncHeader() { document.documentElement.style.setProperty('--hh', ($('#topbar').offsetHeight || 64) + 'px'); }

export function showView(v) {
  S.view = v;
  $('#viewLanding').hidden = v !== 'landing';
  $('#viewApp').hidden = v !== 'app';
  $('#nav').hidden = v !== 'app';
  syncHero(); syncHeader(); syncStage(); moveNavPill(false);
}
export function paintAvatar(el) {
  el.textContent = '';
  if (S.avatar) { const i = document.createElement('img'); i.alt = ''; i.src = S.avatar; el.appendChild(i); }
  else el.textContent = (S.user ? S.user.name.trim().charAt(0) : '?').toUpperCase();
}
export function renderAccount() {
  const on = !!S.user;
  $('#guestBtns').hidden = on;
  $('#userBtn').hidden = !on;
  closeUserMenu();
  if (on) { $('#uName').textContent = S.user.name; paintAvatar($('#avTop')); }
  syncHeader();
}
/* Each screen remembers where the user had scrolled to, and going back to it returns there instead
   of to the top. Reports are remembered per session. Cleared at log in (enterApp). */
const scrollKey = name => (name === 'report' ? 'report:' + (S.currentSession ? S.currentSession.id : '') : name);
/* the old screen sliding out is placed for scroll 0; move it by the new scroll so it does not jump */
function keepLeavingInPlace(el, y) {
  if (!el || !el.classList.contains('leaving')) return;
  const base = el._top0 != null ? el._top0 : (el._top0 = parseFloat(el.style.top) || 0);
  el.style.top = (base + y) + 'px';
}
/* Short app pages are made 1px taller than the screen so they still get a real (dark) scrollbar
   (base.css). There is nothing to scroll, so hide the thumb and leave a plain dark track. */
export function syncScrollThumb() {
  const de = document.documentElement, want = de.scrollHeight - window.innerHeight <= 2;
  if (de.classList.contains('no-scroll') === want) return;
  de.classList.toggle('no-scroll', want);
  repaintScrollbar();   // Chrome keeps the old thumb colour otherwise
}
export function go(name, opts) {
  opts = opts || {};
  if (!S.user) { showView('landing'); return; }
  if (name === 'practice' && practiceLocked()) return;   // an evaluation runs in the background: Practice waits for it
  if (S.scrollKey && !$('#viewApp').hidden) S.scrollPos[S.scrollKey] = window.scrollY;   // where the user leaves this screen
  const fromPos = screenPos(S.screen, S.from);   // measured before S.from changes
  if ((name === 'report' || name === 'profile') && S.screen !== name) S.from = S.screen;
  const dir = screenPos(name, S.from) < fromPos ? -1 : 1;   // 1: old slides left, new comes from the right
  stopPlayback();
  S.screen = name;
  endLeaving();   // a fast second click: finish the previous slide-out first
  const prev = $('.screen.active'), next = $('#' + screenId(name));
  const slide = prev && next && prev !== next && !$('#viewApp').hidden && !matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (slide) { leaveScreen(prev, dir); prev._top0 = null; }
  $$('.screen').forEach(s => s.classList.toggle('active', s.id === screenId(name)));
  if (name === 'home' && prev !== next) heroLightsOn();   // coming back to Home: lights come on, as when scrolling up
  if (slide) slideIn(next, dir, 120);
  const navName = name === 'report' ? (['scriptStudio', 'practice'].indexOf(S.from) >= 0 ? S.from : 'home') : name;
  $$('#nav [data-go]').forEach(b => { if (b.getAttribute('data-go') === navName) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current'); });
  moveNavPill(true);
  if (RENDER[name]) RENDER[name]();
  moveSegPills(false);
  S.scrollKey = scrollKey(name);
  // where the new screen opens: an element asked for (opts.scrollTo, e.g. History) or where it was left.
  // Set once, before anything is painted, and the old screen sliding out is moved by the same amount,
  // so nothing jumps: the old screen slides out exactly where it was, the new one slides in already there.
  const anchor = opts.scrollTo && document.getElementById(opts.scrollTo);
  const hh = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--hh')) || 64;
  const target = () => (anchor ? Math.max(0, anchor.getBoundingClientRect().top + window.scrollY - hh - 16) : (S.scrollPos[S.scrollKey] || 0));
  const place = () => { window.scrollTo(0, target()); if (slide) keepLeavingInPlace(prev, window.scrollY); };
  // the page height is only final once the old screen has slid out (it is still in the page until then)
  setTimeout(syncScrollThumb, slide ? 500 : 0);
  place();
  if (!opts.silent) focusHeading();
  setTimeout(() => {
    redrawCharts();
    // charts can change the page height: place it again once they are drawn
    if (S.scrollKey === scrollKey(name) && (anchor || target())) place();
  }, 0);
}
