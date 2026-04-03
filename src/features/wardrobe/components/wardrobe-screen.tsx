import { type Href, router } from "expo-router";
import type { CSSProperties } from "react";
import { useCallback, useMemo, useState } from "react";
import {
  FlatList,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useBottomTabBarHeight } from "@react-navigation/bottom-tabs";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { EmptyState } from "@/components/ui/empty-state";
import { RemoteSyncNotice } from "@/components/ui/remote-sync-notice";
import { ScreenContainer } from "@/components/ui/screen-container";
import { WebHtmlButton } from "@/components/web/web-html-button";
import { useAuth } from "@/features/auth";
import {
  CategoryFilterBar,
  type WardrobeCategoryFilter,
} from "@/features/wardrobe/components/category-filter-bar";
import { ClothingItemCard } from "@/features/wardrobe/components/clothing-item-card";
import { WardrobeSortBar } from "@/features/wardrobe/components/wardrobe-sort-bar";
import { formatCategoryLabel } from "@/features/wardrobe/lib/format-category";
import {
  getWardrobeListForDisplay,
  type WardrobeSortMode,
} from "@/features/wardrobe/lib/wardrobe-list-display";
import { useWardrobeItems } from "@/features/wardrobe/wardrobe-service";
import { useRemoteSyncStore } from "@/lib/sync";
import { layout } from "@/lib/constants";
import { theme } from "@/theme";

const COLUMN_GAP = theme.spacing.sm;

const FAB_LIST_EXTRA_PADDING = layout.fabSize + theme.spacing.md;

const ADD_ITEM_HREF = "/add-item" as Href;
const WARDROBE_INSIGHTS_HREF = "/wardrobe-insights" as Href;

