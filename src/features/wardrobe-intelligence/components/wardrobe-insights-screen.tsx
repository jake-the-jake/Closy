import { Image } from "expo-image";
import { type Href, router } from "expo-router";
import { useMemo } from "react";
import {
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { AppButton } from "@/components/ui/app-button";
import { ScreenContainer } from "@/components/ui/screen-container";
import { useOutfitsStore } from "@/features/outfits/state/outfits-store";
import { clothingItemThumbnailUri } from "@/features/wardrobe/lib/clothing-item-images";
import { formatCategoryLabel } from "@/features/wardrobe/lib/format-category";
import type { ClothingItem } from "@/features/wardrobe/types/clothing-item";
import { useWardrobeItems } from "@/features/wardrobe/wardrobe-service";
import { media } from "@/lib/constants";
import { theme } from "@/theme";

import {
  computeItemUsageStats,
  getMostUsedItems,
  getNotUsedRecentlyItems,
} from "../compute-item-usage";
import { buildSimpleOutfitSuggestions } from "../simple-suggestions";

const STALE_DAYS = 30;
const MOST_USED_LIMIT = 6;
const STALE_PREVIEW_LIMIT = 10;
const THUMB = 44;

function ItemRow({
  item,
  subtitle,
  onPress,
}: {
  item: ClothingItem;
  subtitle: string;
  onPress: () => void;
}) {
  const thumb = clothingItemThumbnailUri(item).trim();
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`${item.name}. ${subtitle}`}
      style={({ pressed }) => [styles.itemRow, pressed && styles.itemRowPressed]}
    >
      <View style={styles.thumbBox}>
        {thumb.length > 0 ? (
          <Image
            source={{ uri: thumb }}
            style={styles.thumb}
            contentFit="cover"
            transition={media.imageTransitionMs.card}
          />
        ) : (
          <View style={[styles.thumb, styles.thumbPlaceholder]}>
            <Text style={styles.thumbPhText}>—</Text>
          </View>
        )}
      </View>
      <View style={styles.itemMeta}>
        <Text style={styles.itemName} numberOfLines={2}>
          {item.name.trim() || "Untitled"}
        </Text>
        <Text style={styles.itemSub} numberOfLines={1}>
          {subtitle}
        </Text>
      </View>
      <Text style={styles.chevron}>›</Text>
    </Pressable>
  );
}

function SuggestionCard({
  summary,
  pieces,
  onUse,
}: {
  summary: string;
  pieces: ClothingItem[];
  onUse: () => void;
}) {
  return (
    <View style={styles.suggestionCard}>
      <Text style={styles.suggestionSummary}>{summary}</Text>
      <View style={styles.suggestionThumbs}>
        {pieces.map((p) => {
          const u = clothingItemThumbnailUri(p).trim();
          return (
            <View key={p.id} style={styles.sThumbWrap}>
              {u.length > 0 ? (
                <Image
                  source={{ uri: u }}
                  style={styles.sThumb}
                  contentFit="cover"
                  transition={media.imageTransitionMs.card}
                />
              ) : (
                <View style={[styles.sThumb, styles.thumbPlaceholder]}>
                  <Text style={styles.sThumbPh}>—</Text>
                </View>
              )}
            </View>
          );
        })}
      </View>
      <AppButton
        label="Use in new outfit"
        variant="secondary"
        onPress={onUse}
        fullWidth
        accessibilityHint="Opens the outfit builder with these pieces selected"
      />
    </View>
  );
}

