'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
// script_studio_state.js has no imports, so it loads through a data: URL (same way as coach_mode.test.js).
const source = fs.readFileSync(path.join(__dirname, '../../src/web/static/js/screens/script_studio_state.js'), 'utf8');
const mod = import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));

const FB = 'FALLBACK';
const pick = async (title, max) => (await mod).pickScriptTitle({ title }, FB, max);

/* Run fn with String.prototype.isWellFormed removed (older engines), then restore it exactly. */
async function withoutIsWellFormed(fn) {
  const had = Object.getOwnPropertyDescriptor(String.prototype, 'isWellFormed');
  delete String.prototype.isWellFormed;
  try {
    assert.equal(typeof ''.isWellFormed, 'undefined');
    await fn();
  } finally {
    if (had) Object.defineProperty(String.prototype, 'isWellFormed', had);
  }
}

test('pickScriptTitle trims a valid title', async () => {
  assert.equal(await pick('  My Speech  '), 'My Speech');
  assert.equal(await pick('Plain title'), 'Plain title');
});

test('pickScriptTitle rejects empty, blank and invisible titles', async () => {
  for (const title of ['', '   ', '\u00a0', '\u3000', '\u00a0\u3000', '\u200b', '\u200b\u200b', '\u0007']) {
    assert.equal(await pick(title), FB, JSON.stringify(title));
  }
});

test('pickScriptTitle rejects a title that is not a primitive string', async () => {
  for (const title of [null, undefined, 42, [], ['a'], {}, { a: 1 }, Symbol('x'), new String('abc'), true]) {
    assert.equal(await pick(title), FB, String(typeof title));
  }
});

test('pickScriptTitle falls back when the result is not an object', async () => {
  const { pickScriptTitle } = await mod;
  for (const result of [null, undefined, 5, 'Title', true, {}]) {
    assert.equal(pickScriptTitle(result, FB, 70), FB);
  }
});

test('pickScriptTitle keeps exactly 70 characters and rejects 71', async () => {
  assert.equal(await pick('a'.repeat(70)), 'a'.repeat(70));
  assert.equal(await pick('a'.repeat(71)), FB);
});

test('pickScriptTitle counts emoji surrogate pairs as one character', async () => {
  assert.equal(await pick('😀'.repeat(70)), '😀'.repeat(70));
  assert.equal(await pick('😀'.repeat(71)), FB);
});

test('pickScriptTitle converts NFD Vietnamese to NFC and counts composed characters', async () => {
  const nfd = 'Việt Nam'.normalize('NFD');
  assert.notEqual(nfd, 'Việt Nam');
  assert.equal(await pick(nfd), 'Việt Nam'.normalize('NFC'));
  const e = 'ệ'.normalize('NFD');
  assert.ok(e.length > 1);
  assert.equal(await pick(e.repeat(70)), 'ệ'.normalize('NFC').repeat(70));
  assert.equal(await pick(e.repeat(71)), FB);
});

test('pickScriptTitle turns line breaks and tabs into single spaces', async () => {
  assert.equal(await pick('Line1\nLine2'), 'Line1 Line2');
  assert.equal(await pick('  a\t\tb  '), 'a b');
  assert.equal(await pick('a\r\nb'), 'a b');
  assert.equal(await pick('a\u00a0\u00a0b'), 'a b');
});

test('pickScriptTitle turns control characters inside a title into a space', async () => {
  assert.equal(await pick('a\u0007b'), 'a b');
  assert.equal(await pick('a\u0000b'), 'a b');
  assert.equal(await pick('a\u0007\u0000b'), 'a b');
});

test('pickScriptTitle keeps a zero-width space between letters (Cf is not stripped, so ZWJ emoji survive)', async () => {
  assert.equal(await pick('a\u200bb'), 'a\u200bb');
});

test('pickScriptTitle rejects lone surrogates anywhere in the title', async () => {
  for (const title of ['ab\ud83dcd', '\ud83dabc', 'abc\ud83d', 'ab\ude00cd', '\ude00abc', 'abc\ude00']) {
    assert.equal(await pick(title), FB, JSON.stringify(title));
  }
});

