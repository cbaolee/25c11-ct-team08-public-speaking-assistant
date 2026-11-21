import { api, readJson } from '../api.js';
import { T } from '../i18n.js';
import { requireConsent, startRecorder } from '../recorder.js';
import { CONFIG, S } from '../state.js';
import { fmtTime } from '../utils.js';
import { EXT_BY_MIME, practiceLocked } from './practice.js';
import { PA, hasAudio, stopPlayback } from './report.js';

const ACCENT_LANG = { 'American English': 'en-US', 'British English': 'en-GB' };
let anchor = null, session = null, recorder = null, request = null, clipStop = null, voiceListener = null, generation = 0;
const panel = () => document.getElementById('wordCoach');
const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
function lock(on) {
  document.querySelectorAll('#playBtn, #seek, #recBtn, #profileBaselineStart, #profileBaselineAgain').forEach(n => { if (on) { n.dataset.wcDisabled = String(n.disabled); n.disabled = true; } else if (n.dataset.wcDisabled != null) { n.disabled = n.dataset.wcDisabled === 'true'; delete n.dataset.wcDisabled; } });
}
function detachClip() { if (PA) { if (clipStop) PA.removeEventListener('timeupdate', clipStop); PA.removeEventListener('playing', attachClip); PA.removeEventListener('pause', detachClip); PA.removeEventListener('ended', detachClip); } clipStop = null; }
function attachClip() { PA.addEventListener('pause', detachClip, { once: true }); PA.addEventListener('ended', detachClip, { once: true }); }
function stopClip() { detachClip(); if (PA && !PA.paused) PA.pause(); }
export function closeWordCoach(focus = true) {
  const p = panel(); if (!p || p.hidden) return;
  generation++; if (recorder) recorder.cancel(); recorder = null; if (request) request.abort(); request = null;
  lock(false); stopClip(); if (window.speechSynthesis) { if (voiceListener) window.speechSynthesis.removeEventListener('voiceschanged', voiceListener); window.speechSynthesis.cancel(); } voiceListener = null;
  p.hidden = true; if (focus && anchor && anchor.isConnected) anchor.focus({ preventScroll: true }); anchor = null; session = null;
}
function place() {
  const p = panel(); if (!anchor || p.hidden || innerWidth <= 640) return;
  const r = anchor.getBoundingClientRect(), box = p.getBoundingClientRect(), gap = 8;
  p.style.left = Math.max(gap, Math.min(r.left, innerWidth - box.width - gap)) + 'px';
  p.style.top = Math.max(gap, Math.min(r.bottom + gap + box.height <= innerHeight ? r.bottom + gap : r.top - box.height - gap, innerHeight - box.height - gap)) + 'px';
}
function bounds(words, word) {
  const pad = CONFIG.RETRY.clipPad;
  if (word && word.start == null && word.end == null) {
    const all = session.an.words, pos = all.indexOf(word);
    const prev = all.slice(0, pos).reverse().find(w => w.end != null), next = all.slice(pos + 1).find(w => w.start != null);
    if (!prev && !next) return null;
    return [Math.max(0, (prev ? prev.end : next.start) - pad), (next ? next.start : prev.end) + pad];
  }
  const timed = words.filter(w => w.start != null && w.end != null);
  return timed.length ? [Math.max(0, timed[0].start - pad), timed[timed.length - 1].end + pad] : null;
}
function open(words, kind, target, clicked, word) {
  closeWordCoach(false); session = S.currentSession; anchor = clicked; const token = ++generation, p = panel();
  p.replaceChildren(); p.hidden = false; p.style.left = ''; p.style.top = '';
  const close = el('button', 'wc-close', '×'); close.type = 'button'; close.setAttribute('aria-label', T('wc.closeLabel')); close.onclick = () => closeWordCoach(); p.append(close);
  const title = el('h2', 'wc-title', target); title.id = 'wcTitle'; p.append(title);
  if (word && word.status === 'wrong' && word.hypWord) p.append(el('p', 'wc-heard', T('wc.heardAs', { x: word.hypWord })));
  const actions = el('div', 'wc-actions'), hear = el('button', 'btn btn-sm btn-ghost', T('wc.hearIt')), self = el('button', 'btn btn-sm btn-ghost', T('wc.hearYourself')), retry = el('button', 'btn btn-sm btn-primary', T('wc.tryAgain'));
  [hear, self, retry].forEach(b => { b.type = 'button'; actions.append(b); }); p.append(actions);
  const timer = el('span', 'wc-timer'); p.append(timer);
  const result = el('div', 'wc-result'); result.setAttribute('aria-live', 'polite'); p.append(result);
  const voiceNote = el('p', 'wc-note', T('wc.sampleVoice')), noVoice = el('p', 'wc-note', T('wc.noVoice')); p.append(voiceNote, noVoice, el('p', 'wc-note', T('wc.practiceOnly')));
  const lvl = el('div', 'wc-level'); for (let i = 0; i < 5; i++) lvl.append(el('i')); p.append(lvl);
  let voice = null; const synth = window.speechSynthesis;
  const updateVoices = () => { if (token !== generation) return; const voices = synth ? synth.getVoices() : [], lang = ACCENT_LANG[S.currentSession.accent || S.profile?.accent] || 'en-US'; voice = voices.find(v => v.lang.toLowerCase() === lang.toLowerCase()) || voices.find(v => v.lang.toLowerCase().startsWith('en')); hear.hidden = !voice; voiceNote.hidden = !voice; noVoice.hidden = !!voice; };
  updateVoices(); if (synth) { voiceListener = updateVoices; synth.addEventListener('voiceschanged', voiceListener); }
  hear.onclick = () => { if (!voice) return; stopClip(); synth.cancel(); const u = new SpeechSynthesisUtterance(target); u.voice = voice; u.lang = voice.lang; synth.speak(u); };
  const range = bounds(words, word); self.hidden = !session.audioUrl || session.compact || !range || !hasAudio();
  self.onclick = () => { stopClip(); stopPlayback(); if (synth) synth.cancel(); PA.currentTime = range[0]; clipStop = () => { if (PA.currentTime >= range[1]) stopClip(); }; PA.addEventListener('timeupdate', clipStop); PA.addEventListener('playing', attachClip, { once: true }); PA.play().catch(stopClip); };
  const setResult = (text, state) => { result.className = 'wc-result' + (state ? ' wc-' + state : ''); result.textContent = text; place(); };
  const idle = () => { retry.disabled = false; retry.className = 'btn btn-sm btn-primary'; retry.textContent = T('wc.tryAgain'); timer.textContent = ''; };
  retry.onclick = () => {
    if (recorder) { recorder.stop(false); return; }
    if (practiceLocked()) return;   // no new recording while an evaluation runs in the background
    requireConsent(() => {
      if (token !== generation || session !== S.currentSession || p.hidden) return;
      stopPlayback(); stopClip(); if (synth) synth.cancel(); lock(true); setResult('');
      const max = kind === 'word' ? CONFIG.RETRY.wordMax : CONFIG.RETRY.sentenceMax;
      retry.className = 'btn btn-sm btn-record'; retry.textContent = T('wc.stop'); timer.textContent = T('wc.timer', { elapsed: fmtTime(0), max: fmtTime(max) });
      recorder = startRecorder({ lvl, max, onTick: sec => { timer.textContent = T('wc.timer', { elapsed: fmtTime(sec), max: fmtTime(max) }); }, onError: () => { recorder = null; lock(false); idle(); setResult(T('wc.errMic'), 'bad'); }, onEnd: async (_sec, _auto, rec) => {
        recorder = null; lock(false); retry.disabled = true; retry.className = 'btn btn-sm btn-primary'; retry.textContent = T('wc.checking'); retry.classList.add('wc-checking'); timer.textContent = '';
        if (!rec.blob || !rec.blob.size) { idle(); setResult(T('wc.notHeard'), 'bad'); return; }
        const fd = new FormData(); fd.append('audio', rec.blob, 'retry' + (EXT_BY_MIME[(rec.mime || '').split(';')[0]] || '.webm')); fd.append('target_text', target); fd.append('kind', kind); request = new AbortController();
        try {
          const response = await readJson(await api('/api/practice/retry', { method: 'POST', body: fd, signal: request.signal }));
          if (token !== generation) return;
          if (!response.ok || !response.j) { setResult(T(response.status === 429 ? 'wc.errRate' : response.status === 503 ? 'wc.errStt' : 'wc.errNet'), 'bad'); }
          else { const j = response.j, key = { correct: 'recognised', close: 'close', not_yet: 'heard', not_heard: 'notHeard' }[j.verdict] || 'notHeard'; setResult(T('wc.' + key, { x: j.heard_text || '', y: j.heard_text || '' }), j.verdict === 'correct' ? 'ok' : j.verdict === 'close' ? 'warn' : 'bad'); if (kind === 'sentence' && j.words) { const wrong = j.words.filter(w => w.status !== 'equal').map(w => w.ref_word).filter(Boolean); if (wrong.length) { result.append(el('div', 'wc-wrong-list', T('wc.stillWrong', { x: wrong.join(', ') }))); place(); } } }
        } catch (e) { if (token === generation) setResult(T('wc.errNet'), 'bad'); } finally { if (token === generation) { request = null; idle(); } }
      } });
    });
  };
  place(); close.focus({ preventScroll: true });
}
export function openWordCoach(i, clicked) { const s = S.currentSession, w = s && s.an.words.find(x => x.i === i); if (!w || !['wrong', 'near', 'missing'].includes(w.status)) return; open([w], 'word', w.raw.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, ''), clicked, w); }
export function openSentenceCoach(si, clicked) { const s = S.currentSession, words = s && s.an.words.filter(w => w.si === si).sort((a, b) => a.i - b.i); if (words && words.length) open(words, 'sentence', words.map(w => w.raw).join(' '), clicked); }
document.addEventListener('keydown', e => { if (e.key === 'Escape' && panel() && !panel().hidden && !S.modal.length) { e.preventDefault(); closeWordCoach(); } });
document.addEventListener('click', e => { const p = panel(); if (p && !p.hidden && !recorder && !p.contains(e.target) && !(anchor && anchor.contains(e.target)) && !e.target.closest('#consentModal')) closeWordCoach(); });
window.addEventListener('resize', place); window.addEventListener('scroll', place, { passive: true, capture: true });
new MutationObserver(() => { if (session && (S.currentSession !== session || S.screen !== 'report' || S.view !== 'app')) closeWordCoach(false); }).observe(document.documentElement, { attributes: true, subtree: true, attributeFilter: ['class', 'hidden'] });
