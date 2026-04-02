import { Image } from "expo-image";
import {
  Platform,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { AppButton } from "@/components/ui/app-button";
import { AppInput } from "@/components/ui/app-input";
import { ScreenContainer } from "@/components/ui/screen-container";
import { AddItemCategoryPicker } from "@/features/wardrobe/components/add-item-category-picker";
import {
  hasAddItemFormErrors,
  type AddItemFormErrors,
} from "@/features/wardrobe/lib/validate-add-item-form";
import type { AddItemFormValues } from "@/features/wardrobe/types/add-item-form";
import { media } from "@/lib/constants";
import { theme } from "@/theme";

export type WardrobeItemFormProps = {
  form: AddItemFormValues;
  fieldErrors: AddItemFormErrors;
  patchForm: (patch: Partial<AddItemFormValues>) => void;
  pickingImage: boolean;
  submitting: boolean;
  imagePickNotice: string | null;
  onPickImage: () => void;
  onClearImage: () => void;
  headerTitle: string;
  headerLede: string;
  /** Shown under the Photo section label. */
  photoHint: string;
  primaryLabel: string;
  canSubmit: boolean;
  onSubmit: () => void;
  primaryAccessibilityHint: { ready: string; blocked: string };
};

/**
 * Shared add / edit item fields — keeps one layout for create and update flows.
 */
export function WardrobeItemForm({
  form,
  fieldErrors,
  patchForm,
  pickingImage,
  submitting,
  imagePickNotice,
  onPickImage,
  onClearImage,
  headerTitle,
  headerLede,
  photoHint,
  primaryLabel,
  canSubmit,
  onSubmit,
  primaryAccessibilityHint,
}: WardrobeItemFormProps) {
  return (
    <ScreenContainer
      scroll
      omitTopSafeArea
      style={styles.screenFill}
      contentContainerStyle={[
        styles.scrollContent,
        Platform.OS === "web" && styles.scrollContentWeb,
      ]}
    >
      <View style={styles.stack}>
        <View style={styles.headerBlock}>
          <Text style={styles.title}>{headerTitle}</Text>
          <Text style={styles.lede}>{headerLede}</Text>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionLabel}>Photo</Text>
          <Text style={styles.sectionHint}>{photoHint}</Text>
          <View
            style={styles.previewFrame}
            accessibilityLabel={
              form.imageUri ? "Selected item photo preview" : "No photo selected"
            }
            accessibilityRole="image"
          >
            {form.imageUri ? (
              <Image
                source={{ uri: form.imageUri }}
                style={styles.previewImage}
                contentFit="cover"
                transition={media.imageTransitionMs.card}
              />
            ) : (
              <View style={styles.previewPlaceholder}>
                <Text style={styles.previewPlaceholderText}>
                  Tap below to add a photo
                </Text>
              </View>
            )}
          </View>
          <View style={styles.imageActions}>
            <AppButton
              label="Choose from library"
              onPress={onPickImage}
              variant="secondary"
              fullWidth
              loading={pickingImage}
              disabled={pickingImage || submitting}
              accessibilityHint="Opens a single photo from your device gallery."
            />
            {form.imageUri ? (
              <AppButton
                label="Remove photo"
                onPress={onClearImage}
                variant="ghost"
                fullWidth
                disabled={submitting}
                accessibilityHint="Clears the selected image. You can save the item without a photo."
              />
            ) : null}
          </View>
          {imagePickNotice ? (
            <Text
              style={styles.imageNotice}
              accessibilityRole="alert"
              accessibilityLiveRegion="polite"
            >
              {imagePickNotice}
            </Text>
          ) : null}
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionLabel}>Details</Text>
          <Text style={styles.sectionHint}>
            Name, category, and colour are required. Brand is optional.
          </Text>

          {hasAddItemFormErrors(fieldErrors) ? (
            <Text
              style={styles.formSummary}
              accessibilityRole="alert"
              accessibilityLiveRegion="polite"
            >
              Check the highlighted fields and try again.
            </Text>
          ) : null}

          <View style={styles.fields}>
            <AppInput
              label="Name"
              value={form.name}
              onChangeText={(name) => patchForm({ name })}
              placeholder="e.g. Slim chinos"
              autoCapitalize="words"
              error={fieldErrors.name}
            />

            <AddItemCategoryPicker
              label="Category"
              value={form.category}
              onChange={(category) => patchForm({ category })}
              error={fieldErrors.category}
            />

            <AppInput
              label="Colour"
              value={form.colour}
              onChangeText={(colour) => patchForm({ colour })}
              placeholder="e.g. Navy, Ecru"
              autoCapitalize="words"
              error={fieldErrors.colour}
            />

            <AppInput
              label="Brand"
              value={form.brand}
              onChangeText={(brand) => patchForm({ brand })}
              placeholder="Optional"
              autoCapitalize="words"
            />
          </View>
        </View>

        <View style={styles.footer}>
          <AppButton
            label={primaryLabel}
            onPress={onSubmit}
            fullWidth
            disabled={!canSubmit || submitting || pickingImage}
            loading={submitting}
            accessibilityHint={
              canSubmit ? primaryAccessibilityHint.ready : primaryAccessibilityHint.blocked
            }
          />
        </View>
      </View>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  /** Fill the /add-item route root so the inner ScrollView gets a real height on web. */
  screenFill: {
    flex: 1,
    minHeight: 0,
  },
  scrollContent: {
    flexGrow: 1,
  },
  /**
   * RN Web: a content container with flexGrow:1 can starve column children of height.
   * Size to children so every section (photo, details, footer) participates in layout and scrolls.
   */
  scrollContentWeb: {
    flexGrow: 0,
    width: "100%",
    maxWidth: "100%",
    alignItems: "stretch",
  },
  stack: {
    gap: theme.spacing.lg,
    width: "100%",
    maxWidth: "100%",
    minWidth: 0,
  },
  headerBlock: {
    gap: theme.spacing.xs,
  },
  title: {
    fontSize: theme.typography.fontSize.xxl,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  lede: {
    fontSize: theme.typography.fontSize.md,
    lineHeight: theme.typography.lineHeight.lede,
    color: theme.colors.textMuted,
  },
  section: {
    gap: theme.spacing.sm,
    width: "100%",
    minWidth: 0,
  },
  sectionLabel: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  sectionHint: {
    fontSize: theme.typography.fontSize.caption,
    lineHeight: theme.typography.lineHeight.lede,
    color: theme.colors.textMuted,
    marginTop: -theme.spacing.xs,
  },
  formSummary: {
    fontSize: theme.typography.fontSize.sm,
    fontWeight: theme.typography.fontWeight.medium,
    color: theme.colors.danger,
  },
  previewFrame: {
    marginTop: theme.spacing.xs,
    borderRadius: theme.radii.lg,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
    alignSelf: "stretch",
  },
  previewImage: {
    width: "100%",
    aspectRatio: media.cardAspect,
    backgroundColor: theme.colors.border,
  },
  previewPlaceholder: {
    width: "100%",
    aspectRatio: media.cardAspect,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: theme.colors.background,
    paddingVertical: theme.spacing.lg,
  },
  previewPlaceholderText: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
    textAlign: "center",
    paddingHorizontal: theme.spacing.lg,
  },
  imageActions: {
    gap: theme.spacing.sm,
    marginTop: theme.spacing.xs,
  },
  imageNotice: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.danger,
  },
  fields: {
    gap: theme.spacing.md,
    width: "100%",
    minWidth: 0,
  },
  footer: {
    marginTop: theme.spacing.sm,
    paddingTop: theme.spacing.md,
    width: "100%",
    minWidth: 0,
  },
});