test('pickScriptTitle keeps valid surrogate pairs', async () => {
  assert.equal(await pick('Hello 😀 world'), 'Hello 😀 world');
  assert.equal(await pick('😀'), '😀');
});

test('pickScriptTitle keeps the ZWJ inside a joined emoji', async () => {
  const title = '\u{1F468}\u200d\u{1F469}\u200d\u{1F467} Family Day Out';
  assert.ok(title.includes('\u200d'));
  assert.equal(await pick(title), title);
});

test('pickScriptTitle counts the length after whitespace is collapsed', async () => {
  assert.equal(await pick(Array(35).fill('a').join('\n')), Array(35).fill('a').join(' '));   // 69 characters
  assert.equal(await pick(Array(36).fill('a').join('\n')), FB);                              // 71 characters
});

test('pickScriptTitle uses 70 when maxChars is missing or broken', async () => {
  for (const max of [undefined, null, NaN, 0, -5, Infinity, '70', {}]) {
    assert.equal(await pick('a'.repeat(70), max), 'a'.repeat(70), String(max));
    assert.equal(await pick('a'.repeat(71), max), FB, String(max));
  }
});

test('pickScriptTitle honours a custom maxChars', async () => {
  assert.equal(await pick('abcde', 5), 'abcde');
  assert.equal(await pick('abcdef', 5), FB);
  assert.equal(await pick('abcdef', 6), 'abcdef');
});

test('pickScriptTitle keeps ordinary punctuation', async () => {
  assert.equal(await pick('Rise of the U.S.'), 'Rise of the U.S.');
  assert.equal(await pick('Hello, world: a "talk" (v2) - 100%!'), 'Hello, world: a "talk" (v2) - 100%!');
});

test('pickScriptTitle rejects a title with no letter, digit or emoji', async () => {
  for (const title of ['!!!', '...', '-- --', '()']) assert.equal(await pick(title), FB, title);
  assert.equal(await pick('2024'), '2024');
});

test('pickScriptTitle works without String.prototype.isWellFormed', async () => {
  await withoutIsWellFormed(async () => {
    for (const title of ['ab\ud83dcd', '\ud83dabc', 'abc\ud83d', 'ab\ude00cd', '\ude00abc', 'abc\ude00']) {
      assert.equal(await pick(title), FB, JSON.stringify(title));
    }
    assert.equal(await pick('Hello 😀 world'), 'Hello 😀 world');
    assert.equal(await pick('😀😀'), '😀😀');
    assert.equal(await pick('😀'.repeat(71)), FB);
    assert.equal(await pick('  Title  '), 'Title');
  });
});

test('composerActionState: a running cooldown disables Regenerate only', async () => {
  const { composerActionState } = await mod;
  for (const cooldownLeftS of [1, 0.2, 600]) {
    assert.deepEqual(composerActionState({ hasScript: true, cooldownLeftS }), { mode: 'regenerate', disabled: true }, String(cooldownLeftS));
    for (const hasScript of [false, undefined, 'true', 1]) {
      assert.deepEqual(composerActionState({ hasScript, cooldownLeftS }), { mode: 'send', disabled: false }, String(hasScript));
    }
  }
});

test('composerActionState: a finished or broken cooldown does not disable, busy still does', async () => {
  const { composerActionState } = await mod;
  for (const cooldownLeftS of [0, -1, NaN, Infinity, '5', null, undefined, true, {}, [5]]) {
    assert.deepEqual(composerActionState({ hasScript: true, cooldownLeftS }), { mode: 'regenerate', disabled: false }, String(cooldownLeftS));
    assert.equal(composerActionState({ busy: true, hasScript: true, cooldownLeftS }).disabled, true);
  }
  assert.deepEqual(Object.keys(composerActionState({ hasScript: true, cooldownLeftS: 9 })).sort(), ['disabled', 'mode']);
});

