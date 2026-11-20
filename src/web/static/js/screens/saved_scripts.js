import { api, readJson } from '../api.js';
import { T } from '../i18n.js';
import { openConfirmDialog } from '../modals/confirm.js';
import { pickSavedScript, renderPractice, startMineEdit } from '../screens/practice.js';
import { closeReaderIfShowing, openReader, refreshReader } from '../screens/script_reader.js';
import { forgetSavedScript, renameChatScript } from '../screens/script_studio.js';
import { CONFIG, S } from '../state.js';
import { closeModal, openModal, popIn, slideDown, slideUp, toast, withBusy } from '../ui.js';
import { $, $$, IC, clearErr, esc, showErr } from '../utils.js';

/* ---------- Saved Scripts: the user's own list, shown on Practice (Mine tab) and in Script Studio (Show my scripts) ----------
   A script reaches this list only through Save. Practice never saves: a practised script is kept in sessions.script_snapshot. */

const PENCIL = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16zM14 6l4 4"/></svg>';
const TRASH = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/></svg>';
/* GeneratedScript.source ("template" / "llm") -> the scripts.source value the API stores. */
export const SCRIPT_SOURCE = { template: 'generated_template', llm: 'generated_llm' };
export const SCRIPT_DURATIONS = [5, 10, 15, 20];   // fixed by the scripts.duration_min check in SQL

export function savedScriptLimit() {
  return CONFIG.MAX_SAVED_SCRIPTS;
}
export function isSavedListFull() {
  return S.savedScripts !== null && S.savedScriptTotal >= savedScriptLimit();
}

/* GET /api/scripts returns every saved script (the default page is the whole cap) plus total and limit. */
export function loadSavedScripts() {
  if (!S.user) return Promise.resolve();
  return api('/api/scripts').then(r => (r.ok ? r.json() : null)).then(d => {
    if (!d) return;
    S.savedScripts = d.items || [];
    S.savedScriptTotal = d.total != null ? d.total : S.savedScripts.length;
    if (d.limit != null) CONFIG.MAX_SAVED_SCRIPTS = d.limit;
    const mine = S.texts.mine;
    if (mine && mine.id && !S.savedScripts.some(s => s.id === mine.id)) S.texts.mine = null;   // deleted elsewhere
    renderSavedLists();
  }).catch(() => {});
}

/* Meta line shared by the lists and the Practice preview: "5 min · 658 words" (no minutes when unknown). */
export function scriptMeta(durationMin, wordCount) {
  return durationMin ? T('saved.meta', { d: durationMin, n: wordCount }) : T('saved.words', { n: wordCount });
}
/* Same card as a script in the Chat Feed: file icon, name, meta; then Edit and Delete icons. */
function itemHtml(script, selectedId) {
  const on = script.id === selectedId;
  return '<li class="fcard saved-item' + (on ? ' is-on' : '') + '" data-id="' + esc(script.id) + '">' +
    '<button type="button" class="saved-pick" data-act="open"' + (on ? ' aria-current="true"' : '') + '>' + IC.file +
    '<span class="fc-main"><span class="fc-name">' + esc(script.title) + '</span><span class="note">' + esc(scriptMeta(script.duration_min, script.word_count)) + '</span></span></button>' +
    '<button type="button" class="btn btn-ghost iconbtn saved-act" data-act="edit" aria-label="' + esc(T('saved.editAria', { title: script.title })) + '" title="' + esc(T('saved.edit')) + '">' + PENCIL + '</button>' +
    '<button type="button" class="btn btn-ghost iconbtn saved-act saved-del" data-act="delete" aria-label="' + esc(T('saved.deleteAria', { title: script.title })) + '" title="' + esc(T('common.delete')) + '">' + TRASH + '</button>' +
    '</li>';
}
/* Cards rise in one after another when the list content changes (not on every repaint of the same list). */
function listKey(items) {
  return items.map(s => s.id + s.title + s.word_count).join('|');
}
function fillList(list, count, countKey, empty, selectedId, motion) {
  if (!list) return;
  const items = S.savedScripts || [];
  const html = items.map(s => itemHtml(s, selectedId)).join('');
  const fresh = list._shown !== listKey(items);
  list.innerHTML = html;
  list._shown = items.map(s => s.id + s.title + s.word_count).join('|');
  list.hidden = !items.length;
  if (empty) empty.hidden = !!items.length;
  if (count) count.textContent = T(countKey, { n: S.savedScriptTotal, max: savedScriptLimit() });
  if (fresh && list.offsetParent) $$('.saved-item', list).forEach((li, i) => popIn(li, Object.assign({}, motion, { delay: (motion && motion.delay || 0) + i * 45 })));
}
export function renderSavedLists() {
  const mine = S.texts.mine;
  fillList($('#mineList'), $('#mineCount'), 'saved.countLong', $('#mineEmpty'), mine && mine.id);
  // Show my scripts: after the menu has grown, the cards slide in to the right one after another
  fillList($('#studioSavedList'), $('#studioSavedCount'), 'saved.count', $('#studioSavedEmpty'), null, { x: -24, y: 0, duration: 340, delay: 200 });
}

