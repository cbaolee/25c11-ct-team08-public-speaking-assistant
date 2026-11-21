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
   on the chat route. The parser codes unsupported_file_type, file_too_large, file_too_small, invalid_text_encoding and
   text_too_long come from DocumentParserError in the Member 1 brief; no document says which HTTP status or response body
   carries them, so the error_code is read first (GUESS: they reach the chat routes as error_code). */
const ERR_KIND = { invalid_pdf: 'file', no_text_layer: 'file', unsupported_file_type: 'file', file_too_large: 'file', file_too_small: 'file',
  invalid_text_encoding: 'file', invalid_text_file: 'file', empty_file: 'file', empty_document: 'file', text_too_long: 'file',
  content_rejected: 'blocked', session_not_found: 'session',
  rate_limited: 'rate', moderation_unavailable: 'moderation', generation_unavailable: 'generation', net: 'net' };
const ERR_TEXT = { rate: 'script.errRate', moderation: 'script.errModeration', net: 'eval.errNet' };   // other groups: server message, else script.errGeneric
const FILE_ERR_TEXT = { unsupported_file_type: 'script.errFileType', file_too_large: 'script.errFileBig', file_too_small: 'script.errFileSmall',
  empty_file: 'script.errFileSmall', empty_document: 'script.errFileSmall', invalid_text_file: 'script.errFileEncoding',
  invalid_text_encoding: 'script.errFileEncoding', text_too_long: 'script.errFileWords', no_text_layer: 'script.errFileNoText' };   // other file codes: script.errFile

/* Chat endpoints (Member 2 contract). */
const URL_SUGGEST = '/api/script-chat/suggest', URL_SELECT = '/api/script-chat/select-topic', URL_MESSAGE = '/api/script-chat/message';
/* Typing exactly one of these words (whole message, trimmed, any case) means "Generate Script"; it only counts while
   gathering or after a script. A message that carries a file is never a keyword. */
const GENERATE_KEYWORDS = new Set(['generate', 'done', 'tạo', 'xong']);
const TOPIC_MAX_CHARS = 120;                                           // longest free-topic text sent as `topic`
/* Client-side file limits (a quick check before upload). Keep in sync with parser limits; the server is the source of truth.
   PDF: app_constants.toml [script] min_pdf_size_bytes = 1024 (line 42) and max_pdf_size_bytes = 26_214_400 (line 43).
   .md / .txt: MAX_TEXT_FILE_BYTES = 2 * 1024 * 1024 in the Member 1 parser contract; the smallest allowed size is 1 byte. */
const TEXT_LIMITS = { min: 1, max: 2 * 1024 * 1024 };
const FILE_LIMITS = { '.pdf': { min: 1024, max: 25 * 1024 * 1024 }, '.md': TEXT_LIMITS, '.txt': TEXT_LIMITS };

/* ---------- Chat state: lives in memory only (no localStorage / sessionStorage / IndexedDB), gone on reload ----------
   chatStage: 'idle' | 'picking_topic' | 'gathering' | 'generated'. chatEpoch grows on every New chat so that answers
   of an older turn can tell they are stale. chatAbort / chatPollTimer belong to the turn that is running.
   chatSeed = {prompt, fileName} of the first request (names a free-topic script); chatCards = the bubble holding the topic cards. */
