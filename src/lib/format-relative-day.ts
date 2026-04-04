const DAY_MS = 86_400_000;

/** Compact relative label for a past timestamp (calendar-day style, not precise clocks). */
export function formatRelativeDay(ts: number, nowMs: number = Date.now()): string {
  const d = Math.floor((nowMs - ts) / DAY_MS);
  if (d <= 0) return "today";
  if (d === 1) return "yesterday";
  if (d < 14) return `${d} days ago`;
  const weeks = Math.floor(d / 7);
  if (weeks < 8) return `${weeks} wk ago`;
  const months = Math.floor(d / 30);
  return `${months} mo ago`;
}
