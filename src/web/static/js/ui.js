import { api } from './api.js';
import { T } from './i18n.js';
import { S } from './state.js';
import { $, $$ } from './utils.js';

/* ---------- toast ---------- */
export let toastTimer = null;
export function toast(msg, err) {
  const t = $('#toast');
  t.className = 'show' + (err ? ' err' : '');
  t.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true">' + (err ? '<circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/>' : '<path d="M5 12l5 5 9-10"/>') + '</svg><span></span>';
  $('span', t).textContent = msg;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 3800);
}

/* ---------- modals (focus trap, Esc, focus return) ---------- */
export const FOCUSABLE = 'a[href],button,input,select,textarea,[tabindex]:not([tabindex="-1"])';
export const usable = el => !el.disabled && !el.closest('[hidden]') && el.getAttribute('tabindex') !== '-1';
export function openModal(id, opts) {
  opts = opts || {};
  const m = $('#' + id);
  m._opener = document.activeElement;
  m._lock = !!opts.lock;
  if (m._closing) { m._closing.forEach(a => a.cancel()); m._closing = null; }   // reopened while it was still closing
  m.classList.add('show');
  S.modal.push(id);
  document.body.style.overflow = 'hidden';
  const target = (opts.focus && $(opts.focus, m)) || $$(FOCUSABLE, m).filter(usable)[0] || $('.box', m);
  target.focus();
}
export function closeModal(id, restore) {
  const m = $('#' + id);
  if (!m || !m.classList.contains('show') || m._closing) return;
  /* After login: mirror of the opening, the window fades out while sinking a little, then it is hidden */
  const box = $('.box', m);
  if (S.view === 'app' && box && m.animate && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
    const opt = { duration: 320, easing: 'cubic-bezier(.4, 0, .8, .4)', fill: 'forwards' };
    const anims = [box.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translateY(40px)' }], opt),
      m.animate([{ opacity: 1 }, { opacity: 0 }], opt)];
    m._closing = anims;
    anims[0].onfinish = () => { if (m._closing !== anims) return; m._closing = null; m.classList.remove('show'); anims.forEach(a => a.cancel()); };
  } else m.classList.remove('show');
  S.modal = S.modal.filter(x => x !== id);
  if (!S.modal.length) document.body.style.overflow = '';
  if (restore === false) return;
  const op = m._opener;
  if (op && document.body.contains(op) && !op.closest('[hidden]') && op.focus) op.focus();
  else focusHeading();
}
export function focusHeading() {
  const h = $('.screen.active h1');
  if (h && S.view === 'app') { h.setAttribute('tabindex', '-1'); h.focus({ preventScroll: true }); }
}

/* ---------- views / navigation ---------- */
/* Every password field gets an eye button on its right: open eye = show the password, crossed eye = hide it again */
export const EYE_OPEN = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>';
export const EYE_SHUT = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9.9 5.2A10.4 10.4 0 0 1 12 5c6.4 0 10 7 10 7a17.6 17.6 0 0 1-2.6 3.6M6.6 6.6A17.4 17.4 0 0 0 2 12s3.6 7 10 7a9.8 9.8 0 0 0 5.4-1.6"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/><path d="M3 3l18 18"/></svg>';
export function paintEye(b, inp) {
  const shown = inp.type === 'text';
  b.innerHTML = shown ? EYE_SHUT : EYE_OPEN;
  b.setAttribute('aria-pressed', String(shown));
  b.setAttribute('aria-label', T(shown ? 'auth.hide' : 'auth.show')); b.title = b.getAttribute('aria-label');
}
export function setupPwEyes() {
  $$('input[type=password]').forEach(inp => {
    let wrap = inp.parentElement;
    if (!wrap.classList.contains('pwwrap')) { wrap = document.createElement('div'); wrap.className = 'pwwrap'; inp.before(wrap); wrap.appendChild(inp); }
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'eye'; b.setAttribute('aria-controls', inp.id);
    b.onclick = () => { inp.type = inp.type === 'password' ? 'text' : 'password'; paintEye(b, inp); };
    wrap.appendChild(b); paintEye(b, inp);
    inp._eye = b;
  });
}

