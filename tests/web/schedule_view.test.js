const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../src/web/static/js/schedule/schedule_view.js'), 'utf8');
const view = import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
test('other view toggles month and week and defaults to month', async () => {
  const { otherView } = await view;
  assert.equal(otherView('month'), 'week');
  assert.equal(otherView('week'), 'month');
  for (const value of ['', 'day', undefined]) assert.equal(otherView(value), 'month');
});
test('month to week selects today in the current month and otherwise the first day', async () => {
  const { weekForMonthView } = await view;
  const now = new Date(2026, 10, 27, 12).getTime();
  for (const [month, expected] of [['2026-11', '2026-11-23'], ['2026-12', '2026-11-30'], ['2027-02', '2027-02-01'], ['2026-03', '2026-02-23'], ['2026-01', '2025-12-29']]) {
    assert.equal(weekForMonthView(month, now), expected);
  }
});
test('week to month prefers today, otherwise the Thursday of the week', async () => {
  const { monthForWeekView } = await view;
  assert.equal(monthForWeekView('2026-11-30', new Date(2026, 11, 1, 12).getTime()), '2026-12');
  assert.equal(monthForWeekView('2026-12-28', new Date(2027, 0, 1, 12).getTime()), '2027-01');
  const now = new Date(2026, 10, 27, 12).getTime();
  for (const [day, expected] of [['2026-11-30', '2026-12'], ['2025-12-29', '2026-01'], ['2026-12-03', '2026-12'], ['2026-08-31', '2026-09']]) {
    assert.equal(monthForWeekView(day, now), expected);
  }
});
test('month and week round trip follows the Thursday rule for every other month in 2026', async () => {
  const { weekForMonthView, monthForWeekView } = await view;
  const now = new Date(2026, 10, 27, 12).getTime();
  for (let m = 0; m < 12; m++) {
    if (m === 10) continue;
    const key = `2026-${String(m + 1).padStart(2, '0')}`;
    const day = new Date(2026, m, 1).getDay();
    // Friday through Sunday puts the first day's week in the previous month by Thursday.
    const previous = new Date(2026, m - 1, 1);
    const expected = day === 0 || day >= 5 ? `${previous.getFullYear()}-${String(previous.getMonth() + 1).padStart(2, '0')}` : key;
    assert.equal(monthForWeekView(weekForMonthView(key, now), now), expected, key);
  }
});
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

test('result link requires a matching history session', async () => {
  const { resultLink } = await view;
  assert.equal(resultLink({}, [{ id: 'a' }]), null);
  assert.equal(resultLink({ session_id: 'missing' }, [{ id: 'a' }]), null);
  assert.equal(resultLink({ session_id: 'a' }, [{ id: 'a' }]), 'a');
});

test('picker wheels wrap months and clamp years independently', async () => {
  const { wrapWheel, clampWheel, wheelWindow } = await view;
  assert.equal(wrapWheel(12, 0, 11), 0);
  assert.equal(wrapWheel(-1, 0, 11), 11);
  assert.equal(clampWheel(2032, 2021, 2031), 2031);
  assert.equal(clampWheel(2020, 2021, 2031), 2021);
  assert.deepEqual(wheelWindow(0, 0, 11, true), [11, 0, 1]);
  assert.deepEqual(wheelWindow(2021, 2021, 2031), [null, 2021, 2022]);
  assert.deepEqual(wheelWindow(2031, 2021, 2031), [2030, 2031, null]);
});

test('carousel duration words and urgency cover boundaries', async () => {
  const { formatDurationWords, closesTone } = await view;
  assert.equal(formatDurationWords(80 * 60000), '1 hour 20 minutes');
  assert.equal(formatDurationWords(120 * 60000), '2 hours');
  assert.equal(formatDurationWords(45 * 60000), '45 minutes');
  assert.equal(formatDurationWords(60000), '1 minute');
  assert.equal(formatDurationWords(59999), 'less than a minute');
  assert.equal(closesTone(60 * 60000), 'ok');
  assert.equal(closesTone(60 * 60000 - 1), 'danger');
});
test('carousel steps clamp and fades reflect hidden cards', async () => {
  const { carouselStep, edgeFades } = await view;
  assert.equal(carouselStep(0, 8, 3, 3), 3);
  assert.equal(carouselStep(3, 8, 3, 3), 5);
  assert.equal(carouselStep(1, 8, 3, -3), 0);
  assert.equal(carouselStep(0, 2, 3, 3), 0);
  assert.deepEqual(edgeFades(0, 8, 3), { left: false, right: true });
  assert.deepEqual(edgeFades(3, 8, 3), { left: true, right: true });
  assert.deepEqual(edgeFades(5, 8, 3), { left: true, right: false });
});

