/* Tunable values. Defaults below; GET /api/config (app_constants.toml [web]) overrides them in main.js. */
export const CONFIG = {
  auth: { otp_length: 6, resend_cooldown_s: 60, unconfirmed_ttl_min: 60 }, // fallback mirrors app_constants.toml [auth] and SQL 0009
  EVAL_JOB: { pollMs: 700, maxWaitS: 360, weights: { upload: 5, decode: 10, vad: 10, stt: 35, align: 10, fluency: 5, pitch: 10, semantic: 10, save: 5 }, tauS: 20, closeDelayMs: 400, announcePct: 25 }, // fallback mirrors app_constants.toml [evaluate_job]
  PART_GOOD_MIN: 85,                   // a part score from here counts as good (Overview, key numbers, coach note)
  RETENTION: { insufficientDays: 7 }, // fallback mirrors app_constants.toml [retention] insufficient_days and SQL pg_cron
  COACH: { maxFocus: 3 },             // fallback mirrors app_constants.toml [coach] max_focus_items
  RETRY: { minRatio: 0.30, wordMax: 6, sentenceMax: 30, clipPad: 0.15 }, // fallback mirrors app_constants.toml [retry]
  OWN_MAX_WORDS: 1500,                 // max words in "write my own text"
  BASELINE_MIN_SECONDS: 10,            // shortest baseline accepted (the backend also rejects audio with too little speech)
  MAX_AUDIO_SECONDS: 1920,              // practice recording stops itself here (server: [audio] max_audio_seconds)
  BASELINE_SECONDS: 30,                // length of the baseline recording (lower it for quick demos)
  SPEAKING_WPM_FOR_ESTIMATE: 145,      // midpoint of the 130-160 target, only used for "about 0:25" hints
  FOLLOW_LEAD_S: 1.0,                  // seconds before the highlight reaches the first sentence while recording
  FOLLOW_GAP_S: 0.5,                   // pause added after each sentence (matches a natural stop at a full stop)
  HISTORY_MAX_PAGES: 5,                // 5 pages x 20 = the newest 100 sessions on Home and History
  HISTORY_PAGE_SIZE: 20,               // sessions per /api/sessions page
  FOLLOW_WPM_MIN: 60,                  // lowest speed a user may pick in Settings, words per minute
  FOLLOW_WPM_MAX: 240,                 // highest speed a user may pick in Settings, words per minute
  FOLLOW_WPM_MIN_CHOOSE: 100,          // slider minimum until the user picks their own, words per minute
  FOLLOW_WPM_MAX_CHOOSE: 180,          // slider maximum until the user picks their own, words per minute
  FOLLOW_WPM_STEP: 5,                  // slider step, words per minute
  FOLLOW_WPM_DEFAULT: 145,             // used when the profile has no follow_wpm
  FOLLOW_AUTO_WEIGHT: 0.4,             // share of the measured speed mixed in at each tap (auto speed)
  FOLLOW_AUTO_MIN_S: 1.5,                // taps closer in time are not measured, seconds
  FOLLOW_AUTO_MIN_WORDS: 3,            // taps closer in words are not measured
  FOLLOW_AUTO_MAX_AHEAD: 4,            // a tap further ahead (sentences) is a skip, not measured
  FOLLOW_WPM_SAVE_DELAY_MS: 800,       // wait after the last slider move before PATCH /api/profile, in ms
  CHAT_HISTORY_MAX_MESSAGES: 20,       // most Script Studio chat messages kept in localStorage
  COMPOSER_MAX_WORDS: 2000,            // most words in one Script Studio message
  COMPOSER_MAX_LINES: 5.5,             // the Script Studio text box grows up to this many lines
  SCRIPT_POLL_INTERVAL_MS: 650,        // wait between two status checks of a script being generated
  EVALUATE_BACKGROUND_AFTER_MS: 5000,  // after this the evaluation goes on in the background and the user is sent Home
  EVAL_COUNT_STEP_MS: 30,              // the shown percent moves one step per tick toward the real progress
  EVAL_DOCK_HOLD_MS: 3000,             // the progress dock stays at 100% this long, then slides out
  MAX_SAVED_SCRIPTS: 10,               // saved scripts per user (app_constants.toml [storage])
  SCRIPT_TITLE_MAX_CHARS: 70,          // longest saved script name ([storage])
  MAX_PDF_SIZE_BYTES: 26214400,        // largest PDF for Script Studio ([script], 25 MB)
  MAX_PDF_PAGES: 10,                   // most PDF pages ([script])
  MAX_TURN_TEXT_CHARS: 18000,          // most NFC characters in one Script Studio turn ([script])
  MAX_TEXT_FILE_BYTES: 2097152,        // largest .md / .txt upload ([script], 2 MB)
  MAX_TEXT_FILE_WORDS: 15000,          // most words in an uploaded .md / .txt file ([script])
  ETA_BUFFER_S: 10,                    // safety buffer added to Script Studio stage estimates ([script])
  SCRIPT_TELEMETRY: {
    etaBufferS: 10,
    chatStepDurationsS: { validating_input: 0.5, moderating: 1.0, matching_templates: 1.5, analyzing_slots: 1.0, updating_context: 0.5, compacting_context: 2.5, analyzing_with_llm: 3.5 },
    generateStageDurationsS: { validating_input: 1.0, extracting: 2.0, moderating: 1.5, generating: 8.0, validating_output: 1.0 },
  },
};



/* ---------- state ---------- */
export const S = {
  view: 'landing', screen: 'home', from: 'home', authMode: 'in',
  scrollPos: {}, scrollKey: null,   // where each screen was last scrolled to (nav.js go)
  user: null, profile: null, consent: false, baseline: null, avatar: null,
  texts: { mine: null, sample: null, own: null }, pickerTab: 'mine', sampleN: 0,
  chatFile: null, chatBusy: false,
  chatHistory: [],
  savedScripts: null, savedScriptTotal: 0, ownSaved: null, nameDialog: null,
  audio: null, rec: null, brec: null, voiceTab: 'rec',
  sessions: [], currentSession: null, nextId: 1,
  play: { t: 0, on: false, iv: null },
  evaluation: null, modal: [], confirmCb: null, afterConsent: null, pmFirst: false,
  signupDraft: null, choosing: true, followWpm: 145, baselineGate: null, grec: null, follow: null, auth: null
};
/* Screen renderers: each screens/*.js module registers RENDER.<screen> when it loads. */
export const RENDER = {};