export function WardrobeInsightsScreen() {
  const items = useWardrobeItems();
  const outfits = useOutfitsStore((s) => s.outfits);

  const usage = useMemo(
    () => computeItemUsageStats(items, outfits),
    [items, outfits],
  );

  const mostUsed = useMemo(
    () => getMostUsedItems(items, usage, MOST_USED_LIMIT),
    [items, usage],
  );

  const notRecent = useMemo(
    () => getNotUsedRecentlyItems(items, usage, STALE_DAYS),
    [items, usage],
  );

  const suggestions = useMemo(
    () => buildSimpleOutfitSuggestions(items, outfits),
    [items, outfits],
  );

  const openItem = (id: string) => {
    router.push({ pathname: "/item/[id]", params: { id } } as Href);
  };

  const openCreateWith = (ids: readonly string[]) => {
    router.push({
      pathname: "/create-outfit",
      params: { itemIds: [...ids].join(",") },
    } as Href);
  };

  const notRecentPreview = notRecent.slice(0, STALE_PREVIEW_LIMIT);
  const notRecentExtra = Math.max(0, notRecent.length - notRecentPreview.length);

  return (
    <ScreenContainer scroll={false} omitTopSafeArea style={styles.screen}>
      <ScrollView
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <Text style={styles.lede}>
          Simple stats from your saved outfits—no cloud AI, just patterns in your
          own closet.
        </Text>

        <Text style={styles.sectionTitle}>Most used</Text>
        <Text style={styles.sectionHint}>
          Pieces that appear in the most outfits you have saved.
        </Text>
        {mostUsed.length === 0 ? (
          <Text style={styles.emptyLine}>
            Save a few outfits first—usage shows up here automatically.
          </Text>
        ) : (
          <View style={styles.card}>
            {mostUsed.map(({ item, outfitCount }) => (
              <ItemRow
                key={item.id}
                item={item}
                subtitle={`In ${outfitCount} ${outfitCount === 1 ? "outfit" : "outfits"} · ${formatCategoryLabel(item.category)}`}
                onPress={() => openItem(item.id)}
              />
            ))}
          </View>
        )}

        <Text style={styles.sectionTitle}>Not used recently</Text>
        <Text style={styles.sectionHint}>
          No outfit saved in the last {STALE_DAYS} days, or never used in an
          outfit.
        </Text>
        {notRecent.length === 0 ? (
          <Text style={styles.emptyLine}>
            Everything has appeared in an outfit lately, or your wardrobe is
            empty.
          </Text>
        ) : (
          <View style={styles.card}>
            {notRecentPreview.map((item) => {
              const row = usage.get(item.id);
              const sub =
                row != null && row.outfitCount === 0
                  ? `Never in an outfit · ${formatCategoryLabel(item.category)}`
                  : row?.lastUsedAt != null
                    ? `Last outfit ${formatRelativeDay(row.lastUsedAt)} · ${formatCategoryLabel(item.category)}`
                    : formatCategoryLabel(item.category);
              return (
                <ItemRow
                  key={item.id}
                  item={item}
                  subtitle={sub}
                  onPress={() => openItem(item.id)}
                />
              );
            })}
            {notRecentExtra > 0 ? (
              <Text style={styles.moreNote}>
                +{notRecentExtra} more not shown—open each category in Wardrobe to
                browse everything.
              </Text>
            ) : null}
          </View>
        )}

        <Text style={styles.sectionTitle}>Outfit ideas</Text>
        <Text style={styles.sectionHint}>
          Dress + shoes, then top + bottom pairs. Duplicates of outfits you
          already saved are skipped.
        </Text>
        {suggestions.length === 0 ? (
          <Text style={styles.emptyLine}>
            Add at least one dress and shoe, or a top and bottom, to get combo
            suggestions.
          </Text>
        ) : (
          suggestions.map((s) => {
            const pieces = s.clothingItemIds
              .map((id) => items.find((i) => i.id === id))
              .filter((x): x is ClothingItem => x != null);
            return (
              <SuggestionCard
                key={s.id}
                summary={s.summary}
                pieces={pieces}
                onUse={() => openCreateWith(s.clothingItemIds)}
              />
            );
          })
        )}
      </ScrollView>
    </ScreenContainer>
  );
}

function formatRelativeDay(ts: number): string {
  const d = Math.floor((Date.now() - ts) / 86_400_000);
  if (d <= 0) return "today";
  if (d === 1) return "yesterday";
  if (d < 14) return `${d} days ago`;
  const weeks = Math.floor(d / 7);
  if (weeks < 8) return `${weeks} wk ago`;
  const months = Math.floor(d / 30);
  return `${months} mo ago`;
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
  },
  scroll: {
    paddingBottom: theme.spacing.xl,
    paddingTop: theme.spacing.xs,
    gap: theme.spacing.md,
    maxWidth: 560,
    width: "100%",
    alignSelf: "center",
    ...(Platform.OS === "web" ? { boxSizing: "border-box" as const } : {}),
  },
  lede: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
    lineHeight: 20,
    marginBottom: theme.spacing.xs,
  },
  sectionTitle: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.6,
    marginTop: theme.spacing.sm,
  },
  sectionHint: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    lineHeight: 18,
    marginTop: theme.spacing.xxs,
    marginBottom: theme.spacing.xs,
  },
  emptyLine: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
    fontStyle: "italic",
    lineHeight: 20,
  },
  card: {
    borderRadius: theme.radii.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
    overflow: "hidden",
  },
  itemRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
    paddingHorizontal: theme.spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: theme.colors.border,
  },
  itemRowPressed: {
    backgroundColor: "rgba(0,0,0,0.03)",
  },
  thumbBox: {
    borderRadius: theme.radii.sm,
    overflow: "hidden",
  },
  thumb: {
    width: THUMB,
    height: Math.round((THUMB * 4) / 3),
    backgroundColor: theme.colors.border,
  },
  thumbPlaceholder: {
    alignItems: "center",
    justifyContent: "center",
  },
  thumbPhText: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
  },
  itemMeta: {
    flex: 1,
    minWidth: 0,
  },
  itemName: {
    fontSize: theme.typography.fontSize.md,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  itemSub: {
    marginTop: 2,
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
  },
  chevron: {
    fontSize: 22,
    color: theme.colors.textMuted,
    marginLeft: theme.spacing.xs,
  },
  moreNote: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    padding: theme.spacing.md,
    lineHeight: 18,
  },
  suggestionCard: {
    borderRadius: theme.radii.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
    padding: theme.spacing.md,
    gap: theme.spacing.sm,
    marginBottom: theme.spacing.sm,
  },
  suggestionSummary: {
    fontSize: theme.typography.fontSize.md,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  suggestionThumbs: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: theme.spacing.sm,
  },
  sThumbWrap: {
    borderRadius: theme.radii.sm,
    overflow: "hidden",
  },
  sThumb: {
    width: 56,
    height: Math.round((56 * 4) / 3),
    backgroundColor: theme.colors.border,
  },
  sThumbPh: {
    fontSize: theme.typography.fontSize.xs,
    color: theme.colors.textMuted,
  },
});
