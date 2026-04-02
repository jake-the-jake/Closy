import type { AddItemFormValues } from "@/features/wardrobe/types/add-item-form";

/** Inline field messages only; brand is optional and not validated here. */
export type AddItemFormErrors = Partial<
  Record<"name" | "category" | "colour", string>
>;

export function validateAddItemForm(values: AddItemFormValues): AddItemFormErrors {
  const errors: AddItemFormErrors = {};

  if (!values.name.trim()) {
    errors.name = "Add a name for this piece.";
  }

  if (values.category === null) {
    errors.category = "Choose a category.";
  }

  if (!values.colour.trim()) {
    errors.colour = "Colour is required.";
  }

  return errors;
}

export function hasAddItemFormErrors(errors: AddItemFormErrors): boolean {
  return Object.keys(errors).length > 0;
}

/** Same rules as submit validation — use to enable the primary button without duplicating logic. */
export function isAddItemFormValid(values: AddItemFormValues): boolean {
  return !hasAddItemFormErrors(validateAddItemForm(values));
}