test('occurrence styles use palette colors, status and accessible text', async () => {
  const { occurrenceStyle, blendOver, contrastRatio, DONE_FILL_OPACITY, MISSED_BORDER_OPACITY } = await view;
  assert.equal(contrastRatio('#FFFFFF', '#000000'), 21);
  assert.equal(blendOver('#1D4ED8', 0.6, '#FFFFFF'), '#7795E8');
  assert.equal(DONE_FILL_OPACITY, 0.5);
  assert.equal(blendOver('#1D4ED8', DONE_FILL_OPACITY, '#FFFFFF'), '#8EA7EC');
  for (const color of ['blue', 'sky']) {
    for (const status of ['active', 'upcoming', 'done', 'missed']) {
      const style = occurrenceStyle(status, color);
      assert.equal(style.ring, status === 'active');
      assert.equal(style.borderStyle, status === 'missed' ? 'dashed' : 'solid');
      assert.equal(style.borderOpacity, status === 'missed' ? MISSED_BORDER_OPACITY : 1);
      assert.equal(style.fillOpacity, status === 'missed' ? 0 : status === 'done' ? DONE_FILL_OPACITY : 1);
    }
  }
  assert.equal(occurrenceStyle('upcoming', 'lime').text, '#1B2433');
  assert.equal(occurrenceStyle('active', 'sky').text, '#1B2433');
  assert.equal(occurrenceStyle('active', 'blue').text, '#FFFFFF');
  assert.equal(occurrenceStyle('active', 'slate').text, '#FFFFFF');
  assert.deepEqual(occurrenceStyle('done', 'unknown'), occurrenceStyle('done', 'lime'));
  for (const color of ['lime', 'blue', 'green', 'amber', 'brown', 'red', 'slate', 'gray', 'sky']) {
    for (const status of ['active', 'upcoming', 'done']) {
      const style = occurrenceStyle(status, color);
      const background = blendOver(style.fill, style.fillOpacity, '#FFFFFF');
      assert.ok(contrastRatio(style.text, background) >= 4.5, `${color} ${status}`);
    }
  }
});


test('event style variables and labels handle all day and optional lengths', async () => {
  const { rgba, styleVars, occurrenceStyle, sessionTimeLabel, lengthLabel } = await view;
  assert.equal(rgba('#1D4ED8', 0.5), 'rgba(29, 78, 216, 0.5)');
  assert.deepEqual(styleVars(occurrenceStyle('missed', 'blue')), { '--sch-ev-fill': 'transparent', '--sch-ev-border': 'rgba(29, 78, 216, 0.6)', '--sch-ev-border-style': 'dashed', '--sch-ev-text': '#1B2433', '--sch-ev-ring': 'transparent' });
  assert.equal(styleVars(occurrenceStyle('active', 'blue'))['--sch-ev-ring'], '#1D4ED8');
  const words = { allDay: 'All day', anyLength: 'Any length', minutes: '{n} min' };
  assert.equal(sessionTimeLabel({ all_day: true, start: 42 }, () => { throw Error('unexpected'); }, words), 'All day');
  assert.equal(sessionTimeLabel({ all_day: false, start: 42 }, n => `time ${n}`, words), 'time 42');
  assert.equal(lengthLabel(null, words), 'Any length');
  assert.equal(lengthLabel(10, words), '10 min');
});

test('chip capacity reserves the measured overflow line only when needed', async () => {
  const { chipsThatFit } = await view;
  assert.deepEqual(chipsThatFit(48, 28, 20, 14, 4, 1), { shown: 1, more: 0 });
  assert.deepEqual(chipsThatFit(100, 28, 20, 14, 4, 3), { shown: 3, more: 0 });
  assert.deepEqual(chipsThatFit(100, 28, 20, 14, 4, 4), { shown: 2, more: 2 });
  assert.deepEqual(chipsThatFit(80, 28, 20, 14, 4, 3), { shown: 1, more: 2 });
  assert.deepEqual(chipsThatFit(66, 28, 20, 14, 4, 2), { shown: 0, more: 2 });
  assert.deepEqual(chipsThatFit(100, 28, 20, 14, 4, 0), { shown: 0, more: 0 });
});

