import { S } from './state.js';
import { openModal } from './ui.js';
import { $$ } from './utils.js';

/* ---------- recorder helper (real microphone: getUserMedia + MediaRecorder + AnalyserNode) ---------- */
/* levelAnim(lvlEl, stream): level bars driven by the real mic level (RMS per slice of the waveform).
   With no `stream` it opens the mic itself (Profile mic test) and closes its own tracks on stop. */
export function levelAnim(lvlEl, stream, onErr) {
  const bars = $$('i', lvlEl);
  let ctx = null, iv = null, own = null, stopped = false;
  const attach = st => {
    if (stopped) { if (own) own.getTracks().forEach(t => t.stop()); return; }
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      ctx = new AC();
      if (ctx.state === 'suspended') ctx.resume();
      const an = ctx.createAnalyser(); an.fftSize = 1024;
      ctx.createMediaStreamSource(st).connect(an);   // not connected to destination: no echo
      const buf = new Uint8Array(an.fftSize), seg = Math.floor(buf.length / bars.length);
      lvlEl.classList.add('live');
      iv = setInterval(() => {
        an.getByteTimeDomainData(buf);
        bars.forEach((b, k) => {
          let s = 0;
          for (let i = k * seg; i < (k + 1) * seg; i++) { const d = (buf[i] - 128) / 128; s += d * d; }
          const lv = Math.min(1, Math.sqrt(s / seg) * 5);
          b.style.height = (4 + 34 * lv * (0.4 + 0.6 * Math.sin((k + 1) / (bars.length + 1) * Math.PI))) + 'px';
        });
      }, 70);
    } catch (e) { /* no AudioContext: bars stay idle, recording itself is unaffected */ }
  };
  if (stream) attach(stream);
  else if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    navigator.mediaDevices.getUserMedia({ audio: true }).then(st => { own = st; attach(st); }).catch(e => { if (!stopped && onErr) onErr(e); });
  } else if (onErr) Promise.resolve().then(() => { if (!stopped) onErr({ name: 'unsupported' }); });
  return () => {
    stopped = true; clearInterval(iv);
    if (own) own.getTracks().forEach(t => t.stop());
    if (ctx && ctx.state !== 'closed') ctx.close().catch(() => { });
    lvlEl.classList.remove('live'); bars.forEach(b => { b.style.height = ''; });
  };
}
/* startRecorder(o) -> {stop, cancel} returned synchronously; the mic opens asynchronously.
   o.onTick(sec) · o.onEnd(sec, auto, {blob, mime}) fires after the Blob is ready · o.onError('denied'|'nodevice'|'unsupported').
   Baseline and practice recordings both go through this one function, so they share one capture chain (browser defaults,
   no extra signal-processing constraints). */
export function startRecorder(o) {
  const MIMES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'];
  let stream = null, mr = null, t0 = 0, tickIv = null, stopLvl = null, pausedMs = 0, pausedAt = 0;
  const elapsed = () => (Date.now() - t0 - pausedMs - (pausedAt ? Date.now() - pausedAt : 0)) / 1000;   // seconds recorded, pauses left out
  const chunks = [];
  const release = () => {
    clearInterval(tickIv);
    if (stopLvl) { stopLvl(); stopLvl = null; }
    if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
  };
  const r = {
    done: false,
    stop(auto) {
      if (r.done) return; r.done = true; r.auto = !!auto;
      if (mr && mr.state !== 'inactive') mr.stop();            // onstop -> release() + onEnd with the Blob
      else { release(); o.onEnd(0, !!auto, { blob: null, mime: '' }); }   // stopped before the mic was ready
    },
    paused: false,
    pause() {                        // keeps the mic open; time and the follow-along stop until resume()
      if (r.done || r.paused || !mr || mr.state !== 'recording') return;
      mr.pause(); pausedAt = Date.now(); r.paused = true;
    },
    resume() {
      if (r.done || !r.paused || !mr) return;
      mr.resume(); pausedMs += Date.now() - pausedAt; pausedAt = 0; r.paused = false;
    },
    cancel() {                       // abort without calling onEnd (log out, leaving the page)
      if (r.done) return; r.done = true; r.cancelled = true;
      if (mr && mr.state !== 'inactive') mr.stop(); else release();
    }
  };
  const fail = err => {
    if (r.done) return; r.done = true; release();
    const n = err && err.name;
    const code = n === 'NotAllowedError' || n === 'SecurityError' ? 'denied' : n === 'unsupported' ? 'unsupported' : 'nodevice';
    if (o.onError) o.onError(code, err);
  };
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || typeof MediaRecorder === 'undefined') {
    Promise.resolve().then(() => fail({ name: 'unsupported' }));   // async so the caller has stored the handle first
    return r;
  }
  navigator.mediaDevices.getUserMedia({ audio: true }).then(st => {
    if (r.done) { st.getTracks().forEach(t => t.stop()); return; }   // stop/cancel arrived before the mic was ready
    stream = st;
    try {
      const mime = MIMES.find(m => MediaRecorder.isTypeSupported(m));
      const opt = { audioBitsPerSecond: 32000 }; if (mime) opt.mimeType = mime;
      mr = new MediaRecorder(st, opt);
      mr.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
      mr.onstop = () => {
        release();
        if (r.cancelled) return;
        const type = mr.mimeType || mime || '';
        o.onEnd(Math.round(elapsed() * 10) / 10, !!r.auto, { blob: new Blob(chunks, { type }), mime: type });
      };
      stopLvl = levelAnim(o.lvl, st);
      t0 = Date.now(); mr.start();
      tickIv = setInterval(() => { if (r.paused) return; const s = elapsed(); o.onTick(s); if (o.max && s >= o.max) r.stop(true); }, 200);
    } catch (e) { fail({ name: 'unsupported' }); }
  }).catch(fail);
  return r;
}
export function requireConsent(cb) {
  if (S.consent) { cb(); return; }
  S.afterConsent = cb; openModal('consentModal');
}
