import { type Href, useRouter } from "expo-router";
import { useCallback, useMemo, useState } from "react";
import { Platform, StyleSheet, View } from "react-native";

import { WardrobeItemForm } from "@/features/wardrobe/components/wardrobe-item-form";
import { parseAddItemFormToCreateInput } from "@/features/wardrobe/lib/create-clothing-item";
import { pickWardrobeImageFromLibrary } from "@/features/wardrobe/lib/pick-wardrobe-image";
import {
  hasAddItemFormErrors,
  isAddItemFormValid,
  validateAddItemForm,
  type AddItemFormErrors,
} from "@/features/wardrobe/lib/validate-add-item-form";
import { wardrobeService } from "@/features/wardrobe/wardrobe-service";
import {
  ADD_ITEM_FORM_INITIAL,
  type AddItemFormValues,
} from "@/features/wardrobe/types/add-item-form";
import { theme } from "@/theme";

export default function AddItemRoute() {
  const router = useRouter();
  const [form, setForm] = useState<AddItemFormValues>(ADD_ITEM_FORM_INITIAL);
  const [fieldErrors, setFieldErrors] = useState<AddItemFormErrors>({});
  const [pickingImage, setPickingImage] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [imagePickNotice, setImagePickNotice] = useState<string | null>(null);

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

  const resetFormAfterSuccess = useCallback(() => {
    setForm(ADD_ITEM_FORM_INITIAL);
    setFieldErrors({});
    setImagePickNotice(null);
    setPickingImage(false);
  }, []);

  const handleAdd = useCallback(async () => {
    if (submitting) return;

    const nextErrors = validateAddItemForm(form);
    if (hasAddItemFormErrors(nextErrors)) {
      setFieldErrors(nextErrors);
      return;
    }

    const input = parseAddItemFormToCreateInput(form);
    if (!input) return;

    setSubmitting(true);
    try {
      await wardrobeService.createItem(input);
      resetFormAfterSuccess();
      if (router.canGoBack()) {
        router.back();
      } else {
        router.replace("/(tabs)" as Href);
      }
    } finally {
      setSubmitting(false);
    }
  }, [form, resetFormAfterSuccess, router, submitting]);

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
        headerTitle="Add item"
        headerLede="Signed-in users save wardrobe pieces to the cloud when configured; others stay on this device."
        photoHint="Optional — choose from your library."
        primaryLabel="Add to wardrobe"
        canSubmit={canSubmit}
        onSubmit={handleAdd}
        primaryAccessibilityHint={{
          ready: "Adds this item to your local wardrobe list.",
          blocked: "Enter a name, choose a category, and add a colour to save this item.",
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
