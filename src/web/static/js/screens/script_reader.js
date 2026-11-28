import { T, TOPICS } from '../i18n.js';
import { openConfirmDialog } from '../modals/confirm.js';
import { go } from '../nav.js';
import { practiceLocked } from '../screens/practice.js';
import { patchSavedScript } from '../screens/saved_scripts.js';
import { canJumpToChatMessage, jumpToChatMessage, refreshChatScript, saveChatScript } from '../screens/script_studio.js';
import { formatCitationPill, formatCitationSourceLabel } from '../screens/script_studio_state.js';
import { CONFIG, S } from '../state.js';
import { caretToStart, closeModal, editedText, fillParagraphs, guardTitle, openModal, popIn, popOut, setEditable, showSavedTick, toast } from '../ui.js';
import { $, $$, clearErr, showErr } from '../utils.js';

/* ---------- Script Reader: shows a script (from the chat or from Saved Scripts), edits it in place,
   renders Gemini-style sentence citations with hover/tap popovers & click-to-jump to chat,
   and offers Save / Copy / Download / Practice in a menu that slides out from the right. ----------
   A chat script is edited only in this browser (the chat copy in localStorage); a saved script is edited in the database. */

let draft = null;   // { title, text } while editing; null when not editing
let citePop = null;
let citeAnchor = null;
let citeCloseTimer = null;
let citeEventsBound = false;

const fmtPage = n => T('script.page', { n });

function cancelCiteClose() {
  if (citeCloseTimer) { clearTimeout(citeCloseTimer); citeCloseTimer = null; }
}
function scheduleCiteClose() {
  cancelCiteClose();
  citeCloseTimer = setTimeout(() => closeCitePopover(false), 140);
}
function ensureCitePopover() {
  if (citePop && citePop.isConnected) return citePop;
  const host = $('#scriptReader') || document.body;
  citePop = document.createElement('div');
  citePop.id = 'citePopover';
  citePop.className = 'cite-pop';
  citePop.setAttribute('role', 'dialog');
  citePop.setAttribute('aria-modal', 'false');
  citePop.hidden = true;
  citePop.addEventListener('mouseenter', cancelCiteClose);
  citePop.addEventListener('mouseleave', scheduleCiteClose);
  citePop.addEventListener('focusin', cancelCiteClose);
  citePop.addEventListener('focusout', e => {
    if (!citePop.contains(e.relatedTarget) && e.relatedTarget !== citeAnchor) scheduleCiteClose();
  });
  citePop.addEventListener('click', e => {
    const item = e.target.closest('button.cite-pop-item');
    if (!item || !item._citeSource) return;
    const sc = S.readerScript;
    const body = $('#mrBody');
    if (sc && body) sc._lastReaderScrollTop = body.scrollTop;
    const src = item._citeSource;
    closeCitePopover(false);
    closeModal('scriptReader', false);
    jumpToChatMessage(src.source_msg_id, src.source_file);
  });
  host.appendChild(citePop);
  return citePop;
}
function closeCitePopover(restoreFocus = false) {
  cancelCiteClose();
  const prev = citeAnchor;
  if (prev) prev.setAttribute('aria-expanded', 'false');
  citeAnchor = null;
  if (citePop) {
    citePop.hidden = true;
    citePop.replaceChildren();
  }
  if (restoreFocus && prev && prev.isConnected) prev.focus();
}
function positionCitePopover(anchor, pop) {
  const rect = anchor.getBoundingClientRect();
  const margin = 12;
  const vw = window.innerWidth || 800;
  const vh = window.innerHeight || 600;
  pop.style.left = '0px';
  pop.style.top = '0px';
  pop.hidden = false;
  const pw = pop.offsetWidth || 320;
  const ph = pop.offsetHeight || 120;
  let left = rect.left;
  if (left + pw > vw - margin) left = vw - margin - pw;
  if (left < margin) left = margin;
  const spaceBelow = vh - rect.bottom - margin;
  const spaceAbove = rect.top - margin;
  let top;
  if (spaceBelow >= ph || spaceBelow >= spaceAbove) {
    top = Math.min(vh - margin - ph, rect.bottom + 6);
  } else {
    top = Math.max(margin, rect.top - ph - 6);
  }
  pop.style.left = Math.round(left) + 'px';
  pop.style.top = Math.round(top) + 'px';
}
function openCitePopover(anchor) {
  const sources = anchor && anchor._citeSources;
  if (!Array.isArray(sources) || !sources.length) return;
  cancelCiteClose();
  if (citeAnchor && citeAnchor !== anchor) citeAnchor.setAttribute('aria-expanded', 'false');
  citeAnchor = anchor;
  anchor.setAttribute('aria-expanded', 'true');
  const pop = ensureCitePopover();
  const sc = S.readerScript;
  pop.replaceChildren();
  sources.forEach(src => {
    const label = formatCitationSourceLabel(src, fmtPage);
    const excerpt = typeof src.excerpt === 'string' ? src.excerpt.trim() : '';
    const canJump = Boolean(sc && !sc.fromList && canJumpToChatMessage(src.source_msg_id, src.source_file));
    const item = document.createElement(canJump ? 'button' : 'div');
    item.className = 'cite-pop-item' + (canJump ? '' : ' is-readonly');
    if (canJump) {
      item.type = 'button';
      item.title = T('script.citeJumpHint');
      item._citeSource = src;
    }
    const titleEl = document.createElement('span');
    titleEl.className = 'cite-pop-title';
    titleEl.textContent = label;
    item.appendChild(titleEl);
    if (excerpt) {
      const exEl = document.createElement('span');
      exEl.className = 'cite-pop-excerpt';
      exEl.textContent = excerpt;
      item.appendChild(exEl);
    }
    if (!canJump) {
      const noteEl = document.createElement('span');
      noteEl.className = 'cite-pop-note';
      noteEl.textContent = T('script.citeNoJump');
      item.appendChild(noteEl);
    }
    pop.appendChild(item);
  });
  positionCitePopover(anchor, pop);
}
function bindCiteEvents() {
  if (citeEventsBound) return;
  citeEventsBound = true;
  const body = $('#mrBody');
  if (body) {
    body.addEventListener('mouseover', e => {
      const pill = e.target.closest('.cite-pill');
      if (pill && body.contains(pill)) openCitePopover(pill);
    });
    body.addEventListener('mouseout', e => {
      const pill = e.target.closest('.cite-pill');
      if (!pill) return;
      const to = e.relatedTarget;
      if (to && (pill.contains(to) || (citePop && citePop.contains(to)))) return;
      scheduleCiteClose();
    });
    body.addEventListener('focusin', e => {
      const pill = e.target.closest('.cite-pill');
      if (pill && body.contains(pill)) openCitePopover(pill);
    });
    body.addEventListener('focusout', e => {
      const pill = e.target.closest('.cite-pill');
      if (!pill) return;
      const to = e.relatedTarget;
      if (to && citePop && citePop.contains(to)) return;
      scheduleCiteClose();
    });
    body.addEventListener('click', e => {
      const pill = e.target.closest('.cite-pill');
      if (!pill || !body.contains(pill)) return;
      e.preventDefault();
      e.stopPropagation();
      if (citeAnchor === pill && citePop && !citePop.hidden) closeCitePopover(false);
      else openCitePopover(pill);
    });
    body.addEventListener('scroll', () => { if (citePop && !citePop.hidden) closeCitePopover(false); });
  }
  document.addEventListener('click', e => {
    if (!citePop || citePop.hidden) return;
    if (citePop.contains(e.target) || (citeAnchor && citeAnchor.contains(e.target))) return;
    closeCitePopover(false);
  });
  /* Capture phase so Escape closes an open citation popover first instead of closing the whole Reader modal. */
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && citePop && !citePop.hidden) {
      e.preventDefault();
      e.stopImmediatePropagation();
      closeCitePopover(true);
    }
  }, true);
}

