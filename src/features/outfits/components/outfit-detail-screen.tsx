import { useCallback, useLayoutEffect, useState } from "react";
import { Alert, Platform, Pressable, StyleSheet, Text, View } from "react-native";
import { useNavigation } from "@react-navigation/native";
import { type Href, Link, useRouter } from "expo-router";

import { AppButton } from "@/components/ui/app-button";
import { EmptyState } from "@/components/ui/empty-state";
import { ScreenContainer } from "@/components/ui/screen-container";
import { useAuth } from "@/features/auth";
import { discoverService } from "@/features/discover";
import { confirmDeleteOutfit } from "@/features/outfits/lib/confirm-delete-outfit";
import { outfitsService } from "@/features/outfits/outfits-service";
import {
  buildOutfitSharePayload,
  presentOutfitShareSheet,
} from "@/features/social";
import type { Outfit } from "@/features/outfits/types/outfit";
import { findClothingItemById } from "@/features/wardrobe/data/find-clothing-item";
import { formatCategoryLabel } from "@/features/wardrobe/lib/format-category";
import { useWardrobeItems } from "@/features/wardrobe/wardrobe-service";
import { theme } from "@/theme";

export type OutfitDetailScreenProps = {
  outfit: Outfit | undefined;
};

type ActionNotice = {
  variant: "success" | "error";
  message: string;
} | null;

