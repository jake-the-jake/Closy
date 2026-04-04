import type { ClothingItem } from "@/features/wardrobe/types/clothing-item";

/**
 * Per-item rollups derived from saved outfits only (not real-world wear tracking).
 * `lastUsedAt` is the latest outfit **activity** timestamp: see `outfitActivityTimestamp`.
 */
export type ItemUsageStats = {
  itemId: string;
  outfitCount: number;
  /** Latest outfit activity among outfits that include this item, or null if never used. */
  lastUsedAt: number | null;
};

export type MostUsedRow = {
  item: ClothingItem;
  outfitCount: number;
};

export type LeastUsedRow = {
  item: ClothingItem;
  outfitCount: number;
};

/** Rule-based combo suggestion, deterministic for the same wardrobe snapshot. */
export type WardrobeComboSuggestion = {
  /** Stable key: normalized sorted id tuple when `skipExistingExact` groups by set equality; still unique per ordered recipe in our builder. */
  id: string;
  clothingItemIds: readonly string[];
  summary: string;
};

export type BuildSimpleSuggestionsOptions = {
  maxSuggestions?: number;
  /** If true, skip combos that match an existing outfit’s item set exactly (order ignored). */
  skipExistingExact?: boolean;
};