function buildCitePillButton(sources) {
  const pill = formatCitationPill(sources, fmtPage);
  if (!pill.primaryLabel) return null;
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'cite-pill';
  btn.setAttribute('aria-haspopup', 'dialog');
  btn.setAttribute('aria-expanded', 'false');
  const fullAria = pill.primaryLabel + (pill.extraCount > 0 ? ' +' + pill.extraCount : '');
  btn.setAttribute('aria-label', T('script.citeAria', { label: fullAria }));
  btn._citeSources = pill.sources;
  const lbl = document.createElement('span');
  lbl.className = 'cite-pill-lbl';
  lbl.textContent = pill.primaryLabel;
  btn.appendChild(lbl);
  if (pill.extraCount > 0) {
    const more = document.createElement('span');
    more.className = 'cite-pill-more';
    more.textContent = '+' + pill.extraCount;
    btn.appendChild(more);
  }
  return btn;
}

/* Paragraphs with sentence-level Gemini citation pills (Contract D), falling back to paragraph-level badges for legacy scripts. */
function paintBody(sc) {
  closeCitePopover(false);
  const body = $('#mrBody'), paras = sc.text.split(/\n\n+/).filter(Boolean), cites = sc.citations || [], warns = sc.warnings || [];
  body.replaceChildren();
  let usedSentenceCites = false;
  let hasUncited = false;
  paras.forEach((p, i) => {
    const c = cites.find(x => x.paragraph === i + 1 || x.paragraph_index === i);
    const div = document.createElement('div');
    div.className = 'para';
    if (c && Array.isArray(c.sentences) && c.sentences.length) {
      usedSentenceCites = true;
      c.sentences.forEach((sent, idx) => {
        if (idx > 0) div.appendChild(document.createTextNode(' '));
        const span = document.createElement('span');
        span.className = 'sent';
        span.textContent = typeof sent.text === 'string' ? sent.text : '';
        div.appendChild(span);
        if (sent.status === 'cited' && Array.isArray(sent.sources) && sent.sources.length) {
          const btn = buildCitePillButton(sent.sources);
          if (btn) div.appendChild(btn);
        } else {
          hasUncited = true;
        }
      });
    } else {
      const ptxt = document.createElement('span');
      ptxt.className = 'ptxt';
      ptxt.textContent = p;
      div.appendChild(ptxt);
      if (c) {
        if (c.status === 'cited') {
          const srcList = Array.isArray(c.sources) && c.sources.length ? c.sources : [c];
          const btn = buildCitePillButton(srcList);
          if (btn) div.appendChild(btn);
        } else {
          hasUncited = true;
          const badge = document.createElement('span');
          badge.className = 'cite un';
          badge.textContent = T('script.uncited');
          div.appendChild(badge);
        }
      }
    }
    body.appendChild(div);
  });
  if (warns.length) {
    const wp = document.createElement('p');
    wp.className = 'note';
    wp.style.marginTop = '8px';
    wp.style.color = 'var(--warn,#b45309)';
    wp.textContent = warns.join(' ');
    body.appendChild(wp);
  }
  if (!usedSentenceCites) hasUncited = cites.some(x => x.status !== 'cited');
  const citeNote = !cites.length ? T('script.citeNone') : (hasUncited ? T('script.uncitedHelp') : T('script.citeAllOk'));
  const np = document.createElement('p');
  np.className = 'note';
  np.style.marginTop = '10px';
  np.textContent = citeNote;
  body.appendChild(np);
  $('#mrTitle').textContent = sc.cardName || sc.title;
}

