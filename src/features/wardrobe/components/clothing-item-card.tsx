import { Image } from "expo-image";
import { Link } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { formatCategoryLabel } from "@/features/wardrobe/lib/format-category";
import type { ClothingItem } from "@/features/wardrobe/types/clothing-item";
import { media } from "@/lib/constants";
import { theme } from "@/theme";

export type ClothingItemCardProps = {
  item: ClothingItem;
};

export function ClothingItemCard({ item }: ClothingItemCardProps) {
  const brandDisplay = item.brand.trim() ? item.brand : "—";
  const nameDisplay = item.name.trim() ? item.name.trim() : "Untitled piece";
  const colourDisplay = item.colour.trim() ? item.colour.trim() : "—";

  return (
    <Link href={{ pathname: "/item/[id]", params: { id: item.id } }} asChild>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${nameDisplay}. ${formatCategoryLabel(item.category)}. ${colourDisplay}. ${brandDisplay === "—" ? "No brand" : brandDisplay}.`}
        style={({ pressed }) => [styles.pressable, pressed && styles.pressed]}
      >
        <View style={styles.card}>
          {item.imageUrl.trim() ? (
            <Image
              source={{ uri: item.imageUrl }}
              style={styles.image}
              contentFit="cover"
              transition={media.imageTransitionMs.card}
            />
          ) : (
            <View
              style={[styles.image, styles.imagePlaceholder]}
              accessibilityLabel="No photo"
            >
              <Text style={styles.imagePlaceholderText}>No photo</Text>
            </View>
          )}
          <View style={styles.meta}>
            <Text style={styles.name} numberOfLines={2}>
              {nameDisplay}
            </Text>
            <Text style={styles.metaLine} numberOfLines={1}>
              {formatCategoryLabel(item.category)}
            </Text>
            <Text style={styles.metaLine} numberOfLines={1}>
              {colourDisplay}
            </Text>
            <Text style={styles.brand} numberOfLines={1}>
              {brandDisplay}
            </Text>
          </View>
        </View>
      </Pressable>
    </Link>
  );
}

const styles = StyleSheet.create({
  pressable: {
    flex: 1,
  },
  pressed: {
    opacity: 0.94,
  },
  card: {
    flex: 1,
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    overflow: "hidden",
  },
  image: {
    aspectRatio: media.cardAspect,
    width: "100%",
    backgroundColor: theme.colors.border,
  },
  imagePlaceholder: {
    alignItems: "center",
    justifyContent: "center",
  },
  imagePlaceholderText: {
    fontSize: theme.typography.fontSize.xs,
    color: theme.colors.textMuted,
  },
  meta: {
    padding: theme.spacing.sm,
    gap: theme.spacing.xxs,
  },
  name: {
    fontSize: theme.typography.fontSize.md,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  metaLine: {
    fontSize: theme.typography.fontSize.xs,
    color: theme.colors.textMuted,
  },
  brand: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.medium,
    color: theme.colors.text,
    marginTop: theme.spacing.xxs,
  },
});
