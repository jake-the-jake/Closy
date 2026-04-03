export function resolveAuthorRouteUserId(
  id: string | string[] | undefined,
): string | null {
  if (id === undefined) return null;
  const raw = Array.isArray(id) ? id[0] : id;
  if (raw == null || raw === "") return null;
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}