test('parseRetryAfterS prefers retry_after_s of the body over the header', async () => {
  const { parseRetryAfterS } = await mod;
  assert.equal(parseRetryAfterS({ retry_after_s: 15 }, '99'), 15);
  assert.equal(parseRetryAfterS({ retry_after_s: 15 }, null), 15);
  assert.equal(parseRetryAfterS({ retry_after_s: 1.2 }, '99'), 2);
});

test('parseRetryAfterS falls back to a header given in seconds and rounds up', async () => {
  const { parseRetryAfterS } = await mod;
  for (const body of [null, undefined, {}, 'x', 5, { retry_after_s: null }]) assert.equal(parseRetryAfterS(body, '30'), 30);
  assert.equal(parseRetryAfterS(null, '1.2'), 2);
  assert.equal(parseRetryAfterS(null, ' 7 '), 7);
  for (const retry_after_s of [0, -3, NaN, Infinity, '5', true, {}, []]) {
    assert.equal(parseRetryAfterS({ retry_after_s }, '8'), 8, String(retry_after_s));
  }
});

test('parseRetryAfterS returns 0 when neither value is usable', async () => {
  const { parseRetryAfterS } = await mod;
  const headers = [null, undefined, '', '   ', '0', '-5', 'NaN', 'Infinity', 'soon', '5s', '1e3', '0x10', '1.', '.5', '9'.repeat(400), 'Wed, 21 Oct 2026 07:28:00 GMT', 30];
  for (const header of headers) {
    assert.equal(parseRetryAfterS(null, header), 0, String(header));
    assert.equal(parseRetryAfterS({ retry_after_s: -1 }, header), 0, String(header));
  }
  assert.equal(parseRetryAfterS(), 0);
});

test('formatRetryWait writes minutes and seconds, and nothing for no wait', async () => {
  const { formatRetryWait } = await mod;
  const cases = [[1, '1s'], [5, '5s'], [59, '59s'], [60, '1m'], [61, '1m 1s'], [90, '1m 30s'], [525, '8m 45s'], [600, '10m'], [4.2, '5s'], [59.5, '1m']];
  for (const [seconds, text] of cases) assert.equal(formatRetryWait(seconds), text, String(seconds));
  for (const bad of [0, -1, NaN, Infinity, '5', null, undefined, {}]) assert.equal(formatRetryWait(bad), '', String(bad));
});

test('secondsLeft rounds up and never goes below 0', async () => {
  const { secondsLeft } = await mod;
  assert.equal(secondsLeft(16000, 1000), 15);
  assert.equal(secondsLeft(16000, 1001), 15);
  assert.equal(secondsLeft(16000, 15999), 1);
  assert.equal(secondsLeft(16000, 16000), 0);
  assert.equal(secondsLeft(16000, 99000), 0);
  for (const bad of [NaN, undefined, null, 'x', {}]) assert.equal(secondsLeft(bad, 1000), 0, String(bad));
  assert.equal(secondsLeft(16000, undefined), 0);
});

test('rateLimitScope: each known reason has a fixed scope', async () => {
  const { rateLimitScope } = await mod;
  for (const again of [true, false]) {
    assert.equal(rateLimitScope('cooldown', again), 'regenerate');
    assert.equal(rateLimitScope('regenerate_quota', again), 'regenerate');
    assert.equal(rateLimitScope('generate_quota', again), 'all');
    assert.equal(rateLimitScope('job_running', again), 'all');
  }
});

test('rateLimitScope: an unknown or missing reason holds the kind of run that was refused', async () => {
  const { rateLimitScope } = await mod;
  for (const reason of [undefined, null, '', 'other', 'toString', '__proto__', 7, {}]) {
    assert.equal(rateLimitScope(reason, true), 'regenerate', String(reason));
    assert.equal(rateLimitScope(reason, false), 'all', String(reason));
  }
});

