import { useCallback, useLayoutEffect, useMemo } from "react";
import { Image } from "expo-image";
import { type Href, useRouter } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useNavigation } from "@react-navigation/native";

import { EmptyState } from "@/components/ui/empty-state";
import { ScreenContainer } from "@/components/ui/screen-container";
import { useOutfitsStore } from "@/features/outfits/state/outfits-store";
import { computeItemOutfitUsage } from "@/features/wardrobe-intelligence/compute-item-usage";
import { clothingItemDisplayUri } from "@/features/wardrobe/lib/clothing-item-images";
import { confirmDeleteWardrobeItem } from "@/features/wardrobe/lib/confirm-delete-item";
import { formatCategoryLabel } from "@/features/wardrobe/lib/format-category";
import type { ClothingItem } from "@/features/wardrobe/types/clothing-item";
import { wardrobeService } from "@/features/wardrobe/wardrobe-service";
import { formatRelativeDay } from "@/lib/format-relative-day";
import { media } from "@/lib/constants";
import { theme } from "@/theme";

export type ClothingItemDetailScreenProps = {
  item: ClothingItem | undefined;
};

function DetailField({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <Text style={styles.fieldValue}>{value}</Text>
    </View>
  );
}

export function ClothingItemDetailScreen({ item }: ClothingItemDetailScreenProps) {
  const navigation = useNavigation();
  const router = useRouter();
  const outfits = useOutfitsStore((s) => s.outfits);
  const outfitUsage = useMemo(() => {
    if (item == null) return null;
    return computeItemOutfitUsage(item.id, outfits);
  }, [item, outfits]);

  const openEdit = useCallback(() => {
    if (!item) return;
    router.push({
      pathname: "/edit-item/[id]",
      params: { id: item.id },
    } as Href);
  }, [item, router]);

  const requestDelete = useCallback(
    (row: ClothingItem) => {
      const label = row.name.trim() || "This item";
      confirmDeleteWardrobeItem({
        title: "Delete item?",
        message: `“${label}” will be removed from this device. This cannot be undone.`,
        onConfirm: () => {
          void (async () => {
            await wardrobeService.deleteItem(row.id);
            router.dismissTo("/(tabs)" as Href);
          })();
        },
      });
    },
    [router],
  );

  useLayoutEffect(() => {
    const title =
      item != null ? item.name.trim() || "Untitled piece" : "Item";
    navigation.setOptions({
      title,
      headerRight:
        item != null
          ? () => (
              <View style={styles.headerActions}>
                <Pressable
                  onPress={openEdit}
                  accessibilityRole="button"
                  accessibilityLabel="Edit item"
                  style={({ pressed }) => [
                    styles.headerEditHit,
                    pressed && { opacity: 0.7 },
                  ]}
                >
                  <Text style={styles.headerEditText}>Edit</Text>
                </Pressable>
                <Pressable
                  onPress={() => requestDelete(item)}
                  accessibilityRole="button"
                  accessibilityLabel="Delete item"
                  style={({ pressed }) => [
                    styles.headerDeleteHit,
                    pressed && { opacity: 0.7 },
                  ]}
                >
                  <Text style={styles.headerDeleteText}>Delete</Text>
                </Pressable>
              </View>
            )
          : undefined,
    });
  }, [item, navigation, openEdit, requestDelete]);

  if (!item) {
    return (
      <ScreenContainer scroll={false} omitTopSafeArea>
        <EmptyState
          title="Item not found"
          description="This piece may have been removed or the link is out of date."
        />
      </ScreenContainer>
    );
  }

  const brandDisplay = item.brand.trim() ? item.brand : "—";
  const colourDisplay = item.colour.trim() ? item.colour : "—";
  const titleText = item.name.trim() ? item.name.trim() : "Untitled piece";
  const imageUri = clothingItemDisplayUri(item).trim();
  const tagList = item.tags.filter((t) => t.trim().length > 0);

  return (
    <ScreenContainer scroll omitTopSafeArea contentContainerStyle={styles.scrollInner}>
      {imageUri ? (
        <Image
          source={{ uri: imageUri }}
          style={styles.hero}
          contentFit="contain"
          transition={media.imageTransitionMs.detail}
        />
      ) : (
        <View
          style={[styles.hero, styles.heroPlaceholder]}
          accessibilityRole="image"
          accessibilityLabel="No photo"
        >
          <Text style={styles.heroPlaceholderText}>No photo</Text>
        </View>
      )}

      <View style={styles.body}>
        <Text style={styles.title}>{titleText}</Text>

        <View style={styles.fields}>
          <DetailField label="Category" value={formatCategoryLabel(item.category)} />
          <DetailField label="Colour" value={colourDisplay} />
          <DetailField label="Brand" value={brandDisplay} />
        </View>

        {outfitUsage != null ? (
          <View style={styles.usageBlock}>
            <DetailField
              label="Saved outfit usage"
              value={
                outfitUsage.outfitCount === 0
                  ? "Not in any saved outfit yet."
                  : `${outfitUsage.outfitCount} saved ${outfitUsage.outfitCount === 1 ? "outfit" : "outfits"} · last activity ${formatRelativeDay(outfitUsage.lastUsedAt!)}`
              }
            />
            <Text style={styles.usageFootnote}>
              Counts when an outfit that includes this piece is saved or edited in
              Closy—not real-world wears.
            </Text>
          </View>
        ) : null}

        <View style={styles.tagsSection}>
          <Text style={styles.tagsHeading}>Tags</Text>
          {tagList.length > 0 ? (
            <View style={styles.tags}>
              {tagList.map((tag, index) => (
                <View key={`${tag}-${index}`} style={styles.tagChip}>
                  <Text style={styles.tagText}>{tag}</Text>
                </View>
              ))}
            </View>
          ) : (
            <Text style={styles.tagsEmpty}>No tags yet.</Text>
          )}
        </View>

        <View style={styles.dangerZone}>
          <Pressable
            onPress={() => requestDelete(item)}
            accessibilityRole="button"
            accessibilityLabel="Delete from wardrobe"
            accessibilityHint="Opens a confirmation before removing this item from this device."
            style={({ pressed }) => [
              styles.deleteFromWardrobeHit,
              pressed && styles.deleteFromWardrobePressed,
            ]}
          >
            <Text style={styles.deleteFromWardrobeText}>Delete from wardrobe</Text>
          </Pressable>
        </View>
      </View>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  /** Overrides ScreenContainer horizontal/top padding so the hero can be full-bleed. Bottom inset stays from ScreenContainer. */
  scrollInner: {
    paddingHorizontal: 0,
    paddingTop: 0,
  },
  hero: {
    width: "100%",
    aspectRatio: media.detailHeroAspect,
    backgroundColor: theme.colors.border,
  },
  heroPlaceholder: {
    alignItems: "center",
    justifyContent: "center",
  },
  heroPlaceholderText: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
  },
  body: {
    paddingHorizontal: theme.spacing.md,
    paddingTop: theme.spacing.md,
    gap: theme.spacing.lg,
  },
  title: {
    fontSize: theme.typography.fontSize.xxl,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
    lineHeight: theme.typography.lineHeight.title,
  },
  fields: {
    gap: theme.spacing.md,
  },
  usageBlock: {
    gap: theme.spacing.xs,
  },
  usageFootnote: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    lineHeight: 18,
  },
  field: {
    gap: theme.spacing.xs,
  },
  fieldLabel: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  fieldValue: {
    fontSize: theme.typography.fontSize.lg,
    color: theme.colors.text,
  },
  tagsSection: {
    gap: theme.spacing.sm,
  },
  tagsHeading: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  tags: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: theme.spacing.sm,
  },
  tagChip: {
    paddingVertical: theme.spacing.xs + 2,
    paddingHorizontal: theme.spacing.sm,
    borderRadius: theme.radii.sm,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  tagText: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.text,
  },
  tagsEmpty: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
  },
  headerActions: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.md,
    marginRight: -theme.spacing.xs,
  },
  headerEditHit: {
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
  },
  headerEditText: {
    fontSize: theme.typography.fontSize.md,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.primary,
  },
  headerDeleteHit: {
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
  },
  headerDeleteText: {
    fontSize: theme.typography.fontSize.md,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.danger,
  },
  dangerZone: {
    marginTop: theme.spacing.lg,
    paddingTop: theme.spacing.lg,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: theme.colors.border,
  },
  deleteFromWardrobeHit: {
    alignSelf: "flex-start",
    paddingVertical: theme.spacing.sm,
    paddingHorizontal: theme.spacing.xs,
  },
  deleteFromWardrobePressed: {
    opacity: 0.75,
  },
  deleteFromWardrobeText: {
    fontSize: theme.typography.fontSize.sm,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.danger,
  },
});
