import { Image } from "expo-image";
import { type Href, Link } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { EmptyState } from "@/components/ui/empty-state";
import { ScreenContainer } from "@/components/ui/screen-container";
import { discoverService } from "@/features/discover/discover-service";
import type { PublishedOutfit } from "@/features/discover/types/published-outfit";
import { media } from "@/lib/constants";
import { theme } from "@/theme";

function formatPublishedLabel(publishedAt: number): string {
  try {
    const d = new Date(publishedAt);
    return d.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return "";
  }
}

function DiscoverCard({ item }: { item: PublishedOutfit }) {
  const previewLine = item.snapshot.lines.find((l) => l.imageUrl.trim().length > 0);
  const imageUri = previewLine?.imageUrl.trim() ?? "";

  return (
    <Link
      href={
        {
          pathname: "/published-outfit/[id]",
          params: { id: item.id },
        } as unknown as Href
      }
      asChild
    >
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`Open published outfit ${item.name}`}
        style={({ pressed }) => [styles.card, pressed && styles.cardPressed]}
      >
        {imageUri ? (
          <Image
            source={{ uri: imageUri }}
            style={styles.cardImage}
            contentFit="cover"
            transition={media.imageTransitionMs.card}
          />
        ) : (
          <View style={[styles.cardImage, styles.cardImagePlaceholder]}>
            <Text style={styles.cardImagePlaceholderText}>No preview</Text>
          </View>
        )}
        <View style={styles.cardBody}>
          <Text style={styles.cardTitle} numberOfLines={2}>
            {item.name.trim() || "Untitled outfit"}
          </Text>
          <Text style={styles.cardMeta} numberOfLines={1}>
            {item.pieceCount} piece{item.pieceCount === 1 ? "" : "s"} ·{" "}
            {formatPublishedLabel(item.publishedAt)}
          </Text>
        </View>
      </Pressable>
    </Link>
  );
}

export function DiscoverFeedScreen() {
  const [items, setItems] = useState<PublishedOutfit[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    const next = await discoverService.fetchFeed();
    setItems(next);
  }, []);

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
          <DiscoverCard item={item} />
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
  card: {
    flexDirection: "row",
    borderRadius: theme.radii.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
    overflow: "hidden",
  },
  cardPressed: {
    opacity: 0.92,
  },
  cardImage: {
    width: 96,
    minHeight: 96,
    backgroundColor: theme.colors.border,
  },
  cardImagePlaceholder: {
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: theme.spacing.sm,
  },
  cardImagePlaceholderText: {
    fontSize: theme.typography.fontSize.xs,
    color: theme.colors.textMuted,
    textAlign: "center",
  },
  cardBody: {
    flex: 1,
    minWidth: 0,
    padding: theme.spacing.md,
    justifyContent: "center",
    gap: theme.spacing.xs,
  },
  cardTitle: {
    fontSize: theme.typography.fontSize.md,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  cardMeta: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
  },
});
