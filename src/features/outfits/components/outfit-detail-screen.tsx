import { useCallback, useLayoutEffect } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useNavigation } from "@react-navigation/native";
import { type Href, Link, useRouter } from "expo-router";

import { AppButton } from "@/components/ui/app-button";
import { EmptyState } from "@/components/ui/empty-state";
import { ScreenContainer } from "@/components/ui/screen-container";
import { findClothingItemById } from "@/features/wardrobe/data/find-clothing-item";
import { formatCategoryLabel } from "@/features/wardrobe/lib/format-category";
import { confirmDeleteOutfit } from "@/features/outfits/lib/confirm-delete-outfit";
import { useOutfitsStore } from "@/features/outfits/state/outfits-store";
import type { Outfit } from "@/features/outfits/types/outfit";
import { useWardrobeItems } from "@/features/wardrobe/wardrobe-service";
import { theme } from "@/theme";

export type OutfitDetailScreenProps = {
  outfit: Outfit | undefined;
};

export function OutfitDetailScreen({ outfit }: OutfitDetailScreenProps) {
  const navigation = useNavigation();
  const router = useRouter();
  const wardrobeItems = useWardrobeItems();
  const deleteOutfit = useOutfitsStore((s) => s.deleteOutfit);

  const openEdit = useCallback(() => {
    if (outfit == null) return;
    router.push({
      pathname: "/edit-outfit/[id]",
      params: { id: outfit.id },
    } as Href);
  }, [outfit, router]);

  const requestDeleteOutfit = useCallback(() => {
    if (outfit == null) return;
    const id = outfit.id;
    const displayName = outfit.name.trim() || "This outfit";
    confirmDeleteOutfit({
      title: "Delete this outfit?",
      message: `"${displayName}" will be removed from your saved outfits. You can create it again later from your wardrobe.`,
      onConfirm: () => {
        deleteOutfit(id);
        router.replace("/(tabs)/outfits" as Href);
      },
    });
  }, [deleteOutfit, outfit, router]);

  useLayoutEffect(() => {
    const title =
      outfit != null ? outfit.name.trim() || "Outfit" : "Outfit";
    navigation.setOptions({
      title,
      headerRight:
        outfit != null
          ? () => (
              <Pressable
                onPress={openEdit}
                accessibilityRole="button"
                accessibilityLabel="Edit outfit"
                style={({ pressed }) => [
                  styles.headerEditHit,
                  pressed && { opacity: 0.75 },
                ]}
              >
                <Text style={styles.headerEditText}>Edit</Text>
              </Pressable>
            )
          : undefined,
    });
  }, [navigation, openEdit, outfit]);

  if (!outfit) {
    return (
      <ScreenContainer scroll={false} omitTopSafeArea>
        <EmptyState
          title="Outfit not found"
          description="It may have been removed. Go back to Outfits to see your saved looks."
        />
      </ScreenContainer>
    );
  }

  const resolved = outfit.clothingItemIds.map((id) => ({
    id,
    item: findClothingItemById(wardrobeItems, id),
  }));

  return (
    <ScreenContainer scroll omitTopSafeArea>
      <View style={styles.stack}>
        <Text style={styles.lede}>
          {outfit.clothingItemIds.length}{" "}
          {outfit.clothingItemIds.length === 1 ? "piece" : "pieces"}
        </Text>

        <AppButton
          label="Edit outfit"
          variant="secondary"
          fullWidth
          onPress={openEdit}
          accessibilityLabel="Edit outfit"
          accessibilityHint="Change the name or wardrobe pieces for this outfit"
        />

        <Text style={styles.sectionLabel}>Items in this outfit</Text>
        <View style={styles.list}>
          {resolved.map(({ id, item }) =>
            item ? (
              <Link
                key={id}
                href={{ pathname: "/item/[id]", params: { id: item.id } }}
                asChild
              >
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={`Open ${item.name}`}
                  style={({ pressed }) => [
                    styles.row,
                    pressed && styles.rowPressed,
                  ]}
                >
                  <View style={styles.rowText}>
                    <Text style={styles.rowTitle} numberOfLines={2}>
                      {item.name.trim() || "Untitled piece"}
                    </Text>
                    <Text style={styles.rowSub} numberOfLines={1}>
                      {formatCategoryLabel(item.category)}
                    </Text>
                  </View>
                  <Text style={styles.chevron}>›</Text>
                </Pressable>
              </Link>
            ) : (
              <View key={id} style={styles.rowMuted}>
                <Text style={styles.removedLabel}>Removed from wardrobe</Text>
                <Text style={styles.removedId} numberOfLines={1}>
                  Id: {id}
                </Text>
              </View>
            ),
          )}
        </View>

        <Pressable
          onPress={requestDeleteOutfit}
          accessibilityRole="button"
          accessibilityLabel="Delete outfit"
          style={({ pressed }) => [
            styles.deleteHit,
            pressed && styles.deleteHitPressed,
          ]}
        >
          <Text style={styles.deleteLabel}>Delete outfit</Text>
        </Pressable>
      </View>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  stack: {
    gap: theme.spacing.lg,
    width: "100%",
    paddingBottom: theme.spacing.xl,
  },
  lede: {
    fontSize: theme.typography.fontSize.md,
    color: theme.colors.textMuted,
  },
  sectionLabel: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  list: {
    borderRadius: theme.radii.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    overflow: "hidden",
    backgroundColor: theme.colors.surface,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: theme.spacing.md,
    paddingHorizontal: theme.spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: theme.colors.border,
  },
  rowPressed: {
    backgroundColor: theme.colors.background,
  },
  rowText: {
    flex: 1,
    minWidth: 0,
  },
  rowTitle: {
    fontSize: theme.typography.fontSize.md,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  rowSub: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    marginTop: 2,
  },
  chevron: {
    fontSize: 22,
    color: theme.colors.textMuted,
    marginLeft: theme.spacing.sm,
  },
  rowMuted: {
    paddingVertical: theme.spacing.md,
    paddingHorizontal: theme.spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: theme.colors.border,
    backgroundColor: theme.colors.background,
  },
  removedLabel: {
    fontSize: theme.typography.fontSize.sm,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
  },
  removedId: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    marginTop: 4,
  },
  headerEditHit: {
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    marginRight: -theme.spacing.xs,
  },
  headerEditText: {
    fontSize: theme.typography.fontSize.md,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.primary,
  },
  deleteHit: {
    alignSelf: "flex-start",
    paddingVertical: theme.spacing.sm,
    paddingHorizontal: theme.spacing.xs,
    marginLeft: -theme.spacing.xs,
  },
  deleteHitPressed: {
    opacity: 0.75,
  },
  deleteLabel: {
    fontSize: theme.typography.fontSize.md,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.danger,
  },
});
