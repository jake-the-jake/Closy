import { Image } from "expo-image";
import { useCallback, useEffect, useLayoutEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useNavigation } from "@react-navigation/native";

import { EmptyState } from "@/components/ui/empty-state";
import { discoverService } from "@/features/discover/discover-service";
import { PublishedOutfitFeedCard } from "@/features/discover/components/published-outfit-feed-card";
import { publishedOutfitAuthorLabel } from "@/features/discover/lib/published-outfit-attribution";
import type { PublishedOutfit } from "@/features/discover/types/published-outfit";
import { fetchPublicProfileByUserId } from "@/features/profile/lib/cloud-profiles";
import type { PublicUserProfile } from "@/features/profile/types/public-user-profile";
import { displayInitials } from "@/features/profile/types/account-profile";
import { media } from "@/lib/constants";
import { theme } from "@/theme";

export type AuthorProfileScreenProps = {
  authorUserId: string | null;
  /** Optional label from navigation (e.g. tap on “By …”) for instant header text. */
  initialDisplayName?: string | null;
};

function resolveProfileTitle(
  remote: PublicUserProfile | null,
  posts: PublishedOutfit[],
  initialDisplayName: string | undefined,
  authorUserId: string,
): string {
  const fromProfile = remote?.displayName?.trim();
  if (fromProfile) return fromProfile;
  const fromParam = initialDisplayName?.trim();
  if (fromParam) return fromParam;
  if (posts.length > 0) return publishedOutfitAuthorLabel(posts[0]);
  const compact = authorUserId.replace(/-/g, "");
  return `Member ${compact.slice(0, 8)}`;
}

