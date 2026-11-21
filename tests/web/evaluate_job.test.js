const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const client = require('../../src/web/static/js/evaluate_client.js');

function harness(replies) {
  const source = fs.readFileSync('src/web/static/js/screens/practice.js', 'utf8');
  const code = source.slice(source.indexOf('export function cancelEval()'), source.indexOf('export function finishEvalReal')).replaceAll('export ', '');
  const nodes = new Map(), calls = [], timers = [], errors = [], finished = [], closed = [];
  const node = () => ({ textContent: '', style: {}, dataset: {}, setAttribute() {} });
  const $ = key => { if (!nodes.has(key)) nodes.set(key, node()); return nodes.get(key); };
  const ctx = { S: { audio: { kind: 'file', name: 'a.wav', file: 'audio' } }, CONFIG: { EVAL_JOB: { pollMs: 700, maxWaitS: 300, weights: {}, tauS: 20, closeDelayMs: 400, announcePct: 25 } }, EvaluateClient: client, AbortController, Date, encodeURIComponent,
    FormData: class { append() {} }, $, $$: () => [], T: (x) => x, openModal() {}, closeModal(...args) { closed.push(args); }, toast() {}, openBaselineGate() {}, showEvalError: null,
    setTimeout: (fn, ms) => { const t = { fn, ms }; timers.push(t); return t; }, clearTimeout: t => { t.cleared = true; }, matchMedia: () => ({ matches: true }),
    finishEvalReal: (...args) => finished.push(args), api: (url, opts = {}) => { calls.push([url, opts.method || 'GET', opts]); const reply = replies.shift(); return Promise.resolve(reply).then(r => ({ status: r.status, ok: r.status < 400, json: () => Promise.resolve(r.body) })); } };
  vm.createContext(ctx); vm.runInContext(code, ctx); ctx.showEvalError = msg => errors.push(msg);
  return { ctx, calls, timers, errors, finished, nodes, closed };
}
const flush = () => new Promise(resolve => setImmediate(resolve));

test('202 job polls without overlap and passes the completed result', async () => {
  const h = harness([{ status: 202, body: { job_id: 'id' } }, { status: 200, body: { status: 'running', progress: 5, stages: [] } }, { status: 200, body: { status: 'done', progress: 100, stages: [], result: { value: 1 } } }]);
  h.ctx.runEvalReal({ text: 'hello' }); await flush();
  assert.deepEqual(h.calls.map(x => x[1]), ['POST', 'GET']);
  h.timers.find(t => t.ms === 700).fn(); await flush();
  h.timers.find(t => t.ms === 0).fn();
  assert.equal(h.finished[0][0].value, 1);
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
  const running = (progress, stage) => ({ status: 200, body: { status: 'running', progress, stage, stages: [{ key: stage, state: 'running' }] } });
  const h = harness([{ status: 202, body: { job_id: 'id' } }, running(10, 'vad'), running(15, 'vad'), running(26, 'vad'), running(27, 'stt')]);
  h.ctx.runEvalReal({ text: 'hello' }); await flush();
  const live = h.nodes.get('#evLive');
  assert.equal(live.textContent, 'eval.stages.vad - eval.percentLabel');
  live.textContent = 'unchanged';
  const poll = () => h.timers.filter(t => t.ms === 700).at(-1).fn();
  poll(); await flush(); assert.equal(live.textContent, 'unchanged');
  poll(); await flush(); assert.equal(live.textContent, 'eval.stages.vad - eval.percentLabel');
  poll(); await flush(); assert.equal(live.textContent, 'eval.stages.stt - eval.percentLabel');
  assert.equal(h.nodes.get('#ovStep').textContent, 'eval.estimateNote');
  assert.equal(h.nodes.get('#ovStep').hidden, false);
});
