import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Platform,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { EmptyState } from "@/components/ui/empty-state";
import { ScreenContainer } from "@/components/ui/screen-container";
import { useAuth } from "@/features/auth";
import { discoverService } from "@/features/discover/discover-service";
import type { ForYouFeedSignalsRow } from "@/features/discover/lib/cloud-published-outfits";
import { DiscoverFeedSkeleton } from "@/features/discover/components/discover-feed-skeleton";
import { PublishedOutfitFeedCard } from "@/features/discover/components/published-outfit-feed-card";
import type { PublishedOutfit } from "@/features/discover/types/published-outfit";
import { theme } from "@/theme";

type FeedMode = "all" | "following" | "forYou";

function signalStrength(s: ForYouFeedSignalsRow | null): number {
  if (s == null) return 0;
  return s.follows + s.likes + s.comments + s.wardrobePieces;
}

export function DiscoverFeedScreen() {
  const { isAuthenticated, supabaseConfigured } = useAuth();
  const [mode, setMode] = useState<FeedMode>("all");
  const [items, setItems] = useState<PublishedOutfit[]>([]);
  const [followedUserCount, setFollowedUserCount] = useState(0);
  const [forYouSignals, setForYouSignals] =
    useState<ForYouFeedSignalsRow | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    if (mode === "all") {
      const next = await discoverService.fetchFeed();
      setItems(next);
      setFollowedUserCount(0);
      setForYouSignals(null);
      return;
    }
    if (mode === "following") {
      if (!isAuthenticated) {
        setItems([]);
        setFollowedUserCount(0);
        setForYouSignals(null);
        return;
      }
      const r = await discoverService.fetchFollowingFeed();
      setItems(r.items);
      setFollowedUserCount(r.followedUserCount);
      setForYouSignals(null);
      return;
    }
    if (!isAuthenticated) {
      setItems([]);
      setFollowedUserCount(0);
      setForYouSignals(null);
      return;
    }
    const r = await discoverService.fetchForYouFeed();
    setItems(r.items);
    setFollowedUserCount(0);
    setForYouSignals(r.signals);
  }, [mode, isAuthenticated]);

  const patchLike = useCallback(
    (id: string, next: { likeCount: number; likedByMe: boolean }) => {
      setItems((prev) =>
        prev.map((it) => (it.id === id ? { ...it, ...next } : it)),
      );
    },
    [],
  );

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    void load().finally(() => {
      if (mounted) setLoading(false);
    });
    return () => {
      mounted = false;
    };
  }, [load]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await load();
    } finally {
      setRefreshing(false);
    }
  }, [load]);

  const hasStrongForYouSignals = useMemo(
    () => signalStrength(forYouSignals) > 0,
    [forYouSignals],
  );

  const forYouWeakHint = useMemo(() => {
    if (
      mode !== "forYou" ||
      !isAuthenticated ||
      hasStrongForYouSignals ||
      items.length === 0
    ) {
      return null;
    }
    return (
      <View style={styles.forYouHint}>
        <Text style={styles.forYouHintTitle}>Roughly sorted for you</Text>
        <Text style={styles.forYouHintBody}>
          This feed bumps posts from people you follow, authors you have liked or
          commented on, outfits that overlap your wardrobe categories, then a
          light blend of popularity and recency. Follow, heart, comment, or sync
          wardrobe pieces to sharpen it—nothing here is black-box ML.
        </Text>
      </View>
    );
  }, [mode, isAuthenticated, hasStrongForYouSignals, items.length]);

  if (!supabaseConfigured) {
    return (
      <View style={styles.root}>
        <ScreenContainer scroll omitTopSafeArea contentContainerStyle={styles.emptyWrap}>
          <EmptyState
            title="Discover isn’t connected yet"
            description="Add your Supabase project URL and anon key to your environment, restart the app, then use All, Following, and For You with likes and profiles."
          />
        </ScreenContainer>
      </View>
    );
  }

  const segmentBar = (
    <View style={styles.segmentBar}>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ selected: mode === "all" }}
        onPress={() => setMode("all")}
        style={({ pressed }) => [
          styles.segment,
          mode === "all" && styles.segmentActive,
          pressed && styles.segmentPressed,
        ]}
      >
        <Text
          style={[
            styles.segmentLabel,
            mode === "all" && styles.segmentLabelActive,
          ]}
          numberOfLines={1}
        >
          All
        </Text>
      </Pressable>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ selected: mode === "following" }}
        onPress={() => setMode("following")}
        style={({ pressed }) => [
          styles.segment,
          mode === "following" && styles.segmentActive,
          pressed && styles.segmentPressed,
        ]}
      >
        <Text
          style={[
            styles.segmentLabel,
            mode === "following" && styles.segmentLabelActive,
          ]}
          numberOfLines={1}
        >
          Following
        </Text>
      </Pressable>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ selected: mode === "forYou" }}
        onPress={() => setMode("forYou")}
        style={({ pressed }) => [
          styles.segment,
          mode === "forYou" && styles.segmentActive,
          pressed && styles.segmentPressed,
        ]}
      >
        <Text
          style={[
            styles.segmentLabel,
            mode === "forYou" && styles.segmentLabelActive,
          ]}
          numberOfLines={1}
        >
          For You
        </Text>
      </Pressable>
    </View>
  );

  if (loading) {
    return (
      <View style={styles.root}>
        {segmentBar}
        <ScreenContainer scroll={false} omitTopSafeArea style={styles.skeletonWrap}>
          <DiscoverFeedSkeleton />
          <View style={styles.skeletonFooter}>
            <ActivityIndicator color={theme.colors.primary} />
            <Text style={styles.loadingText}>Loading Discover…</Text>
          </View>
        </ScreenContainer>
      </View>
    );
  }

  if (mode === "following" && !isAuthenticated) {
    return (
      <View style={styles.root}>
        {segmentBar}
        <ScreenContainer scroll omitTopSafeArea contentContainerStyle={styles.emptyWrap}>
          <EmptyState
            title="Sign in to use Following"
            description="Following shows only posts from people you follow. Sign in (or create an account) and you’ll see that feed here."
          />
        </ScreenContainer>
      </View>
    );
  }

  if (mode === "forYou" && !isAuthenticated) {
    return (
      <View style={styles.root}>
        {segmentBar}
        <ScreenContainer scroll omitTopSafeArea contentContainerStyle={styles.emptyWrap}>
          <EmptyState
            title="Sign in for For You"
            description="For You ranks Discover posts based on your follows, likes, comments, and wardrobe categories. Sign in to get a tailored mix—or browse All for the full public feed."
          />
        </ScreenContainer>
      </View>
    );
  }

  if (
    mode === "following" &&
    isAuthenticated &&
    followedUserCount === 0
  ) {
    return (
      <View style={styles.root}>
        {segmentBar}
        <ScreenContainer scroll omitTopSafeArea contentContainerStyle={styles.emptyWrap}>
          <EmptyState
            title="You’re not following anyone yet"
            description="Open the All tab, tap a post, then the creator’s name to open their profile. Tap Follow—new publishes from them will show up in Following first."
          />
        </ScreenContainer>
      </View>
    );
  }

  if (
    mode === "following" &&
    isAuthenticated &&
    followedUserCount > 0 &&
    items.length === 0
  ) {
    return (
      <View style={styles.root}>
        {segmentBar}
        <ScreenContainer scroll omitTopSafeArea contentContainerStyle={styles.emptyWrap}>
          <EmptyState
            title="No new posts from follows"
            description="Nobody you follow has published recently. Check back later, or browse All for the full community feed."
          />
        </ScreenContainer>
      </View>
    );
  }

  if (mode === "all" && items.length === 0) {
    return (
      <View style={styles.root}>
        {segmentBar}
        <ScreenContainer scroll omitTopSafeArea contentContainerStyle={styles.emptyWrap}>
          <EmptyState
            title="No outfits on Discover yet"
            description="Publish an outfit from your wardrobe (open an outfit, then share to Discover). Your post will show up here for everyone—and you can like and comment on others’ posts too."
          />
        </ScreenContainer>
      </View>
    );
  }

  if (mode === "forYou" && isAuthenticated && items.length === 0) {
    return (
      <View style={styles.root}>
        {segmentBar}
        <ScreenContainer scroll omitTopSafeArea contentContainerStyle={styles.emptyWrap}>
          <EmptyState
            title="Nothing on Discover yet"
            description="Once the community publishes outfits, your For You mix will appear here—ranked with follows, engagement, wardrobe overlap, and recency."
          />
        </ScreenContainer>
      </View>
    );
  }

  return (
    <View style={styles.root}>
      {segmentBar}
      <FlatList
        style={styles.list}
        data={items}
        keyExtractor={(row) => row.id}
        initialNumToRender={6}
        windowSize={7}
        maxToRenderPerBatch={8}
        updateCellsBatchingPeriod={50}
        removeClippedSubviews={Platform.OS === "android"}
        ListHeaderComponent={forYouWeakHint ?? undefined}
        renderItem={({ item }) => (
          <View style={styles.cardWrap}>
            <PublishedOutfitFeedCard item={item} onLikeUpdated={patchLike} />
          </View>
        )}
        contentContainerStyle={styles.listContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={() => void onRefresh()} />
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
  },
  segmentBar: {
    flexDirection: "row",
    gap: theme.spacing.xs,
    paddingHorizontal: theme.spacing.md,
    paddingTop: theme.spacing.sm,
    paddingBottom: theme.spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: theme.colors.border,
    backgroundColor: theme.colors.background,
  },
  segment: {
    flex: 1,
    paddingVertical: theme.spacing.sm,
    paddingHorizontal: theme.spacing.xs,
    borderRadius: theme.radii.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
    alignItems: "center",
    minWidth: 0,
  },
  segmentActive: {
    borderColor: theme.colors.primary,
    backgroundColor: theme.colors.surface,
  },
  segmentPressed: {
    opacity: 0.88,
  },
  segmentLabel: {
    fontSize: theme.typography.fontSize.sm,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
  },
  segmentLabelActive: {
    color: theme.colors.primary,
  },
  skeletonWrap: {
    flex: 1,
    paddingBottom: theme.spacing.lg,
  },
  skeletonFooter: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: theme.spacing.sm,
    paddingTop: theme.spacing.md,
  },
  loadingText: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
  },
  emptyWrap: {
    paddingTop: theme.spacing.xl,
    paddingHorizontal: theme.spacing.md,
    flexGrow: 1,
  },
  list: {
    flex: 1,
  },
  listContent: {
    paddingHorizontal: theme.spacing.md,
    paddingTop: theme.spacing.md,
    paddingBottom: theme.spacing.xl,
  },
  forYouHint: {
    marginBottom: theme.spacing.md,
    borderRadius: theme.radii.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
    padding: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  forYouHintTitle: {
    fontSize: theme.typography.fontSize.sm,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  forYouHintBody: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    lineHeight: 20,
  },
  cardWrap: {
    marginBottom: theme.spacing.md,
  },
});
