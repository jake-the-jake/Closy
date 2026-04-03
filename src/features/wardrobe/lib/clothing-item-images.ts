import type {
  ClothingItem,
  ClothingItemImageRefs,
} from "@/features/wardrobe/types/clothing-item";

function trimOrEmpty(s: string | undefined | null): string {
  return (s ?? "").trim();
}

/** Grid, cards, small previews — square thumbnail when available. */
export function clothingItemThumbnailUri(item: ClothingItem): string {
  const fromRefs = trimOrEmpty(item.imageRefs?.thumbnail);
  if (fromRefs) return fromRefs;
  const display = trimOrEmpty(item.imageRefs?.display);
  if (display) return display;
  return trimOrEmpty(item.imageUrl);
}

/** Detail / edit preview — aspect-preserved display derivative or best fallback. */
export function clothingItemDisplayUri(item: ClothingItem): string {
  const fromRefs = trimOrEmpty(item.imageRefs?.display);
  if (fromRefs) return fromRefs;
  return trimOrEmpty(item.imageUrl);
}

/** Full bleed original for future zoom / reprocess / AI (HTTP only). */
export function clothingItemOriginalUri(item: ClothingItem): string {
  const fromRefs = trimOrEmpty(item.imageRefs?.original);
  if (fromRefs) return fromRefs;
  return trimOrEmpty(item.imageUrl);
}

export function normalizeImageRefs(
  partial: Partial<ClothingItemImageRefs> | null | undefined,
  fallbackPublicUrl: string,
): ClothingItemImageRefs {
  const fb = fallbackPublicUrl.trim();
  return {
    original: trimOrEmpty(partial?.original) || fb,
    thumbnail: trimOrEmpty(partial?.thumbnail),
    display: trimOrEmpty(partial?.display) || fb,
  };
}