test('rateLimitTextKey names a message per reason and a general one otherwise', async () => {
  const { rateLimitTextKey } = await mod;
  assert.equal(rateLimitTextKey('cooldown'), 'script.errRateCooldown');
  assert.equal(rateLimitTextKey('regenerate_quota'), 'script.errRateRegen');
  assert.equal(rateLimitTextKey('generate_quota'), 'script.errRateGenerate');
  assert.equal(rateLimitTextKey('job_running'), 'script.errRateBusy');
  for (const reason of [undefined, null, '', 'other', 'constructor', 7]) {
    assert.equal(rateLimitTextKey(reason), 'script.errRateWait', String(reason));
  }
});

// i18n.js imports only the DOM helper of applyText (not called here), so that line is dropped to load it the same way.
const i18nSource = fs.readFileSync(path.join(__dirname, '../../src/web/static/js/i18n.js'), 'utf8').replace(/^import .*$/m, '');
const i18n = import('data:text/javascript;base64,' + Buffer.from(i18nSource).toString('base64'));

test('every rate limit message and wait hint exists in TEXT.script and takes {wait}', async () => {
  const { rateLimitTextKey } = await mod;
  const { TEXT } = await i18n;
  const keys = ['cooldown', 'regenerate_quota', 'generate_quota', 'job_running', undefined].map(rateLimitTextKey)
    .concat('script.regenWaitHint', 'script.generateWaitHint');
  for (const key of keys) {
    const [group, name] = key.split('.');
    assert.equal(group, 'script', key);
    assert.match(String(TEXT.script[name]), /\{wait\}/, key);
  }
});

test('a wait hint with a long wait is no longer than the hint it replaces', async () => {
  const { formatRetryWait } = await mod;
  const { TEXT } = await i18n;
  const wait = formatRetryWait(599);
  assert.equal(wait, '9m 59s');
  for (const [waiting, usual] of [['regenWaitHint', 'regenHint'], ['generateWaitHint', 'fileHint']]) {
    assert.ok(TEXT.script[waiting].replace('{wait}', wait).length <= TEXT.script[usual].length, waiting);
  }
});

test('regenerateFeedback returns typed text trimmed, whatever the attempt', async () => {
  const { regenerateFeedback } = await mod;
  assert.equal(regenerateFeedback('  make it shorter  ', 1), 'make it shorter');
  assert.equal(regenerateFeedback('make it shorter', 5), 'make it shorter');
  assert.equal(regenerateFeedback('\n\t make it shorter \r\n', undefined), 'make it shorter');
});

test('regenerateFeedback keeps inner line breaks and never cuts long text', async () => {
  const { regenerateFeedback } = await mod;
  assert.equal(regenerateFeedback(' line one\nline two\r\n\r\nline three ', 2), 'line one\nline two\r\n\r\nline three');
  const long = 'word '.repeat(5000).trim();
  assert.equal(regenerateFeedback(long + '   ', 1), long);
});

test('regenerateFeedback: blank text gives the fixed request, numbered from the second attempt', async () => {
  const { regenerateFeedback } = await mod;
  const base = 'Write a fresh variation of this speech.';
  for (const blank of ['', ' ', '   \n\t \r\n ', ' 　']) {
    assert.equal(regenerateFeedback(blank, 1), base);
    assert.equal(regenerateFeedback(blank, 2), 'Write a fresh variation of this speech (variation 2).');
    assert.equal(regenerateFeedback(blank, 10), 'Write a fresh variation of this speech (variation 10).');
  }
});

test('regenerateFeedback treats a bad attempt as the first one', async () => {
  const { regenerateFeedback } = await mod;
  const base = 'Write a fresh variation of this speech.';
  for (const attempt of [0, 1, -1, -5, undefined, null, NaN, Infinity, 'x', '3', 2.5, {}, [], true]) {
    assert.equal(regenerateFeedback('', attempt), base, String(attempt));
  }
  assert.equal(regenerateFeedback(''), base);
});

