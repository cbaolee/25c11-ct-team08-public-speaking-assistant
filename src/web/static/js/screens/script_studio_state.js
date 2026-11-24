/* Pure helpers for Script Studio (no imports, so Node can load this file in tests). */

/* Used only when the caller passes a broken limit; mirrors CONFIG.SCRIPT_TITLE_MAX_CHARS so a bad value
   cannot let an over-long AI title through. */
const DEFAULT_MAX_CHARS = 70;

/* A UTF-16 half of a pair with no partner (no lookbehind, so older Safari can run it; no nested quantifiers). */
const LONE_SURROGATE = /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?:^|[^\uD800-\uDBFF])[\uDC00-\uDFFF]/;
/* Control characters and any whitespace (\n, \t, NBSP...) become one space. \p{Cf} is kept on purpose: ZWJ joins emoji. */
const CONTROL_OR_SPACE = /[\p{Cc}\s]+/gu;
/* A title must show something: a letter, a digit or an emoji. */
const VISIBLE = /[\p{L}\p{N}\p{Extended_Pictographic}]/u;

/* Script Title from the job result (`result.title`, string or null), else `fallback`.
   The title is LLM output and the backend is not trusted either, so it is only accepted when it is clean and fits:
   a broken, invisible or over-long one is rejected, never cut (a cut would also split emoji or a combining mark).
   Line breaks and tabs are turned into a space first: the Script Name Dialog's input.value drops "\n" and would
   glue the words together, and the Script Reader's readTitle no longer matches the Script Bubble name if the title has "\n". */
export function pickScriptTitle(result, fallback, maxChars) {
  if (!result || typeof result !== 'object' || typeof result.title !== 'string') return fallback;
  const raw = result.title;
  if (typeof raw.isWellFormed === 'function' ? !raw.isWellFormed() : LONE_SURROGATE.test(raw)) return fallback;
  const title = raw.normalize('NFC').replace(CONTROL_OR_SPACE, ' ').trim();   // NFC first: the limit counts composed characters
  const limit = Number.isFinite(maxChars) && maxChars > 0 ? maxChars : DEFAULT_MAX_CHARS;
  if (!VISIBLE.test(title) || Array.from(title).length > limit) return fallback;   // by code point, like the saved-name limit
  return title;
}

/* Feedback sent with a Regenerate. Typed text is returned as typed (trimmed, never cut: the length limit is the caller's job).
   A blank one becomes a fixed request for a new version; `attempt` (1 for the first Regenerate of a chat session) is added from
   the second one on, because the backend caches by the feedback text and would otherwise hand back the old script.
   A bad `attempt` (not a whole number above 1) counts as the first. A non-string `text` counts as blank. */
export function regenerateFeedback(text, attempt) {
  const typed = typeof text === 'string' ? text.trim() : '';
  if (typed) return typed;
  const base = 'Write a fresh variation of this speech';
  return Number.isInteger(attempt) && attempt > 1 ? base + ' (variation ' + attempt + ').' : base + '.';
}

/* What the Composer's action button (#composerSend) is for. Once the chat session has a script (`hasScript` exactly true) it
   is the Regenerate button and the Composer text is the feedback; before that it is Send. `busy` (any truthy value) disables it
   and never changes the mode. A missing or broken `input` counts as "Send, enabled". */
export function composerActionState(input) {
  const { busy, hasScript } = input || {};
  return { mode: hasScript === true ? 'regenerate' : 'send', disabled: !!busy };
}