test('week helpers use calendar days, ranges and initial scroll', async () => {
  const { weekDays, weekRangeLabel, initialScrollHour, blockGeometry } = await view;
  const fmt = (d, options) => new Intl.DateTimeFormat('en-US', options).format(d);
  assert.deepEqual(weekDays('2026-03-08'), ['2026-03-02','2026-03-03','2026-03-04','2026-03-05','2026-03-06','2026-03-07','2026-03-08']);
  assert.equal(weekRangeLabel('2026-11-23', fmt), 'Nov 23 \u2013 29, 2026');
  assert.equal(weekRangeLabel('2026-11-30', fmt), 'Nov 30 \u2013 Dec 6, 2026');
  assert.equal(weekRangeLabel('2026-12-28', fmt), 'Dec 28, 2026 \u2013 Jan 3, 2027');
  assert.equal(initialScrollHour(weekDays('2026-03-08'), '2026-03-08', 19), 19);
  assert.equal(initialScrollHour(weekDays('2026-03-08'), '2026-03-09', 19), 7);
  assert.deepEqual(blockGeometry(1435, null, 60), { top: 1435, height: 5 });
  assert.deepEqual(blockGeometry(60, 10, 60), { top: 60, height: 30 });
});
test('week overlap clusters use reusable columns and treat touching blocks as separate', async () => {
  const { layoutDayBlocks } = await view;
  const layout = intervals => layoutDayBlocks(intervals.map(([startMin,endMin], key) => ({ key, startMin, endMin }))).map(({col, cols}) => [col, cols]);
  assert.deepEqual(layout([[0,10],[10,20]]), [[0,1],[0,1]]);
  assert.deepEqual(layout([[0,10],[5,15]]), [[0,2],[1,2]]);
  assert.deepEqual(layout([[0,10],[1,11],[2,12]]), [[0,3],[1,3],[2,3]]);
  assert.deepEqual(layout([[0,10],[5,15],[10,20]]), [[0,2],[1,2],[0,2]]);
});


test('slot start chooses the next valid local five minute time', async () => {
  const { slotStartTime } = await view, key = '2026-11-27';
  const now = (h, m, sec = 0) => new Date(2026, 10, 27, h, m, sec).getTime();
  assert.equal(slotStartTime(key, 16, now(15, 20)), '16:00');
  assert.equal(slotStartTime(key, 14, now(15, 20)), null);
  assert.equal(slotStartTime(key, 15, now(15, 20, 30)), '15:25');
  assert.equal(slotStartTime(key, 15, now(15, 55)), '16:00');
  assert.equal(slotStartTime(key, 23, now(23, 57)), null);
  assert.equal(slotStartTime('2026-11-28', 0, now(15, 0)), '00:00');
  assert.equal(slotStartTime('2026-11-26', 23, now(0, 0)), null);
  assert.equal(slotStartTime(key, 0, now(0, 0)), '00:05');
});
test('slot navigation skips closed positions and respects boundaries', async () => {
  const { slotTarget } = await view;
  const open = (d, h) => d >= 1 && d <= 5 && (d !== 2 || h >= 12) && h !== 14;
  assert.deepEqual(slotTarget(3, 13, 'ArrowDown', open), { dayIndex: 3, hour: 15 });
  assert.deepEqual(slotTarget(3, 15, 'ArrowUp', open), { dayIndex: 3, hour: 13 });
  assert.deepEqual(slotTarget(3, 13, 'ArrowRight', open), { dayIndex: 4, hour: 13 });
  assert.deepEqual(slotTarget(3, 9, 'ArrowLeft', open), { dayIndex: 2, hour: 12 });
  assert.deepEqual(slotTarget(1, 9, 'ArrowRight', open), { dayIndex: 2, hour: 12 });
  assert.deepEqual(slotTarget(2, 15, 'Home', open), { dayIndex: 2, hour: 12 });
  assert.deepEqual(slotTarget(2, 15, 'End', open), { dayIndex: 2, hour: 23 });
  assert.equal(slotTarget(1, 0, 'ArrowUp', open), null);
  assert.equal(slotTarget(5, 23, 'ArrowDown', open), null);
  assert.equal(slotTarget(5, 9, 'ArrowRight', open), null);
  assert.equal(slotTarget(1, 9, 'ArrowLeft', open), null);
});
