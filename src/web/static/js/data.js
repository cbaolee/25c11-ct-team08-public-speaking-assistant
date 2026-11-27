import { T } from './i18n.js';
import { S } from './state.js';

/* =====================================================================
   NON-UI DATA (practice scripts, banned words, mock take profiles)
   ===================================================================== */
/* Generic practice texts for the Sample tab (not tied to a topic). */
export const SAMPLE_TEXTS = [
  "Honourable guests, fellow citizens, welcome to tonight's public forum. Our community faces real choices about education, jobs and the future of our city. Tonight we will listen first, debate respectfully, and look for common ground. Every voice in this room matters, so please take your seats and let us begin.",
  "Good morning, and thank you for joining this youth policy dialogue. Democracy works best when people take part, ask hard questions and stay open to new ideas. Over the next hour, our speakers will share their plans, and you will have the chance to challenge them. Let us keep the conversation honest and kind.",
  "Good evening and welcome to today's news briefing. We begin with the stories shaping our week: rising energy prices, a new transport plan for the city, and a record number of students going abroad. Stay with us as we break down the facts, hear from experts, and explain what it all means for you.",
  "Hello everyone, and welcome to our weekly current affairs talk. This week the world is watching climate talks, technology laws and a major sports final. We will separate the headlines from the facts, so you can leave today better informed and ready to join the discussion.",
  "Ladies and gentlemen, welcome to the opening night of our spring art exhibition. Each painting, sculpture and photograph you will see tonight tells a story about courage, memory and hope. Please take your time, ask the artists questions, and let colour and light guide you through the gallery.",
  "Good evening, art lovers, and welcome to tonight's performance. Music, dance and poetry will fill this hall with stories from every corner of our community. Silence your phones, open your hearts, and enjoy the magic of live art. The curtain rises in just a moment.",
  "Dear friends and generous supporters, welcome to our annual charity gala. Tonight, every ticket, every song and every smile helps children in rural areas return to school. Thank you for believing that small acts of kindness can change a whole life. Let us make tonight unforgettable.",
  "Good evening, everyone, and thank you for joining our volunteer day kickoff. Today we will plant trees, pack food boxes and visit the senior home down the road. You do not need special skills, only a warm heart and a willing hand. Let us get started together!"
];

/* =====================================================================
   SCORING CONSTANTS (ADR-003)
   ===================================================================== */
export const ADR = {
  wpmLo: 130, wpmHi: 160, wpmPenalty: 2.5,
  pauseMin: 0.25, hesMin: 0.5, forgotMin: 1.2,
  fillerFull: 2, fillerZero: 10, fillerWarn: 4,
  nearWeight: 5, pitchFull: 6, pitchZero: 2, monotone: 4,
  cosine: 0.82, minVoiced: 0.30,
  weights: { A: 0.40, F: 0.30, P: 0.20, S: 0.10 },
  minSessionsForDelta: 6
};
export const mean = a => (a.length ? a.reduce((s, x) => s + x, 0) / a.length : 0);

export function tokenize(text) {
  const sentences = (text.match(/[^.!?]+[.!?]*["')]*\s*/g) || [text]).map(s => s.trim()).filter(Boolean);
  const words = [];
  sentences.forEach((s, si) => {
    const parts = s.split(/\s+/).filter(Boolean);
    parts.forEach((raw, wi) => words.push({
      raw, norm: raw.toLowerCase().replace(/[^a-z0-9']/g, ''), si,
      last: wi === parts.length - 1,
      endSent: /[.!?]["')]*$/.test(raw), endClause: /[,;:]$/.test(raw)
    }));
  });
  return { sentences, words };
}

/* score shown through the same rule as the backend (display_round: 1 decimal, half-up); null -> N/A. fx = other measures. */
export const sh = v => { const r = EvaluateClient.displayRound(v); return r == null ? T('common.na') : r.toFixed(1); };
export const fx = (v, d) => (v == null || !Number.isFinite(v) ? T('common.na') : v.toFixed(d));
export const hasBase = sc => (sc.flags ? !sc.flags.includes('no_baseline') : !!S.baseline);
/* Next-step advice: deterministic templates over the lowest sub-scores (the LLM never grades). */
export function adviceList(sc, limit, below) {
  const items = [
    { key: 'wpm', v: sc.Fwpm, area: 'areaWpm', val: Math.round(sc.wpm) },
    { key: 'pause', v: sc.Fpause, area: 'areaPause', val: fx(sc.H, 1) },
    { key: 'filler', v: sc.Ffiller, area: 'areaFiller', val: fx(sc.R, 1) },
    { key: 'accuracy', v: sc.A, area: 'areaAccuracy', val: sc.sub + sc.del },
    { key: 'clarity', v: sc.Pclar, area: 'areaClarity', val: sc.near },
    { key: 'pitch', v: sc.Ppitch, area: 'areaPitch', val: fx(sc.Rst, 1) },
    { key: 'semantic', v: sc.S, area: 'areaSemantic', val: sc.nSent == null ? T('common.na') : sc.nSent - sc.cosOk }
  ];
  return items.filter(x => x.v != null && x.v < (below == null ? 85 : below)).sort((a, b) => a.v - b.v).slice(0, limit)
    .map(x => ({ key: x.key, v: x.v, area: T('report.' + x.area), text: T('report.adv_' + x.key, { v: x.val }) }));
}

/* Progress (ADR-003): mean of the last 3 scored sessions minus the 3 before; needs >= 6. */
export function progressDelta(sessions) {
  const sc = sessions.filter(s => s.sc.status === 'ok').sort((a, b) => a.ts - b.ts).map(s => s.sc.overall).filter(v => v != null);
  if (sc.length < ADR.minSessionsForDelta) return { d: null, n: sc.length };
  return { d: mean(sc.slice(-3)) - mean(sc.slice(-6, -3)), n: sc.length };
}

export function paceWindows(an) {
  const dur = an.dur, SZ = 5, nWin = Math.max(1, Math.floor(dur / SZ));
  const out = [];
  for (let k = 0; k < nWin; k++) {
    const ws = k * SZ, we = k === nWin - 1 ? dur : ws + SZ;
    const count = an.words.filter(w => w.status !== 'missing' && w.start >= ws && w.start < we).length;
    out.push({ label: Math.round(ws) + '-' + Math.round(we) + 's', wpm: count / ((we - ws) / 60) });
  }
  return out;
}