test('regenerateFeedback treats a non-string text as blank', async () => {
  const { regenerateFeedback } = await mod;
  const base = 'Write a fresh variation of this speech.';
  for (const text of [undefined, null, 0, 42, NaN, false, true, {}, [], ['text'], { trim: () => 'x' }]) {
    assert.equal(regenerateFeedback(text, 1), base, String(text));
  }
  assert.equal(regenerateFeedback(null, 3), 'Write a fresh variation of this speech (variation 3).');
});

test('composerActionState: only hasScript === true switches to regenerate', async () => {
  const { composerActionState } = await mod;
  assert.deepEqual(composerActionState({ hasScript: true }), { mode: 'regenerate', disabled: false });
  for (const hasScript of ['true', 1, {}, [], null, undefined, false, 0, '']) {
    assert.equal(composerActionState({ hasScript }).mode, 'send', String(hasScript));
  }
});

test('composerActionState: busy disables the button and keeps the mode', async () => {
  const { composerActionState } = await mod;
  for (const busy of [true, 1, 'yes', {}, []]) {
    assert.deepEqual(composerActionState({ busy, hasScript: true }), { mode: 'regenerate', disabled: true });
    assert.deepEqual(composerActionState({ busy, hasScript: false }), { mode: 'send', disabled: true });
  }
  for (const busy of [false, 0, '', null, undefined]) {
    assert.equal(composerActionState({ busy, hasScript: true }).disabled, false);
  }
});

test('composerActionState: missing, null or empty input is Send and enabled', async () => {
  const { composerActionState } = await mod;
  assert.deepEqual(composerActionState(), { mode: 'send', disabled: false });
  assert.deepEqual(composerActionState(null), { mode: 'send', disabled: false });
  assert.deepEqual(composerActionState({}), { mode: 'send', disabled: false });
});

test('composerActionState returns exactly the keys mode and disabled', async () => {
  const { composerActionState } = await mod;
  assert.deepEqual(Object.keys(composerActionState({ busy: true, hasScript: true, stage: 'generated', extra: 1 })).sort(), ['disabled', 'mode']);
});

test('formatReplyMarkup wraps **bold** spans in <strong class="key-req"> and preserves newlines', async () => {
  const { formatReplyMarkup } = await mod;
  assert.equal(
    formatReplyMarkup('Share your **target audience** and **key examples**.\n- Optional: **tone**'),
    'Share your <strong class="key-req">target audience</strong> and <strong class="key-req">key examples</strong>.\n- Optional: <strong class="key-req">tone</strong>'
  );
});

test('formatReplyMarkup escapes HTML before formatting so untrusted text cannot inject tags', async () => {
  const { formatReplyMarkup } = await mod;
  assert.equal(
    formatReplyMarkup('<script>alert("x")</script> **<img src=x onerror=\'pwn()\'> & more**'),
    '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; <strong class="key-req">&lt;img src=x onerror=&#39;pwn()&#39;&gt; &amp; more</strong>'
  );
});

test('formatReplyMarkup leaves unmatched, empty, whitespace-only, or multi-line ** literal and handles non-strings', async () => {
  const { formatReplyMarkup } = await mod;
  assert.equal(formatReplyMarkup('single *star* and **** and **   ** and **across\nlines**'), 'single *star* and **** and **   ** and **across\nlines**');
  for (const bad of [null, undefined, 0, 42, false, {}, []]) {
    assert.equal(formatReplyMarkup(bad), '');
  }
});

test('shouldShowGenerateButton hides button on Turn 1 and after a script exists, shows from Turn 2 onward', async () => {
  const { shouldShowGenerateButton } = await mod;
  assert.equal(shouldShowGenerateButton({ hasScript: false, assistantTurn: 1, canGenerate: false }), false);
  assert.equal(shouldShowGenerateButton({ hasScript: false, assistantTurn: 1, canGenerate: true }), false);
  assert.equal(shouldShowGenerateButton({ hasScript: false, assistantTurn: 2, canGenerate: false }), false);
  assert.equal(shouldShowGenerateButton({ hasScript: false, assistantTurn: 2, canGenerate: true }), true);
  assert.equal(shouldShowGenerateButton({ hasScript: false, assistantTurn: 4 }), true);
  assert.equal(shouldShowGenerateButton({ hasScript: true, assistantTurn: 3, canGenerate: true }), false);
  assert.equal(shouldShowGenerateButton(), false);
});

