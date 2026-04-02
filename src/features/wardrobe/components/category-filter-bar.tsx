import { ScrollView, Pressable, StyleSheet, Text, View } from "react-native";

import { formatCategoryLabel } from "@/features/wardrobe/lib/format-category";
import {
  CLOTHING_CATEGORIES,
  type ClothingCategory,
} from "@/features/wardrobe/types/clothing-item";
import { theme } from "@/theme";

export type WardrobeCategoryFilter = ClothingCategory | "all";

type CategoryFilterBarProps = {
  selected: WardrobeCategoryFilter;
  onSelect: (value: WardrobeCategoryFilter) => void;
};

const FILTERS: readonly WardrobeCategoryFilter[] = [
  "all",
  ...CLOTHING_CATEGORIES,
];

function chipLabel(value: WardrobeCategoryFilter): string {
  return value === "all" ? "All" : formatCategoryLabel(value);
}

export function CategoryFilterBar({ selected, onSelect }: CategoryFilterBarProps) {
  return (
    <View style={styles.wrap}>
      <ScrollView
        horizontal
        nestedScrollEnabled
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.scrollContent}
        accessibilityRole="none"
        keyboardShouldPersistTaps="handled"
      >
        {FILTERS.map((value) => {
          const isActive = selected === value;
          return (
            <Pressable
              key={value}
              accessibilityRole="button"
              accessibilityLabel={`Filter: ${chipLabel(value)}`}
              accessibilityState={{ selected: isActive }}
              onPress={() => onSelect(value)}
              style={({ pressed }) => [
                styles.chip,
                isActive ? styles.chipActive : styles.chipIdle,
                pressed && styles.chipPressed,
              ]}
            >
              <Text
                style={[styles.chipText, isActive && styles.chipTextActive]}
                numberOfLines={1}
              >
                {chipLabel(value)}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    marginBottom: theme.spacing.sm,
  },
  scrollContent: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.sm,
    paddingVertical: theme.spacing.xxs,
  },
  chip: {
    minHeight: 40,
    justifyContent: "center",
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
  chipPressed: {
    opacity: 0.92,
  },
  chipText: {
    fontSize: theme.typography.fontSize.sm,
    fontWeight: theme.typography.fontWeight.medium,
    color: theme.colors.text,
  },
  chipTextActive: {
    color: theme.colors.surface,
  },
});
