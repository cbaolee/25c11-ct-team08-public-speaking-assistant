const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../src/web/static/js/schedule/schedule_view.js'), 'utf8');
const view = import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
test('month grid starts Monday and spans six weeks across a year boundary', async () => {
  const { monthGrid } = await view;
  const days = monthGrid(2026, 0);
  assert.equal(days.length, 42);
  assert.equal(days[0], '2025-12-29');
  assert.equal(days[41], '2026-02-08');
});
test('month grid handles a leap February starting on Monday', async () => {
  const { monthGrid } = await view;
  const days = monthGrid(2016, 1);
  assert.equal(days[0], '2016-02-01');
  assert.equal(days[28], '2016-02-29');
  assert.equal(days[41], '2016-03-13');
});