/* ---------- drop-down slide (account menu, select lists): unrolls downwards, rolls back up; no fade ---------- */
export const calmMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
export const isDropOpen = el => !el.hidden && !el._closing;
export function slideDown(el) {
  if (el._closing) { el._closing.cancel(); el._closing = null; }
  el.hidden = false;
  if (calmMotion() || !el.animate) return;
  el.animate([{ clipPath: 'inset(0 0 100% 0)', transform: 'translateY(-8px)' }, { clipPath: 'inset(0 0 0 0)', transform: 'none' }],
    { duration: 280, easing: 'cubic-bezier(.2, .7, .3, 1)' });
}
export function slideUp(el, done) {
  if (el.hidden || el._closing) return;
  if (calmMotion() || !el.animate) { el.hidden = true; if (done) done(); return; }
  el.getAnimations().forEach(a => a.cancel());
  const a = el.animate([{ clipPath: 'inset(0 0 0 0)', transform: 'none' }, { clipPath: 'inset(0 0 100% 0)', transform: 'translateY(-8px)' }],
    { duration: 220, easing: 'cubic-bezier(.4, 0, .8, .4)', fill: 'forwards' });
  el._closing = a;
  a.onfinish = () => { if (el._closing !== a) return; el._closing = null; el.hidden = true; a.cancel(); if (done) done(); };
}


/* ---------- custom select: the native <select> stays (hidden) as the source of truth, so all existing code keeps
   reading/writing .value and listening to change; the button + list are only the visible layer ---------- */
