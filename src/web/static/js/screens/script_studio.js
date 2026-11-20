import { api } from '../api.js';
import { T, TOPICS } from '../i18n.js';
import { paintAvatar } from '../nav.js';
import { isSavedListFull, openListFull, saveScriptAs } from '../screens/saved_scripts.js';
import { openReader, runScriptAction } from '../screens/script_reader.js';
import { CONFIG, RENDER, S } from '../state.js';
import { openModal, popIn, toast } from '../ui.js';
import { $, $$, IC, clearErr, esc, showErr, wordsOf } from '../utils.js';

/* ---------- Script (Generate Script) ---------- */
export const CAT_LABELS = Object.assign({}, TOPICS, { free: 'Free topic (LLM)' });
export const topicLabel = k => CAT_LABELS[k] || TOPICS[k] || k;
/* Category select: one of the six fixed categories (no free topic). There is no template choice in the
   UI any more; the request keeps its fields (tplId empty) until the backend is updated. */
export function fillTopicSelect() {
  const sel = $('#composerTopic'), keep = sel.value;
  if (!S.apiTopics) {
    fetch('/api/topics').then(r => r.ok ? r.json() : null).then(d => {
      if (d && d.topics) { S.apiTopics = d.topics; S.apiCategories = d.categories || []; fillTopicSelect(); }
    }).catch(() => {});
  }
  const keys = Object.keys(TOPICS);
  sel.innerHTML = keys.map(k => '<option value="' + k + '">' + esc(topicLabel(k)) + '</option>').join('');
  if (keep && keys.indexOf(keep) >= 0) sel.value = keep;
}
/* Chat-app layout: each message is a row with the sender's picture outside the bubble,
   the assistant's logo on the left, the user's avatar (photo or initial) on the right. */
