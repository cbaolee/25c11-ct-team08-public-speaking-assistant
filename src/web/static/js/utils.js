import { S } from './state.js';

export const $ = (s, r = document) => r.querySelector(s);
export const $$ = (s, r = document) => [...r.querySelectorAll(s)];
export const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
export const fmtTime = s => Math.floor(s / 60) + ':' + String(Math.floor(s % 60)).padStart(2, '0');


export const pad2 = n => String(Math.floor(n)).padStart(2, '0');
export const fmtClock = s => pad2(s / 60) + ':' + pad2(s % 60);
export const fmtDay = ts => new Date(ts).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
export const fmtDayLong = ts => new Date(ts).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
export const minus = s => String(s).replace('-', '−');
export const wordsOf = t => t.trim().split(/\s+/).filter(Boolean).length;
export const plain = raw => raw.replace(/[^\w']/g, '');
export const scored = () => S.sessions.filter(s => s.sc.status === 'ok').sort((a, b) => a.ts - b.ts);
export const IC = {
  up: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7"/></svg>',
  down: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M19 12l-7 7-7-7"/></svg>',
  flat: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14"/></svg>',
  alert: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/></svg>',
  play: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5l12 7-12 7z"/></svg>',
  pause: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14M16 5v14"/></svg>',
  x: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  file: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M9 13h6M9 17h6"/></svg>',
  chev: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>',
  ai: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" aria-hidden="true"><rect width="256" height="256" rx="58" fill="#1D4ED8"/><rect x="30" y="108" width="16" height="40" rx="8" fill="#fff"/><rect x="58" y="82" width="16" height="92" rx="8" fill="#fff"/><rect x="86" y="58" width="16" height="140" rx="8" fill="#fff"/><rect x="154" y="72" width="16" height="112" rx="8" fill="#fff"/><rect x="182" y="94" width="16" height="68" rx="8" fill="#fff"/><rect x="210" y="113" width="16" height="30" rx="8" fill="#fff"/><path d="M114 138 L128 110 L142 138" fill="none" stroke="#F59E0B" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"/></svg>'
};
export function showErr(el, msg) { el.textContent = msg; el.classList.add('show'); }
export function clearErr(el) { el.textContent = ''; el.classList.remove('show'); }