test('canTriggerGenerateKeyword blocks Turn 1, file attachments, and post-script state; allows Turn 2+ keywords', async () => {
  const { canTriggerGenerateKeyword } = await mod;
  assert.equal(canTriggerGenerateKeyword({ stage: 'gathering', hasScript: false, canGenerateNow: false, hasFile: false, text: 'generate' }), false);
  assert.equal(canTriggerGenerateKeyword({ stage: 'picking_topic', hasScript: false, canGenerateNow: true, hasFile: false, text: 'done' }), false);
  assert.equal(canTriggerGenerateKeyword({ stage: 'gathering', hasScript: false, canGenerateNow: true, hasFile: true, text: 'generate' }), false);
  assert.equal(canTriggerGenerateKeyword({ stage: 'gathering', hasScript: true, canGenerateNow: true, hasFile: false, text: 'generate' }), false);
  for (const kw of ['generate', '  DONE ', 'Xong', 'tạo'.normalize('NFD')]) {
    assert.equal(canTriggerGenerateKeyword({ stage: 'gathering', hasScript: false, canGenerateNow: true, hasFile: false, text: kw }), true, kw);
  }
  assert.equal(canTriggerGenerateKeyword({ stage: 'gathering', hasScript: false, canGenerateNow: true, hasFile: false, text: 'please generate now' }), false);
});

test('validateTurnText enforces NFC code-point and word ceilings consistently with backend', async () => {
  const { validateTurnText } = await mod;
  assert.deepEqual(validateTurnText(''), { ok: true, chars: 0, words: 0 });
  assert.deepEqual(validateTurnText(null), { ok: true, chars: 0, words: 0 });

  const nfd = 'ệ'.normalize('NFD');
  assert.equal(validateTurnText(nfd.repeat(10), { maxChars: 10, maxWords: 100 }).ok, true);
  const overChars = validateTurnText(nfd.repeat(11), { maxChars: 10, maxWords: 100 });
  assert.deepEqual(overChars, { ok: false, reason: 'chars', limit: 10, chars: 11, words: 1 });

  assert.equal(validateTurnText('😀'.repeat(10), { maxChars: 10, maxWords: 100 }).ok, true);
  assert.equal(validateTurnText('😀'.repeat(11), { maxChars: 10, maxWords: 100 }).reason, 'chars');

  assert.equal(validateTurnText('word '.repeat(5).trim(), { maxChars: 100, maxWords: 5 }).ok, true);
  const overWords = validateTurnText('word '.repeat(6).trim(), { maxChars: 100, maxWords: 5 });
  assert.equal(overWords.ok, false);
  assert.equal(overWords.reason, 'words');
  assert.equal(overWords.limit, 5);

  // Default word cap is 2,000 words when limits are omitted
  assert.equal(validateTurnText('w '.repeat(2000).trim()).ok, true);
  assert.deepEqual(validateTurnText('w '.repeat(2001).trim()), {
    ok: false,
    reason: 'words',
    limit: 2000,
    chars: 4001,
    words: 2001,
  });
});

