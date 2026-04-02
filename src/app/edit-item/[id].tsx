import { type Href, useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useLayoutEffect, useMemo, useState } from "react";
import { Platform, StyleSheet, View } from "react-native";

import { EmptyState } from "@/components/ui/empty-state";
import { ScreenContainer } from "@/components/ui/screen-container";
import { WardrobeItemForm } from "@/features/wardrobe/components/wardrobe-item-form";
import {
  applyItemFormToExistingClothingItem,
  clothingItemToFormValues,
} from "@/features/wardrobe/lib/create-clothing-item";
import { findClothingItemById } from "@/features/wardrobe/data/find-clothing-item";
import { pickWardrobeImageFromLibrary } from "@/features/wardrobe/lib/pick-wardrobe-image";
import { resolveClothingItemRouteId } from "@/features/wardrobe/lib/resolve-item-route-id";
import {
  hasAddItemFormErrors,
  isAddItemFormValid,
  validateAddItemForm,
  type AddItemFormErrors,
} from "@/features/wardrobe/lib/validate-add-item-form";
import {
  useWardrobeItems,
  wardrobeService,
} from "@/features/wardrobe/wardrobe-service";
import {
  ADD_ITEM_FORM_INITIAL,
  type AddItemFormValues,
} from "@/features/wardrobe/types/add-item-form";
import { theme } from "@/theme";

export default function EditItemRoute() {
  const router = useRouter();
  const { id: idParam } = useLocalSearchParams<{ id: string | string[] }>();
  const resolvedId = resolveClothingItemRouteId(idParam);
  const items = useWardrobeItems();
  const item = useMemo(
    () => (resolvedId ? findClothingItemById(items, resolvedId) : undefined),
    [items, resolvedId],
  );

  const [form, setForm] = useState<AddItemFormValues>(ADD_ITEM_FORM_INITIAL);
  const [fieldErrors, setFieldErrors] = useState<AddItemFormErrors>({});
  const [pickingImage, setPickingImage] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [imagePickNotice, setImagePickNotice] = useState<string | null>(null);

  // Key off id only so a Zustand reference refresh for the same row does not wipe in-progress edits.
  useLayoutEffect(() => {
    if (!item) return;
    setForm(clothingItemToFormValues(item));
    setFieldErrors({});
    setImagePickNotice(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- see above
  }, [item?.id]);

  const canSubmit = useMemo(() => isAddItemFormValid(form), [form]);

  const patchForm = useCallback((patch: Partial<AddItemFormValues>) => {
    setForm((prev) => ({ ...prev, ...patch }));
    setFieldErrors((prev) => {
      const next = { ...prev };
      for (const key of Object.keys(patch) as (keyof AddItemFormValues)[]) {
        if (key === "name" || key === "category" || key === "colour") {
          delete next[key];
        }
      }
      return next;
    });
  }, []);

  const handlePickImage = useCallback(async () => {
    setImagePickNotice(null);
    setPickingImage(true);
    try {
      const result = await pickWardrobeImageFromLibrary();
      switch (result.status) {
        case "picked":
          patchForm({ imageUri: result.uri });
          break;
        case "canceled":
          break;
        case "permission_denied":
          setImagePickNotice(
            "Photo library access is off. You can enable it in your device settings.",
          );
          break;
        case "error":
          setImagePickNotice("Could not open the photo library. Please try again.");
          break;
        default: {
          const _exhaustive: never = result;
          return _exhaustive;
        }
      }
    } finally {
      setPickingImage(false);
    }
  }, [patchForm]);

  const handleClearImage = useCallback(() => {
    setImagePickNotice(null);
    patchForm({ imageUri: null });
  }, [patchForm]);

  const handleSave = useCallback(async () => {
    if (submitting || !resolvedId) return;

    const nextErrors = validateAddItemForm(form);
    if (hasAddItemFormErrors(nextErrors)) {
      setFieldErrors(nextErrors);
      return;
    }

    const latest = findClothingItemById(wardrobeService.getItems(), resolvedId);
    if (!latest) return;

    const updated = applyItemFormToExistingClothingItem(form, latest);
    if (!updated) return;

    setSubmitting(true);
    try {
      await wardrobeService.updateItem(updated);
      if (router.canGoBack()) {
        router.back();
      } else {
        router.replace(
          {
            pathname: "/item/[id]",
            params: { id: updated.id },
          } as Href,
        );
      }
    } finally {
      setSubmitting(false);
    }
  }, [form, resolvedId, router, submitting]);

  if (!resolvedId || !item) {
    return (
      <ScreenContainer scroll={false} omitTopSafeArea>
        <EmptyState
          title="Item not found"
          description="This piece may have been removed. Go back to your wardrobe and try again."
        />
      </ScreenContainer>
    );
  }

  return (
    <View style={styles.routeRoot}>
      <WardrobeItemForm
        form={form}
        fieldErrors={fieldErrors}
        patchForm={patchForm}
        pickingImage={pickingImage}
        submitting={submitting}
        imagePickNotice={imagePickNotice}
        onPickImage={() => {
          void handlePickImage();
        }}
        onClearImage={handleClearImage}
        headerTitle="Edit item"
        headerLede="Changes update this device; cloud-backed rows sync when you are signed in."
        photoHint="Replace the photo from your library, or remove it for no photo."
        primaryLabel="Save changes"
        canSubmit={canSubmit}
        onSubmit={handleSave}
        primaryAccessibilityHint={{
          ready: "Updates this item in your wardrobe.",
          blocked: "Enter a name, choose a category, and add a colour to save.",
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  routeRoot: {
    flex: 1,
    minHeight: 0,
    backgroundColor: theme.colors.background,
    ...Platform.select({
      web: {
        width: "100%",
        alignSelf: "stretch",
      },
      default: {},
    }),
  },
});