/* One click handler for both lists. `where`: 'practice' edits and shows on the right; 'studio' opens the reader. */
export function onSavedListClick(e, where) {
  const b = e.target.closest('[data-act]'), li = e.target.closest('.saved-item');
  if (!b || !li) return;
  const id = li.getAttribute('data-id'), act = b.getAttribute('data-act');
  if (act === 'delete') deleteSavedScript(id, li);
  else if (where === 'practice') {
    if (act === 'edit') startMineEdit(id); else pickSavedScript(id, true);
  } else openSavedScript(id, act === 'edit');
}

/* ---- Script Name Dialog: one text box; resolves with the trimmed name, or never when cancelled ---- */
export function askScriptName(heading, okLabel, initial) {
  return new Promise(resolve => {
    const input = $('#scriptNameInput');
    $('#scriptNameTitle').textContent = heading;
    $('#scriptNameOk').textContent = okLabel;
    input.maxLength = CONFIG.SCRIPT_TITLE_MAX_CHARS;
    input.value = (initial || '').slice(0, CONFIG.SCRIPT_TITLE_MAX_CHARS);
    clearErr($('#scriptNameError')); input.removeAttribute('aria-invalid');
    paintNameCount();
    S.nameDialog = resolve;
    openModal('scriptNameDialog', { focus: '#scriptNameInput' });
    input.select();
  });
}
/* The name box stops at the limit (pasting a longer name keeps only the first characters). */
export function paintNameCount() {
  const input = $('#scriptNameInput'), max = CONFIG.SCRIPT_TITLE_MAX_CHARS;
  if (input.value.length > max) input.value = input.value.slice(0, max);
  $('#scriptNameCount').textContent = T('saved.nameCount', { n: input.value.length, max });
}
export function confirmScriptName() {
  const input = $('#scriptNameInput'), name = input.value.trim();
  if (!name) { showErr($('#scriptNameError'), T('saved.errNameEmpty')); input.setAttribute('aria-invalid', 'true'); input.focus(); return; }
  const resolve = S.nameDialog; S.nameDialog = null;
  closeModal('scriptNameDialog');
  if (resolve) resolve(name);
}

/* A notice with only a Close button (list full, duplicate text). */
function openNotice(title, message) {
  $('#scriptListFullTitle').textContent = title;
  $('#scriptListFullMessage').textContent = message;
  openModal('scriptListFull', { focus: '[data-close]' });
}
export function openListFull() {
  openNotice(T('saved.fullTitle'), T('saved.fullMsg', { max: savedScriptLimit() }));
}

/* Save a script under a name the user picks. `sc`: { title, text, source, topic, duration_min, template_id, models_used, citations }.
   Resolves with the saved row, or null when nothing was saved (cancelled, list full, error shown). */
export function saveScriptAs(sc) {
  if (isSavedListFull()) { openListFull(); return Promise.resolve(null); }
  return askScriptName(T('saved.saveTitle'), T('common.save'), sc.title).then(name => {
    const d = +sc.duration_min;
    return withBusy(api('/api/scripts', { method: 'POST', json: {
      title: name, body: sc.text, source: SCRIPT_SOURCE[sc.source] || 'written',
      duration_min: SCRIPT_DURATIONS.indexOf(d) >= 0 ? d : null, topic: sc.title ? sc.title.slice(0, CONFIG.SCRIPT_TITLE_MAX_CHARS) : null,
      category: sc.topic || null, template_id: sc.template_id || null, models_used: sc.models_used || [], citations: sc.citations || []
    } }), T('busy.saving')).then(readJson).then(({ ok, status, j }) => {
      if (!ok) {
        const code = j && j.error_code;
        if (code === 'script_limit_reached') { openListFull(); loadSavedScripts(); return null; }
        if (code === 'content_rejected') { openModal('safetyAlert'); return null; }
        toast((j && j.message) || T('eval.errServer'), true);
        return null;
      }
      toast(T(status === 200 ? 'saved.already' : 'saved.saved', { title: j.title }));
      loadSavedScripts();
      return j;
    }).catch(() => { toast(T('eval.errNet'), true); return null; });
  });
}

/* PATCH a saved script with what changed ({ title?, body? }). Resolves with the new row, or null with the error shown
   in `errorBox`. Every place that shows the script is updated (both lists, Practice, the reader, chat bubbles). */
export function patchSavedScript(id, patch, errorBox) {
  return withBusy(api('/api/scripts/' + encodeURIComponent(id), { method: 'PATCH', json: patch }), T('busy.saving')).then(readJson).then(({ ok, j }) => {
    if (!ok) {
      if (j && j.error_code === 'content_rejected') openModal('safetyAlert');
      else if (j && j.error_code === 'script_duplicate') openNotice(T('saved.duplicateTitle'), T('saved.duplicateMsg', { title: j.duplicate_title }));
      else showErr(errorBox, (j && j.message) || T('eval.errServer'));
      return null;
    }
    applyEdit(j, 'body' in patch);
    toast(T('saved.edited'));
    return j;
  }).catch(() => { showErr(errorBox, T('eval.errNet')); return null; });
}
function applyEdit(row, bodyChanged) {
  const item = (S.savedScripts || []).find(x => x.id === row.id);
  if (item) { item.title = row.title; item.word_count = row.word_count; }
  const mine = S.texts.mine;
  if (mine && mine.id === row.id) { mine.title = mine.short = row.title; mine.text = row.body; }
  refreshReader(row);
  if (bodyChanged) forgetSavedScript(row.id);   // the chat keeps the assistant's text, which is no longer this saved script
  else renameChatScript(row.id, row.title);
  renderSavedLists();
  if (S.screen === 'practice') renderPractice();
}

