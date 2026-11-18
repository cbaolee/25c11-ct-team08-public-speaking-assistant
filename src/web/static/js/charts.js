import { T } from './i18n.js';
import { $, $$, esc } from './utils.js';

/* =====================================================================
   CHARTS  (self-drawn responsive SVG; swap for Chart.js later if the team wants)
   Rules followed: thin marks, 2px lines, r=4 markers with a 2px surface ring, solid hairline grid,
   dashed only for threshold lines, selective labels (last value only), tooltip per mark,
   a "View as table" alternative for every chart, text never wears the series colour.
   ===================================================================== */

export function niceTicks(lo, hi, n) {
  n = n || 4;
  const span = (hi - lo) || 1, raw = span / n, mag = Math.pow(10, Math.floor(Math.log10(raw))), norm = raw / mag;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10) * mag;
  const a = Math.floor(lo / step + 1e-9) * step, b = Math.ceil(hi / step - 1e-9) * step;
  const ticks = [];
  for (let v = a; v <= b + step / 2; v += step) ticks.push(+v.toFixed(6));
  return { ticks, lo: a, hi: b };
}

/* ---- tooltip ---- */
export function showTip(text, cx, cy) {
  const t = $('#tip');
  if (!t) return;
  t.textContent = text;
  t.style.display = 'block';
  const w = t.offsetWidth || 120, h = t.offsetHeight || 30;
  let x = cx + 14, y = cy - h - 10;
  if (x + w > window.innerWidth - 8) x = cx - w - 14;
  if (y < 8) y = cy + 16;
  t.style.left = Math.max(8, x) + 'px';
  t.style.top = y + 'px';
}
export function hideTip() { const t = $('#tip'); if (t) t.style.display = 'none'; }

/* ---- main renderer ----
   spec = { kind:'line'|'bar', pts:[{x,y,tip,color}], xNum, xMax, yMin, include:[numbers], fmtY(v),
            xTick(p,i), band:{lo,hi,label}, ref:{y,label}, barW, height, aria,
            table:{head:[...], rows:[[...]]}, legend:[{label,color}] }                          */
