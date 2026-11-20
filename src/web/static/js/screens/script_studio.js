import { api, readJson } from '../api.js';
import { T, TOPICS } from '../i18n.js';
import { go, paintAvatar } from '../nav.js';
import { loadSavedScripts } from '../screens/practice.js';
import { RENDER, S } from '../state.js';
import { openModal, toast, withBusy } from '../ui.js';
import { $, $$, IC, clearErr, esc, showErr, wordsOf } from '../utils.js';

/* ---------- Chat constants (Issue #58) ---------- */
const POLL_INTERVAL_MS = 650;                                          // gap between two GET /api/generate-script/{id} polls
const POLL_MAX_MS = 5 * 60 * 1000;                                     // stop polling after about 5 minutes
const POLL_MAX_TRIES = Math.ceil(POLL_MAX_MS / POLL_INTERVAL_MS);
const FALLBACK_USER_NAME = 'you';                                      // same fallback as userName() in auth_panel.js
/* Error code -> message group. In the contract (contracts.py, Brief 5.7): invalid_pdf, no_text_layer,
   content_rejected (422), rate_limited (429), generation_unavailable (503). moderation_unavailable (503) is raised by
   moderation.py / ADR-006 but is not in the contract list. job_not_found IS in the code (src/app/main.py:640, 404
   {"error_code": "job_not_found"}) but not in the Member 2 contract; it is NOT mapped to 'session' on purpose: a lost
   job is not an expired chat, and resetting would wipe scripts that are not saved yet (it shows the generic error
   bubble with a retry button instead). GUESSES for the chat endpoint, not confirmed by its owner:
   session_not_found (today only the evaluation sessions return {"error": "session_not_found"}), a bare HTTP 429
   without a code, a bare HTTP 503 without a code, and rate_limited / moderation_unavailable / generation_unavailable
   on the chat route. */
const ERR_KIND = { invalid_pdf: 'file', no_text_layer: 'file', content_rejected: 'blocked', session_not_found: 'session',
  rate_limited: 'rate', moderation_unavailable: 'moderation', generation_unavailable: 'generation', net: 'net' };
const ERR_TEXT = { rate: 'script.errRate', moderation: 'script.errModeration', net: 'eval.errNet' };   // other groups: server message, else script.errGeneric

/* ---------- Chat state: lives in memory only (no localStorage / sessionStorage / IndexedDB), gone on reload ----------
   chatStage: 'idle' | 'picking_topic' | 'gathering' | 'generated'. chatEpoch grows on every New chat so that answers
   of an older turn can tell they are stale. chatAbort / chatPollTimer belong to the turn that is running. */
export function initChatState() {
  Object.assign(S, { chatSessionId: null, chatStage: 'idle', selectedTemplate: null, sessionFiles: [],
    chatEpoch: 0, chatPollTimer: null, chatAbort: null, chatOwner: null });
}
initChatState();
const setComposerBusy = on => { S.chatBusy = on; $('#composerSend').disabled = on; };
/* New chat: drop the running turn (timer, request, answer) and every piece of chat state, then show the greeting
   like resetChat() in modals/auth_panel.js does. Works while a turn is busy. */
export function startNewChat() {
  S.chatEpoch += 1;
  clearTimeout(S.chatPollTimer); S.chatPollTimer = null;
  if (S.chatAbort) { S.chatAbort.abort(); S.chatAbort = null; }
  Object.assign(S, { chatSessionId: null, chatStage: 'idle', selectedTemplate: null, sessionFiles: [] });
  setComposerBusy(false);
  $('#chatFeed').innerHTML = '';
  addBubble('ai', '<p></p>').querySelector('p').textContent = T('script.greeting', { name: S.user ? S.user.name : FALLBACK_USER_NAME });
  S.chatFile = null; renderChatFile(); $('#composerInput').value = ''; S.composerFolded = false; fitComposer(); clearErr($('#composerError'));
}

