/* Saved-script duplicate errors (409 from POST/PATCH /api/scripts) -> the i18n keys of their notice.
   Plain script (no imports) so tests/web can load it with require(). */
(function (root) {
  'use strict';
  const NOTICES = {
    script_duplicate_body: { title: 'saved.dupBodyT', message: 'saved.dupBodyMsg' },
    script_duplicate_title: { title: 'saved.dupTitleT', message: 'saved.dupTitleMsg' }
  };
  function duplicateNotice(code) { return NOTICES[code] || null; }
  const api = { duplicateNotice };
  root.ScriptDuplicate = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