export function addBubble(cls, html, animate = true) {
  const feed = $('#chatFeed'), row = document.createElement('div'), d = document.createElement('div');
  const mine = cls.split(' ').indexOf('me') >= 0;
  row.className = 'msg-row ' + (mine ? 'me' : 'ai');
  const pic = document.createElement('span');
  pic.className = mine ? 'avatar msg-av' : 'msg-av msg-ai';
  pic.setAttribute('aria-hidden', 'true');
  if (mine) paintAvatar(pic); else pic.innerHTML = IC.ai;
  d.className = 'bubble ' + cls;
  if (cls === 'ai') d.innerHTML = '<div class="who">' + IC.ai + '<span>' + esc(T('script.assistant')) + '</span></div>' + html;
  else d.innerHTML = html;
  row.append(pic, d);
  feed.appendChild(row);
  d.remove = () => row.remove();   // callers remove the bubble; take its picture with it
  /* Chat-style entry: the feed glides down to the new message while it rises and fades in */
  const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (animate && !calm && d.animate && feed.offsetParent) {
    feed.scrollTo({ top: feed.scrollHeight, behavior: 'smooth' });
    row.animate([{ opacity: 0, transform: 'translateY(24px) scale(.98)' }, { opacity: 1, transform: 'none' }],
      { duration: 420, easing: 'cubic-bezier(.2, .7, .3, 1)' });
  } else feed.scrollTop = feed.scrollHeight;
  return d;
}
/* The answer replaces the loading lines in the same bubble: fade the new content in and glide to the bottom */
export function revealBubble(d) {
  const feed = $('#chatFeed');
  if (matchMedia('(prefers-reduced-motion: reduce)').matches || !d.animate) { feed.scrollTop = feed.scrollHeight; return; }
  [...d.children].slice(1).forEach((el, i) => el.animate([{ opacity: 0, transform: 'translateY(10px)' }, { opacity: 1, transform: 'none' }],
    { duration: 380, delay: i * 50, easing: 'cubic-bezier(.2, .7, .3, 1)', fill: 'backwards' }));
  feed.scrollTo({ top: feed.scrollHeight, behavior: 'smooth' });
}
export function renderChatFile() {
  const box = $('#composerFile');
  if (!S.chatFile) { box.innerHTML = ''; return; }
  box.innerHTML = '<span class="fchip"><span></span><button type="button" class="btn btn-ghost btn-sm iconbtn" style="width:30px;height:30px;min-height:30px" id="chatFileX">' + IC.x + '</button></span>';
  $('.fchip > span', box).textContent = S.chatFile.name;
  $('#chatFileX').setAttribute('aria-label', T('common.delete') + ' ' + S.chatFile.name);
}
export function titleFrom(txt, file, topic) {
  if (txt) { const w = txt.split(/\s+/).slice(0, 4).join(' '); return w.charAt(0).toUpperCase() + w.slice(1) + (txt.split(/\s+/).length > 4 ? '…' : ''); }
  if (file) return file.name.replace(/\.pdf$/i, '');
  return topicLabel(topic);
}
export function renderBlockedBubble(ai) {
  ai.classList.add('blocked');
  ai.innerHTML = '<div class="who">' + IC.ai + '<span>' + esc(T('script.assistant')) + '</span></div>' +
    '<div class="row"><span class="pill bad">' + IC.alert + esc(T('script.blockedTag')) + '</span></div>' +
    '<h3 class="blk-t">' + esc(T('script.blockedTitle')) + '</h3>' +
    '<p>' + esc(T('script.blockedHarm')) + '</p>' +
    '<p class="note" style="margin-top:8px">' + esc(T('script.blockedNext')) + '</p>';
}
/* The latest Script Studio chat, kept in localStorage per user so two accounts on one browser never see each other's chat. */
const chatHistoryKey = userId => 'psa.chat.' + userId;
export function clearChatHistory(userId) {        // on Log out and Delete account, not on session expiry
  if (!userId) return;
  try { localStorage.removeItem(chatHistoryKey(userId)); } catch (e) { /* storage may be unavailable */ }
}
function chatMaxMessages() {
  return Math.max(1, Number(CONFIG.CHAT_HISTORY_MAX_MESSAGES) || 1);   // default lives in CONFIG; 1 only guards a broken value
}
function isQuotaError(e) {                        // localStorage is full (name/code differ between browsers)
  return !!e && (e.name === 'QuotaExceededError' || e.code === 22 || e.code === 1014);
}
function persistedMessage(message) {
  if (message.role === 'me') {
    return {
      role: 'me',
      text: message.text,
      topic: message.topic,
      duration_min: message.duration_min,
      file_name: message.file_name || null,
    };
  }
  if (message.blocked) return { role: 'ai', blocked: true };
  const sc = message.script;
  return {
    role: 'ai',
    script: {
      title: sc.title,
      cardName: sc.cardName,
      text: sc.text,
      topic: sc.topic,
      duration_min: sc.duration_min,
      source: sc.source,
      template_id: sc.template_id || null,
      models_used: sc.models_used || [],
      citations: sc.citations || [],
      savedId: sc.savedId || null,
      warnings: sc.warnings || [],
    },
  };
}
/* Only the stored copy is capped: the chat on screen keeps every message of this visit. */
function storedChat(skip) {                       // newest N messages, minus `skip` oldest ones after a quota error
  return S.chatHistory.slice(-chatMaxMessages()).slice(skip).map(persistedMessage);
}
export function persistChat() {
  if (!S.user || !S.user.id || !S.chatHistory.length) return;
  const key = chatHistoryKey(S.user.id);
  try {
    localStorage.setItem(key, JSON.stringify(storedChat(0)));
  } catch (e) {
    if (!isQuotaError(e)) return;
    try { localStorage.setItem(key, JSON.stringify(storedChat(1))); } catch (retryError) { /* blocked or still full */ }
  }
}
/* A saved script was renamed: the chat bubbles of the same script show the new name. */
export function renameChatScript(id, title) {
  let changed = false;
  S.chatHistory.forEach(m => {
    if (!m.script || m.script.savedId !== id) return;
    m.script.title = m.script.cardName = title; changed = true;
    const name = m.bubble && $('.fc-name', m.bubble);
    if (name) name.textContent = title;
  });
  if (changed) persistChat();
}
/* A saved script was deleted: its chat bubbles must save it again next time. */
export function forgetSavedScript(id) {
  let changed = false;
  S.chatHistory.forEach(m => { if (m.script && m.script.savedId === id) { m.script.savedId = null; changed = true; } });
  if (changed) persistChat();
}
function recordChatMessage(message) {
  S.chatHistory.push(message);
  persistChat();
}
function renderUserMessage(message, animate = false) {
  const bubble = addBubble('me', '<span></span>', animate);
  bubble.firstChild.textContent = [
    message.text || '',
    message.file_name ? '📎 ' + message.file_name : '',
  ].filter(Boolean).join('\n');
  return bubble;
}
/* The file card itself opens the reader; Practice is the main action. */
function scriptCardHtml() {
  return '<button type="button" class="fcard fcard-open" data-a="view">' + IC.file + '<span class="fc-main"><span class="fc-name"></span><span class="note"></span></span></button>' +
    '<div class="acts"><button class="btn btn-primary btn-sm" type="button" data-a="practice"></button><button class="btn btn-sm" type="button" data-a="save"></button><button class="btn btn-sm" type="button" data-a="copy"></button><button class="btn btn-sm" type="button" data-a="download"></button><button class="btn btn-sm" type="button" data-a="again"></button></div>';
}
function fillScriptBubble(ai, sc) {
  ai.innerHTML = '<div class="who">' + IC.ai + '<span>' + esc(T('script.assistant')) + '</span></div>' + scriptCardHtml();
  $('.fc-name', ai).textContent = sc.cardName;
  const wc = wordsOf(sc.text);
  $('.fc-main .note', ai).textContent = sc.duration_min + ' ' + T('script.min') + ' · ' + wc + ' ' + T('script.words') + (sc.warnings.length ? ' · ' + T('script.hasNotes') : '');
  $('[data-a=view]', ai).setAttribute('aria-label', T('script.viewAria', { title: sc.cardName }));
  $('[data-a=practice]', ai).textContent = T('script.practice');
  $('[data-a=save]', ai).textContent = T('saved.saveScript');
  $('[data-a=copy]', ai).textContent = T('script.copy');
  $('[data-a=download]', ai).textContent = T('script.download');
  const again = $('[data-a=again]', ai);
  again.textContent = T('script.regenerate');
  if (!sc.req) again.disabled = true;
  ai._script = sc;
}
export function restoreChat() {
  if (!S.user || !S.user.id) return false;
  let saved;
  try { saved = JSON.parse(localStorage.getItem(chatHistoryKey(S.user.id)) || 'null'); } catch (e) { return false; }
  if (!Array.isArray(saved)) return false;
  const history = saved.filter(item =>
    item && (item.role === 'me' && typeof item.text === 'string'
      || item.role === 'ai' && (item.blocked === true || item.script && typeof item.script.text === 'string'))
  ).slice(-chatMaxMessages());
  if (!history.length) return false;
  S.chatHistory = history;
  history.forEach((item, index) => {
    if (item.role === 'me') {
      item.bubble = renderUserMessage(item);
      return;
    }
    if (item.blocked) {
      const bubble = addBubble('ai', '', false);
      renderBlockedBubble(bubble);
      item.bubble = bubble;
      return;
    }
    const sc = item.script;
    sc.title = typeof sc.title === 'string' ? sc.title : '';
    sc.cardName = typeof sc.cardName === 'string' ? sc.cardName : sc.title;
    sc.text = typeof sc.text === 'string' ? sc.text : '';
    sc.topic = typeof sc.topic === 'string' ? sc.topic : '';
    sc.duration_min = Number.isFinite(sc.duration_min) ? sc.duration_min : 5;
    sc.source = typeof sc.source === 'string' ? sc.source : 'written';
    sc.template_id = typeof sc.template_id === 'string' ? sc.template_id : null;
    sc.savedId = typeof sc.savedId === 'string' ? sc.savedId : null;
    sc.warnings = Array.isArray(sc.warnings) ? sc.warnings : [];
    sc.citations = Array.isArray(sc.citations) ? sc.citations : [];
    sc.models_used = Array.isArray(sc.models_used) ? sc.models_used : [];
    const previous = history.slice(0, index).reverse().find(entry => entry.role === 'me');
    sc.req = previous && !previous.file_name
      ? { txt: previous.text, file: null, topic: previous.topic, tplId: '', tplTitle: '', dur: previous.duration_min }
      : null;
    const bubble = addBubble('ai', '', false);
    fillScriptBubble(bubble, sc);
    item.bubble = bubble;
  });
  return true;
}
export function generateScript(req, again) {
  S.chatBusy = true; $('#composerSend').disabled = true;
  const ai = addBubble('ai', '<div class="skel" style="width:92%"></div><div class="skel" style="width:78%"></div><div class="skel" style="width:60%"></div><p class="note" role="status"></p>');
  const status = $('.note', ai);
  status.textContent = req.file ? T('script.extracting') : (again ? T('script.regenerating') : T('script.generating'));
  const fd = new FormData(), cleanTxt = (req.txt || '').replace(/^#+\s+/, '');
  const isShortPrompt = !req.tplId && !req.file && wordsOf(cleanTxt) > 0 && wordsOf(cleanTxt) <= 25;
  fd.append('topic', req.tplId || (isShortPrompt ? cleanTxt : titleFrom(cleanTxt, req.file, req.topic)));
  fd.append('category', req.tplId ? req.topic : 'free');
  fd.append('duration_min', String(req.dur || 5));
  if (cleanTxt && !isShortPrompt) fd.append('raw_text', cleanTxt);
  if (req.file && req.file.raw) fd.append('pdf', req.file.raw, req.file.name);
  const failJob = (code, msg) => {
    S.chatBusy = false; $('#composerSend').disabled = false;
    if (code === 'invalid_pdf' || code === 'no_text_layer') { ai.remove(); showErr($('#composerError'), msg || T('script.errFile', { mb: Math.round(CONFIG.MAX_PDF_SIZE_BYTES / (1024 * 1024)), pages: CONFIG.MAX_PDF_PAGES })); return; }
    if (code === 'content_rejected') {
      renderBlockedBubble(ai);
      recordChatMessage({ role: 'ai', blocked: true, bubble: ai });
      openModal('safetyAlert'); revealBubble(ai); return;
    }
    toast(msg || T('eval.errServer'), true);
    ai.innerHTML = '<div class="who">' + IC.ai + '<span>' + esc(T('script.assistant')) + '</span></div><p class="note">' + esc(msg || T('eval.errServer')) + '</p><div class="acts"><button class="btn btn-sm" type="button" data-a="again">' + esc(T('script.regenerate')) + '</button></div>';
    ai._script = { req }; revealBubble(ai);
  };
  const poll = id => api('/api/generate-script/' + id).then(r => r.json().then(j => ({ ok: r.ok, j }))).then(({ ok, j }) => {
    if (!ok || !j || j.status === 'failed') { failJob(j && j.error_code, j && j.message); return; }
    if (j.status !== 'completed') {
      status.textContent = (j.status === 'extracting' ? T('script.extracting') : j.status === 'moderating' ? T('script.checking') : T('script.generating')) + ' (' + (j.progress || 0) + '%)';
      setTimeout(() => poll(id), CONFIG.SCRIPT_POLL_INTERVAL_MS); return;
    }
    const res = j.result || {}, text = res.script || '';
    const title = req.tplTitle || titleFrom(req.txt, req.file, req.topic);
    /* The card is named after the Topic the person picked (template title when one is chosen), not the chat message */
    const cardName = req.tplTitle || topicLabel(req.topic), dur = res.duration_min || req.dur || 5;
    /* word_count comes from the result; if the API omits it, count whitespace-separated tokens (wordsOf) */
    const wc = res.word_count || wordsOf(text);
    ai._script = { title, cardName, text, topic: req.topic, duration_min: res.duration_min || req.dur || 5, source: res.source || (req.tplId ? 'template' : 'llm'),
      template_id: res.template_id || null, models_used: res.models_used || [], citations: res.citations || [], warnings: res.warnings || [], req };
    fillScriptBubble(ai, ai._script);
    recordChatMessage({ role: 'ai', script: ai._script, bubble: ai });
    S.chatBusy = false; $('#composerSend').disabled = false; revealBubble(ai);
  }).catch(() => failJob('net', T('eval.errNet')));
  api('/api/generate-script', { method: 'POST', body: fd }).then(r => r.json().then(j => ({ ok: r.ok, j }))).then(({ ok, j }) => {
    if (!ok || !j || !j.job_id) { failJob(j && j.error_code, j && j.message); return; }
    poll(j.job_id);
  }).catch(() => failJob('net', T('eval.errNet')));
}
/* Composer text box: when short it is exactly as tall as the buttons beside it (attach / send), grows
   line by line as the text gets longer, up to 5.5 lines (then it scrolls inside). The arrow at the top
   right of the composer folds it back to the button height (arrow points down) and unfolds it again to
   fit the text, at most 5.5 lines (arrow points up). The arrow only shows when the text is taller than
   that short box, the only time folding changes anything. */
export function fitComposer() {
  const ta = $('#composerInput'), fold = $('#composerFold'); if (!ta) return;
  const st = getComputedStyle(ta), line = parseFloat(st.lineHeight) || 22;
  const pad = parseFloat(st.paddingTop) + parseFloat(st.paddingBottom), edge = parseFloat(st.borderTopWidth) + parseFloat(st.borderBottomWidth);
  // measure the text alone (height 0) with the height transition off, then put the old height back so
  // the transition runs from where the box is now, not from 0 (that would flicker on every key)
  const prev = ta.offsetHeight;
  ta.style.transition = 'none'; ta.style.height = '0px';
  const text = ta.scrollHeight - pad;
  ta.style.height = prev + 'px'; void ta.offsetHeight; ta.style.transition = '';
  const btn = $('#attachBtn'), lo = Math.max(line, ((btn && btn.offsetHeight) || 44) - pad - edge), hi = CONFIG.COMPOSER_MAX_LINES * line;
  const open = Math.min(hi, Math.max(lo, text));
  const tall = text > lo + 1;
  if (!tall) S.composerFolded = false;                           // nothing to fold any more
  ta.style.height = ((S.composerFolded ? lo : open) + pad + edge) + 'px';
  fold.hidden = !tall;
  fold.classList.toggle('up', !!S.composerFolded);
  fold.setAttribute('aria-expanded', String(!S.composerFolded));
  fold.setAttribute('aria-label', T(S.composerFolded ? 'script.unfold' : 'script.fold'));
  fold.title = fold.getAttribute('aria-label');
}
export function toggleComposerFold() {
  S.composerFolded = !S.composerFolded;
  fitComposer();
  if (!S.composerFolded) { const ta = $('#composerInput'); ta.scrollTop = ta.scrollHeight; }
}
export function sendChat() {
  if (S.chatBusy) return;
  const txt = $('#composerInput').value.trim(), err = $('#composerError'), tplId = '';   // no template choice in the UI
  const tpl = (S.apiTopics || []).find(t => t.template_id === tplId);
  if (!txt && !S.chatFile && !tplId) return;
  if (wordsOf(txt) > CONFIG.COMPOSER_MAX_WORDS) { showErr(err, T('script.errLong', { max: CONFIG.COMPOSER_MAX_WORDS.toLocaleString('en-US') })); return; }
  clearErr(err);
  const tplName = tpl ? (tpl.topic || tpl.title) : '';
  const req = { txt, file: S.chatFile, topic: $('#composerTopic').value, tplId, tplTitle: tplName, dur: +($('#composerDuration') && $('#composerDuration').value || 5) };
  const message = { role: 'me', text: txt, topic: $('#composerTopic').value, duration_min: req.dur, file_name: S.chatFile ? S.chatFile.name : null };
  message.bubble = renderUserMessage(message, true);
  recordChatMessage(message);
  $('#composerInput').value = ''; S.chatFile = null; renderChatFile();
  S.composerFolded = false; fitComposer();   // back to one short line
  S.lastReq = req;
  generateScript(req, false);
}
/* Save from a chat bubble or the reader menu: asks for a name, then the chat copy remembers the saved id. */
export function saveChatScript(sc) {
  const known = sc.savedId && (S.savedScripts || []).some(s => s.id === sc.savedId);
  if (known) { toast(T('saved.already', { title: sc.cardName || sc.title })); return; }
  if (isSavedListFull()) { openListFull(); return; }
  saveScriptAs(sc).then(j => { if (j) { sc.savedId = j.id; sc.title = sc.cardName = j.title; renameChatScript(j.id, j.title); persistChat(); } });
}
/* A chat script was edited in the reader: redraw its card and keep the change in localStorage. */
export function refreshChatScript(sc) {
  const item = S.chatHistory.find(m => m.script === sc);
  if (item && item.bubble) { fillScriptBubble(item.bubble, sc); popIn($('.fcard', item.bubble)); }
  persistChat();
}
export function onChatAction(e) {
  const b = e.target.closest('[data-a]');
  if (!b) return;
  const sc = b.closest('.bubble')._script;
  if (!sc) return;
  const a = b.getAttribute('data-a');
  if (a === 'view') {
    b.focus();   // some browsers do not focus a button on click; openModal stores document.activeElement as the opener to return to
    openReader(sc);
  } else if (a === 'again') {
    if (!S.chatBusy) generateScript(sc.req, true);
  } else runScriptAction(sc, a);
}
RENDER.scriptStudio = function () { fillTopicSelect(); };
