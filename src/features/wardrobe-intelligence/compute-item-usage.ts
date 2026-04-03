import type { Outfit } from "@/features/outfits/types/outfit";
import type { ClothingItem } from "@/features/wardrobe/types/clothing-item";

import type { ItemUsageStats, MostUsedRow } from "./types";

function compareItemsByDisplayName(a: ClothingItem, b: ClothingItem): number {
  const an = (a.name.trim().toLowerCase() || a.id) as string;
  const bn = (b.name.trim().toLowerCase() || b.id) as string;
  if (an !== bn) return an < bn ? -1 : 1;
  return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
}

const DAY_MS = 86_400_000;

/**
 * O(outfits × avg items per outfit). Fine for on-device wardrobe sizes.
 */
export function computeItemUsageStats(
  items: readonly ClothingItem[],
  outfits: readonly Outfit[],
): Map<string, ItemUsageStats> {
  const map = new Map<string, ItemUsageStats>();
  for (const item of items) {
    map.set(item.id, {
      itemId: item.id,
      outfitCount: 0,
      lastUsedAt: null,
    });
  }
  for (const outfit of outfits) {
    const t = outfit.createdAt;
    for (const id of outfit.clothingItemIds) {
      const row = map.get(id);
      if (row == null) continue;
      row.outfitCount += 1;
      row.lastUsedAt =
        row.lastUsedAt == null ? t : Math.max(row.lastUsedAt, t);
    }
  }
  return map;
}

export function getMostUsedItems(
  items: readonly ClothingItem[],
  stats: ReadonlyMap<string, ItemUsageStats>,
  limit: number,
): MostUsedRow[] {
  const rows: MostUsedRow[] = [];
  for (const item of items) {
    const n = stats.get(item.id)?.outfitCount ?? 0;
    if (n > 0) rows.push({ item, outfitCount: n });
  }
  rows.sort((a, b) => {
    if (b.outfitCount !== a.outfitCount)
      return b.outfitCount - a.outfitCount;
    return compareItemsByDisplayName(a.item, b.item);
  });
  return rows.slice(0, Math.max(0, limit));
}

/**
 * Items never appearing in an outfit, or whose last outfit is older than `staleDays`.
 */
export function getNotUsedRecentlyItems(
  items: readonly ClothingItem[],
  stats: ReadonlyMap<string, ItemUsageStats>,
  staleDays: number,
  nowMs: number = Date.now(),
): ClothingItem[] {
  const threshold = nowMs - staleDays * DAY_MS;
  const stale: ClothingItem[] = [];
  for (const item of items) {
    const row = stats.get(item.id);
    if (row == null || row.outfitCount === 0 || row.lastUsedAt == null) {
      stale.push(item);
      continue;
    }
    if (row.lastUsedAt < threshold) stale.push(item);
  }
  stale.sort(compareItemsByDisplayName);
  return stale;
}