/* Delete after a confirm; the card folds away before the list reloads. */
export function deleteSavedScript(id, card) {
  const row = (S.savedScripts || []).find(s => s.id === id);
  openConfirmDialog(T('saved.deleteTitle'), T('saved.deleteMsg', { title: row ? row.title : '' }), T('common.delete'), () => {
    withBusy(api('/api/scripts/' + encodeURIComponent(id), { method: 'DELETE' }), T('busy.deleting')).then(r => {
      if (!r.ok) { toast(T('eval.errServer'), true); return; }
      if (S.texts.mine && S.texts.mine.id === id) S.texts.mine = null;
      if (S.ownSaved && S.ownSaved.id === id) S.ownSaved = null;
      closeReaderIfShowing(id);
      forgetSavedScript(id);
      toast(T('saved.deleted'));
      foldAway(card, () => {
        // drop the row here first, so the lists redraw as they already look (no cards rising in again)
        S.savedScripts = (S.savedScripts || []).filter(s => s.id !== id);
        S.savedScriptTotal = Math.max(0, S.savedScriptTotal - 1);
        const key = listKey(S.savedScripts);
        $$('.saved-list').forEach(list => { list._shown = key; });
        renderSavedLists();
        loadSavedScripts().then(() => { if (S.screen === 'practice') renderPractice(); });
      });
    }).catch(() => toast(T('eval.errNet'), true));
  });
}
/* A deleted card fades out where it is; then its space closes, so only the cards below slide up. */
function foldAway(el, done) {
  if (!el || !el.animate || matchMedia('(prefers-reduced-motion: reduce)').matches) { done(); return; }
  const fade = el.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 240, easing: 'ease-out', fill: 'forwards' });
  fade.onfinish = () => {
    const list = el.parentElement, gap = list ? parseFloat(getComputedStyle(list).rowGap) || 0 : 0;
    el.style.overflow = 'hidden';
    const close = el.animate([
      { height: el.offsetHeight + 'px', marginBottom: '0px', opacity: 0 },
      { height: '0px', marginBottom: -gap + 'px', paddingTop: '0px', paddingBottom: '0px', borderTopWidth: '0px', borderBottomWidth: '0px', opacity: 0 }
    ], { duration: 300, easing: 'cubic-bezier(.2, .7, .3, 1)', fill: 'forwards' });
    close.onfinish = () => { el.remove(); done(); };
  };
}

/* Script Studio: open a saved script in the reader (`edit`: straight into editing, from the list's pencil). */
export function openSavedScript(id, edit) {
  closeStudioSavedMenu(false);
  withBusy(api('/api/scripts/' + encodeURIComponent(id)), T('busy.loading')).then(r => (r.ok ? r.json() : null)).then(s => {
    if (!s) { toast(T('eval.errServer'), true); return; }
    openReader({ title: s.title, cardName: s.title, text: s.body, citations: s.citations || [], warnings: [], savedId: s.id, fromList: true,
      topic: s.category || null, duration_min: s.duration_min, source: s.source }, { edit });
  }).catch(() => toast(T('eval.errNet'), true));
}

/* ---- Script Studio "Show my scripts" menu: opens upward from the button at the top right of the Composer ---- */
export function toggleStudioSavedMenu() {
  const menu = $('#studioSavedMenu'), btn = $('#studioSavedButton');
  if (!menu.hidden && !menu._closing) { closeStudioSavedMenu(true); return; }
  const list = $('#studioSavedList');
  list.innerHTML = ''; list._shown = null;          // start empty: the cards arrive once the list is loaded
  $('#studioSavedEmpty').hidden = true;
  slideDown(menu);                                  // same roll-out as the Category and Duration lists
  btn.setAttribute('aria-expanded', 'true');
  const h0 = menu.offsetHeight;
  loadSavedScripts().then(() => {
    const h1 = menu.offsetHeight;
    if (h1 > h0 + 1 && menu.animate && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
      menu.animate([{ height: h0 + 'px' }, { height: h1 + 'px' }], { duration: 360, easing: 'cubic-bezier(.2, .7, .3, 1)' });   // grows upward
    }
    const first = $$('#studioSavedList .saved-pick')[0];
    if (first) first.focus({ preventScroll: true });
  });
}
export function closeStudioSavedMenu(focusButton) {
  const menu = $('#studioSavedMenu');
  if (!menu || menu.hidden || menu._closing) return;
  $('#studioSavedButton').setAttribute('aria-expanded', 'false');
  slideUp(menu);
  if (focusButton) $('#studioSavedButton').focus();
}
