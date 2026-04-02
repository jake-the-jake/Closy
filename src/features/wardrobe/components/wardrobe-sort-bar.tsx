import { ScrollView, Pressable, StyleSheet, Text, View } from "react-native";

import type { WardrobeSortMode } from "@/features/wardrobe/lib/wardrobe-list-display";
import { theme } from "@/theme";

type WardrobeSortBarProps = {
  selected: WardrobeSortMode;
  onSelect: (value: WardrobeSortMode) => void;
};

const OPTIONS: readonly { value: WardrobeSortMode; label: string }[] = [
  { value: "newest", label: "Newest first" },
  { value: "name_az", label: "Name A–Z" },
];

export function WardrobeSortBar({ selected, onSelect }: WardrobeSortBarProps) {
  return (
    <View style={styles.wrap}>
      <Text style={styles.caption}>Sort</Text>
      <ScrollView
        horizontal
        nestedScrollEnabled
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.scrollContent}
        accessibilityRole="none"
        keyboardShouldPersistTaps="handled"
      >
        {OPTIONS.map(({ value, label }) => {
          const isActive = selected === value;
          return (
            <Pressable
              key={value}
              accessibilityRole="button"
              accessibilityLabel={`Sort by ${label}`}
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
                {label}
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
    gap: theme.spacing.xs,
    marginBottom: theme.spacing.xxs,
  },
  caption: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.6,
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
