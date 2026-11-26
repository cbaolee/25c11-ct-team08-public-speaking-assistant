const PREFIX = 'psa.schedule.ai.v1.';
const object = value => value && typeof value === 'object' && !Array.isArray(value);
export function pickTopic(topics, durationMin, rand = Math.random) {
  const list = topics.filter(topic => topic.duration_min === durationMin);
  return list.length ? list[Math.floor(rand() * list.length)] : null;
}
export function readAiCache(storage, userId) {
  try { const value = JSON.parse(storage.getItem(PREFIX + userId)); return object(value) ? value : {}; } catch (_) { return {}; }
}
export function writeAiCache(storage, userId, cache) {
  try { storage.setItem(PREFIX + userId, JSON.stringify(cache)); return true; } catch (_) { return false; }
}
export function getAiScript(cache, occKey, now) {
  const entry = Object.hasOwn(cache, occKey) ? cache[occKey] : null;
  return object(entry) && Number.isFinite(entry.closes_at) && now < entry.closes_at ? { ...entry } : null;
}
export function putAiScript(cache, occKey, entry) { return { ...cache, [occKey]: { ...entry } }; }
export function removeAiScript(cache, occKey) { const result = { ...cache }; delete result[occKey]; return result; }
export function pruneAiCache(cache, now) { return Object.fromEntries(Object.entries(cache).filter(([key]) => getAiScript(cache, key, now))); }
