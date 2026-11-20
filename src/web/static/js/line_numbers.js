/* Line numbers beside script text (Practice sheet, My script preview, Script Reader).
   The lines are the lines as the browser wraps them, so they are measured after layout and again
   whenever the box changes size or its text changes. Numbered: line 1, every 5th line, the last line.
   Numbers are small, sit on the same baseline as the text and are right-aligned in one column.
   They are drawn by CSS (::after with data-n), so they are never part of the text (copy, innerText, editing). */

const TOLERANCE_PX = 3;   // line boxes whose tops differ by less than this are the same line

function lineTops(el) {
  const tops = [], walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, {
    // only the script itself (.para): notes and citation badges are not script lines
    acceptNode: n => (!n.parentElement.closest('.para') || n.parentElement.closest('.cite') || !n.nodeValue.trim() ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT)
  });
  const range = document.createRange(), base = el.getBoundingClientRect();
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const para = n.parentElement.closest('.para');
    const cs = getComputedStyle(para), lh = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.5;
    range.selectNodeContents(n);
    for (const r of range.getClientRects()) {
      if (!r.width) continue;
      // the text box is shorter than the line box: centre the line box on it
      const top = r.top - base.top + el.scrollTop - (lh - r.height) / 2;
      const left = para.getBoundingClientRect().left - base.left;
      if (!tops.some(t => Math.abs(t.top - top) < TOLERANCE_PX)) tops.push({ top, lh, left, size: cs.fontSize });
    }
  }
  return tops.sort((a, b) => a.top - b.top);
}

function draw(el) {
  const old = el.querySelector(':scope > .ln-gutter');
  if (old) old.remove();
  el.classList.add('has-ln');   // put back after code that resets className (Practice sets the sheet's class on every render)
  if (el.isContentEditable || el.classList.contains('empty') || !el.offsetParent) return;
  const lines = lineTops(el);
  if (!lines.length) return;
  const g = document.createElement('div');
  g.className = 'ln-gutter'; g.setAttribute('aria-hidden', 'true');
  lines.forEach((l, i) => {
    const n = i + 1;
    if (n !== 1 && n % 5 !== 0 && n !== lines.length) return;
    const d = document.createElement('div');
    d.className = 'ln';
    d.setAttribute('data-n', String(n));
    d.style.top = l.top + 'px'; d.style.height = l.lh + 'px'; d.style.lineHeight = l.lh + 'px';
    d.style.fontSize = l.size;
    d.style.right = 'calc(100% - ' + l.left + 'px + 0.55em)';
    g.appendChild(d);
  });
  el.appendChild(g);
}

/* Keep the numbers of `el` up to date (call once per box). */
export function watchLineNumbers(el) {
  if (!el || el._lnWatch) return;
  let queued = false, busy = false;
  const redraw = () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; busy = true; draw(el); mo.takeRecords(); busy = false; });
  };
  const mo = new MutationObserver(records => {
    if (busy || records.every(r => r.target.closest && r.target.closest('.ln-gutter'))) return;
    redraw();
  });
  mo.observe(el, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['contenteditable', 'class'] });
  new ResizeObserver(redraw).observe(el);
  if (document.fonts) document.fonts.ready.then(redraw);
  el.classList.add('has-ln');
  el._lnWatch = true;
  redraw();
}