export function AuthorProfileScreen({
  authorUserId,
  initialDisplayName,
}: AuthorProfileScreenProps) {
  const navigation = useNavigation();
  const [items, setItems] = useState<PublishedOutfit[]>([]);
  const [authorProfile, setAuthorProfile] = useState<PublicUserProfile | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    if (!authorUserId) {
      setItems([]);
      setAuthorProfile(null);
      return;
    }
    const [next, profileRow] = await Promise.all([
      discoverService.fetchPublishedOutfitsForAuthor(authorUserId),
      fetchPublicProfileByUserId(authorUserId),
    ]);
    setItems(next);
    setAuthorProfile(profileRow);
  }, [authorUserId]);

  useEffect(() => {
    let mounted = true;
    if (!authorUserId) {
      setLoading(false);
      setItems([]);
      setAuthorProfile(null);
      return;
    }
    setLoading(true);
    void load().finally(() => {
      if (mounted) setLoading(false);
    });
    return () => {
      mounted = false;
    };
  }, [authorUserId, load]);

  const profileTitle = useMemo(
    () =>
      authorUserId
        ? resolveProfileTitle(
            authorProfile,
            items,
            initialDisplayName ?? undefined,
            authorUserId,
          )
        : "Profile",
    [authorProfile, authorUserId, initialDisplayName, items],
  );

  const headerAvatarUri =
    authorProfile?.avatarUrl?.trim() ||
    items[0]?.authorAvatarUrl?.trim() ||
    "";
  const headerInitials = displayInitials(profileTitle);

  useLayoutEffect(() => {
    navigation.setOptions({ title: profileTitle });
  }, [navigation, profileTitle]);

  const patchLike = useCallback(
    (id: string, next: { likeCount: number; likedByMe: boolean }) => {
      setItems((prev) =>
        prev.map((it) => (it.id === id ? { ...it, ...next } : it)),
      );
    },
    [],
  );

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await load();
    } finally {
      setRefreshing(false);
    }
  }, [load]);

  const listHeader = useMemo(() => {
    if (!authorUserId || loading) return null;
    return (
      <View style={styles.header}>
        <Text style={styles.headerKicker}>Discover creator</Text>
        <View style={styles.headerHero}>
          {headerAvatarUri.length > 0 ? (
            <Image
              source={{ uri: headerAvatarUri }}
              style={styles.headerAvatar}
              contentFit="cover"
              transition={media.imageTransitionMs.card}
              accessibilityLabel=""
            />
          ) : (
            <View style={styles.headerAvatarFallback}>
              <Text style={styles.headerAvatarInitials}>{headerInitials}</Text>
            </View>
          )}
          <Text style={styles.headerName}>{profileTitle}</Text>
        </View>
        <Text style={styles.headerSummary}>
          {items.length} public look{items.length === 1 ? "" : "s"}
        </Text>
      </View>
    );
  }, [
    authorUserId,
    headerAvatarUri,
    headerInitials,
    items.length,
    loading,
    profileTitle,
  ]);

  if (!authorUserId) {
    return (
      <View style={styles.missing}>
        <EmptyState
          title="Profile not found"
          description="This link may be invalid or incomplete."
        />
      </View>
    );
  }

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator color={theme.colors.primary} />
        <Text style={styles.loadingText}>Loading profile…</Text>
      </View>
    );
  }

  if (items.length === 0) {
    return (
      <View style={styles.list}>
        <View style={styles.emptyListContent}>
          <View style={styles.header}>
            <Text style={styles.headerKicker}>Discover creator</Text>
            <View style={styles.headerHero}>
              {headerAvatarUri.length > 0 ? (
                <Image
                  source={{ uri: headerAvatarUri }}
                  style={styles.headerAvatar}
                  contentFit="cover"
                  transition={media.imageTransitionMs.card}
                  accessibilityLabel=""
                />
              ) : (
                <View style={styles.headerAvatarFallback}>
                  <Text style={styles.headerAvatarInitials}>{headerInitials}</Text>
                </View>
              )}
              <Text style={styles.headerName}>{profileTitle}</Text>
            </View>
            <Text style={styles.headerSummary}>No public looks yet</Text>
          </View>
          <View style={styles.emptyBody}>
            <EmptyState
              title="No posts yet"
              description="When this person publishes outfits to Discover, they’ll show up here."
            />
          </View>
        </View>
      </View>
    );
  }

  return (
    <FlatList
      style={styles.list}
      data={items}
      keyExtractor={(row) => row.id}
      ListHeaderComponent={listHeader}
      renderItem={({ item }) => (
        <View style={styles.cardWrap}>
          <PublishedOutfitFeedCard
            item={item}
            onLikeUpdated={patchLike}
            showAuthorAttribution={false}
          />
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
  list: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  listContent: {
    paddingHorizontal: theme.spacing.md,
    paddingTop: theme.spacing.md,
    paddingBottom: theme.spacing.xl,
  },
  cardWrap: {
    marginBottom: theme.spacing.md,
  },
  header: {
    marginBottom: theme.spacing.lg,
    gap: theme.spacing.sm,
  },
  headerHero: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.md,
  },
  headerAvatar: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: theme.colors.border,
  },
  headerAvatarFallback: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: theme.colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  headerAvatarInitials: {
    fontSize: theme.typography.fontSize.md,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.surface,
  },
  headerKicker: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  headerName: {
    flex: 1,
    minWidth: 0,
    fontSize: theme.typography.fontSize.xxl,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
    lineHeight: theme.typography.lineHeight.title,
  },
  headerSummary: {
    fontSize: theme.typography.fontSize.md,
    color: theme.colors.textMuted,
  },
  centered: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: theme.spacing.md,
    backgroundColor: theme.colors.background,
  },
  loadingText: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
  },
  missing: {
    flex: 1,
    padding: theme.spacing.md,
    backgroundColor: theme.colors.background,
  },
  emptyListContent: {
    paddingHorizontal: theme.spacing.md,
    paddingTop: theme.spacing.md,
    paddingBottom: theme.spacing.xl,
    flexGrow: 1,
  },
  emptyBody: {
    paddingTop: theme.spacing.md,
  },
});