/* opts.edit: start in edit mode (the pencil in Saved Scripts). */
export function openReader(sc, opts) {
  opts = opts || {};
  bindCiteEvents();
  S.readerScript = sc;
  draft = null;                                     // an edit left open last time is dropped
  setEditing(false, false);
  paintBody(sc);
  $('#mrBody').scrollTop = Number.isFinite(sc._lastReaderScrollTop) ? sc._lastReaderScrollTop : 0;
  $('[data-ra=save]', $('#mrMenu')).hidden = !!sc.fromList;   // already in the list
  closeMenu();
  openModal('scriptReader', { focus: '[data-close]' });
  if (opts.edit) startEdit();
}
function isOpen() {
  return S.modal.indexOf('scriptReader') >= 0;
}
/* A saved script changed elsewhere (or here): show the new version if the reader has it open. */
export function refreshReader(row) {
  const sc = S.readerScript;
  if (!sc || sc.savedId !== row.id || !isOpen()) return;
  sc.title = sc.cardName = row.title;
  if (row.body !== sc.text) { sc.text = row.body; sc.citations = []; }
  if (!draft) paintBody(sc);
}
export function closeReaderIfShowing(savedId) {
  if (S.readerScript && S.readerScript.savedId === savedId && isOpen()) closeModal('scriptReader');
}

