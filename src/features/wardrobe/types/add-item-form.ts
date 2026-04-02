import type { ClothingCategory } from "./clothing-item";

/**
 * Add Item screen state. Category is chosen from `CLOTHING_CATEGORIES` only (`null` = not selected yet).
 */
export type AddItemFormValues = {
  name: string;
  category: ClothingCategory | null;
  colour: string;
  brand: string;
  /** Local `file://` or content URI from the image picker; `null` / cleared saves with no photo. */
  imageUri: string | null;
};

export const ADD_ITEM_FORM_INITIAL: AddItemFormValues = {
  name: "",
  category: null,
  colour: "",
  brand: "",
  imageUri: null,
};
