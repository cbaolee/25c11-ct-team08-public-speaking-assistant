const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const source = fs.readFileSync('src/web/static/js/schedule/schedule_script.js');
const modulePromise = import('data:text/javascript;base64,' + source.toString('base64'));
test('pickTopic filters duration and uses the supplied random value', async () => {
  const m = await modulePromise, topics = [{ duration_min: 5, title: 'a' }, { duration_min: 10 }, { duration_min: 5, title: 'b' }];
  assert.equal(m.pickTopic(topics, 5, () => 0).title, 'a');
  assert.equal(m.pickTopic(topics, 5, () => 0.999).title, 'b');
  assert.equal(m.pickTopic(topics, 15), null);
});
test('cache helpers are immutable and expire at the closing boundary', async () => {
  const m = await modulePromise, original = {}, entry = { title: 'a', text: 'text', closes_at: 100 };
  const cache = m.putAiScript(original, 'one', entry), later = m.putAiScript(cache, 'two', { closes_at: 101 });
  assert.deepEqual(original, {}); assert.notEqual(cache.one, entry);
  assert.equal(m.getAiScript(cache, 'one', 99).title, 'a'); assert.equal(m.getAiScript(cache, 'one', 100), null);
  assert.deepEqual(m.pruneAiCache(later, 100), { two: { closes_at: 101 } });
  assert.deepEqual(m.removeAiScript(cache, 'one'), {}); assert.ok(cache.one);
});
test('cache storage handles corrupt and blocked storage', async () => {
  const m = await modulePromise, values = {};
  const storage = { getItem: key => values[key], setItem: (key, value) => { values[key] = value; } };
  values['psa.schedule.ai.v1.user'] = '{'; assert.deepEqual(m.readAiCache(storage, 'user'), {});
  assert.equal(m.writeAiCache(storage, 'user', { a: { closes_at: 10 } }), true);
  assert.deepEqual(m.readAiCache(storage, 'user'), { a: { closes_at: 10 } });
  const blocked = { getItem() { throw Error(); }, setItem() { throw Error(); } };
  assert.deepEqual(m.readAiCache(blocked, 'user'), {}); assert.equal(m.writeAiCache(blocked, 'user', {}), false);
});