test('normalizeTelemetrySteps and computeBufferedRemainingS handle +10s buffer, countdown, skipped, and completion', async () => {
  const { normalizeTelemetrySteps, computeBufferedRemainingS } = await mod;
  const fallback = normalizeTelemetrySteps(null, ['validating_input', 'moderating', 'analyzing_with_llm']);
  assert.deepEqual(fallback, [
    { key: 'validating_input', state: 'running' },
    { key: 'moderating', state: 'pending' },
    { key: 'analyzing_with_llm', state: 'pending' },
  ]);

  const durs = { validating_input: 0.5, moderating: 1.0, compacting_context: 2.5, analyzing_with_llm: 3.5 };
  // Fallback estimate: running (1.0) + pending (3.5) + 10s buffer = 14.5 -> ceil = 15s (skipped compacting_context ignored)
  const est = computeBufferedRemainingS(
    {
      stage: 'moderating',
      eta_buffer_s: 10,
      steps: [
        { key: 'validating_input', state: 'done' },
        { key: 'moderating', state: 'running' },
        { key: 'compacting_context', state: 'skipped' },
        { key: 'analyzing_with_llm', state: 'pending' },
      ],
    },
    0,
    durs,
    10
  );
  assert.equal(est, 15);

  // Server estimated_remaining_s counts down smoothly and clamps at 1s until completed/failed
  assert.equal(computeBufferedRemainingS({ status: 'running', estimated_remaining_s: 14.2 }, 3.0), 12);
  assert.equal(computeBufferedRemainingS({ status: 'running', estimated_remaining_s: 4.0 }, 25.0), 1);
  assert.equal(computeBufferedRemainingS({ status: 'completed', estimated_remaining_s: 10.0 }, 0), 0);
  assert.equal(computeBufferedRemainingS({ stage: 'failed', estimated_remaining_s: 10.0 }, 0), 0);
});

test('parseRestoredChatSession restores picking_topic, gathering (Turn 1 / Turn 2+), and generated sessions within TTL', async () => {
  const { parseRestoredChatSession } = await mod;
  const now = 1_700_000_000_000;
  const validGenerated = {
    chatSessionId: 'sess-123',
    chatHasScript: true,
    chatRegenCount: 2,
    assistantTurn: 3,
    selectedTemplate: { template_id: 'wildlife/keystone_5m', topic: 'Keystone Species' },
    sessionFiles: ['notes.pdf', '', 42],
    chatSeed: { prompt: 'Keystone species', fileName: 'notes.pdf' },
    category: 'wildlife',
    duration_min: 10,
    savedAt: now - 5 * 60 * 1000,
  };
  // Backward compatible when chatStage is omitted on a generated session
  assert.deepEqual(parseRestoredChatSession(validGenerated, now), {
    chatSessionId: 'sess-123',
    chatStage: 'generated',
    chatHasScript: true,
    chatRegenCount: 2,
    assistantTurn: 3,
    canGenerateNow: true,
    selectedTemplate: { template_id: 'wildlife/keystone_5m', topic: 'Keystone Species' },
    sessionFiles: ['notes.pdf'],
    chatSeed: { prompt: 'Keystone species', fileName: 'notes.pdf' },
    category: 'wildlife',
    duration_min: 10,
  });

  // picking_topic stage keeps topic cards active and disables generation
  assert.deepEqual(
    parseRestoredChatSession({
      chatSessionId: 'sess-pick',
      chatStage: 'picking_topic',
      chatHasScript: false,
      assistantTurn: 0,
      canGenerateNow: true,
      sessionFiles: ['outline.md'],
      chatSeed: { prompt: 'Ocean plastic', fileName: 'outline.md' },
      category: 'environment',
      duration_min: 5,
      savedAt: now - 60_000,
    }, now),
    {
      chatSessionId: 'sess-pick',
      chatStage: 'picking_topic',
      chatHasScript: false,
      chatRegenCount: 0,
      assistantTurn: 0,
      canGenerateNow: false,
      selectedTemplate: null,
      sessionFiles: ['outline.md'],
      chatSeed: { prompt: 'Ocean plastic', fileName: 'outline.md' },
      category: 'environment',
      duration_min: 5,
    }
  );

  // gathering Turn 1 always enforces canGenerateNow = false (Turn 1 hard rule)
  const turn1 = parseRestoredChatSession({
    chatSessionId: 'sess-g1',
    chatStage: 'gathering',
    assistantTurn: 1,
    canGenerateNow: true,
    selectedTemplate: { template_id: null, topic: null },
    category: 'technology',
    duration_min: 15,
    savedAt: now - 60_000,
  }, now);
  assert.equal(turn1.chatStage, 'gathering');
  assert.equal(turn1.chatHasScript, false);
  assert.equal(turn1.assistantTurn, 1);
  assert.equal(turn1.canGenerateNow, false);

  // gathering Turn 2+ restores canGenerateNow = true
  const turn2 = parseRestoredChatSession({
    chatSessionId: 'sess-g2',
    chatStage: 'gathering',
    assistantTurn: 2,
    canGenerateNow: true,
    category: 'technology',
    duration_min: 15,
    savedAt: now - 60_000,
  }, now);
  assert.equal(turn2.chatStage, 'gathering');
  assert.equal(turn2.assistantTurn, 2);
  assert.equal(turn2.canGenerateNow, true);

  // Expired (> 30 min TTL) -> null
  assert.equal(parseRestoredChatSession({ ...validGenerated, savedAt: now - 31 * 60 * 1000 }, now), null);
  // Inconsistent or unknown stage / missing session id -> null
  assert.equal(parseRestoredChatSession({ ...validGenerated, chatStage: 'generated', chatHasScript: false }, now), null);
  assert.equal(parseRestoredChatSession({ ...validGenerated, chatStage: 'idle', chatHasScript: false }, now), null);
  assert.equal(parseRestoredChatSession({ ...validGenerated, chatHasScript: false }, now), null);
  assert.equal(parseRestoredChatSession({ ...validGenerated, chatSessionId: '   ' }, now), null);
  // Non-object / null -> null
  for (const bad of [null, undefined, 'x', 123, {}]) {
    assert.equal(parseRestoredChatSession(bad, now), null);
  }
});

