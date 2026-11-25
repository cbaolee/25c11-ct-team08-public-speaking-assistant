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

test('countdown floors minutes and handles hour boundaries', async () => {
  const { formatCountdown } = await view;
  assert.equal(formatCountdown(80 * 60000 + 59999), '1 h 20 min');
  assert.equal(formatCountdown(45 * 60000), '45 min');
  assert.equal(formatCountdown(-1), '0 min');
});
test('streak labels interpolate the supplied text', async () => {
  const { streakLabel } = await view;
  assert.equal(streakLabel(0, 'No streak yet', '{n}-week streak'), 'No streak yet');
  assert.equal(streakLabel(1, 'No streak yet', '{n}-week streak'), '1-week streak');
  assert.equal(streakLabel(8, 'No streak yet', '{n}-week streak'), '8-week streak');
});

test('time conversions and five minute choices cover noon and midnight', async () => {
  const { to12h, to24h, MINUTE_STEPS } = await view;
  assert.deepEqual(to12h('19:05'), { h: 7, m: 5, pm: true });
  assert.equal(to24h(12, 0, false), '00:00');
  assert.equal(to24h(12, 5, true), '12:05');
  assert.equal(to24h(7, 5, true), '19:05');
  assert.deepEqual(MINUTE_STEPS, [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]);
});
test('calendar navigation clamps months and starts weeks on Monday', async () => {
  const { moveDay, monthMatrix } = await view;
  assert.equal(moveDay('2024-03-31', 'PageUp'), '2024-02-29');
  assert.equal(moveDay('2026-01-01', 'ArrowLeft'), '2025-12-31');
  assert.equal(moveDay('2026-11-25', 'Home'), '2026-11-23');
  assert.equal(moveDay('2026-11-25', 'End'), '2026-11-29');
  assert.equal(monthMatrix(2026, 10).length, 42);
});
test('new event defaults to the next half hour or future evening', async () => {
  const { defaultTime } = await view;
  assert.equal(defaultTime(new Date(2026, 10, 25, 18, 30).getTime(), '2026-11-25'), '19:00');
  assert.equal(defaultTime(new Date(2026, 10, 25, 23, 40).getTime(), '2026-11-25'), '');
  assert.equal(defaultTime(new Date(2026, 10, 25, 23, 40).getTime(), '2026-11-26'), '19:00');
});

test('session summary counts days and identifies the last occurrence', async () => {
  const { sessionsSummary } = await view;
  assert.deepEqual(sessionsSummary([]), { n: 0, last: null });
  assert.deepEqual(sessionsSummary(['2026-11-25', '2026-12-02']), { n: 2, last: '2026-12-02' });
});
