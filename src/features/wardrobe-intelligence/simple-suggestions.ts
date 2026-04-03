import type { Outfit } from "@/features/outfits/types/outfit";
import type { ClothingCategory, ClothingItem } from "@/features/wardrobe/types/clothing-item";

import type { BuildSimpleSuggestionsOptions, WardrobeComboSuggestion } from "./types";

function compareItemsByDisplayName(a: ClothingItem, b: ClothingItem): number {
  const an = (a.name.trim().toLowerCase() || a.id) as string;
  const bn = (b.name.trim().toLowerCase() || b.id) as string;
  if (an !== bn) return an < bn ? -1 : 1;
  return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
}

function shortLabel(item: ClothingItem): string {
  const n = item.name.trim();
  return n.length > 28 ? `${n.slice(0, 26)}…` : n || "Untitled";
}

/** Same items in any order → same key (for deduping against existing outfits). */
export function normalizedItemSetKey(ids: readonly string[]): string {
  return [...ids].sort().join("\u0001");
}

function bucketByCategory(
  items: readonly ClothingItem[],
): Map<ClothingCategory, ClothingItem[]> {
  const m = new Map<ClothingCategory, ClothingItem[]>();
  for (const item of items) {
    const list = m.get(item.category);
    if (list == null) m.set(item.category, [item]);
    else list.push(item);
  }
  for (const list of m.values()) list.sort(compareItemsByDisplayName);
  return m;
}

/**
 * Lightweight combos: dress+shoe pairs, then top+bottom pairs.
 * Deterministic; caps work for typical wardrobe sizes without nested explosions.
 */
export function buildSimpleOutfitSuggestions(
  items: readonly ClothingItem[],
  outfits: readonly Outfit[],
  options?: BuildSimpleSuggestionsOptions,
): WardrobeComboSuggestion[] {
  const maxSuggestions = options?.maxSuggestions ?? 15;
  const skipExisting = options?.skipExistingExact ?? true;

  const existing = skipExisting
    ? new Set(
        outfits.map((o) => normalizedItemSetKey(o.clothingItemIds)),
      )
    : new Set<string>();

  const buckets = bucketByCategory(items);
  const dresses = buckets.get("dresses") ?? [];
  const shoes = buckets.get("shoes") ?? [];
  const tops = buckets.get("tops") ?? [];
  const bottoms = buckets.get("bottoms") ?? [];

  const out: WardrobeComboSuggestion[] = [];
  const seen = new Set<string>();

  const tryPush = (ids: readonly string[], summary: string) => {
    if (out.length >= maxSuggestions) return;
    const setKey = normalizedItemSetKey(ids);
    if (seen.has(setKey)) return;
    if (existing.has(setKey)) return;
    seen.add(setKey);
    out.push({
      id: ids.join("\u0002"),
      clothingItemIds: ids,
      summary,
    });
  };

  if (dresses.length > 0 && shoes.length > 0) {
    for (let i = 0; i < dresses.length && out.length < maxSuggestions; i++) {
      const dress = dresses[i]!;
      const shoe = shoes[i % shoes.length]!;
      tryPush(
        [dress.id, shoe.id],
        `${shortLabel(dress)} + ${shortLabel(shoe)}`,
      );
    }
  }

  for (const top of tops) {
    for (const bottom of bottoms) {
      if (out.length >= maxSuggestions) break;
      tryPush([top.id, bottom.id], `${shortLabel(top)} + ${shortLabel(bottom)}`);
    }
    if (out.length >= maxSuggestions) break;
  }

  return out;
}
