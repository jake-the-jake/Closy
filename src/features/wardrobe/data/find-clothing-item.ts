import type { ClothingItem } from "@/features/wardrobe/types/clothing-item";

/** Resolve an item from any in-memory list (mocks today, repository later). */
export function findClothingItemById(
  items: readonly ClothingItem[],
  id: string | undefined,
): ClothingItem | undefined {
  if (!id) return undefined;
  return items.find((item) => item.id === id);
}
