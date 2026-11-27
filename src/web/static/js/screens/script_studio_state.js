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

const DEFAULT_MAX_TURN_WORDS = 2000;
const DEFAULT_MAX_TURN_CHARS = 18000;
const DEFAULT_ETA_BUFFER_S = 10;
const DEFAULT_CHAT_SESSION_TTL_MS = 30 * 60 * 1000;
const VALID_STEP_STATES = new Set(['pending', 'running', 'done', 'skipped']);
const GENERATE_KEYWORD_SET = new Set(['generate', 'done', 'tạo', 'xong']);
const HTML_ESC_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

function escapeHtml(raw) {
  return String(raw).replace(/[&<>"']/g, ch => HTML_ESC_MAP[ch]);
}

/* Safely render inline **bold** key requests as <strong class="key-req">...</strong>.
   All raw text is HTML-escaped BEFORE replacing **...** spans, so untrusted text can never inject markup.
   Unmatched '*', empty '****', whitespace-only '**  **', or spans crossing a newline remain literal text. */
export function formatReplyMarkup(raw) {
  if (typeof raw !== 'string' || !raw) return '';
  const safe = escapeHtml(raw);
  return safe.replace(/\*{4,}|\*\*([^\s*](?:[^*\r\n]*?[^\s*])?)\*\*/g, (match, inner) => (inner ? '<strong class="key-req">' + inner + '</strong>' : match));
}

/* Turn 1 (assistant_turn === 1 or can_generate === false) never shows a Generate button;
   from Turn 2 onward every gathering reply shows the Generate action until the session produces its first script. */
export function shouldShowGenerateButton(input) {
  const { hasScript, assistantTurn, canGenerate } = input || {};
  if (hasScript === true || canGenerate === false) return false;
  const turn = Number(assistantTurn);
  if (turn === 1) return false;
  return canGenerate === true || (Number.isFinite(turn) && turn >= 2);
}

/* Typing "generate" / "done" / "tạo" / "xong" triggers generation ONLY during gathering from Turn 2 onward
   (when canGenerateNow === true), without an attached file, and before the first script exists. */
export function canTriggerGenerateKeyword(input) {
  const { stage, hasScript, canGenerateNow, hasFile, text } = input || {};
  if (hasScript === true || stage !== 'gathering' || canGenerateNow !== true || hasFile) return false;
  if (typeof text !== 'string') return false;
  const norm = text.normalize('NFC').trim().toLowerCase();
  return GENERATE_KEYWORD_SET.has(norm);
}

/* Per-turn text validation matching Python's `validate_turn_text_length` (NFC code points first, then words). */
export function validateTurnText(text, limits) {
  if (typeof text !== 'string' || !text) return { ok: true, chars: 0, words: 0 };
  const { maxWords, maxChars } = limits || {};
  const effChars = Number.isFinite(maxChars) && maxChars > 0 ? maxChars : DEFAULT_MAX_TURN_CHARS;
  const effWords = Number.isFinite(maxWords) && maxWords > 0 ? maxWords : DEFAULT_MAX_TURN_WORDS;
  const norm = text.normalize('NFC');
  const chars = Array.from(norm).length;
  const trimmed = norm.trim();
  const words = trimmed ? trimmed.split(/\s+/).length : 0;
  if (chars > effChars) return { ok: false, reason: 'chars', limit: effChars, chars, words };
  if (words > effWords) return { ok: false, reason: 'words', limit: effWords, chars, words };
  return { ok: true, chars, words };
}

/* Normalize step telemetry list from backend (`[{key, state}]`) or build initial steps from `fallbackKeys`. */
export function normalizeTelemetrySteps(steps, fallbackKeys) {
  if (Array.isArray(steps) && steps.length) {
    const clean = steps
      .filter(s => s && typeof s.key === 'string' && s.key)
      .map(s => ({ key: s.key, state: VALID_STEP_STATES.has(s.state) ? s.state : 'pending' }));
    if (clean.length) return clean;
  }
  if (!Array.isArray(fallbackKeys) || !fallbackKeys.length) return [];
  return fallbackKeys.map((key, idx) => ({ key: String(key), state: idx === 0 ? 'running' : 'pending' }));
}

/* Compute buffered remaining seconds (+10s buffer included). Counts down smoothly between polls while active,
   never dropping below 1s until `status` or `stage` reaches `completed` / `failed` (which returns 0). */
export function computeBufferedRemainingS(telemetry, elapsedSinceSyncS = 0, fallbackDurations = null, defaultBufferS = DEFAULT_ETA_BUFFER_S) {
  const t = telemetry || {};
  const status = t.status || '';
  const stage = t.stage || '';
  if (status === 'completed' || status === 'failed' || stage === 'completed' || stage === 'failed') return 0;
  const elapsed = Number.isFinite(elapsedSinceSyncS) && elapsedSinceSyncS > 0 ? elapsedSinceSyncS : 0;
  let base = null;
  if (typeof t.estimated_remaining_s === 'number' && Number.isFinite(t.estimated_remaining_s)) {
    if (t.estimated_remaining_s <= 0) return 0;
    base = t.estimated_remaining_s;
  } else if (Array.isArray(t.steps) && t.steps.length) {
    const durs = fallbackDurations && typeof fallbackDurations === 'object' ? fallbackDurations : {};
    const rem = t.steps.reduce((acc, s) => (s && (s.state === 'pending' || s.state === 'running') ? acc + (Number(durs[s.key]) || 1) : acc), 0);
    if (rem <= 0) return 0;
    const buf = Number.isFinite(t.eta_buffer_s) ? t.eta_buffer_s : (Number.isFinite(defaultBufferS) ? defaultBufferS : DEFAULT_ETA_BUFFER_S);
    base = rem + buf;
  }
  if (base === null) return 0;
  return Math.max(1, Math.ceil(base - elapsed));
}

/* Validate and normalize a saved generated-script chat session from localStorage so F5 reload
   keeps Regenerate mode alive while the backend session is within its 30-minute sliding TTL. */
export function parseRestoredChatSession(raw, nowMs = Date.now(), ttlMs = DEFAULT_CHAT_SESSION_TTL_MS) {
  if (!raw || typeof raw !== 'object') return null;
  if (raw.chatHasScript !== true) return null;
  if (typeof raw.chatSessionId !== 'string' || !raw.chatSessionId.trim()) return null;
  const effTtl = Number.isFinite(ttlMs) && ttlMs > 0 ? ttlMs : DEFAULT_CHAT_SESSION_TTL_MS;
  const savedAt = Number(raw.savedAt);
  if (!Number.isFinite(savedAt) || (nowMs - savedAt) > effTtl || (savedAt - nowMs) > 60_000) return null;
  const regenCount = Number.isInteger(raw.chatRegenCount) && raw.chatRegenCount >= 0 ? raw.chatRegenCount : 0;
  const sel = raw.selectedTemplate && typeof raw.selectedTemplate === 'object'
    ? {
        template_id: typeof raw.selectedTemplate.template_id === 'string' && raw.selectedTemplate.template_id ? raw.selectedTemplate.template_id : null,
        topic: typeof raw.selectedTemplate.topic === 'string' && raw.selectedTemplate.topic ? raw.selectedTemplate.topic : null,
      }
    : null;
  const seed = raw.chatSeed && typeof raw.chatSeed === 'object'
    ? {
        prompt: typeof raw.chatSeed.prompt === 'string' ? raw.chatSeed.prompt : '',
        fileName: typeof raw.chatSeed.fileName === 'string' ? raw.chatSeed.fileName : '',
      }
    : null;
  const sessionFiles = Array.isArray(raw.sessionFiles)
    ? raw.sessionFiles.filter(f => typeof f === 'string' && f.trim())
    : [];
  const category = typeof raw.category === 'string' ? raw.category : '';
  const dur = Number(raw.duration_min);
  const duration_min = [5, 10, 15, 20].includes(dur) ? dur : 5;
  return {
    chatSessionId: raw.chatSessionId.trim(),
    chatStage: 'generated',
    chatHasScript: true,
    chatRegenCount: regenCount,
    selectedTemplate: sel,
    sessionFiles,
    chatSeed: seed,
    category,
    duration_min,
  };
}