export function drawChart(el, spec) {
  el._spec = spec;
  const prevOpen = !!(el.querySelector('details') && el.querySelector('details').open);
  const W = Math.max(240, el.clientWidth || 560), H = spec.height || 200;
  const m = { l: 42, r: 14, t: 14, b: 28 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const pts = spec.pts, n = pts.length;
  const fmtY = spec.fmtY || (v => String(Math.round(v)));

  let ys = pts.map(p => p.y).filter(Number.isFinite).concat(spec.include || []);
  if (!ys.length) ys = [0, 1];
  if (spec.band) ys.push(spec.band.lo, spec.band.hi);
  if (spec.ref) ys.push(spec.ref.y);
  let lo = spec.yMin != null ? spec.yMin : Math.min.apply(null, ys);
  let hi = spec.yMax != null ? spec.yMax : Math.max.apply(null, ys);
  if (hi - lo < 1e-9) { hi = lo + 1; }
  const allPos = lo >= 0;
  if (spec.yMin == null) lo -= (hi - lo) * 0.08;
  if (allPos && spec.yMin == null) lo = Math.max(lo, 0);
  if (spec.yMax == null) hi += (hi - lo) * 0.08;
  const nt = niceTicks(lo, hi, 4);
  lo = nt.lo; hi = nt.hi;
  const py = v => m.t + ih - ((v - lo) / (hi - lo)) * ih;

  let x0 = 0, x1 = 1;
  if (spec.xNum) { x0 = spec.xMin != null ? spec.xMin : Math.min.apply(null, pts.map(p => p.x)); x1 = spec.xMax != null ? spec.xMax : Math.max.apply(null, pts.map(p => p.x)); if (x1 - x0 < 1e-9) x1 = x0 + 1; }
  const px = (p, i) => {
    if (spec.xNum) return m.l + ((p.x - x0) / (x1 - x0)) * iw;
    if (spec.kind === 'bar') return m.l + (iw / n) * (i + 0.5);
    return n === 1 ? m.l + iw / 2 : m.l + (i / (n - 1)) * iw;
  };

  let s = '<svg width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + esc(spec.aria || '') + '"><title>' + esc(spec.aria || '') + '</title>';
  if (spec.band) {
    const y1 = py(spec.band.hi), y2 = py(spec.band.lo);
    s += '<rect class="band" x="' + m.l + '" y="' + y1 + '" width="' + iw + '" height="' + (y2 - y1) + '"/>';
    if (spec.band.label) s += '<text class="band-l" x="' + (m.l + 6) + '" y="' + (y1 + 14) + '">' + esc(spec.band.label) + '</text>';
  }
  s += '<g class="ax">';
  nt.ticks.forEach(v => {
    const y = py(v);
    s += '<line class="grid" x1="' + m.l + '" x2="' + (W - m.r) + '" y1="' + y + '" y2="' + y + '"/><text x="' + (m.l - 8) + '" y="' + (y + 4) + '" text-anchor="end">' + esc(fmtY(v)) + '</text>';
  });
  s += '</g>';
  s += '<line x1="' + m.l + '" x2="' + (W - m.r) + '" y1="' + py(lo) + '" y2="' + py(lo) + '" stroke="var(--line-strong)" stroke-width="1"/>';
  if (spec.ref) {
    const y = py(spec.ref.y);
    s += '<line class="ref" x1="' + m.l + '" x2="' + (W - m.r) + '" y1="' + y + '" y2="' + y + '"/>';
    if (spec.ref.label) s += '<text x="' + (W - m.r) + '" y="' + (y - 5) + '" text-anchor="end">' + esc(spec.ref.label) + '</text>';
  }
  // x ticks (thinned so labels never collide)
  if (spec.xTick) {
    const maxLabels = Math.max(2, Math.floor(iw / 64)), stepN = Math.max(1, Math.ceil(n / maxLabels));
    pts.forEach((p, i) => {
      if (i % stepN !== 0) return;
      const t = spec.xTick(p, i);
      if (t) s += '<text x="' + px(p, i) + '" y="' + (H - 8) + '" text-anchor="middle">' + esc(t) + '</text>';
    });
  }

  if (spec.kind === 'line') {
    const valid = pts.map((p, i) => ({ p, i })).filter(o => Number.isFinite(o.p.y));
    if (valid.length > 1) s += '<path d="' + valid.map((o, k) => (k ? 'L' : 'M') + px(o.p, o.i).toFixed(1) + ',' + py(o.p.y).toFixed(1)).join('') + '" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>';
    if (n <= 24) valid.forEach(o => { s += '<circle class="mk" cx="' + px(o.p, o.i).toFixed(1) + '" cy="' + py(o.p.y).toFixed(1) + '" r="4" fill="var(--accent)" stroke="var(--surface)" stroke-width="2"/>'; });
    if (valid.length && spec.endLabel !== false) {
      const L = valid[valid.length - 1], lx = Math.min(px(L.p, L.i), W - m.r - 2);
      s += '<text x="' + lx + '" y="' + Math.max(m.t + 8, py(L.p.y) - 10) + '" text-anchor="end" style="fill:var(--ink);font-weight:600">' + esc(fmtY(L.p.y)) + '</text>';
    }
    s += '<line id="xh" x1="0" x2="0" y1="' + m.t + '" y2="' + py(lo) + '" stroke="var(--line-strong)" stroke-width="1" style="display:none"/>';
    s += '<circle id="xd" r="5" fill="var(--accent)" stroke="var(--surface)" stroke-width="2" style="display:none"/>';
    s += '<rect class="hit hov" x="' + m.l + '" y="' + m.t + '" width="' + iw + '" height="' + ih + '"/>';
  } else {
    const step = spec.xNum ? iw : iw / n;
    const bw = spec.barW || Math.max(4, Math.min(24, step * 0.6));
    pts.forEach((p, i) => {
      const cx = px(p, i), v = Number.isFinite(p.y) ? p.y : 0, base = py(Math.max(lo, 0)), y = py(v), h = base - y;
      if (h > 0.5) {
        const r = Math.min(4, bw / 2, h), xl = cx - bw / 2, xr = cx + bw / 2;
        s += '<path class="mk" d="M' + xl.toFixed(1) + ',' + base.toFixed(1) + 'V' + (y + r).toFixed(1) + 'Q' + xl.toFixed(1) + ',' + y.toFixed(1) + ' ' + (xl + r).toFixed(1) + ',' + y.toFixed(1) + 'H' + (xr - r).toFixed(1) + 'Q' + xr.toFixed(1) + ',' + y.toFixed(1) + ' ' + xr.toFixed(1) + ',' + (y + r).toFixed(1) + 'V' + base.toFixed(1) + 'Z" fill="' + (p.color || 'var(--accent)') + '"/>';
      }
      const hw = Math.max(bw + 8, 16);
      s += '<rect class="hit hb" data-i="' + i + '" x="' + (cx - hw / 2).toFixed(1) + '" y="' + m.t + '" width="' + hw + '" height="' + ih + '"/>';
    });
  }
  s += '</svg>';

  if (spec.legend && spec.legend.length >= 2) s += '<div class="clegend">' + spec.legend.map(l => '<span><i class="sw" style="background:' + l.color + '"></i>' + esc(l.label) + '</span>').join('') + '</div>';
  if (spec.table) {
    s += '<details' + (prevOpen ? ' open' : '') + '><summary>' + esc(T('chart.table')) + '</summary><table><thead><tr>' + spec.table.head.map(h => '<th scope="col">' + esc(h) + '</th>').join('') + '</tr></thead><tbody>' +
      spec.table.rows.map(r => '<tr>' + r.map(c => '<td>' + esc(c) + '</td>').join('') + '</tr>').join('') + '</tbody></table></details>';
  }
  el.innerHTML = s;

  // ---- hover layer ----
  const svg = $('svg', el);
  const toX = e => { const r = svg.getBoundingClientRect(); return (e.clientX - r.left) * (W / (r.width || W)); };
  if (spec.kind === 'line') {
    const hov = $('.hov', el), xh = $('#xh', el), xd = $('#xd', el);
    const move = e => {
      const x = toX(e);
      let best = -1, bd = 1e9;
      pts.forEach((p, i) => { if (!Number.isFinite(p.y)) return; const d = Math.abs(px(p, i) - x); if (d < bd) { bd = d; best = i; } });
      if (best < 0) return;
      const p = pts[best], cx = px(p, best);
      xh.setAttribute('x1', cx); xh.setAttribute('x2', cx); xh.style.display = '';
      xd.setAttribute('cx', cx); xd.setAttribute('cy', py(p.y)); xd.style.display = '';
      showTip(p.tip || fmtY(p.y), e.clientX, e.clientY);
    };
    const leave = () => { xh.style.display = 'none'; xd.style.display = 'none'; hideTip(); };
    hov.addEventListener('pointermove', move);
    hov.addEventListener('pointerdown', move);
    hov.addEventListener('pointerleave', leave);
  } else {
    $$('.hb', el).forEach(r => {
      const i = +r.getAttribute('data-i');
      const on = e => showTip(pts[i].tip || fmtY(pts[i].y), e.clientX, e.clientY);
      r.addEventListener('pointermove', on);
      r.addEventListener('pointerdown', on);
      r.addEventListener('pointerleave', hideTip);
    });
  }
}

/* Re-draw a chart when its container width changes (guarded: older browsers / jsdom have no ResizeObserver) */
export const chartWatch = (typeof ResizeObserver === 'function') ? new ResizeObserver(entries => {
  entries.forEach(en => {
    const el = en.target, w = Math.round(en.contentRect.width);
    if (el._spec && w > 0 && Math.abs(w - (el._lastW || 0)) > 1) { el._lastW = w; drawChart(el, el._spec); }
  });
}) : null;
export function chart(el, spec) {
  if (typeof el === 'string') el = $(el);
  if (!el) return;
  drawChart(el, spec);
  if (chartWatch && !el._watched) { chartWatch.observe(el); el._watched = true; }
}
export function redrawCharts() { $$('.chart').forEach(el => { if (el._spec && el.clientWidth) drawChart(el, el._spec); }); }

/* =====================================================================
   UI LOGIC  (all behaviour is a front-end simulation: no network, no real audio)
   Real app: replace the marked  SIM  blocks with HTMX calls to FastAPI.
   ===================================================================== */

/* "View as table" opens and closes with motion: the chart box grows (or shrinks) smoothly, so the
   boxes below slide down (or up), then the table fades in (or fades out first). The steps run on
   timers and the animations only show them, so the end state is always right (a hidden tab runs no
   animation frames). With "reduce motion" it opens at once, as a plain <details>. */
const TABLE_GROW_MS = 380, TABLE_FADE_MS = 260, TABLE_EASE = 'cubic-bezier(.4, 0, .2, 1)';
function stopTableMotion(d, tbl) {
  (d._timers || []).forEach(clearTimeout); d._timers = [];
  d.getAnimations().concat(tbl.getAnimations()).forEach(a => a.cancel());
  d.style.overflow = ''; tbl.style.opacity = '';
}
document.addEventListener('click', e => {
  const sum = e.target.closest && e.target.closest('.chart details > summary');
  if (!sum) return;
  const d = sum.parentElement, tbl = $('table', d);
  if (!tbl || !d.animate || matchMedia('(prefers-reduced-motion: reduce)').matches) return;   // the browser toggles it
  e.preventDefault();
  stopTableMotion(d, tbl);
  const later = (ms, fn) => d._timers.push(setTimeout(fn, ms));
  const from = d.offsetHeight;
  if (!d.open) {
    // 1. grow the box (the boxes below move down), table hidden  2. fade the table in
    d.open = true;
    const to = d.offsetHeight;
    tbl.style.opacity = '0'; d.style.overflow = 'hidden';
    d.animate([{ height: from + 'px' }, { height: to + 'px' }], { duration: TABLE_GROW_MS, easing: TABLE_EASE });
    later(TABLE_GROW_MS, () => {
      d.getAnimations().forEach(a => a.cancel());   // the box is at its full height now
      d.style.overflow = ''; tbl.style.opacity = '';
      tbl.animate([{ opacity: 0, transform: 'translateY(-4px)' }, { opacity: 1, transform: 'none' }], { duration: TABLE_FADE_MS, easing: 'ease-out' });
      later(TABLE_FADE_MS, () => stopTableMotion(d, tbl));   // done: nothing left holding a frame
    });
  } else {
    // 1. fade the table out  2. shrink the box (the boxes below move up)  3. close
    const out = Math.round(TABLE_FADE_MS * .7);
    tbl.animate([{ opacity: 1 }, { opacity: 0 }], { duration: out, easing: 'ease-in' });
    later(out, () => {
      tbl.getAnimations().forEach(a => a.cancel());
      tbl.style.opacity = '0'; d.style.overflow = 'hidden';
      d.animate([{ height: from + 'px' }, { height: sum.offsetHeight + 'px' }], { duration: TABLE_GROW_MS, easing: TABLE_EASE, fill: 'forwards' });
      later(TABLE_GROW_MS, () => { stopTableMotion(d, tbl); d.open = false; });
    });
  }
});
