/**
 * A saved outfit references wardrobe items by `ClothingItem.id` (local or future server ids).
 */
export type Outfit = {
  id: string;
  name: string;
  /** Preserves the order the user selected items in the builder. */
  clothingItemIds: readonly string[];
  createdAt: number;
  /**
   * Last time name or pieces changed (create or edit). Omitted on older persisted rows
   * (treated as `createdAt` when rolling up usage).
   */
  updatedAt?: number;
};

export type CreateOutfitInput = {
  name: string;
  clothingItemIds: readonly string[];
};
