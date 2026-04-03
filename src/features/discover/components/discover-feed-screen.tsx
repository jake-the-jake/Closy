import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { EmptyState } from "@/components/ui/empty-state";
import { ScreenContainer } from "@/components/ui/screen-container";
import { discoverService } from "@/features/discover/discover-service";
import { PublishedOutfitFeedCard } from "@/features/discover/components/published-outfit-feed-card";
import type { PublishedOutfit } from "@/features/discover/types/published-outfit";
import { theme } from "@/theme";

export function DiscoverFeedScreen() {
  const [items, setItems] = useState<PublishedOutfit[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    const next = await discoverService.fetchFeed();
    setItems(next);
  }, []);

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

  if (loading) {
    return (
      <ScreenContainer scroll={false} omitTopSafeArea style={styles.centered}>
        <ActivityIndicator color={theme.colors.primary} />
        <Text style={styles.loadingText}>Loading Discover…</Text>
      </ScreenContainer>
    );
  }

  if (items.length === 0) {
    return (
      <ScreenContainer scroll omitTopSafeArea contentContainerStyle={styles.emptyWrap}>
        <EmptyState
          title="Nothing here yet"
          description="When you publish an outfit from its detail screen, it will show up in this feed for everyone."
        />
      </ScreenContainer>
    );
  }

  return (
    <FlatList
      style={styles.list}
      data={items}
      keyExtractor={(row) => row.id}
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
  );
}

const styles = StyleSheet.create({
  centered: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: theme.spacing.md,
  },
  loadingText: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
  },
  emptyWrap: {
    paddingTop: theme.spacing.xl,
    paddingHorizontal: theme.spacing.md,
  },
  list: {
    flex: 1,
  },
  listContent: {
    paddingHorizontal: theme.spacing.md,
    paddingTop: theme.spacing.md,
    paddingBottom: theme.spacing.xl,
  },
  cardWrap: {
    marginBottom: theme.spacing.md,
  },
});
