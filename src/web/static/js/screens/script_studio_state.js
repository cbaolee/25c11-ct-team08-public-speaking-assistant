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

/* Validate Regenerate input before sending a request: requires either an attached file or a message
   with visible letters/digits (prevents blank or punctuation-only Regenerate spam). */
export function classifyRegenerateInput(input) {
  const { text, hasFile } = input || {};
  if (hasFile) return { ok: true, reason: null };
  const trimmed = typeof text === 'string' ? text.normalize('NFC').trim() : '';
  if (!trimmed) return { ok: false, reason: 'empty' };
  if (!/[\p{L}\p{N}]/u.test(trimmed)) return { ok: false, reason: 'no_request' };
  return { ok: true, reason: null };
}

/* Pick one varied cooldown refusal template, avoiding an immediate repeat of `lastIndex` when
   multiple templates are available, and interpolate `{wait}`. */
export function pickCooldownReply(templates, waitText, lastIndex = -1, randFn = Math.random) {
  const list = Array.isArray(templates) ? templates.filter(t => typeof t === 'string' && t.trim()) : [];
  const wait = typeof waitText === 'string' ? waitText : '';
  if (!list.length) return { text: '', index: -1 };
  let idx = 0;
  if (list.length > 1) {
    const raw = typeof randFn === 'function' ? Number(randFn()) : 0;
    const clamped = Number.isFinite(raw) ? Math.min(0.999999999, Math.max(0, raw)) : 0;
    const prev = Number.isInteger(lastIndex) && lastIndex >= 0 && lastIndex < list.length ? lastIndex : -1;
    if (prev >= 0) {
      idx = Math.floor(clamped * (list.length - 1));
      if (idx >= prev) idx += 1;
    } else {
      idx = Math.floor(clamped * list.length);
    }
  }
  return { text: list[idx].replace(/\{wait\}/g, wait), index: idx };
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

/* Show Generate when the session has no script yet and the backend allows it (`canGenerate === true`,
   including Turn 1 when Turn 1 already has enough detail). Legacy data without `canGenerate` falls back to Turn 2+. */
export function shouldShowGenerateButton(input) {
  const { hasScript, assistantTurn, canGenerate } = input || {};
  if (hasScript === true || canGenerate === false) return false;
  if (canGenerate === true) return true;
  const turn = Number(assistantTurn);
  return Number.isFinite(turn) && turn >= 2;
}

/* Typing "generate" / "done" / "tạo" / "xong" triggers generation ONLY during gathering when
   canGenerateNow === true, without an attached file, and before the first script exists. */
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

const VALID_RESTORABLE_STAGES = new Set(['picking_topic', 'gathering', 'generated']);

/* Validate and normalize a saved chat session from localStorage so F5 reload preserves the current
   stage (`picking_topic`, `gathering`, or `generated`) while the backend session stays within its
   30-minute sliding TTL. */
export function parseRestoredChatSession(raw, nowMs = Date.now(), ttlMs = DEFAULT_CHAT_SESSION_TTL_MS) {
  if (!raw || typeof raw !== 'object') return null;
  if (typeof raw.chatSessionId !== 'string' || !raw.chatSessionId.trim()) return null;
  let stage = null;
  if (typeof raw.chatStage === 'string' && VALID_RESTORABLE_STAGES.has(raw.chatStage)) {
    stage = raw.chatStage;
  } else if (raw.chatStage === undefined && raw.chatHasScript === true) {
    stage = 'generated';
  }
  if (!stage) return null;
  if (stage === 'generated' && raw.chatHasScript !== true) return null;
  const effTtl = Number.isFinite(ttlMs) && ttlMs > 0 ? ttlMs : DEFAULT_CHAT_SESSION_TTL_MS;
  const savedAt = Number(raw.savedAt);
  if (!Number.isFinite(savedAt) || (nowMs - savedAt) > effTtl || (savedAt - nowMs) > 60_000) return null;
  const chatHasScript = stage === 'generated';
  const regenCount = chatHasScript && Number.isInteger(raw.chatRegenCount) && raw.chatRegenCount >= 0 ? raw.chatRegenCount : 0;
  let assistantTurn = 0;
  let canGenerateNow = false;
  if (stage === 'gathering') {
    assistantTurn = Number.isInteger(raw.assistantTurn) && raw.assistantTurn >= 1 ? raw.assistantTurn : 1;
    canGenerateNow = assistantTurn >= 2 ? raw.canGenerateNow !== false : raw.canGenerateNow === true;
  } else if (stage === 'generated') {
    assistantTurn = Number.isInteger(raw.assistantTurn) && raw.assistantTurn >= 0 ? raw.assistantTurn : 0;
    canGenerateNow = true;
  }
  const sel = raw.selectedTemplate && typeof raw.selectedTemplate === 'object'
    ? {
        template_id: typeof raw.selectedTemplate.template_id === 'string' && raw.selectedTemplate.template_id ? raw.selectedTemplate.template_id : null,
        topic: typeof raw.selectedTemplate.topic === 'string' && raw.selectedTemplate.topic ? raw.selectedTemplate.topic : null,
      }
    : null;
  const seed = raw.chatSeed && typeof raw.chatSeed === 'object'
    ? Object.assign(
        {
          prompt: typeof raw.chatSeed.prompt === 'string' ? raw.chatSeed.prompt : '',
          fileName: typeof raw.chatSeed.fileName === 'string' ? raw.chatSeed.fileName : '',
        },
        raw.chatSeed.needsTopic === true ? { needsTopic: true } : null
      )
    : null;
  const sessionFiles = Array.isArray(raw.sessionFiles)
    ? raw.sessionFiles.filter(f => typeof f === 'string' && f.trim())
    : [];
  const category = typeof raw.category === 'string' ? raw.category : '';
  const dur = Number(raw.duration_min);
  const duration_min = [5, 10, 15, 20].includes(dur) ? dur : 5;
  return {
    chatSessionId: raw.chatSessionId.trim(),
    chatStage: stage,
    chatHasScript,
    chatRegenCount: regenCount,
    assistantTurn,
    canGenerateNow,
    selectedTemplate: sel,
    sessionFiles,
    chatSeed: seed,
    category,
    duration_min,
  };
}

/* ---------- Contract E v2.1: Gibberish / junk text detector (mirrors src/text_processing/input_guard.py) ----------
   Verified against the shared 75-case fixture `tests/fixtures/gibberish_vectors.json`. */
const GIB_KEYBOARD_ROWS = ['qwertyuiop', 'asdfghjkl', 'zxcvbnm'];
const GIB_RUN_MIN = 5;
const GIB_RUN_WHOLE_MIN = 4;
const GIB_REPEAT_CHAR_MIN = 5;
const GIB_LOW_VARIETY_MIN_LETTERS = 6;
const GIB_LOW_VARIETY_MAX_DISTINCT = 2;
const GIB_NO_VOWEL_MIN = 6;
const GIB_NO_VOWEL_MIN_ALL_CAPS = 8;
const GIB_REPEAT_TOKEN_MIN = 4;
const GIB_VOWELS = new Set(['a', 'e', 'i', 'o', 'u', 'y']);
const GIB_EXEMPT = new Set(['generate', 'done', 'tạo', 'xong', 'yes', 'no', 'ok', 'okay', 'sure']);
/* Contract E v2.1 whitespace: U+0009-U+000D + Unicode Zs/Zl/Zp (excludes U+001C-U+001F, U+0085, U+FEFF). */
const GIB_SPACE_RE = /[\t\n\v\f\r\p{Zs}\p{Zl}\p{Zp}]+/u;
const GIB_LETTER_RE = /^\p{L}$/u;
const GIB_CONTENT_RE = /^[\p{L}\p{N}]$/u;
const GIB_ANY_CONTENT_RE = /[\p{L}\p{N}]/u;
const GIB_ASCII_LETTERS_RE = /^[a-z]+$/;
const GIB_EXEMPT_END_PUNCT_RE = /[.!?]+$/;

function buildKeyboardRuns(minLen, maxLen) {
  const out = new Set();
  for (const row of GIB_KEYBOARD_ROWS) {
    const rev = Array.from(row).reverse().join('');
    for (const line of [row, rev]) {
      const upper = Math.min(maxLen, line.length);
      for (let len = minLen; len <= upper; len += 1) {
        for (let start = 0; start <= line.length - len; start += 1) {
          out.add(line.slice(start, start + len));
        }
      }
    }
  }
  return out;
}

const GIB_WHOLE_TOKEN_RUNS = buildKeyboardRuns(
  GIB_RUN_WHOLE_MIN,
  Math.max(...GIB_KEYBOARD_ROWS.map(r => r.length))
);
const GIB_INNER_RUNS = buildKeyboardRuns(GIB_RUN_MIN, GIB_RUN_MIN);

function gibCore(word) {
  const chars = Array.from(word);
  let start = 0, end = chars.length;
  while (start < end && !GIB_CONTENT_RE.test(chars[start])) start += 1;
  while (end > start && !GIB_CONTENT_RE.test(chars[end - 1])) end -= 1;
  return chars.slice(start, end).join('');
}

function gibHasRepeatedLetter(lowered) {
  let run = 0, prev = '';
  for (const ch of lowered) {
    if (!GIB_LETTER_RE.test(ch)) {
      run = 0;
    } else if (ch === prev) {
      run += 1;
    } else {
      run = 1;
    }
    if (run >= GIB_REPEAT_CHAR_MIN) return true;
    prev = ch;
  }
  return false;
}

function gibHasLowVariety(lettersArr) {
  return lettersArr.length >= GIB_LOW_VARIETY_MIN_LETTERS && new Set(lettersArr).size <= GIB_LOW_VARIETY_MAX_DISTINCT;
}

function gibLacksVowels(core, lettersStr) {
  const folded = lettersStr.normalize('NFD').replace(/\p{Mn}/gu, '');
  if (!GIB_ASCII_LETTERS_RE.test(folded)) return false;
  for (const ch of folded) {
    if (GIB_VOWELS.has(ch)) return false;
  }
  const isAllCaps = !Array.from(core).some(ch => GIB_LETTER_RE.test(ch) && ch !== ch.toUpperCase());
  return folded.length >= (isAllCaps ? GIB_NO_VOWEL_MIN_ALL_CAPS : GIB_NO_VOWEL_MIN);
}

function gibIsKeyboardRun(lowered, lettersArr, lettersStr) {
  if (lettersStr === lowered && GIB_WHOLE_TOKEN_RUNS.has(lowered)) return true;
  // Every longer run contains a 5-char run, so a fixed 5-char window keeps this linear O(n).
  for (let start = 0; start <= lettersArr.length - GIB_RUN_MIN; start += 1) {
    const win = lettersArr[start] + lettersArr[start + 1] + lettersArr[start + 2] + lettersArr[start + 3] + lettersArr[start + 4];
    if (GIB_INNER_RUNS.has(win)) return true;
  }
  return false;
}

function gibIsJunk(core) {
  const lowered = core.toLowerCase();
  const lettersArr = [];
  for (const ch of lowered) {
    if (GIB_LETTER_RE.test(ch)) lettersArr.push(ch);
  }
  const lettersStr = lettersArr.join('');
  return (
    gibHasRepeatedLetter(lowered)
    || gibHasLowVariety(lettersArr)
    || gibLacksVowels(core, lettersStr)
    || gibIsKeyboardRun(lowered, lettersArr, lettersStr)
  );
}

/* Reject gibberish/junk chat messages consistently with backend `input_guard.is_gibberish`.
   Empty text or requests with an attached file always pass (other validators handle empty input). */
export function validateMeaningfulText(text, opts = {}) {
  const { hasFile = false } = opts || {};
  if (hasFile || typeof text !== 'string') return { ok: true, reason: null };
  const words = text.normalize('NFC').split(GIB_SPACE_RE).filter(Boolean);
  if (!words.length) return { ok: true, reason: null };
  const normalized = words.join(' ');
  if (GIB_EXEMPT.has(normalized.toLowerCase().replace(GIB_EXEMPT_END_PUNCT_RE, ''))) {
    return { ok: true, reason: null };
  }
  if (!GIB_ANY_CONTENT_RE.test(normalized)) return { ok: false, reason: 'gibberish' };
  const cores = words.map(gibCore).filter(Boolean);
  if (cores.length >= GIB_REPEAT_TOKEN_MIN && new Set(cores.map(c => c.toLowerCase())).size === 1) {
    return { ok: false, reason: 'gibberish' };
  }
  const lettered = cores.filter(core => Array.from(core).some(ch => GIB_LETTER_RE.test(ch)));
  if (lettered.length && lettered.every(gibIsJunk)) return { ok: false, reason: 'gibberish' };
  return { ok: true, reason: null };
}

/* ---------- Contract D: Sentence-level citation pill & deduplication helpers ---------- */

export function dedupeCitationSources(sources) {
  if (!Array.isArray(sources) || !sources.length) return [];
  const seen = new Set();
  const out = [];
  for (const s of sources) {
    if (!s || typeof s !== 'object') continue;
    const pageNum = Number.isInteger(s.page) && s.page > 0 ? s.page : 0;
    const key = [
      typeof s.source_kind === 'string' ? s.source_kind : '',
      typeof s.source_msg_id === 'string' ? s.source_msg_id : '',
      typeof s.heading === 'string' ? s.heading.trim() : '',
      pageNum,
    ].join('|');
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(s);
  }
  return out;
}

export function formatCitationSourceLabel(source, pageFormatter) {
  if (!source || typeof source !== 'object') return 'cited';
  const rawHeading = typeof source.heading === 'string' ? source.heading.trim() : '';
  const cleanHeading = rawHeading && !/^Page \d+ Overview$/i.test(rawHeading) ? rawHeading : '';
  const hasPage = Number.isInteger(source.page) && source.page > 0;
  const pageText = hasPage
    ? (typeof pageFormatter === 'function' ? pageFormatter(source.page) : 'p. ' + source.page)
    : '';
  const fallbackFile = typeof source.source_file === 'string' ? source.source_file.trim() : '';
  const title = cleanHeading || (hasPage ? '' : fallbackFile);
  if (title && pageText) return title + ' · ' + pageText;
  if (title) return title;
  if (pageText) return pageText;
  return 'cited';
}

export function formatCitationPill(sources, pageFormatter, maxLabelChars = 28) {
  const list = dedupeCitationSources(sources);
  if (!list.length) return { primaryLabel: '', extraCount: 0, sources: [] };
  const full = formatCitationSourceLabel(list[0], pageFormatter);
  const cap = Number.isFinite(maxLabelChars) && maxLabelChars >= 4 ? Math.floor(maxLabelChars) : 28;
  const chars = Array.from(full);
  const primaryLabel = chars.length > cap ? chars.slice(0, cap - 1).join('').trimEnd() + '…' : full;
  return { primaryLabel, extraCount: Math.max(0, list.length - 1), sources: list };
}