test('classifyRegenerateInput rejects empty or punctuation-only text without a file, allows real feedback or file', async () => {
  const { classifyRegenerateInput } = await mod;
  assert.deepEqual(classifyRegenerateInput({ text: '', hasFile: false }), { ok: false, reason: 'empty' });
  assert.deepEqual(classifyRegenerateInput({ text: '   \n\t ', hasFile: false }), { ok: false, reason: 'empty' });
  assert.deepEqual(classifyRegenerateInput({ text: '??? ... !!!', hasFile: false }), { ok: false, reason: 'no_request' });
  assert.deepEqual(classifyRegenerateInput({ text: '', hasFile: true }), { ok: true, reason: null });
  assert.deepEqual(classifyRegenerateInput({ text: 'Make the opening shorter', hasFile: false }), { ok: true, reason: null });
  assert.deepEqual(classifyRegenerateInput({ text: 'Ngắn hơn 30 giây', hasFile: false }), { ok: true, reason: null });
});

test('pickCooldownReply rotates across all 15 TEXT.script.regenCooldownReplies without immediate repeats', async () => {
  const { pickCooldownReply } = await mod;
  const { TEXT } = await i18n;
  const replies = TEXT.script.regenCooldownReplies;
  assert.equal(Array.isArray(replies), true);
  assert.equal(replies.length, 15);
  assert.equal(new Set(replies).size, 15);
  for (const tpl of replies) {
    assert.match(tpl, /\{wait\}/, tpl);
  }
  for (const key of [
    'regenRefuseEmpty',
    'regenRefuseNoRequest',
    'regenRefuseTooLongWords',
    'regenRefuseTooLongChars',
    'regenRefuseQuota',
    'regenRefuseGenerateQuota',
    'regenRefuseBusy',
  ]) {
    assert.equal(typeof TEXT.script[key], 'string', key);
    assert.ok(TEXT.script[key].trim().length > 0, key);
  }
  // Never repeats lastIndex even when randFn returns the exact same value
  const first = pickCooldownReply(replies, '12s', -1, () => 0);
  assert.equal(first.index, 0);
  assert.match(first.text, /12s/);
  const second = pickCooldownReply(replies, '9s', first.index, () => 0);
  assert.notEqual(second.index, first.index);
  assert.match(second.text, /9s/);
  assert.deepEqual(pickCooldownReply([], '5s'), { text: '', index: -1 });
});