export function OutfitDetailScreen({ outfit }: OutfitDetailScreenProps) {
  const navigation = useNavigation();
  const router = useRouter();
  const wardrobeItems = useWardrobeItems();
  const { isAuthenticated, supabaseConfigured } = useAuth();
  const [publishing, setPublishing] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [shareNotice, setShareNotice] = useState<ActionNotice>(null);
  const [publishNotice, setPublishNotice] = useState<ActionNotice>(null);

  const openEdit = useCallback(() => {
    if (outfit == null) return;
    router.push({
      pathname: "/edit-outfit/[id]",
      params: { id: outfit.id },
    } as Href);
  }, [outfit, router]);

  const openShare = useCallback(async () => {
    if (outfit == null) return;
    setShareNotice(null);
    setSharing(true);
    console.log("[Closy][OutfitDetail] share action start", { outfitId: outfit.id });
    try {
      const resolved = outfit.clothingItemIds.map((id) => ({
        id,
        item: findClothingItemById(wardrobeItems, id),
      }));
      const payload = buildOutfitSharePayload(outfit, resolved);
      const result = await presentOutfitShareSheet(payload);
      console.log("[Closy][OutfitDetail] share action result", result);

      if (result.status === "unavailable") {
        setShareNotice({ variant: "error", message: result.message });
      } else if (result.status === "copied") {
        setShareNotice({ variant: "success", message: result.message });
      } else if (result.status === "shared") {
        setShareNotice({
          variant: "success",
          message:
            Platform.OS === "web"
              ? "Share completed (or summary was sent via your browser)."
              : "Share completed.",
        });
      } else {
        setShareNotice({
          variant: "success",
          message: "Share sheet closed without sharing.",
        });
      }
    } catch (err) {
      console.error("[Closy][OutfitDetail] share action threw", err);
      setShareNotice({
        variant: "error",
        message:
          err instanceof Error ? err.message : "Something went wrong while sharing.",
      });
    } finally {
      setSharing(false);
    }
  }, [outfit, wardrobeItems]);

  const runPublishToDiscover = useCallback(async () => {
    if (outfit == null) {
      console.warn("[Closy][OutfitDetail] publish run skipped: no outfit");
      return;
    }
    setPublishing(true);
    setPublishNotice(null);
    console.log("[Closy][OutfitDetail] publish request", { outfitId: outfit.id });
    try {
      const published = await discoverService.publishOutfitFromCurrentWardrobe(
        outfit,
        wardrobeItems,
      );
      if (published) {
        console.log("[Closy][OutfitDetail] publish success", {
          publishedId: published.id,
        });
        setPublishNotice({
          variant: "success",
          message: `Published to Discover. Open the Discover tab and refresh if you don’t see it yet.`,
        });
      } else {
        console.warn("[Closy][OutfitDetail] publish returned null");
        setPublishNotice({
          variant: "error",
          message:
            "Could not publish. Check your connection, sign-in, and Supabase configuration.",
        });
      }
    } catch (err) {
      console.error("[Closy][OutfitDetail] publish threw", err);
      setPublishNotice({
        variant: "error",
        message:
          err instanceof Error ? err.message : "Publish failed unexpectedly.",
      });
    } finally {
      setPublishing(false);
    }
  }, [outfit, wardrobeItems]);

  const beginPublishToDiscover = useCallback(() => {
    if (outfit == null) return;
    setPublishNotice(null);

    if (!supabaseConfigured) {
      console.warn("[Closy][OutfitDetail] publish blocked: supabase not configured");
      setPublishNotice({
        variant: "error",
        message:
          "Discover isn’t configured. Add Supabase env vars and run migrations.",
      });
      return;
    }
    if (!isAuthenticated) {
      console.warn("[Closy][OutfitDetail] publish blocked: not signed in");
      setPublishNotice({
        variant: "error",
        message: "Sign in to publish to Discover.",
      });
      return;
    }

    const body =
      "A snapshot of this outfit (names, categories, and any cloud-stored photo URLs) will appear in Discover. Future edits to your saved outfit won’t change this post.";

    if (Platform.OS === "web") {
      if (typeof window !== "undefined") {
        const ok = window.confirm(`Publish to Discover?\n\n${body}`);
        console.log("[Closy][OutfitDetail] publish confirm (web)", { ok });
        if (ok) void runPublishToDiscover();
      } else {
        console.error("[Closy][OutfitDetail] publish: window undefined on web");
        setPublishNotice({
          variant: "error",
          message: "Cannot confirm publish in this environment.",
        });
      }
      return;
    }

    Alert.alert("Publish to Discover?", body, [
      {
        text: "Cancel",
        style: "cancel",
        onPress: () =>
          console.log("[Closy][OutfitDetail] publish cancelled (native)"),
      },
      {
        text: "Publish",
        onPress: () => {
          void runPublishToDiscover();
        },
      },
    ]);
  }, [
    outfit,
    isAuthenticated,
    supabaseConfigured,
    runPublishToDiscover,
  ]);

  const requestDeleteOutfit = useCallback(() => {
    if (outfit == null) return;
    const id = outfit.id;
    const displayName = outfit.name.trim() || "This outfit";
    confirmDeleteOutfit({
      title: "Delete this outfit?",
      message: `"${displayName}" will be removed from your saved outfits. You can create it again later from your wardrobe.`,
      onConfirm: () => {
        void (async () => {
          await outfitsService.deleteOutfit(id);
          router.replace("/(tabs)/outfits" as Href);
        })();
      },
    });
  }, [outfit, router]);

  useLayoutEffect(() => {
    const title =
      outfit != null ? outfit.name.trim() || "Outfit" : "Outfit";
    navigation.setOptions({
      title,
      headerRight:
        outfit != null
          ? () => (
              <View style={styles.headerActions}>
                <Pressable
                  onPress={() => void openShare()}
                  accessibilityRole="button"
                  accessibilityLabel="Share outfit"
                  style={({ pressed }) => [
                    styles.headerActionHit,
                    pressed && { opacity: 0.75 },
                  ]}
                >
                  <Text style={styles.headerEditText}>Share</Text>
                </Pressable>
                <Pressable
                  onPress={openEdit}
                  accessibilityRole="button"
                  accessibilityLabel="Edit outfit"
                  style={({ pressed }) => [
                    styles.headerActionHitLast,
                    pressed && { opacity: 0.75 },
                  ]}
                >
                  <Text style={styles.headerEditText}>Edit</Text>
                </Pressable>
              </View>
            )
          : undefined,
    });
  }, [navigation, openEdit, openShare, outfit]);

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

        {shareNotice ? (
          <View
            style={[
              styles.notice,
              shareNotice.variant === "error" ? styles.noticeError : styles.noticeSuccess,
            ]}
          >
            <Text style={styles.noticeText}>{shareNotice.message}</Text>
          </View>
        ) : null}

        <AppButton
          label="Share outfit summary"
          fullWidth
          onPress={() => void openShare()}
          loading={sharing}
          accessibilityLabel="Share outfit summary"
          accessibilityHint="Shares a text summary of this look (browser share or copy on web)"
        />

        {publishNotice ? (
          <View
            style={[
              styles.notice,
              publishNotice.variant === "error"
                ? styles.noticeError
                : styles.noticeSuccess,
            ]}
          >
            <Text style={styles.noticeText}>{publishNotice.message}</Text>
          </View>
        ) : null}

        <AppButton
          label="Publish to Discover"
          fullWidth
          onPress={beginPublishToDiscover}
          loading={publishing}
          accessibilityLabel="Publish to Discover"
          accessibilityHint="Posts a public snapshot of this outfit to the Discover feed"
        />

        {publishNotice?.variant === "success" ? (
          <AppButton
            label="Open Discover"
            variant="secondary"
            fullWidth
            onPress={() => {
              console.log("[Closy][OutfitDetail] navigate to Discover tab");
              router.push("/(tabs)/discover" as Href);
            }}
            accessibilityLabel="Open Discover tab"
          />
        ) : null}

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
  notice: {
    borderRadius: theme.radii.md,
    borderWidth: 1,
    padding: theme.spacing.md,
  },
  noticeSuccess: {
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.border,
  },
  noticeError: {
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.danger,
  },
  noticeText: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.text,
    lineHeight: 20,
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
  headerActions: {
    flexDirection: "row",
    alignItems: "center",
  },
  headerActionHit: {
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    marginRight: -theme.spacing.xs,
  },
  headerActionHitLast: {
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    marginRight: -theme.spacing.sm,
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
