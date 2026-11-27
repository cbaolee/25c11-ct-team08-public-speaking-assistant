const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const client = require('../../src/web/static/js/evaluate_client.js');

const BACKGROUND_MS = 5000;   // CONFIG.EVALUATE_BACKGROUND_AFTER_MS in the harness
const COUNT_MS = 30;          // CONFIG.EVAL_COUNT_STEP_MS in the harness
const HOLD_MS = 3000;         // CONFIG.EVAL_DOCK_HOLD_MS in the harness

function harness(replies) {
  const source = fs.readFileSync('src/web/static/js/screens/practice.js', 'utf8');
  const code = source.slice(source.indexOf('export function cancelEval()'), source.indexOf('export function finishEvalReal')).replaceAll('export ', '');
  const nodes = new Map(), calls = [], timers = [], intervals = [], errors = [], finished = [], closed = [], dialogs = [], screens = [];
  const node = () => ({ textContent: '', innerHTML: '', hidden: false, offsetWidth: 0, style: {}, dataset: {}, attrs: {}, classes: new Set(),
    setAttribute(k, v) { this.attrs[k] = v; },
    get classList() { const c = this.classes; return { add: (...x) => x.forEach(n => c.add(n)), remove: (...x) => x.forEach(n => c.delete(n)), contains: n => c.has(n), toggle: (n, on) => (on ? c.add(n) : c.delete(n)) }; } });
  const $ = key => { if (!nodes.has(key)) nodes.set(key, node()); return nodes.get(key); };
  const ctx = { S: { audio: { kind: 'file', name: 'a.wav', file: 'audio' } },
    CONFIG: { EVALUATE_BACKGROUND_AFTER_MS: BACKGROUND_MS, EVAL_COUNT_STEP_MS: COUNT_MS, EVAL_DOCK_HOLD_MS: HOLD_MS, EVAL_JOB: { pollMs: 700, maxWaitS: 360, weights: {}, tauS: 20, closeDelayMs: 400, announcePct: 25 } },
    EvaluateClient: client, AbortController, Date, encodeURIComponent,
    FormData: class { append() {} }, $, $$: sel => sel.includes('#evBar') ? [$('#evBar'), $('#evDockBar')] : [], T: (x) => x, openModal() {}, closeModal(...args) { closed.push(args); }, toast() {}, openBaselineGate() {}, showEvalError: null,
    openConfirmDialog: (...args) => dialogs.push(args), go: name => screens.push(name), safeRun: fn => fn(),
    setTimeout: (fn, ms) => { const t = { fn, ms }; timers.push(t); return t; }, clearTimeout: t => { if (t) t.cleared = true; },
    setInterval: (fn, ms) => { const t = { fn, ms }; intervals.push(t); return t; }, clearInterval: t => { if (t) t.cleared = true; },
    matchMedia: () => ({ matches: true }),
    finishEvalReal: (...args) => finished.push(args), api: (url, opts = {}) => { calls.push([url, opts.method || 'GET', opts]); const reply = replies.shift(); return Promise.resolve(reply).then(r => ({ status: r.status, ok: r.status < 400, json: () => Promise.resolve(r.body) })); } };
  vm.createContext(ctx); vm.runInContext(code, ctx); ctx.showEvalError = msg => errors.push(msg);
  const tick = (n = 1) => { const t = intervals.at(-1); for (let i = 0; i < n && !t.cleared; i++) t.fn(); };
  const poll = () => timers.filter(t => t.ms === 700 && !t.cleared).at(-1).fn();
  return { ctx, calls, timers, errors, finished, nodes, closed, dialogs, screens, tick, poll };
}
const flush = () => new Promise(resolve => setImmediate(resolve));
const running = (progress, stage) => ({ status: 200, body: { status: 'running', progress, stage, stages: [{ key: stage, state: 'running' }] } });

test('202 job polls without overlap and passes the completed result once the count reaches 100', async () => {
  const h = harness([{ status: 202, body: { job_id: 'id' } }, running(5, 'vad'), { status: 200, body: { status: 'done', progress: 100, stages: [], result: { value: 1 } } }]);
  h.ctx.runEvalReal({ text: 'hello' }); await flush();
  assert.deepEqual(h.calls.map(x => x[1]), ['POST', 'GET']);
  h.poll(); await flush();
  assert.equal(h.finished.length, 0);   // still counting up
  h.tick(120);
  h.timers.find(t => t.ms === 0).fn();
  assert.equal(h.finished[0][0].value, 1);
  assert.equal(h.finished[0][2], false);
});