const NO_SESSION = { chatSessionId: null, chatStage: 'idle', selectedTemplate: null, sessionFiles: [], chatSeed: null, chatCards: null };
export function initChatState() {
  Object.assign(S, NO_SESSION, { chatEpoch: 0, chatPollTimer: null, chatAbort: null, chatOwner: null });
}
initChatState();
const setComposerBusy = on => { S.chatBusy = on; $('#composerSend').disabled = on; $$('#chatFeed [data-a=generate]').forEach(b => { b.disabled = on; }); };
/* Category and Duration belong to the session once it exists, so they are locked until New chat (disabling the select disables its custom button too) */
const lockSetup = on => { $('#composerTopic').disabled = on; $('#composerDuration').disabled = on; };
/* Chips of the files the session holds (names from files_loaded); view only, the contract has no call to remove a file */
function setSessionFiles(list) {
  if (!Array.isArray(list)) return;
  S.sessionFiles = list.map(f => (typeof f === 'string' ? f : f && f.name)).filter(Boolean);   // contract says names; objects are tolerated
  renderSessionFiles();
}
function renderSessionFiles() {
  const box = $('#sessionFiles'); box.replaceChildren();
  S.sessionFiles.forEach(name => {
    const chip = document.createElement('span'); chip.className = 'fchip ro'; chip.textContent = name; box.appendChild(chip);
  });
}
/* New chat: drop the running turn (timer, request, answer) and every piece of chat state, then show the greeting
   like resetChat() in modals/auth_panel.js does. Works while a turn is busy. */
export function startNewChat() {
  S.chatEpoch += 1;
  clearTimeout(S.chatPollTimer); S.chatPollTimer = null;
  if (S.chatAbort) { S.chatAbort.abort(); S.chatAbort = null; }
  Object.assign(S, NO_SESSION);
  setComposerBusy(false); lockSetup(false); renderSessionFiles();
  $('#chatFeed').innerHTML = '';
  addBubble('ai', '<p></p>').querySelector('p').textContent = T('script.greeting', { name: S.user ? S.user.name : FALLBACK_USER_NAME });
  S.chatFile = null; renderChatFile(); $('#composerInput').value = ''; S.composerFolded = false; fitComposer(); clearErr($('#composerError'));
}

/* ---------- Script (Generate Script) ---------- */
export const topicLabel = k => TOPICS[k] || k;   // the six fixed categories only
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
  if (file) return file.name.replace(/\.(pdf|md|txt)$/i, '');
  return topicLabel(topic);
}
/* Text sent to /api/generate-script as `topic` when no template was picked: the first prompt (cut at a word
   boundary near TOPIC_MAX_CHARS), else the file name without its extension, else the category name. */
