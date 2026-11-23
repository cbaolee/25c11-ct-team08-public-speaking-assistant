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
