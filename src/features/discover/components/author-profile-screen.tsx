import { Image } from "expo-image";
import { useCallback, useEffect, useLayoutEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useNavigation } from "@react-navigation/native";

import { EmptyState } from "@/components/ui/empty-state";
import { useAuth } from "@/features/auth";
import { AuthorProfileHeader } from "@/features/discover/components/author-profile-header";
import { discoverService } from "@/features/discover/discover-service";
import { PublishedOutfitFeedCard } from "@/features/discover/components/published-outfit-feed-card";
import { publishedOutfitAuthorLabel } from "@/features/discover/lib/published-outfit-attribution";
import type { PublishedOutfit } from "@/features/discover/types/published-outfit";
import { fetchPublicProfileByUserId } from "@/features/profile/lib/cloud-profiles";
import type { PublicUserProfile } from "@/features/profile/types/public-user-profile";
import { displayInitials } from "@/features/profile/types/account-profile";
import type { AuthorFollowSnapshot } from "@/features/social";
import {
  fetchAuthorFollowSnapshot,
  followAuthor,
  unfollowAuthor,
} from "@/features/social";
import { media } from "@/lib/constants";
import { supabase } from "@/lib/supabase/client";
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

const EMPTY_SNAPSHOT: AuthorFollowSnapshot = {
  followerCount: 0,
  followingCount: 0,
  isFollowing: false,
};

export function AuthorProfileScreen({
  authorUserId,
  initialDisplayName,
}: AuthorProfileScreenProps) {
  const navigation = useNavigation();
  const { user, isAuthenticated } = useAuth();
  const [items, setItems] = useState<PublishedOutfit[]>([]);
  const [authorProfile, setAuthorProfile] = useState<PublicUserProfile | null>(
    null,
  );
  const [followSnapshot, setFollowSnapshot] =
    useState<AuthorFollowSnapshot | null>(null);
  const [followBusy, setFollowBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    if (!authorUserId) {
      setItems([]);
      setAuthorProfile(null);
      setFollowSnapshot(null);
      return;
    }
    const viewerId = user?.id ?? null;
    const [next, profileRow, snap] = await Promise.all([
      discoverService.fetchPublishedOutfitsForAuthor(authorUserId),
      fetchPublicProfileByUserId(authorUserId),
      fetchAuthorFollowSnapshot(authorUserId, viewerId),
    ]);
    setItems(next);
    setAuthorProfile(profileRow);
    setFollowSnapshot(snap ?? EMPTY_SNAPSHOT);
  }, [authorUserId, user?.id]);

  useEffect(() => {
    let mounted = true;
    if (!authorUserId) {
      setLoading(false);
      setItems([]);
      setAuthorProfile(null);
      setFollowSnapshot(null);
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
  const isOwnProfile =
    authorUserId != null && user?.id != null && authorUserId === user.id;

  const headerAvatarEl = useMemo(
    () =>
      headerAvatarUri.length > 0 ? (
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
      ),
    [headerAvatarUri, headerInitials],
  );

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

  const onFollowPress = useCallback(() => {
    if (!authorUserId || !followSnapshot) return;
    if (!isAuthenticated || !user?.id) {
      Alert.alert(
        "Sign in",
        "Sign in to follow creators on Discover.",
      );
      return;
    }
    if (!supabase) return;
    if (followBusy) return;

    const wasFollowing = followSnapshot.isFollowing;
    setFollowBusy(true);
    void (async () => {
      if (wasFollowing) {
        const r = await unfollowAuthor(supabase, user.id, authorUserId);
        setFollowBusy(false);
        if (r.ok) {
          const fresh = await fetchAuthorFollowSnapshot(authorUserId, user.id);
          setFollowSnapshot(fresh ?? EMPTY_SNAPSHOT);
        } else {
          Alert.alert("Couldn’t unfollow", r.message);
        }
      } else {
        const r = await followAuthor(supabase, user.id, authorUserId);
        setFollowBusy(false);
        if (r.ok) {
          const fresh = await fetchAuthorFollowSnapshot(authorUserId, user.id);
          setFollowSnapshot(fresh ?? EMPTY_SNAPSHOT);
        } else {
          Alert.alert("Couldn’t follow", r.message);
        }
      }
    })();
  }, [authorUserId, followBusy, followSnapshot, isAuthenticated, user?.id]);

  const postsSummary =
    items.length === 0
      ? "No public looks yet"
      : `${items.length} public look${items.length === 1 ? "" : "s"}`;

  const snap = followSnapshot ?? EMPTY_SNAPSHOT;

  const listHeader = useMemo(() => {
    if (!authorUserId || loading) return null;
    return (
      <AuthorProfileHeader
        profileTitle={profileTitle}
        headerAvatar={headerAvatarEl}
        postsSummary={postsSummary}
        followerCount={snap.followerCount}
        followingCount={snap.followingCount}
        showFollowChrome={!isOwnProfile}
        isAuthenticated={isAuthenticated}
        isFollowing={snap.isFollowing}
        followBusy={followBusy}
        onFollowPress={onFollowPress}
      />
    );
  }, [
    authorUserId,
    followBusy,
    headerAvatarEl,
    isAuthenticated,
    isOwnProfile,
    loading,
    onFollowPress,
    postsSummary,
    profileTitle,
    snap.followerCount,
    snap.followingCount,
    snap.isFollowing,
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
          <AuthorProfileHeader
            profileTitle={profileTitle}
            headerAvatar={headerAvatarEl}
            postsSummary={postsSummary}
            followerCount={snap.followerCount}
            followingCount={snap.followingCount}
            showFollowChrome={!isOwnProfile}
            isAuthenticated={isAuthenticated}
            isFollowing={snap.isFollowing}
            followBusy={followBusy}
            onFollowPress={onFollowPress}
          />
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
