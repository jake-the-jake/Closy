/**
 * Wardrobe domain — portable shapes that an API can mirror later (JSON-in-JSON-out).
 */

export const CLOTHING_CATEGORIES = [
  "tops",
  "bottoms",
  "dresses",
  "outerwear",
  "shoes",
  "accessories",
] as const;

export type ClothingCategory = (typeof CLOTHING_CATEGORIES)[number];

/**
 * Row already stored in wardrobe state (or returned from `GET /items/:id`).
 * Client-created items use a temporary `id` until a server assigns one.
 */
export type ClothingItem = {
  id: string;
  name: string;
  category: ClothingCategory;
  /** Human-readable colour (e.g. "Navy", "Off-white"). */
  colour: string;
  /** Empty string if unknown or unbranded — keeps a stable shape for API mapping. */
  brand: string;
  /** Remote URL, local `file://` URI, or CDN path after upload. */
  imageUrl: string;
  /** Free-form labels for search, outfits, or seasonal grouping. */
  tags: readonly string[];
};

/**
 * Fields required to create an item (e.g. `POST /items` body + local image before upload).
 * Omits `id` and final `imageUrl`; use `createClothingItem` locally or map after API response.
 */
export type CreateClothingItemInput = {
  name: string;
  category: ClothingCategory;
  colour: string;
  brand: string;
  /** Local picker URI; `null` means “no image yet” and the client picks a placeholder. */
  localImageUri: string | null;
};
