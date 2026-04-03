import { useFocusEffect } from "@react-navigation/native";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import { EmptyState } from "@/components/ui/empty-state";
import { discoverService } from "@/features/discover/discover-service";
import { PublishedOutfitFeedCard } from "@/features/discover/components/published-outfit-feed-card";
import type { PublishedOutfit } from "@/features/discover/types/published-outfit";
import { theme } from "@/theme";

const PUBLISHED_LIMIT = 40;

type ProfilePublishedPostsSectionProps = {
  userId: string;
  supabaseConfigured: boolean;
  isAuthenticated: boolean;
  /** Increment after profile save to refresh list labels. */
  refreshToken?: number;
};

export function ProfilePublishedPostsSection({
  userId,
  supabaseConfigured,
  isAuthenticated,
  refreshToken = 0,
}: ProfilePublishedPostsSectionProps) {
  const [items, setItems] = useState<PublishedOutfit[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!supabaseConfigured || !isAuthenticated || !userId) {
      setItems([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    const next = await discoverService.fetchPublishedOutfitsForAuthor(
      userId,
      PUBLISHED_LIMIT,
    );
    setItems(next);
    setLoading(false);
  }, [userId, supabaseConfigured, isAuthenticated]);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  useEffect(() => {
    if (refreshToken > 0) void load();
  }, [refreshToken, load]);

  const patchLike = useCallback(
    (id: string, next: { likeCount: number; likedByMe: boolean }) => {
      setItems((prev) =>
        prev.map((it) => (it.id === id ? { ...it, ...next } : it)),
      );
    },
    [],
  );

  if (!supabaseConfigured || !isAuthenticated) {
    return null;
  }

  if (loading) {
    return (
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Your Discover posts</Text>
        <Text style={styles.cardHint}>
          Outfits you’ve shared publicly appear here and in Discover.
        </Text>
        <View style={styles.loadingRow}>
          <ActivityIndicator color={theme.colors.primary} />
          <Text style={styles.loadingCaption}>Loading posts…</Text>
        </View>
      </View>
    );
  }

  if (items.length === 0) {
    return (
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Your Discover posts</Text>
        <EmptyState
          title="Nothing published yet"
          description="Open one of your outfits and publish it to Discover to show it here and to everyone."
        />
      </View>
    );
  }

  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>Your Discover posts</Text>
      <Text style={styles.cardHint}>
        Tap a post to open it. Your display name and avatar on these cards match
        what you set above.
      </Text>
      {items.map((item) => (
        <View key={item.id} style={styles.postWrap}>
          <PublishedOutfitFeedCard
            item={item}
            onLikeUpdated={patchLike}
            showAuthorAttribution={false}
          />
        </View>
      ))}
      {items.length >= PUBLISHED_LIMIT ? (
        <Text style={styles.capHint}>
          Showing your most recent {PUBLISHED_LIMIT} posts.
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radii.md,
    backgroundColor: theme.colors.surface,
    padding: theme.spacing.md,
    gap: theme.spacing.sm,
  },
  cardTitle: {
    fontSize: theme.typography.fontSize.sm,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  cardHint: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    lineHeight: 18,
    marginBottom: theme.spacing.xs,
  },
  loadingRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.sm,
    paddingVertical: theme.spacing.md,
  },
  loadingCaption: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
  },
  postWrap: {
    marginBottom: theme.spacing.md,
  },
  capHint: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    fontStyle: "italic",
  },
});
