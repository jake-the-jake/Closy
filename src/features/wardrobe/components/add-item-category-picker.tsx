import type { CSSProperties } from "react";
import {
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { WebHtmlButton } from "@/components/web/web-html-button";
import { formatCategoryLabel } from "@/features/wardrobe/lib/format-category";
import {
  CLOTHING_CATEGORIES,
  type ClothingCategory,
} from "@/features/wardrobe/types/clothing-item";
import { theme } from "@/theme";

type AddItemCategoryPickerProps = {
  label: string;
  value: ClothingCategory | null;
  onChange: (category: ClothingCategory) => void;
  error?: string;
};

function chipWebStyle(isActive: boolean, showError: boolean): CSSProperties {
  const padY = theme.spacing.xs + theme.spacing.xxs;
  return {
    paddingTop: padY,
    paddingBottom: padY,
    paddingLeft: theme.spacing.md,
    paddingRight: theme.spacing.md,
    borderRadius: theme.radii.full,
    borderWidth: 1,
    borderStyle: "solid",
    backgroundColor: isActive ? theme.colors.primary : theme.colors.surface,
    borderColor: isActive
      ? theme.colors.primary
      : showError
        ? theme.colors.danger
        : theme.colors.border,
    color: isActive ? theme.colors.surface : theme.colors.text,
    fontSize: theme.typography.fontSize.sm,
    fontWeight: theme.typography.fontWeight.medium,
    cursor: "pointer",
    userSelect: "none",
    WebkitUserSelect: "none",
    fontFamily: "system-ui, sans-serif",
    boxSizing: "border-box",
  };
}

/**
 * Single-select category control for Add Item — values are always valid `ClothingCategory`s.
 */
export function AddItemCategoryPicker({
  label,
  value,
  onChange,
  error,
}: AddItemCategoryPickerProps) {
  const chips =
    Platform.OS === "web"
      ? CLOTHING_CATEGORIES.map((cat) => {
          const isActive = value === cat;
          return (
            <WebHtmlButton
              key={cat}
              onPress={() => onChange(cat)}
              accessibilityLabel={`Category: ${formatCategoryLabel(cat)}`}
              style={
                chipWebStyle(isActive, !!error && !isActive) as Record<
                  string,
                  unknown
                >
              }
            >
              {formatCategoryLabel(cat)}
            </WebHtmlButton>
          );
        })
      : CLOTHING_CATEGORIES.map((cat) => {
          const isActive = value === cat;
          return (
            <Pressable
              key={cat}
              accessibilityRole="button"
              accessibilityLabel={`Category: ${formatCategoryLabel(cat)}`}
              accessibilityState={{ selected: isActive }}
              onPress={() => onChange(cat)}
              style={({ pressed }) => [
                styles.chip,
                isActive ? styles.chipActive : styles.chipIdle,
                pressed && styles.chipPressed,
                error && !isActive ? styles.chipErroredIdle : null,
              ]}
            >
              <Text
                style={[
                  styles.chipText,
                  styles.chipLabelPassthrough,
                  isActive && styles.chipTextActive,
                ]}
                numberOfLines={1}
              >
                {formatCategoryLabel(cat)}
              </Text>
            </Pressable>
          );
        });

  return (
    <View style={styles.wrap}>
      <Text style={styles.label}>{label}</Text>
      {Platform.OS === "web" ? (
        <View style={styles.chipRowWeb} accessibilityRole="none">
          {chips}
        </View>
      ) : (
        <ScrollView
          horizontal
          style={styles.horizontalScroll}
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.scrollContent}
          accessibilityRole="none"
        >
          {chips}
        </ScrollView>
      )}
      {error ? (
        <Text style={styles.error} accessibilityLiveRegion="polite">
          {error}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    width: "100%",
    maxWidth: "100%",
    minWidth: 0,
    alignSelf: "stretch",
  },
  horizontalScroll: {
    width: "100%",
    maxWidth: "100%",
    minWidth: 0,
    flexGrow: 0,
  },
  chipRowWeb: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    gap: theme.spacing.sm,
    paddingVertical: theme.spacing.xxs,
    width: "100%",
    maxWidth: "100%",
    minWidth: 0,
  },
  label: {
    fontSize: theme.typography.fontSize.sm,
    fontWeight: theme.typography.fontWeight.medium,
    color: theme.colors.text,
    marginBottom: theme.spacing.xs,
  },
  scrollContent: {
    flexDirection: "row",
    alignItems: "center",
    flexWrap: "nowrap",
    gap: theme.spacing.sm,
    paddingVertical: theme.spacing.xxs,
  },
  chip: {
    paddingVertical: theme.spacing.xs + theme.spacing.xxs,
    paddingHorizontal: theme.spacing.md,
    borderRadius: theme.radii.full,
    borderWidth: 1,
  },
  chipIdle: {
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.border,
  },
  chipActive: {
    backgroundColor: theme.colors.primary,
    borderColor: theme.colors.primary,
  },
  chipErroredIdle: {
    borderColor: theme.colors.danger,
  },
  chipPressed: {
    opacity: 0.92,
  },
  chipText: {
    fontSize: theme.typography.fontSize.sm,
    fontWeight: theme.typography.fontWeight.medium,
    color: theme.colors.text,
  },
  chipLabelPassthrough: {
    pointerEvents: "none",
  },
  chipTextActive: {
    color: theme.colors.surface,
  },
  error: {
    marginTop: theme.spacing.xs,
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.danger,
  },
});