test('the shown percent counts up one step per tick and the bar follows it', async () => {
  const h = harness([{ status: 202, body: { job_id: 'id' } }, running(3, 'vad'), running(15, 'vad')]);
  h.ctx.runEvalReal({ text: 'hello' }); await flush();
  h.tick(3);
  assert.equal(h.nodes.get('#evDockPercent').textContent, '3%');
  h.poll(); await flush();
  const seen = [];
  for (let i = 0; i < 20; i++) { h.tick(); seen.push(h.nodes.get('#evDockPercent').textContent); }
  assert.deepEqual(seen.slice(0, 12), ['4%', '5%', '6%', '7%', '8%', '9%', '10%', '11%', '12%', '13%', '14%', '15%']);
  assert.equal(seen.at(-1), '15%');
  assert.equal(h.nodes.get('#evDockBar').style.width, undefined);   // bars are styled through their .ev-fill child
  assert.equal(h.nodes.get('.ev-fill').style.width, '15%');
});

test('after the delay the evaluation moves to the dock, sends the user Home and finishes in a pop-up', async () => {
  const h = harness([{ status: 202, body: { job_id: 'id' } }, running(20, 'stt'), { status: 200, body: { status: 'done', progress: 100, stages: [], result: { value: 2 } } }]);
  h.ctx.runEvalReal({ text: 'hello' }); await flush();
  h.timers.find(t => t.ms === BACKGROUND_MS).fn();
  assert.equal(h.ctx.S.evaluation.background, true);
  assert.deepEqual(h.screens, ['home']);
  assert.equal(h.dialogs[0][0], 'eval.bgT');
  assert.equal(h.nodes.get('#evDock').hidden, false);
  h.poll(); await flush();
  h.tick(120);
  assert.equal(h.finished[0][2], true);
  assert.equal(h.ctx.S.evaluation, null);
  const hold = h.timers.find(t => t.ms === HOLD_MS);
  assert.ok(hold);
  hold.fn();   // reduced motion in the harness: removed at once
  assert.equal(h.nodes.get('#evDock').hidden, true);
});

test('a finished evaluation does not move to the background', async () => {
  const h = harness([{ status: 202, body: { job_id: 'id' } }, { status: 200, body: { status: 'done', progress: 100, stages: [], result: {} } }]);
  h.ctx.runEvalReal({ text: 'hello' }); await flush();
  h.timers.find(t => t.ms === BACKGROUND_MS).fn();
  assert.equal(h.ctx.S.evaluation.background, false);
  assert.deepEqual(h.screens, []);
});

test('cancel deletes the job and prevents further polling', async () => {
  const h = harness([{ status: 202, body: { job_id: 'id' } }, { status: 200, body: { status: 'running', stages: [] } }, { status: 200, body: {} }]);
  h.ctx.runEvalReal({ text: 'hello' }); await flush(); h.ctx.cancelEval(); await flush();
  assert.deepEqual(h.calls.map(x => x[1]), ['POST', 'GET', 'DELETE']);
  assert.ok(h.timers.find(t => t.ms === 700).cleared);
  assert.equal(h.errors.length, 0);
});

test('missing job shows a server error', async () => {
  const h = harness([{ status: 202, body: { job_id: 'id' } }, { status: 404, body: { error_code: 'job_not_found' } }]);
  h.ctx.runEvalReal({ text: 'hello' }); await flush();
  assert.deepEqual(h.errors, ['eval.errServer']);
});

test('announces stage and quarter changes and shows only the STT estimate note', async () => {
  const h = harness([{ status: 202, body: { job_id: 'id' } }, running(10, 'vad'), running(15, 'vad'), running(26, 'vad'), running(27, 'stt')]);
  h.ctx.runEvalReal({ text: 'hello' }); await flush();
  h.tick(10);
  const live = h.nodes.get('#evLive');
  assert.equal(live.textContent, 'eval.stages.vad - eval.percentLabel');
  live.textContent = 'unchanged';
  h.poll(); await flush(); h.tick(10); assert.equal(live.textContent, 'unchanged');
  h.poll(); await flush(); h.tick(20); assert.equal(live.textContent, 'eval.stages.vad - eval.percentLabel');
  h.poll(); await flush(); h.tick(); assert.equal(live.textContent, 'eval.stages.stt - eval.percentLabel');
  assert.equal(h.nodes.get('#ovStep').textContent, 'eval.estimateNote');
  assert.equal(h.nodes.get('#ovStep').hidden, false);
});