export function WardrobeScreen() {
  const items = useWardrobeItems();
  const { supabaseConfigured, isAuthenticated } = useAuth();
  const wardrobeSync = useRemoteSyncStore((s) => s.wardrobe);
  const dismissWardrobeError = useRemoteSyncStore((s) => s.dismissWardrobeError);
  const insets = useSafeAreaInsets();
  const tabBarHeight = useBottomTabBarHeight();
  const [categoryFilter, setCategoryFilter] =
    useState<WardrobeCategoryFilter>("all");
  const [sortMode, setSortMode] = useState<WardrobeSortMode>("newest");

  const fabBottomOffset = useMemo(() => {
    const pad = theme.spacing.md;
    if (Platform.OS === "web") {
      // RN Web: tab bar can overlap the content area; hook may be 0 on first layout.
      const tabH = Math.max(tabBarHeight, 52);
      return pad + tabH + Math.max(insets.bottom, 0);
    }
    return pad + insets.bottom;
  }, [insets.bottom, tabBarHeight]);

  const openAddItem = useCallback(() => {
    router.push(ADD_ITEM_HREF);
  }, []);

  const openInsights = useCallback(() => {
    router.push(WARDROBE_INSIGHTS_HREF);
  }, []);

  const listItems = useMemo(
    () => getWardrobeListForDisplay(items, categoryFilter, sortMode),
    [items, categoryFilter, sortMode],
  );

  const listHeader = useMemo(
    () => (
      <View style={styles.headerBlock}>
        {supabaseConfigured && isAuthenticated ? (
          <RemoteSyncNotice
            snapshot={wardrobeSync}
            domain="wardrobe"
            onDismissError={dismissWardrobeError}
          />
        ) : null}
        <Pressable
          onPress={openInsights}
          accessibilityRole="button"
          accessibilityLabel="Wardrobe insights and outfit ideas"
          style={({ pressed }) => [
            styles.insightsCard,
            pressed && styles.insightsCardPressed,
          ]}
        >
          <Text style={styles.insightsTitle}>Insights & ideas</Text>
          <Text style={styles.insightsSub}>
            Usage from your outfits and simple combo suggestions.
          </Text>
        </Pressable>
        <Text style={styles.count} accessibilityRole="header">
          {items.length === 0
            ? "0 pieces"
            : listItems.length === items.length
              ? `${items.length} ${items.length === 1 ? "piece" : "pieces"}`
              : `${listItems.length} of ${items.length} pieces`}
        </Text>
        <Text style={styles.filterHeading}>Category</Text>
        <CategoryFilterBar
          selected={categoryFilter}
          onSelect={setCategoryFilter}
        />
        <WardrobeSortBar selected={sortMode} onSelect={setSortMode} />
      </View>
    ),
    [
      categoryFilter,
      dismissWardrobeError,
      isAuthenticated,
      openInsights,
      items.length,
      listItems.length,
      sortMode,
      supabaseConfigured,
      wardrobeSync,
    ],
  );

  const listEmptyComponent = useMemo(() => {
    if (listItems.length > 0) return null;
    return (
      <View style={styles.emptyWrap}>
        {items.length === 0 ? (
          <EmptyState
            title="Nothing here yet"
            description={
              supabaseConfigured && isAuthenticated
                ? "Tap + to add a piece. Items sync to your account when the network is available."
                : "Tap + to add an item. Your list is saved on this device."
            }
          />
        ) : (
          <EmptyState
            title={
              categoryFilter === "all"
                ? "Nothing to show"
                : `Nothing in ${formatCategoryLabel(categoryFilter)}`
            }
            description="Choose another category or tap All to see every piece. You can also try a different sort."
          />
        )}
      </View>
    );
  }, [
    categoryFilter,
    isAuthenticated,
    items.length,
    listItems.length,
    supabaseConfigured,
  ]);

  const listExtraData = useMemo(
    () => ({
      n: items.length,
      f: categoryFilter,
      s: sortMode,
      shown: listItems.length,
    }),
    [items.length, categoryFilter, sortMode, listItems.length],
  );

  return (
    <ScreenContainer scroll={false} omitTopSafeArea style={styles.shell}>
      <View style={[styles.stage, styles.stagePointerEvents]} collapsable={false}>
        <FlatList
          style={[styles.list, Platform.OS === "web" && styles.listWeb]}
          data={listItems}
          extraData={listExtraData}
          keyExtractor={(item) => item.id}
          numColumns={2}
          showsVerticalScrollIndicator={false}
          ListHeaderComponent={listHeader}
          columnWrapperStyle={styles.row}
          contentContainerStyle={[
            styles.listContent,
            {
              paddingBottom:
                insets.bottom + theme.spacing.lg + FAB_LIST_EXTRA_PADDING,
            },
          ]}
          ListEmptyComponent={listEmptyComponent}
          keyboardShouldPersistTaps={
            Platform.OS === "web" ? "always" : "handled"
          }
          renderItem={({ item }) => (
            <View style={styles.cell}>
              <ClothingItemCard item={item} />
            </View>
          )}
        />

        {Platform.OS === "web" ? (
          <WebHtmlButton
            accessibilityLabel="Add clothing item"
            onPress={openAddItem}
            style={
              {
                position: "absolute",
                right: theme.spacing.md,
                bottom: fabBottomOffset,
                zIndex: 100,
                width: layout.fabSize,
                height: layout.fabSize,
                borderRadius: theme.radii.full,
                backgroundColor: theme.colors.primary,
                border: "none",
                cursor: "pointer",
                alignItems: "center",
                justifyContent: "center",
                display: "flex",
                padding: 0,
                boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
                fontSize: 28,
                lineHeight: 1,
                fontWeight: 300,
                color: theme.colors.surface,
                fontFamily: "system-ui, sans-serif",
              } satisfies CSSProperties as Record<string, unknown>
            }
          >
            +
          </WebHtmlButton>
        ) : (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Add clothing item"
            onPress={openAddItem}
            hitSlop={12}
            style={({ pressed }) => [
              styles.fab,
              { bottom: fabBottomOffset },
              pressed && styles.fabPressed,
            ]}
          >
            <Text style={[styles.fabIcon, styles.textPassthrough]}>
              +
            </Text>
          </Pressable>
        )}
      </View>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  shell: {
    flex: 1,
  },
  stage: {
    flex: 1,
    position: "relative",
  },
  stagePointerEvents: {
    pointerEvents: "box-none",
  },
  /** Label text should not use the deprecated `pointerEvents` prop on RN Web. */
  textPassthrough: {
    pointerEvents: "none",
  },
  list: {
    flex: 1,
  },
  listWeb: {
    zIndex: 0,
  },
  headerBlock: {
    marginBottom: theme.spacing.xs,
  },
  insightsCard: {
    marginBottom: theme.spacing.md,
    padding: theme.spacing.md,
    borderRadius: theme.radii.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
    ...Platform.select({
      web: { cursor: "pointer" as const },
      default: {},
    }),
  },
  insightsCardPressed: {
    opacity: 0.92,
  },
  insightsTitle: {
    fontSize: theme.typography.fontSize.md,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  insightsSub: {
    marginTop: theme.spacing.xs,
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    lineHeight: 18,
  },
  count: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
    marginBottom: theme.spacing.sm,
  },
  filterHeading: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.6,
    marginBottom: theme.spacing.xs,
  },
  listContent: {
    flexGrow: 1,
    paddingTop: theme.spacing.xs,
  },
  row: {
    gap: COLUMN_GAP,
    marginBottom: COLUMN_GAP,
  },
  cell: {
    flex: 1,
    minWidth: 0,
  },
  emptyWrap: {
    flex: 1,
    flexGrow: 1,
    minHeight: layout.wardrobeEmptyMinHeight,
    justifyContent: "center",
  },
  fab: {
    position: "absolute",
    right: theme.spacing.md,
    zIndex: 20,
    width: layout.fabSize,
    height: layout.fabSize,
    borderRadius: theme.radii.full,
    backgroundColor: theme.colors.primary,
    alignItems: "center",
    justifyContent: "center",
    // RN Web warns on shadow* — use boxShadow on web only; native keeps elevation + shadow*.
    ...(Platform.OS === "web"
      ? { boxShadow: "0 2px 8px rgba(0,0,0,0.2)" }
      : { ...theme.shadows.fab, elevation: 10 }),
  },
  fabPressed: {
    backgroundColor: theme.colors.primaryPressed,
  },
  fabIcon: {
    fontSize: 28,
    lineHeight: 30,
    color: theme.colors.surface,
    fontWeight: "300",
  },
});
