import { Image } from "expo-image";
import { type Href, useRouter } from "expo-router";
import { useCallback, useLayoutEffect, useMemo, useState } from "react";
import {
  Platform,
  Pressable,
  SectionList,
  type SectionListData,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { AppButton } from "@/components/ui/app-button";
import { AppInput } from "@/components/ui/app-input";
import { EmptyState } from "@/components/ui/empty-state";
import { ScreenContainer } from "@/components/ui/screen-container";
import { findClothingItemById } from "@/features/wardrobe/data/find-clothing-item";
import { clothingItemThumbnailUri } from "@/features/wardrobe/lib/clothing-item-images";
import { formatCategoryLabel } from "@/features/wardrobe/lib/format-category";
import {
  CLOTHING_CATEGORIES,
  type ClothingCategory,
  type ClothingItem,
} from "@/features/wardrobe/types/clothing-item";
import { useWardrobeItems } from "@/features/wardrobe/wardrobe-service";
import { outfitsService } from "@/features/outfits/outfits-service";
import { useOutfitsStore } from "@/features/outfits/state/outfits-store";
import { media } from "@/lib/constants";
import { theme } from "@/theme";

export type OutfitBuilderScreenProps =
  | { mode: "create" }
  | { mode: "edit"; outfitId: string };

type SelectedEntry = {
  id: string;
  item: ClothingItem | null;
};

type SelectedGroup = {
  key: string;
  label: string;
  entries: SelectedEntry[];
};

type WardrobeSection = SectionListData<ClothingItem> & {
  category: ClothingCategory;
};

const PREVIEW_TILE_W = 96;
const GRID_TILE_W = 108;

function SelectedTile({
  entry,
  compact,
  onRemove,
}: {
  entry: SelectedEntry;
  compact?: boolean;
  onRemove: () => void;
}) {
  const w = compact ? PREVIEW_TILE_W : GRID_TILE_W;
  const item = entry.item;
  const title =
    item != null
      ? item.name.trim() || "Untitled"
      : "Removed from wardrobe";
  const thumb = item != null ? clothingItemThumbnailUri(item).trim() : "";
  const hasImage = thumb.length > 0;

  return (
    <View style={[styles.tileWrap, { width: w }, entry.item == null && styles.tileOrphan]}>
      <View
        style={[styles.tileImageBox, { height: Math.round((w * 4) / 3) }]}
        accessibilityLabel={title}
      >
        {hasImage ? (
          <Image
            source={{ uri: thumb }}
            style={StyleSheet.absoluteFill}
            contentFit="cover"
            transition={media.imageTransitionMs.card}
          />
        ) : (
          <View style={[StyleSheet.absoluteFill, styles.tilePlaceholder]}>
            <Text style={styles.tilePlaceholderText}>No photo</Text>
          </View>
        )}
        <Pressable
          onPress={onRemove}
          accessibilityRole="button"
          accessibilityLabel={`Remove ${title} from outfit`}
          style={({ pressed }) => [
            styles.tileRemoveFab,
            pressed && { opacity: 0.85 },
          ]}
        >
          <Text style={styles.tileRemoveFabText}>×</Text>
        </Pressable>
        {item != null ? (
          <View style={styles.tileSelectedBadge}>
            <Text style={styles.tileSelectedBadgeText}>✓</Text>
          </View>
        ) : null}
      </View>
      <Text style={styles.tileTitle} numberOfLines={2}>
        {title}
      </Text>
    </View>
  );
}

export function OutfitBuilderScreen(props: OutfitBuilderScreenProps) {
  const router = useRouter();
  const wardrobeItems = useWardrobeItems();

  const outfit = useOutfitsStore((s) =>
    props.mode === "edit"
      ? s.outfits.find((o) => o.id === props.outfitId)
      : undefined,
  );

  const [name, setName] = useState("");
  const [nameError, setNameError] = useState<string | undefined>();
  const [selectionError, setSelectionError] = useState<string | undefined>();
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  useLayoutEffect(() => {
    if (props.mode !== "edit") return;
    if (outfit == null) return;
    setName(outfit.name);
    setSelectedIds([...outfit.clothingItemIds]);
    setNameError(undefined);
    setSelectionError(undefined);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- only reseed when switching edit target
  }, [props.mode, outfit?.id]);

  const selectedOrdered: SelectedEntry[] = useMemo(
    () =>
      selectedIds.map((id) => ({
        id,
        item: findClothingItemById(wardrobeItems, id) ?? null,
      })),
    [selectedIds, wardrobeItems],
  );

  const selectedGroups: SelectedGroup[] = useMemo(() => {
    const byCategory = new Map<ClothingCategory, SelectedEntry[]>();
    for (const c of CLOTHING_CATEGORIES) byCategory.set(c, []);
    const orphans: SelectedEntry[] = [];
    for (const entry of selectedOrdered) {
      if (entry.item == null) orphans.push(entry);
      else byCategory.get(entry.item.category)!.push(entry);
    }
    const groups: SelectedGroup[] = [];
    for (const cat of CLOTHING_CATEGORIES) {
      const entries = byCategory.get(cat)!;
      if (entries.length > 0) {
        groups.push({
          key: cat,
          label: formatCategoryLabel(cat),
          entries,
        });
      }
    }
    if (orphans.length > 0) {
      groups.push({
        key: "orphan",
        label: "Not in wardrobe",
        entries: orphans,
      });
    }
    return groups;
  }, [selectedOrdered]);

  const wardrobeSections: WardrobeSection[] = useMemo(() => {
    const bucket = new Map<ClothingCategory, ClothingItem[]>();
    for (const c of CLOTHING_CATEGORIES) bucket.set(c, []);
    for (const item of wardrobeItems) {
      bucket.get(item.category)!.push(item);
    }
    return CLOTHING_CATEGORIES.filter((c) => bucket.get(c)!.length > 0).map(
      (c) => ({
        category: c,
        title: formatCategoryLabel(c),
        data: bucket.get(c)!,
      }),
    );
  }, [wardrobeItems]);

  const removeId = useCallback((id: string) => {
    setSelectionError(undefined);
    setSelectedIds((prev) => prev.filter((x) => x !== id));
  }, []);

  const toggleId = useCallback((id: string) => {
    setSelectionError(undefined);
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }, []);

  const saveDisabled =
    props.mode === "create" && wardrobeItems.length === 0;

  const handleSave = useCallback(async () => {
    const trimmed = name.trim();
    if (!trimmed) {
      setNameError("Add a name for this outfit.");
      return;
    }
    if (selectedIds.length === 0) {
      setSelectionError("Choose at least one piece from this outfit.");
      return;
    }
    setNameError(undefined);
    setSelectionError(undefined);
    setSaving(true);
    try {
      if (props.mode === "create") {
        await outfitsService.addOutfit({
          name: trimmed,
          clothingItemIds: selectedIds,
        });
        if (router.canGoBack()) router.back();
        else router.replace("/(tabs)/outfits" as Href);
      } else {
        await outfitsService.updateOutfit(props.outfitId, {
          name: trimmed,
          clothingItemIds: selectedIds,
        });
        if (router.canGoBack()) router.back();
        else
          router.replace({
            pathname: "/outfit/[id]",
            params: { id: props.outfitId },
          } as Href);
      }
    } finally {
      setSaving(false);
    }
  }, [name, props.mode, props.mode === "edit" ? props.outfitId : "", router, selectedIds]);

  if (props.mode === "edit" && outfit == null) {
    return (
      <ScreenContainer scroll={false} omitTopSafeArea>
        <EmptyState
          title="Outfit not found"
          description="This look may have been removed. Go back to Outfits."
        />
      </ScreenContainer>
    );
  }

  const primaryLabel = props.mode === "create" ? "Save outfit" : "Save changes";

  const listHeader = useMemo(
    () => (
      <View style={styles.headerStack}>
        <AppInput
          label="Outfit name"
          value={name}
          onChangeText={(t) => {
            setName(t);
            if (nameError != null) setNameError(undefined);
          }}
          placeholder="e.g. Weekend brunch"
          autoCapitalize="words"
          error={nameError}
        />

        <View style={styles.previewSection}>
          <Text style={styles.previewHeading}>Preview</Text>
          <Text style={styles.previewSub}>
            Order matches how you added pieces. Tap × on a card to remove it.
          </Text>
          {selectedOrdered.length === 0 ? (
            <View style={styles.previewEmpty}>
              <Text style={styles.previewEmptyText}>
                Nothing selected yet — pick pieces below.
              </Text>
            </View>
          ) : (
            <ScrollView
              horizontal
              nestedScrollEnabled
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={styles.previewScroll}
              accessibilityRole="scrollbar"
              accessibilityLabel="Selected items preview"
            >
              {selectedOrdered.map((entry) => (
                <SelectedTile
                  key={entry.id}
                  entry={entry}
                  compact
                  onRemove={() => removeId(entry.id)}
                />
              ))}
            </ScrollView>
          )}
        </View>

        {selectedGroups.length > 0 ? (
          <View style={styles.groupedSection}>
            <Text style={styles.sectionLabel}>By category</Text>
            {selectedGroups.map((g) => (
              <View key={g.key} style={styles.groupBlock}>
                <Text style={styles.groupLabel}>{g.label}</Text>
                <View style={styles.groupGrid}>
                  {g.entries.map((entry) => (
                    <SelectedTile
                      key={entry.id}
                      entry={entry}
                      onRemove={() => removeId(entry.id)}
                    />
                  ))}
                </View>
              </View>
            ))}
          </View>
        ) : null}

        {selectionError != null ? (
          <Text style={styles.selectionError} accessibilityRole="alert">
            {selectionError}
          </Text>
        ) : null}

        <Text style={[styles.sectionLabel, styles.pickerIntro]}>
          Add from your wardrobe
        </Text>
        {wardrobeItems.length === 0 ? (
          <Text style={styles.emptyPicker}>
            {props.mode === "edit"
              ? "No pieces in your wardrobe. Add items under Wardrobe, or keep only saved references above."
              : "Add pieces in the Wardrobe tab first, then return here to build an outfit."}
          </Text>
        ) : null}
      </View>
    ),
    [
      name,
      nameError,
      props.mode,
      removeId,
      selectedGroups,
      selectedOrdered,
      selectionError,
      wardrobeItems.length,
    ],
  );

  const listFooter = useMemo(
    () => (
      <View style={styles.footer}>
        <AppButton
          label={primaryLabel}
          onPress={handleSave}
          fullWidth
          loading={saving}
          disabled={saveDisabled || saving}
          accessibilityHint={
            props.mode === "create"
              ? "Saves this outfit to your device."
              : "Updates this outfit on your device."
          }
        />
      </View>
    ),
    [handleSave, primaryLabel, props.mode, saveDisabled, saving],
  );

  return (
    <ScreenContainer scroll={false} omitTopSafeArea style={styles.screen}>
      {wardrobeItems.length === 0 ? (
        <View style={styles.inner}>
          {listHeader}
          {listFooter}
        </View>
      ) : (
        <SectionList<ClothingItem, WardrobeSection>
          sections={wardrobeSections}
          keyExtractor={(item) => item.id}
          stickySectionHeadersEnabled={Platform.OS === "ios"}
          nestedScrollEnabled
          keyboardShouldPersistTaps="handled"
          ListHeaderComponent={listHeader}
          ListFooterComponent={listFooter}
          contentContainerStyle={styles.sectionListContent}
          renderSectionHeader={({ section: { title } }) => (
            <View style={styles.pickerSectionHeader}>
              <Text style={styles.pickerSectionTitle}>{title}</Text>
              <Text style={styles.pickerSectionHint}>
                Tap a row to select or deselect
              </Text>
            </View>
          )}
          renderItem={({ item }) => {
            const on = selectedIds.includes(item.id);
            const rowThumb = clothingItemThumbnailUri(item).trim();
            return (
              <Pressable
                onPress={() => toggleId(item.id)}
                accessibilityRole="checkbox"
                accessibilityState={{ checked: on }}
                accessibilityLabel={`${item.name}. ${formatCategoryLabel(item.category)}. ${on ? "Selected" : "Not selected"}`}
                style={({ pressed }) => [
                  styles.pickerRow,
                  on && styles.pickerRowSelected,
                  pressed && styles.pickerRowPressed,
                ]}
              >
                <View style={styles.pickerThumbBox}>
                  {rowThumb ? (
                    <Image
                      source={{ uri: rowThumb }}
                      style={styles.pickerThumb}
                      contentFit="cover"
                      transition={media.imageTransitionMs.card}
                    />
                  ) : (
                    <View style={[styles.pickerThumb, styles.pickerThumbEmpty]}>
                      <Text style={styles.pickerThumbEmptyText}>—</Text>
                    </View>
                  )}
                </View>
                <View style={[styles.checkbox, on && styles.checkboxOn]}>
                  {on ? <Text style={styles.checkmark}>✓</Text> : null}
                </View>
                <View style={styles.pickerMeta}>
                  <Text style={styles.pickerName} numberOfLines={2}>
                    {item.name.trim() || "Untitled piece"}
                  </Text>
                  <Text style={styles.pickerSub} numberOfLines={1}>
                    {formatCategoryLabel(item.category)}
                    {item.colour.trim() ? ` · ${item.colour.trim()}` : ""}
                  </Text>
                </View>
              </Pressable>
            );
          }}
        />
      )}
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    minHeight: 0,
    ...Platform.select({
      web: { width: "100%", alignSelf: "stretch" },
      default: {},
    }),
  },
  inner: {
    flex: 1,
    minHeight: 0,
    gap: theme.spacing.md,
    paddingBottom: theme.spacing.lg,
  },
  headerStack: {
    gap: theme.spacing.md,
    paddingBottom: theme.spacing.sm,
  },
  previewSection: {
    gap: theme.spacing.xs,
  },
  previewHeading: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  previewSub: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    lineHeight: 18,
  },
  previewEmpty: {
    minHeight: 120,
    borderRadius: theme.radii.md,
    borderWidth: 1,
    borderStyle: "dashed",
    borderColor: theme.colors.border,
    justifyContent: "center",
    alignItems: "center",
    padding: theme.spacing.md,
    backgroundColor: theme.colors.surface,
  },
  previewEmptyText: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
    textAlign: "center",
  },
  previewScroll: {
    gap: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
  },
  groupedSection: {
    gap: theme.spacing.md,
  },
  sectionLabel: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  pickerIntro: {
    marginTop: theme.spacing.xs,
  },
  groupBlock: {
    gap: theme.spacing.sm,
  },
  groupLabel: {
    fontSize: theme.typography.fontSize.sm,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  groupGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: theme.spacing.sm,
  },
  tileWrap: {
    marginBottom: theme.spacing.xs,
  },
  tileOrphan: {
    opacity: 0.92,
  },
  tileImageBox: {
    width: "100%",
    borderRadius: theme.radii.md,
    overflow: "hidden",
    backgroundColor: theme.colors.border,
    position: "relative",
  },
  tilePlaceholder: {
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: theme.colors.background,
  },
  tilePlaceholderText: {
    fontSize: 10,
    color: theme.colors.textMuted,
  },
  tileRemoveFab: {
    position: "absolute",
    top: 6,
    right: 6,
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: "rgba(0,0,0,0.58)",
    alignItems: "center",
    justifyContent: "center",
  },
  tileRemoveFabText: {
    color: "#fff",
    fontSize: 18,
    fontWeight: "700",
    lineHeight: 20,
    marginTop: -1,
  },
  tileSelectedBadge: {
    position: "absolute",
    bottom: 6,
    left: 6,
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: theme.colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  tileSelectedBadgeText: {
    color: theme.colors.surface,
    fontSize: 12,
    fontWeight: "800",
  },
  tileTitle: {
    marginTop: theme.spacing.xs,
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.medium,
    color: theme.colors.text,
    lineHeight: 16,
  },
  selectionError: {
    fontSize: theme.typography.fontSize.sm,
    fontWeight: theme.typography.fontWeight.medium,
    color: theme.colors.danger,
  },
  emptyPicker: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
    lineHeight: 20,
  },
  sectionListContent: {
    paddingBottom: theme.spacing.xl,
  },
  pickerSectionHeader: {
    paddingTop: theme.spacing.md,
    paddingBottom: theme.spacing.xs,
    paddingHorizontal: theme.spacing.xs,
    backgroundColor: theme.colors.background,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: theme.colors.border,
  },
  pickerSectionTitle: {
    fontSize: theme.typography.fontSize.sm,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  pickerSectionHint: {
    marginTop: 2,
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
  },
  pickerRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
    paddingHorizontal: theme.spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
  },
  pickerRowSelected: {
    backgroundColor: "rgba(32, 138, 239, 0.08)",
  },
  pickerRowPressed: {
    opacity: 0.92,
  },
  pickerThumbBox: {
    borderRadius: theme.radii.sm,
    overflow: "hidden",
  },
  pickerThumb: {
    width: 52,
    height: Math.round((52 * 4) / 3),
    backgroundColor: theme.colors.border,
  },
  pickerThumbEmpty: {
    alignItems: "center",
    justifyContent: "center",
  },
  pickerThumbEmptyText: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
  },
  checkbox: {
    width: 24,
    height: 24,
    borderRadius: theme.radii.sm,
    borderWidth: 2,
    borderColor: theme.colors.border,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: theme.colors.surface,
  },
  checkboxOn: {
    borderColor: theme.colors.primary,
    backgroundColor: theme.colors.primary,
  },
  checkmark: {
    color: theme.colors.surface,
    fontSize: 14,
    fontWeight: "800",
  },
  pickerMeta: {
    flex: 1,
    minWidth: 0,
  },
  pickerName: {
    fontSize: theme.typography.fontSize.md,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  pickerSub: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    marginTop: 2,
  },
  footer: {
    paddingTop: theme.spacing.lg,
    paddingBottom: theme.spacing.md,
    paddingHorizontal: theme.spacing.xs,
  },
});