/* ---------- Script (Generate Script) ---------- */
export const CAT_LABELS = Object.assign({}, TOPICS, { free: 'Free topic (LLM)' });
export const topicLabel = k => CAT_LABELS[k] || TOPICS[k] || k;
/* GeneratedScript.source ("template" / "llm") -> the scripts.source value the API stores. */
export const SCRIPT_SOURCE = { template: 'generated_template', llm: 'generated_llm' };
export const SCRIPT_DURATIONS = [5, 10, 15, 20];
/* POST /api/scripts. Saving the same text again returns the same id (the server dedupes by content hash). */
export function saveScript(sc) {
  if (sc.savedId) return Promise.resolve({ id: sc.savedId });
  const d = +sc.duration_min;
  return withBusy(api('/api/scripts', { method: 'POST', json: {
    title: (sc.title || 'Script').slice(0, 200), body: sc.text, source: SCRIPT_SOURCE[sc.source] || 'written',
    duration_min: SCRIPT_DURATIONS.indexOf(d) >= 0 ? d : null, topic: sc.title ? sc.title.slice(0, 200) : null,
    category: sc.topic || null, template_id: sc.template_id || null, models_used: sc.models_used || [], citations: sc.citations || []
  } }), T('busy.saving')).then(readJson).then(({ ok, j }) => {
    if (!ok) throw Object.assign(new Error('save'), { code: j && j.error_code, msg: j && j.message });
    sc.savedId = j.id;
    return j;
  });
}
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
export function addBubble(cls, html) {
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
  if (!calm && d.animate && feed.offsetParent) {
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
/* Error bubble with a retry button; the text is set with textContent (it may come from the server). */
function renderErrorBubble(ai, text) {
  ai.innerHTML = '<div class="who">' + IC.ai + '<span>' + esc(T('script.assistant')) + '</span></div><p class="note"></p><div class="acts"><button class="btn btn-sm" type="button" data-a="again"></button></div>';
  $('.note', ai).textContent = text; $('[data-a=again]', ai).textContent = T('script.regenerate');
  revealBubble(ai);
}
/* Which message group an error belongs to: error_code first, HTTP status only when there is no known code. */
export function chatErrorKind(code, status) {
  if (Object.hasOwn(ERR_KIND, code)) return ERR_KIND[code];
  return status === 429 ? 'rate' : status === 503 ? 'generation' : 'other';
}
/* One place for every chat error. `ai` is the loading bubble of the failed turn (ai._script.req is kept for retry).
   Each error group has its own message. A session error starts a new chat but keeps the user's text. */
export function handleChatError(ai, code, message, status) {
  const kind = chatErrorKind(code, status);
  if (kind === 'file') { ai.remove(); showErr($('#composerError'), message || T('script.errFile')); return; }
  if (kind === 'blocked') { renderBlockedBubble(ai); openModal('safetyAlert'); revealBubble(ai); return; }
  if (kind === 'session') {
    const input = $('#composerInput'), draft = input.value, sent = ai._script && ai._script.req && ai._script.req.txt;
    toast(T('script.errSession'), true); startNewChat();
    input.value = draft.trim() ? draft : (sent || ''); fitComposer();   // keep the draft, else the request that was just sent
    return;
  }
  const text = Object.hasOwn(ERR_TEXT, kind) ? T(ERR_TEXT[kind]) : (message || T('script.errGeneric'));   // fail-closed moderation never opens safetyAlert
  toast(text, true);
  renderErrorBubble(ai, text);
}
export function generateScript(req, again) {
  const ep = S.chatEpoch, owner = S.user, ctl = new AbortController();
  /* New chat, logout or another login since this turn began. S.user is a new object on every login (and null after
     logout), so comparing the reference also catches logout then login of the same account. */
  const stale = () => ep !== S.chatEpoch || S.user !== owner;
  S.chatAbort = ctl; setComposerBusy(true);
  const ai = addBubble('ai', '<div class="skel" style="width:92%"></div><div class="skel" style="width:78%"></div><div class="skel" style="width:60%"></div><p class="note" role="status"></p>');
  ai._script = { req };
  const status = $('.note', ai);
  status.textContent = req.file ? T('script.extracting') : (again ? T('script.regenerating') : T('script.generating'));
  const fd = new FormData(), cleanTxt = (req.txt || '').replace(/^#+\s+/, '');
  const isShortPrompt = !req.tplId && !req.file && wordsOf(cleanTxt) > 0 && wordsOf(cleanTxt) <= 25;
  fd.append('topic', req.tplId || (isShortPrompt ? cleanTxt : titleFrom(cleanTxt, req.file, req.topic)));
  fd.append('category', req.tplId ? req.topic : 'free');
  fd.append('duration_min', String(req.dur || 5));
  if (cleanTxt && !isShortPrompt) fd.append('raw_text', cleanTxt);
  if (req.file && req.file.raw) fd.append('pdf', req.file.raw, req.file.name);
  /* A stale turn (New chat / other account) stays silent: no render, no busy flag. `j.error` is read too because
     some routes answer {"error": "<code>"} instead of {"error_code": ...}. */
  const fail = (code, msg, httpStatus) => { if (!stale()) { setComposerBusy(false); handleChatError(ai, code, msg, httpStatus); } };
  const failFrom = (j, httpStatus) => fail(j && (j.error_code || (typeof j.error === 'string' ? j.error : null)), j && j.message, httpStatus);
  let tries = 0;
  const poll = id => {
    if (stale()) return;
    if (++tries > POLL_MAX_TRIES) { fail('poll_timeout', null); return; }
    api('/api/generate-script/' + id, { signal: ctl.signal }).then(readJson).then(({ ok, status: httpStatus, j }) => {
    if (stale()) return;
    if (!ok || !j || j.status === 'failed') { failFrom(j, httpStatus); return; }
    if (j.status !== 'completed') {
      status.textContent = (j.status === 'extracting' ? T('script.extracting') : j.status === 'moderating' ? T('script.checking') : T('script.generating')) + ' (' + (j.progress || 0) + '%)';
      S.chatPollTimer = setTimeout(() => poll(id), POLL_INTERVAL_MS); return;
    }
    const res = j.result || {}, text = res.script || '';
    const title = req.tplTitle || titleFrom(req.txt, req.file, req.topic);
    /* The card is named after the Topic the person picked (template title when one is chosen), not the chat message */
    const cardName = req.tplTitle || topicLabel(req.topic), dur = res.duration_min || req.dur || 5;
    /* word_count comes from the result; if the API omits it, count whitespace-separated tokens (wordsOf) */
    const wc = res.word_count || wordsOf(text);
    let h = '<div class="fcard">' + IC.file + '<div class="fc-main"><div class="fc-name"></div><div class="note"></div></div></div>';
    h += '<div class="acts"><button class="btn btn-primary btn-sm" type="button" data-a="view"></button><button class="btn btn-sm" type="button" data-a="practice"></button><button class="btn btn-sm" type="button" data-a="save">Save script</button><button class="btn btn-sm" type="button" data-a="copy"></button><button class="btn btn-sm" type="button" data-a="download"></button><button class="btn btn-sm" type="button" data-a="again"></button></div>';
    ai.innerHTML = '<div class="who">' + IC.ai + '<span>' + esc(T('script.assistant')) + '</span></div>' + h;
    $('.fc-name', ai).textContent = cardName;
    $('.fc-main .note', ai).textContent = dur + ' ' + T('script.min') + ' · ' + wc + ' ' + T('script.words') + ((res.warnings || []).length ? ' · ' + T('script.hasNotes') : '');
    const vb = $('[data-a=view]', ai); vb.textContent = T('script.viewNow'); vb.setAttribute('aria-label', T('script.viewAria', { title: cardName }));
    $('[data-a=practice]', ai).textContent = T('script.practice'); $('[data-a=copy]', ai).textContent = T('script.copy');
    $('[data-a=download]', ai).textContent = T('script.download'); $('[data-a=again]', ai).textContent = T('script.regenerate');
    ai._script = { title, cardName, text, topic: req.topic, duration_min: res.duration_min || req.dur || 5, source: res.source || (req.tplId ? 'template' : 'llm'),
      template_id: res.template_id || null, models_used: res.models_used || [], citations: res.citations || [], warnings: res.warnings || [], req };
    setComposerBusy(false); revealBubble(ai);
    }).catch(() => fail('net', null));
  };
  api('/api/generate-script', { method: 'POST', body: fd, signal: ctl.signal }).then(readJson).then(({ ok, status: httpStatus, j }) => {
    if (stale()) return;
    if (!ok || !j || !j.job_id) { failFrom(j, httpStatus); return; }
    poll(j.job_id);
  }).catch(() => fail('net', null));
}
/* Composer text box: when short it is exactly as tall as the buttons beside it (attach / send), grows
   line by line as the text gets longer, up to 5.5 lines (then it scrolls inside). The arrow at the top
   right of the composer folds it back to the button height (arrow points down) and unfolds it again to
   fit the text, at most 5.5 lines (arrow points up). The arrow only shows when the text is taller than
   that short box, the only time folding changes anything. */
const COMPOSER_MAX_LINES = 5.5;
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
  const btn = $('#attachBtn'), lo = Math.max(line, ((btn && btn.offsetHeight) || 44) - pad - edge), hi = COMPOSER_MAX_LINES * line;
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
  if (wordsOf(txt) > 3000) { showErr(err, T('script.errLong')); return; }
  clearErr(err);
  const tplName = tpl ? (tpl.topic || tpl.title) : '';
  const req = { txt, file: S.chatFile, topic: $('#composerTopic').value, tplId, tplTitle: tplName, dur: +($('#composerDuration') && $('#composerDuration').value || 5) };
  const me = addBubble('me', '<span></span>');
  me.firstChild.textContent = [tplName ? '📄 ' + tplName : '', txt, S.chatFile ? '📎 ' + S.chatFile.name : ''].filter(Boolean).join('\n');
  $('#composerInput').value = ''; S.chatFile = null; renderChatFile();
  S.composerFolded = false; fitComposer();   // back to one short line
  S.lastReq = req;
  generateScript(req, false);
}
/* Reader window: paragraphs with their citation / uncited badge, then the warnings and the citation note (same content the feed used to show) */
export function openReader(sc) {
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
  body.scrollTop = 0;
  $('#mrTitle').textContent = sc.cardName || sc.title;
  openModal('scriptReader', { focus: '[data-close]' });
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
  } else if (a === 'practice') {
    const lbl = sc.title || TOPICS[sc.topic] || sc.topic;
    const practise = id => { S.texts.mine = { id: id || null, title: T('practice.fromScript', { title: lbl }), short: lbl, text: sc.text, topic: sc.topic }; S.pickerTab = 'mine'; S.choosing = false; go('practice'); };
    saveScript(sc).then(j => practise(j.id), () => practise(null));   // saved so the session links to it (C2); unsaved still works
  } else if (a === 'save') {
    saveScript(sc).then(j => { toast('Script saved.'); loadSavedScripts(j.id); })
      .catch(e => toast((e && e.msg) || (e && e.code ? T('eval.errServer') : T('eval.errNet')), true));
  } else if (a === 'copy') {
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(sc.text).then(() => toast(T('script.copied')), () => toast(T('script.copyFail'), true));
    else toast(T('script.copyFail'), true);
  } else if (a === 'download') {
    const url = URL.createObjectURL(new Blob([sc.text], { type: 'text/plain' })), a2 = document.createElement('a');
    a2.href = url; a2.download = T('script.downloadName'); document.body.appendChild(a2); a2.click(); a2.remove(); setTimeout(() => URL.revokeObjectURL(url), 500);
  } else if (a === 'again') {
    if (!S.chatBusy) generateScript(sc.req, true);
  }
}
RENDER.scriptStudio = function () {
  fillTopicSelect();
  $('#chatResetBtn').onclick = () => startNewChat();   // property, not addEventListener: running RENDER again never stacks handlers
  if (S.user && S.user !== S.chatOwner) { startNewChat(); S.chatOwner = S.user; }   // new login (any account) without F5: no chat carry-over
};
