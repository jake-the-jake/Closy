/**
 * Normalise `useLocalSearchParams().id` (string vs array, URL decoding) for wardrobe routes.
 */
export function resolveClothingItemRouteId(
  id: string | string[] | undefined,
): string | undefined {
  if (id === undefined) return undefined;
  const raw = Array.isArray(id) ? id[0] : id;
  if (raw == null || raw === "") return undefined;
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}