/* ---- edit in place: the title and the text stay exactly where and how they look; only a caret appears ---- */
function swapLabel(btn, label) {                     // Edit <-> Cancel: the button fades its new word in
  btn.textContent = label;
  popIn(btn, { y: 4, duration: 220 });
}
/* `after` runs once Edit is back (leaving edit mode): the saved tick appears then, not before. */
function setEditing(on, animate, after) {
  const title = $('#mrTitle'), body = $('#mrBody'), save = $('#mrSave'), edit = $('#mrEdit');
  setEditable(title, on); setEditable(body, on);
  body.classList.toggle('reader-editing', on);
  clearErr($('#mrError'));
  if (!animate) { save.hidden = !on; edit.hidden = false; edit.textContent = T(on ? 'common.cancel' : 'saved.edit'); if (after) after(); return; }
  popIn(body, { y: 6, duration: 300 });
  if (on) {
    swapLabel(edit, T('common.cancel'));
    save.hidden = false; popIn(save, { y: 4, duration: 220 });
    return;
  }
  let left = 2;                                       // Save and Cancel both fade out, then Edit comes back
  const back = () => {
    if (--left) return;
    edit.textContent = T('saved.edit'); edit.hidden = false;
    popIn(edit, { y: 4, duration: 220 });
    if (after) after();
  };
  popOut(save, back); popOut(edit, back);
}
export function startEdit() {
  const sc = S.readerScript; if (!sc) return;
  closeCitePopover(false);
  draft = { title: sc.cardName || sc.title, text: sc.text };
  $('#mrTitle').textContent = draft.title;
  fillParagraphs($('#mrBody'), draft.text);          // plain paragraphs, no citation badges while editing
  setEditing(true, true);
  caretToStart($('#mrBody'));
}
export function toggleEdit() {
  if (draft) { draft = null; paintBody(S.readerScript); setEditing(false, true); } else startEdit();
}
function readTitle() { return $('#mrTitle').innerText.replace(/\n/g, ' ').trim(); }
function hasUnsavedEdit() {
  if (!draft) return false;
  const sc = S.readerScript;
  return readTitle() !== (sc.cardName || sc.title) || editedText($('#mrBody')) !== sc.text.trim();
}
export function saveEdit() {
  const sc = S.readerScript; if (!sc || !draft) return;
  const title = readTitle(), text = editedText($('#mrBody')), err = $('#mrError');
  if (!title) { showErr(err, T('saved.errNameEmpty')); $('#mrTitle').focus(); return; }
  if (!text) { showErr(err, T('saved.errBodyEmpty')); $('#mrBody').focus(); return; }
  const titleChanged = title !== (sc.cardName || sc.title), textChanged = text !== sc.text.trim();
  const done = () => { draft = null; paintBody(sc); setEditing(false, true, () => showSavedTick($('#mrSavedTick'))); };
  if (!titleChanged && !textChanged) { done(); return; }
  if (sc.fromList) {                                   // a saved script: the database copy changes
    const patch = {};
    if (titleChanged) patch.title = title;
    if (textChanged) patch.body = text;
    patchSavedScript(sc.savedId, patch, err).then(row => { if (row) done(); });
    return;
  }
  // a chat script: only the copy in this browser changes (the chat bubble and localStorage)
  sc.title = sc.cardName = title;
  if (textChanged) { sc.text = text; sc.citations = []; sc.warnings = []; sc.savedId = null; }   // no longer the saved copy
  refreshChatScript(sc);
  done();
}
export function setupReaderTitle() {
  guardTitle($('#mrTitle'), () => CONFIG.SCRIPT_TITLE_MAX_CHARS, () => caretToStart($('#mrBody')));
}

/* ---- the menu: Save script / Copy text / Download / Practise. With unsaved edits it uses the last saved version. ---- */
export function onMenuClick(e) {
  const b = e.target.closest('[data-ra]'); if (!b || !S.readerScript) return;
  const action = b.getAttribute('data-ra'), sc = S.readerScript;
  closeMenu();
  if (hasUnsavedEdit()) openConfirmDialog(T('reader.unsavedTitle'), T('reader.unsavedMsg'), T('reader.useLast'), () => runScriptAction(sc, action));
  else runScriptAction(sc, action);
}
export function toggleMenu() {
  const menu = $('#mrMenu'), open = !menu.classList.contains('open');
  menu.classList.toggle('open', open);
  $('#mrMoreButton').setAttribute('aria-expanded', String(open));
  if (open) { const first = $$('[data-ra]:not([hidden])', menu)[0]; if (first) first.focus(); }
}
export function closeMenu() {
  $('#mrMenu').classList.remove('open');
  $('#mrMoreButton').setAttribute('aria-expanded', 'false');
}

/* The script actions, shared by the reader menu and the chat bubble buttons. */
export function runScriptAction(sc, action) {
  if (action === 'practice') {
    if (practiceLocked()) return;   // an evaluation runs in the background: leave the Practice text alone
    /* Practice does not save: the text goes to Practice as it is, and only a finished evaluation keeps it
       (sessions.script_snapshot). A script the user saved before still links its session by id. */
    const lbl = sc.cardName || sc.title || TOPICS[sc.topic] || sc.topic;
    S.texts.mine = { id: sc.savedId || null, title: lbl, short: lbl, text: sc.text, topic: sc.topic, duration_min: sc.duration_min || null };
    S.pickerTab = 'mine'; S.choosing = false;
    if (isOpen()) closeModal('scriptReader', false);
    go('practice');
  } else if (action === 'save') {
    saveChatScript(sc);
  } else if (action === 'copy') {
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(sc.text).then(() => toast(T('script.copied')), () => toast(T('script.copyFail'), true));
    else toast(T('script.copyFail'), true);
  } else if (action === 'download') {
    const url = URL.createObjectURL(new Blob([sc.text], { type: 'text/plain' })), a = document.createElement('a');
    a.href = url; a.download = T('script.downloadName'); document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 500);
  }
}
/* Closing the window drops an unsaved edit. */
export function onReaderClosed() {
  closeCitePopover(false);
  draft = null;
}
