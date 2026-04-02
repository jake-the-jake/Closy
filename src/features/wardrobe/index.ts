/** Wardrobe feature — domain types, seed data, and entry components. */
export type { AddItemFormValues } from "./types/add-item-form";
export { ADD_ITEM_FORM_INITIAL } from "./types/add-item-form";
export type {
  ClothingCategory,
  ClothingItem,
  CreateClothingItemInput,
} from "./types/clothing-item";
export {
  applyItemFormToExistingClothingItem,
  clothingItemToFormValues,
  createClothingItem,
  parseAddItemFormToCreateInput,
} from "./lib/create-clothing-item";
export { CLOTHING_CATEGORIES } from "./types/clothing-item";
export { MOCK_CLOTHING_ITEMS } from "./data/mock-clothing-items";
export { useWardrobeStore } from "./state/wardrobe-store";
export type { WardrobeState } from "./state/wardrobe-store";
export { wardrobeService, useWardrobeItems } from "./wardrobe-service";
export {
  CategoryFilterBar,
  type WardrobeCategoryFilter,
} from "./components/category-filter-bar";
export { ClothingItemCard } from "./components/clothing-item-card";
export { ClothingItemDetailScreen } from "./components/clothing-item-detail-screen";
export { WardrobeScreen } from "./components/wardrobe-screen";
