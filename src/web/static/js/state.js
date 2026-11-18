/* Tunable values. Defaults below; GET /api/config (app_constants.toml [web]) overrides them in main.js. */
export const CONFIG = {
  RETRY: { minRatio: 0.30, wordMax: 6, sentenceMax: 30, clipPad: 0.15 }, // fallback mirrors app_constants.toml [retry]
  OWN_MAX_WORDS: 1500,                 // max words in "write my own text"
  BASELINE_MIN_SECONDS: 10,            // shortest baseline accepted (the backend also rejects audio with too little speech)
  BASELINE_SECONDS: 30,                // length of the baseline recording (lower it for quick demos)
  SPEAKING_WPM_FOR_ESTIMATE: 145,      // midpoint of the 130-160 target, only used for "about 0:25" hints
  FOLLOW_LEAD_S: 1.0,                  // seconds before the highlight reaches the first sentence while recording
  FOLLOW_GAP_S: 0.5,                   // pause added after each sentence (matches a natural stop at a full stop)
  HISTORY_MAX_PAGES: 5,                // 5 pages x 20 = the newest 100 sessions on Home and History
  HISTORY_PAGE_SIZE: 20,               // sessions per /api/sessions page
};



/* ---------- state ---------- */
export const S = {
  view: 'landing', screen: 'home', from: 'home', authMode: 'in',
  scrollPos: {}, scrollKey: null,   // where each screen was last scrolled to (nav.js go)
  user: null, profile: null, consent: false, baseline: null, avatar: null,
  texts: { mine: null, sample: null, own: null }, pickerTab: 'mine', sampleN: 0,
  chatFile: null, lastReq: null, chatBusy: false,
  audio: null, rec: null, brec: null, voiceTab: 'rec',
  sessions: [], currentSession: null, nextId: 1,
  play: { t: 0, on: false, iv: null },
  evaluation: null, modal: [], confirmCb: null, afterConsent: null, onDeny: null, pmFirst: false,
  signupDraft: null, choosing: true, followWpm: 145, baselineGate: null, grec: null, follow: null, auth: null
};
/* Screen renderers: each screens/*.js module registers RENDER.<screen> when it loads. */
export const RENDER = {};
