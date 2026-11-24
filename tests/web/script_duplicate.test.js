'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { duplicateNotice } = require('../../src/web/static/js/script_duplicate.js');

const I18N = fs.readFileSync(path.join(__dirname, '../../src/web/static/js/i18n.js'), 'utf8');
const hasKey = key => I18N.includes(' ' + key.split('.')[1] + ':');   // keys sit after a space: "  dupBodyT: '...'"

test('the two duplicate codes open two different notices', () => {
  const body = duplicateNotice('script_duplicate_body'), title = duplicateNotice('script_duplicate_title');
  assert.deepEqual(body, { title: 'saved.dupBodyT', message: 'saved.dupBodyMsg' });
  assert.deepEqual(title, { title: 'saved.dupTitleT', message: 'saved.dupTitleMsg' });
  assert.notEqual(body.title, title.title); assert.notEqual(body.message, title.message);
});
test('other codes and the old code open no duplicate notice', () => {
  for (const code of ['script_duplicate', 'script_limit_reached', 'content_rejected', undefined, null]) assert.equal(duplicateNotice(code), null);
});
test('every notice key exists in i18n.js', () => {
  for (const code of ['script_duplicate_body', 'script_duplicate_title']) {
    const n = duplicateNotice(code);
    assert.ok(hasKey(n.title), n.title); assert.ok(hasKey(n.message), n.message);
  }
});
