/**
 * Short relative labels for feed timestamps (no extra dependency).
 */
export function formatRelativeTime(iso: string): string {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";

  const sec = Math.round((Date.now() - t) / 1000);
  if (sec < 45) return "Just now";

  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

  const minutes = Math.round(sec / 60);
  if (minutes < 60) return rtf.format(-minutes, "minute");

  const hours = Math.round(minutes / 60);
  if (hours < 48) return rtf.format(-hours, "hour");

  const days = Math.round(hours / 24);
  if (days < 14) return rtf.format(-days, "day");

  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}
