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

/* Retry-After as plain seconds; its other form (an HTTP date) is not read. */
const DELAY_SECONDS = /^\d+(\.\d+)?$/;
/* `reason` of a 429 from POST /api/generate-script: which runs it holds and the message that names it. */
const RATE_REASONS = {
  cooldown: { scope: 'regenerate', textKey: 'script.errRateCooldown' },
  regenerate_quota: { scope: 'regenerate', textKey: 'script.errRateRegen' },
  generate_quota: { scope: 'all', textKey: 'script.errRateGenerate' },
  job_running: { scope: 'all', textKey: 'script.errRateBusy' },
};
/* A positive wait rounded up to whole seconds; anything else is 0. */
const wholeSeconds = value => (Number.isFinite(value) && value > 0 ? Math.ceil(value) : 0);

/* Seconds a 429 asks to wait: `body.retry_after_s`, else the Retry-After header; 0 when neither is usable. */
export function parseRetryAfterS(body, headerValue) {
  const fromBody = wholeSeconds(body && body.retry_after_s);
  if (fromBody) return fromBody;
  const header = typeof headerValue === 'string' ? headerValue.trim() : '';
  return DELAY_SECONDS.test(header) ? wholeSeconds(Number(header)) : 0;
}

/* "5s", "1m", "1m 30s"; '' when there is nothing to wait for. */
export function formatRetryWait(seconds) {
  const total = wholeSeconds(seconds), m = Math.floor(total / 60), s = total % 60;
  return [m ? m + 'm' : '', s ? s + 's' : ''].filter(Boolean).join(' ');
}

/* Whole seconds from `nowMs` until `untilMs`, never negative. */
export function secondsLeft(untilMs, nowMs) {
  return wholeSeconds((untilMs - nowMs) / 1000);
}

/* 'regenerate' or 'all' runs. Without a known reason, only the kind of run that was refused is held. */
export function rateLimitScope(reason, again) {
  if (Object.hasOwn(RATE_REASONS, reason)) return RATE_REASONS[reason].scope;
  return again ? 'regenerate' : 'all';
}

export function rateLimitTextKey(reason) {
  return Object.hasOwn(RATE_REASONS, reason) ? RATE_REASONS[reason].textKey : 'script.errRateWait';
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
   and never changes the mode. `cooldownLeftS` above 0 disables Regenerate only, never Send.
   A missing or broken `input` counts as "Send, enabled". */
export function composerActionState(input) {
  const { busy, hasScript, cooldownLeftS } = input || {};
  const cooling = hasScript === true && Number.isFinite(cooldownLeftS) && cooldownLeftS > 0;
  return { mode: hasScript === true ? 'regenerate' : 'send', disabled: !!busy || cooling };
}
