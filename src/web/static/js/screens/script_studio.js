import { api, readJson } from '../api.js';
import { T, TOPICS } from '../i18n.js';
import { go } from '../nav.js';
import { loadSavedScripts } from '../screens/practice.js';
import { RENDER, S } from '../state.js';
import { openModal, toast } from '../ui.js';
import { $, $$, IC, clearErr, esc, showErr, wordsOf } from '../utils.js';

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
  return api('/api/scripts', { method: 'POST', json: {
    title: (sc.title || 'Script').slice(0, 200), body: sc.text, source: SCRIPT_SOURCE[sc.source] || 'written',
    duration_min: SCRIPT_DURATIONS.indexOf(d) >= 0 ? d : null, topic: sc.title ? sc.title.slice(0, 200) : null,
    category: sc.topic || null, template_id: sc.template_id || null, models_used: sc.models_used || [], citations: sc.citations || []
  } }).then(readJson).then(({ ok, j }) => {
    if (!ok) throw Object.assign(new Error('save'), { code: j && j.error_code, msg: j && j.message });
    sc.savedId = j.id;
    return j;
  });
}
export function syncTplSelect() {
  const cat = $('#composerTopic').value, tplSel = $('#chatTpl'), durSel = $('#composerDuration');
  if (!tplSel || !durSel) return;
  const list = (S.apiTopics || []).filter(t => t.category_slug === cat);
  tplSel.innerHTML = '<option value="">Custom topic (LLM)</option>' + list.map(t => '<option value="' + esc(t.template_id) + '">' + esc((t.topic || t.title) + ' (' + t.duration_min + 'm)') + '</option>').join('');
  tplSel.value = list.length ? list[0].template_id : '';
  tplSel.disabled = cat === 'free' || !list.length;
  syncDurLock();
}
export function syncDurLock() {
  const tplSel = $('#chatTpl'), durSel = $('#composerDuration');
  if (!tplSel || !durSel) return;
  const tpl = (S.apiTopics || []).find(t => t.template_id === tplSel.value);
  if (tpl) { durSel.value = String(tpl.duration_min); durSel.disabled = true; }
  else durSel.disabled = false;
}
export function fillTopicSelect() {
  const sel = $('#composerTopic'), keep = sel.value;
  if (!S.apiTopics) {
    fetch('/api/topics').then(r => r.ok ? r.json() : null).then(d => {
      if (d && d.topics) { S.apiTopics = d.topics; S.apiCategories = d.categories || []; fillTopicSelect(); }
    }).catch(() => {});
  }
  const keys = Object.keys(CAT_LABELS);
  sel.innerHTML = keys.map(k => '<option value="' + k + '">' + esc(topicLabel(k)) + '</option>').join('');
  if (keep && keys.indexOf(keep) >= 0) sel.value = keep;
  syncTplSelect();
}
export function addBubble(cls, html) {
  const feed = $('#chatFeed'), d = document.createElement('div');
  d.className = 'bubble ' + cls;
  if (cls === 'ai') d.innerHTML = '<div class="who">' + IC.ai + '<span>' + esc(T('script.assistant')) + '</span></div>' + html;
  else d.innerHTML = html;
  feed.appendChild(d);
  /* Chat-style entry: the feed glides down to the new message while it rises and fades in */
  const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (!calm && d.animate && feed.offsetParent) {
    feed.scrollTo({ top: feed.scrollHeight, behavior: 'smooth' });
    d.animate([{ opacity: 0, transform: 'translateY(24px) scale(.98)' }, { opacity: 1, transform: 'none' }],
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
    if (code === 'invalid_pdf' || code === 'no_text_layer') { ai.remove(); showErr($('#composerError'), msg || T('script.errFile')); return; }
    if (code === 'content_rejected') { renderBlockedBubble(ai); openModal('safetyAlert'); revealBubble(ai); return; }
    toast(msg || T('eval.errServer'), true);
    ai.innerHTML = '<div class="who">' + IC.ai + '<span>' + esc(T('script.assistant')) + '</span></div><p class="note">' + esc(msg || T('eval.errServer')) + '</p><div class="acts"><button class="btn btn-sm" type="button" data-a="again">' + esc(T('script.regenerate')) + '</button></div>';
    ai._script = { req }; revealBubble(ai);
  };
  const poll = id => api('/api/generate-script/' + id).then(r => r.json().then(j => ({ ok: r.ok, j }))).then(({ ok, j }) => {
    if (!ok || !j || j.status === 'failed') { failJob(j && j.error_code, j && j.message); return; }
    if (j.status !== 'completed') {
      status.textContent = (j.status === 'extracting' ? T('script.extracting') : j.status === 'moderating' ? T('script.checking') : T('script.generating')) + ' (' + (j.progress || 0) + '%)';
      setTimeout(() => poll(id), 650); return;
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
    S.chatBusy = false; $('#composerSend').disabled = false; revealBubble(ai);
  }).catch(() => failJob('net', T('eval.errNet')));
  api('/api/generate-script', { method: 'POST', body: fd }).then(r => r.json().then(j => ({ ok: r.ok, j }))).then(({ ok, j }) => {
    if (!ok || !j || !j.job_id) { failJob(j && j.error_code, j && j.message); return; }
    poll(j.job_id);
  }).catch(() => failJob('net', T('eval.errNet')));
}
export function sendChat() {
  if (S.chatBusy) return;
  const txt = $('#composerInput').value.trim(), err = $('#composerError'), tplId = $('#chatTpl') ? $('#chatTpl').value : '';
  const tpl = (S.apiTopics || []).find(t => t.template_id === tplId);
  if (!txt && !S.chatFile && !tplId) return;
  if (wordsOf(txt) > 3000) { showErr(err, T('script.errLong')); return; }
  clearErr(err);
  const tplName = tpl ? (tpl.topic || tpl.title) : '';
  const req = { txt, file: S.chatFile, topic: $('#composerTopic').value, tplId, tplTitle: tplName, dur: +($('#composerDuration') && $('#composerDuration').value || 5) };
  const me = addBubble('me', '<span></span>');
  me.firstChild.textContent = [tplName ? '📄 ' + tplName : '', txt, S.chatFile ? '📎 ' + S.chatFile.name : ''].filter(Boolean).join('\n');
  $('#composerInput').value = ''; S.chatFile = null; renderChatFile();
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
RENDER.scriptStudio = function () { fillTopicSelect(); };
