export function coachNoteMode(s) {
  if (!s || !s.sc) return 'none';
  if (s.remote && !s.demo && (s.sc.status === 'ok' || s.sc.status === 'insufficient_audio')) return 'remote';
  return s.sc.status === 'insufficient_audio' ? 'client-rule' : 'none';
}