export function freeTopicText(prompt, fileName, category) {
  const text = (prompt || '').replace(/^#+\s+/, '').replace(/\s+/g, ' ').trim();
  if (text) {
    const chars = Array.from(text);   // by code point, never splits an emoji
    if (chars.length <= TOPIC_MAX_CHARS) return text;
    const cut = chars.slice(0, TOPIC_MAX_CHARS).join(''), at = cut.lastIndexOf(' ');
    return (at > TOPIC_MAX_CHARS / 2 ? cut.slice(0, at) : cut).trim();
  }
  return (fileName || '').replace(/\.(pdf|md|txt)$/i, '').trim() || topicLabel(category);
}
export function renderBlockedBubble(ai) {
  ai.classList.add('blocked');
  ai.innerHTML = '<div class="who">' + IC.ai + '<span>' + esc(T('script.assistant')) + '</span></div>' +
    '<div class="row"><span class="pill bad">' + IC.alert + esc(T('script.blockedTag')) + '</span></div>' +
    '<h3 class="blk-t">' + esc(T('script.blockedTitle')) + '</h3>' +
    '<p>' + esc(T('script.blockedHarm')) + '</p>' +
    '<p class="note" style="margin-top:8px">' + esc(T('script.blockedNext')) + '</p>';
}
/* Error bubble; the text is set with textContent (it may come from the server). Only a failed script turn
   (ai._script.req) gets the retry button; a failed chat turn gives the typed text back (picking a topic is retried by clicking the card again). */
function renderErrorBubble(ai, text) {
  const retry = ai._script && ai._script.req;
  ai.innerHTML = '<div class="who">' + IC.ai + '<span>' + esc(T('script.assistant')) + '</span></div><p class="note"></p>' + (retry ? '<div class="acts"><button class="btn btn-sm" type="button" data-a="again"></button></div>' : '');
  $('.note', ai).textContent = text;
  if (retry) $('[data-a=again]', ai).textContent = T('script.regenerate');
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
  if (kind === 'file') {   // own message per error code (a server message is only the fallback); the typed text comes back
    const input = $('#composerInput');
    ai.remove(); showErr($('#composerError'), Object.hasOwn(FILE_ERR_TEXT, code) ? T(FILE_ERR_TEXT[code]) : (message || T('script.errFile')));
    if (!input.value.trim() && ai._sent) { input.value = ai._sent; fitComposer(); }
    return;
  }
  if (kind === 'blocked') { renderBlockedBubble(ai); openModal('safetyAlert'); revealBubble(ai); return; }
  if (kind === 'session') {
    const input = $('#composerInput'), draft = input.value, sent = ai._sent;
    toast(T('script.errSession'), true); startNewChat();
    input.value = draft.trim() ? draft : (sent || ''); fitComposer();   // keep the draft, else the request that was just sent
    if (ai._file) { S.chatFile = ai._file; renderChatFile(); }   // startNewChat dropped the attachment: give it back too
    return;
  }
  const scriptTurn = !!(ai._script && ai._script.req);
  if (!scriptTurn) giveBackDraft(ai);   // chat turn only: a script turn keeps its own Retry button
  /* The fallback says "writing your script" only for a script turn; a chat turn (topics, message) gets a neutral line */
  const text = Object.hasOwn(ERR_TEXT, kind) ? T(ERR_TEXT[kind]) : (message || T(scriptTurn ? 'script.errGeneric' : 'script.errChat'));   // fail-closed moderation never opens safetyAlert
  toast(text, true);
  renderErrorBubble(ai, text);
}
/* Skeleton bubble shown while a turn runs. `sent` is the text the person typed, kept so a session error can give it back. */
function loadingBubble(text, sent, file) {
  const ai = addBubble('ai', '<div class="skel" style="width:92%"></div><div class="skel" style="width:78%"></div><div class="skel" style="width:60%"></div><p class="note" role="status"></p>');
  $('.note', ai).textContent = text; ai._sent = sent; ai._file = file;
  return ai;
}
/* After a temporary failure: put the sent text and file back together, but only when the composer is still empty
   (text and file are one request: never mix new text with an old file or the other way round) */
function giveBackDraft(ai) {
  const input = $('#composerInput');
  if (input.value.trim() || S.chatFile) return;
  if (ai._sent) { input.value = ai._sent; fitComposer(); }
  if (ai._file) { S.chatFile = ai._file; renderChatFile(); }
}
/* `j.error` is read too because some routes answer {"error": "<code>"} instead of {"error_code": ...}. */
const errCode = j => j && (j.error_code || (typeof j.error === 'string' ? j.error : null));
/* One chat turn on the three chat routes (suggest / select-topic / message): same epoch, owner and AbortController
   rules as generateScript. A stale turn (New chat / other account) stays silent: no render, no busy flag. onOk(j) runs
   only for a current turn whose answer belongs to the open session; onFail() runs before the error is shown. */
function chatTurn(url, init, ai, onOk, onFail) {
  const ep = S.chatEpoch, owner = S.user, ctl = new AbortController();
  const stale = () => ep !== S.chatEpoch || S.user !== owner;
  const fail = (code, msg, httpStatus) => { if (stale()) return; setComposerBusy(false); if (onFail) onFail(); handleChatError(ai, code, msg, httpStatus); };
  S.chatAbort = ctl; setComposerBusy(true);
  api(url, Object.assign({}, init, { signal: ctl.signal })).then(readJson).then(({ ok, status, j }) => {
    if (stale()) return;
    /* GUESS, waiting for Member 2 to fix the code: a 404 without a code on a chat route means the session is gone (not used by the polling GET).
       Not for the first /suggest: there is no session yet, so a bare 404 there is a missing route, not an expired chat. */
    const goneSession = status === 404 && (url !== URL_SUGGEST || S.chatSessionId);
    if (!ok || !j) { fail(errCode(j) || (goneSession ? 'session_not_found' : null), j && j.message, status); return; }
    if (url !== URL_SUGGEST && j.session_id !== S.chatSessionId) { fail('session_mismatch', null); return; }   // answer for another session
    setComposerBusy(false); onOk(j);
  }).catch(() => fail('net', null));
}
export function generateScript(req, again) {
  const ep = S.chatEpoch, owner = S.user, ctl = new AbortController();
  /* New chat, logout or another login since this turn began. S.user is a new object on every login (and null after
     logout), so comparing the reference also catches logout then login of the same account. */
  const stale = () => ep !== S.chatEpoch || S.user !== owner;
  S.chatAbort = ctl; setComposerBusy(true);
  const ai = loadingBubble(again ? T('script.regenerating') : T('script.generating'), req.txt);
  ai._script = { req };
  /* req: sid = chat session, topic = category slug, tplId / tplTitle = picked template (empty when writing freely),
     genTopic = the `topic` field, txt / file = first prompt and file name (only used to name the script) */
  const fd = new FormData(), status = $('.note', ai);
  fd.append('session_id', req.sid);
  fd.append('topic', req.genTopic);
  fd.append('category', req.tplId ? req.topic : 'free');
  fd.append('duration_min', String(req.dur || 5));
  if (req.feedback) fd.append('user_feedback', req.feedback);
  else if (again) fd.append('user_feedback', 'Write a fresh variation of this speech.');
  /* A stale turn (New chat / other account) stays silent: no render, no busy flag. */
  const fail = (code, msg, httpStatus) => { if (!stale()) { setComposerBusy(false); handleChatError(ai, code, msg, httpStatus); } };
  const failFrom = (j, httpStatus) => fail(errCode(j), j && j.message, httpStatus);
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
    S.chatStage = 'generated'; setComposerBusy(false); revealBubble(ai);   // a failed run never reaches here, so it keeps the earlier stage
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
/* Validate a picked file by its extension (Windows often gives .md an empty MIME type, so type is not trusted).
   Returns {ok: true} or {ok: false, key: <i18n key of the message>}. */
export function validateChatFile(file) {
  const dot = file.name.lastIndexOf('.'), ext = dot < 0 ? '' : file.name.slice(dot).toLowerCase();
  if (!Object.hasOwn(FILE_LIMITS, ext)) return { ok: false, key: 'script.errFileType' };
  if (file.size > FILE_LIMITS[ext].max) return { ok: false, key: 'script.errFileBig' };
  if (file.size < FILE_LIMITS[ext].min) return { ok: false, key: 'script.errFileSmall' };
  return { ok: true };
}
/* #composerFileInput change handler (main.js binds it). The input is reset so picking the same file again still fires. */
export function onComposerFile(e) {
  const f = e.target.files && e.target.files[0]; e.target.value = '';
  if (!f) return;
  const v = validateChatFile(f);
  if (!v.ok) { showErr($('#composerError'), T(v.key)); return; }
  clearErr($('#composerError')); S.chatFile = { name: f.name, size: f.size, raw: f }; renderChatFile();
}
/* Step 1: ask for topic cards. While picking_topic, new text or a new file asks again and the new cards replace the old.
   depends on Member 2 confirming what session_id does on /suggest: the one line that sends it is marked below, so
   switching to another rule (for example dropping it) is a one-line change. */
function sendSuggest(txt, file) {
  const fd = new FormData(), ai = loadingBubble(T('script.extracting'), txt, file);
  fd.append('category', $('#composerTopic').value); fd.append('duration_min', $('#composerDuration').value);
  if (txt) fd.append('prompt', txt);
  if (file) fd.append('file', file.raw, file.name);
  if (S.chatSessionId) fd.append('session_id', S.chatSessionId);   // <- the session_id decision (Q11a)
  lockSetup(true);   // locked from the moment the values are read, so they cannot change while /suggest runs
  const unlock = () => { if (!S.chatSessionId) lockSetup(false); };   // a failed first /suggest leaves no session: unlock again
  chatTurn(URL_SUGGEST, { method: 'POST', body: fd }, ai, j => {
    if (!j.session_id) { unlock(); handleChatError(ai, 'bad_response', null); return; }
    const old = S.chatSeed || {}, list = Array.isArray(j.suggestions) ? j.suggestions.filter(t => t && t.template_id && t.topic) : [];
    S.chatSessionId = j.session_id; S.chatStage = 'picking_topic'; lockSetup(true); setSessionFiles(j.files_loaded);
    S.chatSeed = { prompt: txt || old.prompt || '', fileName: file ? file.name : old.fileName || '' };
    if (S.chatCards) S.chatCards.remove();
    S.chatCards = ai; renderTopicCards(ai, list, j.recommend_free_topic === true);
  }, unlock);
}
function topicButton(tpl, title, meta, primary) {
  const b = document.createElement('button'), t = document.createElement('span');
  b.type = 'button'; b.className = 'btn tcard' + (primary ? ' btn-primary' : ''); b.setAttribute('data-a', 'topic'); b._tpl = tpl;
  t.className = 'tc-t'; t.textContent = title; b.appendChild(t);
  if (meta) { const m = document.createElement('span'); m.className = 'tc-m'; m.textContent = meta; b.appendChild(m); }
  return b;
}
/* One button per suggestion (as many as the server sent) plus Write freely, which is the primary button when recommended */
function renderTopicCards(ai, list, recommendFree) {
  ai.innerHTML = '<div class="who">' + IC.ai + '<span>' + esc(T('script.assistant')) + '</span></div><p class="note"></p><div class="tcards"></div>';
  $('.note', ai).textContent = T(list.length ? 'script.pickTopic' : 'script.noTopics');
  const box = $('.tcards', ai);
  list.forEach(t => box.appendChild(topicButton({ template_id: t.template_id, topic: t.topic }, t.topic, t.duration_min ? t.duration_min + ' ' + T('script.min') : '')));
  box.appendChild(topicButton({ template_id: null, topic: null }, T('script.writeFreely'), '', recommendFree));
  revealBubble(ai);
}
/* Step 2: the clicked card locks every card at once (no double click, no second pick); a failed call unlocks them again. */
function pickTopic(btn) {
  if (S.chatBusy || S.chatStage !== 'picking_topic') return;
  const all = $$('[data-a=topic]', btn.closest('.tcards')), tpl = btn._tpl, ai = loadingBubble(T('script.thinking'), '');
  all.forEach(x => { x.disabled = true; }); btn.classList.add('picked'); btn.setAttribute('aria-pressed', 'true');
  chatTurn(URL_SELECT, { method: 'POST', json: { session_id: S.chatSessionId, template_id: tpl.template_id } }, ai, j => {
    S.selectedTemplate = tpl; S.chatStage = 'gathering'; renderGatherBubble(ai, j);
  }, () => { all.forEach(x => { x.disabled = false; }); btn.classList.remove('picked'); btn.removeAttribute('aria-pressed'); });
}
/* reply_message plus the always-visible Generate Script button (primary only when the server says ready_to_generate) */
function renderGatherBubble(ai, j) {
  ai.innerHTML = '<div class="who">' + IC.ai + '<span>' + esc(T('script.assistant')) + '</span></div><p class="reply"></p><div class="acts"><button class="btn btn-sm" type="button" data-a="generate"></button></div>';
  $('.reply', ai).textContent = j.reply_message || '';
  const g = $('[data-a=generate]', ai); g.textContent = T('script.generate'); g.classList.toggle('btn-primary', j.ready_to_generate === true);
  revealBubble(ai);
}
/* Step 3 (and a message after a script, which goes back to gathering): never writes a script, only updates chips and reply */
function sendMessage(txt, file) {
  const fd = new FormData(), ai = loadingBubble(T('script.extracting'), txt, file);
  fd.append('session_id', S.chatSessionId);
  if (txt) fd.append('message', txt);
  if (file) fd.append('file', file.raw, file.name);
  chatTurn(URL_MESSAGE, { method: 'POST', body: fd }, ai, j => { S.chatStage = 'gathering'; setSessionFiles(j.files_loaded); renderGatherBubble(ai, j); });
}
/* Step 4: Generate Script button or keyword. `topic` is the template id when one was picked, else the free-topic text;
   `category` is always the slug chosen in the Category select. */
function startGenerate() {
  if (S.chatBusy || (S.chatStage !== 'gathering' && S.chatStage !== 'generated')) return;
  const sel = S.selectedTemplate || { template_id: null, topic: null }, seed = S.chatSeed || {}, category = $('#composerTopic').value;
  const req = { sid: S.chatSessionId, topic: category, tplId: sel.template_id, tplTitle: sel.topic || '', dur: +$('#composerDuration').value || 5,
    genTopic: sel.template_id || freeTopicText(seed.prompt, seed.fileName, category), txt: seed.prompt || '', file: seed.fileName ? { name: seed.fileName } : null };
  S.lastReq = req;
  generateScript(req, false);
}
export function sendChat() {
  if (S.chatBusy) return;
  const txt = $('#composerInput').value.trim(), err = $('#composerError'), file = S.chatFile;
  if (!txt && !file) return;
  if (wordsOf(txt) > 3000) { showErr(err, T('script.errLong')); return; }
  clearErr(err);
  const me = addBubble('me', '<span></span>');
  me.firstChild.textContent = [txt, file ? '📎 ' + file.name : ''].filter(Boolean).join('\n');
  $('#composerInput').value = ''; S.chatFile = null; renderChatFile();
  S.composerFolded = false; fitComposer();   // back to one short line
  const talking = S.chatStage === 'gathering' || S.chatStage === 'generated';
  if (talking && !file && GENERATE_KEYWORDS.has(txt.normalize('NFC').toLowerCase())) startGenerate();
  else if (talking) sendMessage(txt, file);
  else sendSuggest(txt, file);   // idle, or picking_topic (asks again, see sendSuggest)
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
  const a = b.getAttribute('data-a');
  if (a === 'topic') { pickTopic(b); return; }
  if (a === 'generate') { startGenerate(); return; }
  const sc = b.closest('.bubble')._script;
  if (!sc) return;
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
    if (S.chatBusy) return;
    if (!sc.text) { generateScript(sc.req, true); return; }   // failed turn retry button: run right away
    const bubble = b.closest('.bubble');
    let box = $('.regen-box', bubble);
    if (!box) {
      box = document.createElement('div');
      box.className = 'row regen-box'; box.style.marginTop = '10px';
      box.innerHTML = '<input type="text" class="regen-in" style="flex:1;min-width:180px"><button class="btn btn-primary btn-sm" type="button" data-a="regen-go"></button>';
      const inp = $('.regen-in', box), goBtn = $('[data-a=regen-go]', box);
      inp.placeholder = T('script.regenPlaceholder'); inp.setAttribute('aria-label', T('script.regenPlaceholder'));
      goBtn.textContent = T('script.regenConfirm');
      inp.addEventListener('keydown', ev => { if (ev.key === 'Enter') { ev.preventDefault(); goBtn.click(); } });
      bubble.appendChild(box);
    } else box.hidden = !box.hidden;
    if (!box.hidden) $('.regen-in', box).focus();
  } else if (a === 'regen-go') {
    if (S.chatBusy) return;
    const bubble = b.closest('.bubble'), inp = $('.regen-in', bubble), fb = inp ? inp.value.trim() : '';
    generateScript(Object.assign({}, sc.req, { feedback: fb }), true);
  }
}
RENDER.scriptStudio = function () {
  fillTopicSelect();
  $('#chatResetBtn').onclick = () => startNewChat();   // property, not addEventListener: running RENDER again never stacks handlers
  if (S.user && S.user !== S.chatOwner) { startNewChat(); S.chatOwner = S.user; }   // new login (any account) without F5: no chat carry-over
};