export let openCsel = null;
export const CHEVRON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>';
export function enhanceSelect(sel) {
  if (sel._csel) return;
  const wrap = document.createElement('div'), btn = document.createElement('button'), list = document.createElement('ul'), hl = document.createElement('div');
  wrap.className = 'csel';
  wrap.style.cssText = sel.getAttribute('style') || '';
  if (wrap.style.width === 'auto') wrap.style.display = 'inline-block';
  btn.type = 'button'; btn.className = 'csel-btn'; btn.id = sel.id + 'Btn';
  btn.setAttribute('aria-haspopup', 'listbox'); btn.setAttribute('aria-expanded', 'false');
  btn.innerHTML = '<span class="v"></span>' + CHEVRON;
  list.className = 'csel-list'; list.setAttribute('role', 'listbox'); list.id = sel.id + 'List'; list.hidden = true; list.tabIndex = -1;
  if (sel.closest('.l-auth')) list.classList.add('dark');
  hl.className = 'csel-hl';
  btn.setAttribute('aria-controls', list.id);
  sel.classList.add('csel-native'); sel.tabIndex = -1;
  sel.after(wrap); wrap.appendChild(btn); document.body.appendChild(list);
  $$('label[for="' + sel.id + '"]').forEach(l => { l.htmlFor = btn.id; });
  sel.focus = o => btn.focus(o);

  const P = HTMLSelectElement.prototype;
  const refresh = () => {
    const o = sel.options[sel.selectedIndex];
    $('.v', btn).textContent = o ? o.textContent : '';
    btn.disabled = sel.disabled;
  };
  ['value', 'selectedIndex'].forEach(k => {
    const d = Object.getOwnPropertyDescriptor(P, k);
    Object.defineProperty(sel, k, { configurable: true, get() { return d.get.call(sel); }, set(v) { d.set.call(sel, v); refresh(); } });
  });
  new MutationObserver(refresh).observe(sel, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['disabled'] });
  sel.addEventListener('change', refresh);

  let kb = -1;
  const items = () => $$('li', list);
  const placeHl = animate => {
    const cur = items()[sel.selectedIndex];
    list.classList.toggle('still', !animate);
    if (!cur) { hl.style.height = '0px'; return; }
    hl.style.transform = 'translateY(' + cur.offsetTop + 'px)'; hl.style.height = cur.offsetHeight + 'px';
    if (!animate) { getComputedStyle(hl).transform; list.classList.remove('still'); }
  };
  const setKb = i => {
    const li = items(); if (!li.length) return;
    kb = (i + li.length) % li.length;
    li.forEach((x, j) => x.classList.toggle('kb', j === kb));
    btn.setAttribute('aria-activedescendant', li[kb].id); li[kb].scrollIntoView({ block: 'nearest' });
  };
  const place = () => {
    const r = btn.getBoundingClientRect(), h = list.offsetHeight;
    list.style.minWidth = r.width + 'px'; list.style.left = Math.max(8, Math.min(r.left, innerWidth - list.offsetWidth - 8)) + 'px';
    list.style.top = (r.bottom + 4 + h > innerHeight - 8 && r.top - 4 - h > 8 ? r.top - 4 - h : r.bottom + 4) + 'px';
  };
  const open = () => {
    if (sel.disabled) return;
    if (openCsel && openCsel !== api) openCsel.close();
    list.innerHTML = ''; list.appendChild(hl);
    [...sel.options].forEach((o, i) => {
      const li = document.createElement('li');
      li.id = list.id + '-' + i; li.setAttribute('role', 'option'); li.textContent = o.textContent;
      li.setAttribute('aria-selected', String(i === sel.selectedIndex)); li.dataset.i = i;
      list.appendChild(li);
    });
    slideDown(list); place(); placeHl(false);
    btn.setAttribute('aria-expanded', 'true'); openCsel = api;
    setKb(Math.max(0, sel.selectedIndex));
  };
  const close = () => {
    if (openCsel === api) openCsel = null;
    btn.setAttribute('aria-expanded', 'false'); btn.removeAttribute('aria-activedescendant');
    slideUp(list);
  };
  const choose = i => {
    if (i === sel.selectedIndex) { close(); return; }
    items().forEach((x, j) => x.setAttribute('aria-selected', String(j === i)));
    Object.getOwnPropertyDescriptor(P, 'selectedIndex').set.call(sel, i); refresh();
    placeHl(true);   // highlight glides to the new choice, then the list rolls up
    sel.dispatchEvent(new Event('input', { bubbles: true })); sel.dispatchEvent(new Event('change', { bubbles: true }));
    setTimeout(close, calmMotion() ? 0 : 300);
  };
  const api = { close, wrap, list };
  btn.addEventListener('click', () => { if (isDropOpen(list)) close(); else open(); });
  list.addEventListener('click', e => { const li = e.target.closest('li'); if (li) { choose(+li.dataset.i); btn.focus(); } });
  btn.addEventListener('keydown', e => {
    const k = e.key, isOpen = isDropOpen(list);
    if (!isOpen && (k === 'ArrowDown' || k === 'ArrowUp' || k === 'Enter' || k === ' ')) { e.preventDefault(); open(); return; }
    if (!isOpen) return;
    if (k === 'ArrowDown' || k === 'ArrowUp') { e.preventDefault(); setKb(kb + (k === 'ArrowDown' ? 1 : -1)); }
    else if (k === 'Enter' || k === ' ') { e.preventDefault(); choose(kb); }
    else if (k === 'Escape') { e.preventDefault(); e.stopPropagation(); close(); }
    else if (k === 'Tab') close();
  });
  sel._csel = api; refresh();
}
export function setupSelects() {
  $$('select').forEach(enhanceSelect);
  document.addEventListener('mousedown', e => {
    if (openCsel && !openCsel.wrap.contains(e.target) && !openCsel.list.contains(e.target)) openCsel.close();
  }, true);
  window.addEventListener('scroll', e => { if (openCsel && !openCsel.list.contains(e.target)) openCsel.close(); }, true);
  window.addEventListener('resize', () => { if (openCsel) openCsel.close(); });
}
