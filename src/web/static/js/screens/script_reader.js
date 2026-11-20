import { T, TOPICS } from '../i18n.js';
import { openConfirmDialog } from '../modals/confirm.js';
import { go } from '../nav.js';
import { patchSavedScript } from '../screens/saved_scripts.js';
import { refreshChatScript, saveChatScript } from '../screens/script_studio.js';
import { CONFIG, S } from '../state.js';
import { caretToStart, closeModal, editedText, fillParagraphs, guardTitle, openModal, popIn, popOut, setEditable, showSavedTick, toast } from '../ui.js';
import { $, $$, clearErr, esc, showErr } from '../utils.js';

/* ---------- Script Reader: shows a script (from the chat or from Saved Scripts), edits it in place,
   and offers Save / Copy / Download / Practice in a menu that slides out from the right. ----------
   A chat script is edited only in this browser (the chat copy in localStorage); a saved script is edited in the database. */

let draft = null;   // { title, text } while editing; null when not editing

/* Paragraphs with their citation / uncited badge, then the warnings and the citation note. */
function paintBody(sc) {
  const body = $('#mrBody'), paras = sc.text.split(/\n\n+/).filter(Boolean), cites = sc.citations || [], warns = sc.warnings || [];
  let h = '';
  paras.forEach((p, i) => {
    const c = cites.find(x => x.paragraph === i + 1 || x.paragraph_index === i);
    const badge = c ? (c.status === 'cited' ? '<span class="cite">' + esc((c.heading ? c.heading + ' · ' : '') + (c.page ? T('script.page', { n: c.page }) : 'cited')) + '</span>' : '<span class="cite un">' + esc(T('script.uncited')) + '</span>') : '';
    h += '<div class="para"><span class="ptxt"></span>' + badge + '</div>';
  });
  if (warns.length) h += '<p class="note" style="margin-top:8px;color:var(--warn,#b45309)">' + esc(warns.join(' ')) + '</p>';
  h += '<p class="note" style="margin-top:10px">' + esc(cites.length ? T('script.uncitedHelp') : T('script.citeNone')) + '</p>';
  body.innerHTML = h;
  $$('.ptxt', body).forEach((el, i) => { el.textContent = paras[i]; });
  $('#mrTitle').textContent = sc.cardName || sc.title;
}

/* opts.edit: start in edit mode (the pencil in Saved Scripts). */
export function openReader(sc, opts) {
  opts = opts || {};
  S.readerScript = sc;
  draft = null;                                     // an edit left open last time is dropped
  setEditing(false, false);
  paintBody(sc);
  $('#mrBody').scrollTop = 0;
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
  draft = null;
}
