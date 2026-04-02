import type { WardrobeCategoryFilter } from "@/features/wardrobe/components/category-filter-bar";
import type { ClothingItem } from "@/features/wardrobe/types/clothing-item";

/** How to order rows for the wardrobe grid (local only; `newest` follows store order). */
export type WardrobeSortMode = "newest" | "name_az";

function sortKeyName(name: string): string {
  const t = name.trim();
  /** `\uffff` sorts after normal letters so blank / untitled names list last. */
  return t.length === 0 ? "\uffff" : t;
}

/**
 * Filter by category, then sort. Store order is newest-first (items are prepended on create).
 * `name_az` uses case-insensitive name order, stable tie-break on `id`.
 */
export function getWardrobeListForDisplay(
  items: readonly ClothingItem[],
  categoryFilter: WardrobeCategoryFilter,
  sortMode: WardrobeSortMode,
): ClothingItem[] {
  const filtered =
    categoryFilter === "all"
      ? [...items]
      : items.filter((row) => row.category === categoryFilter);

  if (sortMode === "newest") {
    return filtered;
  }

  return [...filtered].sort((a, b) => {
    const cmp = sortKeyName(a.name).localeCompare(sortKeyName(b.name), undefined, {
      sensitivity: "base",
    });
    if (cmp !== 0) return cmp;
    return a.id.localeCompare(b.id);
  });
}
