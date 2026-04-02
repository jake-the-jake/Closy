import type { AddItemFormValues } from "@/features/wardrobe/types/add-item-form";
import { createLocalWardrobeItemId } from "@/features/wardrobe/lib/local-item-id";
import {
  type ClothingItem,
  type CreateClothingItemInput,
} from "@/features/wardrobe/types/clothing-item";

/** Map a saved row into add-item form state (image uses existing `imageUrl` as preview URI). */
export function clothingItemToFormValues(item: ClothingItem): AddItemFormValues {
  const uri = item.imageUrl.trim();
  return {
    name: item.name,
    category: item.category,
    colour: item.colour,
    brand: item.brand,
    imageUri: uri.length > 0 ? item.imageUrl : null,
  };
}

/**
 * Apply validated form values onto an existing item (same `id` and `tags`); resolves `imageUrl`
 * like create flow when no image is selected.
 */
export function applyItemFormToExistingClothingItem(
  values: AddItemFormValues,
  existing: ClothingItem,
): ClothingItem | null {
  const input = parseAddItemFormToCreateInput(values);
  if (!input) return null;

  const imageUrl =
    input.localImageUri && input.localImageUri.trim().length > 0
      ? input.localImageUri.trim()
      : "";

  return {
    ...existing,
    name: input.name,
    category: input.category,
    colour: input.colour,
    brand: input.brand,
    imageUrl,
  };
}

/** Normalise validated form values into a creation payload (no `id` / resolved `imageUrl` yet). */
export function parseAddItemFormToCreateInput(
  values: AddItemFormValues,
): CreateClothingItemInput | null {
  const name = values.name.trim();
  const colour = values.colour.trim();
  if (!name || !colour || values.category === null) {
    return null;
  }

  const picked = values.imageUri?.trim();
  const localImageUri = picked && picked.length > 0 ? picked : null;

  return {
    name,
    category: values.category,
    colour,
    brand: values.brand.trim(),
    localImageUri,
  };
}

/** Mint a saved `ClothingItem` (local id + `imageUrl`) from a creation payload. */
export function createClothingItem(input: CreateClothingItemInput): ClothingItem {
  const id = createLocalWardrobeItemId();
  const imageUrl =
    input.localImageUri && input.localImageUri.trim().length > 0
      ? input.localImageUri.trim()
      : "";

  return {
    id,
    name: input.name,
    category: input.category,
    colour: input.colour,
    brand: input.brand,
    imageUrl,
    tags: [],
  };
}
