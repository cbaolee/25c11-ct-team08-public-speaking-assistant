export function monthGrid(year, month) {
  const first = new Date(year, month, 1);
  first.setDate(1 - ((first.getDay() + 6) % 7));
  return Array.from({ length: 42 }, (_, i) => {
    const d = new Date(first.getFullYear(), first.getMonth(), first.getDate() + i);
    return `${String(d.getFullYear()).padStart(4, '0')}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  });
}

export function formatCountdown(ms) {
  const minutes = Math.max(0, Math.floor(ms / 60000));
  const hours = Math.floor(minutes / 60);
  return hours ? `${hours} h ${minutes % 60} min` : `${minutes} min`;
}
export function streakLabel(n, noStreak, streak) { return n ? streak.replace('{n}', String(n)) : noStreak; }
