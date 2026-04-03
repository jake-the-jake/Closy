import { Image } from "expo-image";
import { type Href, useRouter } from "expo-router";
import { useCallback, useEffect, useLayoutEffect, useState } from "react";
import { ActivityIndicator, Alert, Pressable, StyleSheet, Text, View } from "react-native";
import { useNavigation } from "@react-navigation/native";

import { AppButton } from "@/components/ui/app-button";
import { EmptyState } from "@/components/ui/empty-state";
import { ScreenContainer } from "@/components/ui/screen-container";
import { useAuth } from "@/features/auth";
import { discoverService } from "@/features/discover/discover-service";
import { publishedOutfitAuthorLabel } from "@/features/discover/lib/published-outfit-attribution";
import type { PublishedOutfit } from "@/features/discover/types/published-outfit";
import { media } from "@/lib/constants";
import { theme } from "@/theme";

export type PublishedOutfitDetailScreenProps = {
  publishedId: string | null;
};

function formatPublishedLabel(publishedAt: number): string {
  try {
    const d = new Date(publishedAt);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

export function PublishedOutfitDetailScreen({ publishedId }: PublishedOutfitDetailScreenProps) {
  const navigation = useNavigation();
  const router = useRouter();
  const { user } = useAuth();
  const [row, setRow] = useState<PublishedOutfit | null | undefined>(undefined);
  const [removing, setRemoving] = useState(false);
  const [likeBusy, setLikeBusy] = useState(false);

  const load = useCallback(async () => {
    if (!publishedId) {
      setRow(null);
      return;
    }
    setRow(undefined);
    const next = await discoverService.fetchPublishedById(publishedId);
    setRow(next);
  }, [publishedId]);

  useEffect(() => {
    void load();
  }, [load]);

  const openAuthorProfile = useCallback(() => {
    if (row == null) return;
    router.push({
      pathname: "/author/[userId]",
      params: {
        userId: row.authorUserId,
        displayName: publishedOutfitAuthorLabel(row),
      },
    } as unknown as Href);
  }, [row, router]);

  const requestUnpublish = useCallback(() => {
    if (row == null) return;
    Alert.alert(
      "Remove from Discover?",
      "This post will disappear for everyone. You can publish the outfit again later from your saved outfit.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Remove",
          style: "destructive",
          onPress: () => {
            void (async () => {
              setRemoving(true);
              try {
                const r = await discoverService.unpublishPublishedOutfit(row.id);
                if (r.ok) {
                  router.replace("/(tabs)/discover" as Href);
                } else {
                  Alert.alert("Could not remove", r.errorMessage);
                }
              } finally {
                setRemoving(false);
              }
            })();
          },
        },
      ],
    );
  }, [row, router]);

  const toggleLike = useCallback(() => {
    if (row == null) return;
    if (user?.id == null) {
      Alert.alert("Sign in", "Sign in to like posts on Discover.");
      return;
    }
    if (likeBusy) return;
    setLikeBusy(true);
    void (async () => {
      const r = await discoverService.togglePublishedOutfitLike(row.id, {
        currentlyLiked: row.likedByMe,
      });
      setLikeBusy(false);
      if (r.ok) {
        setRow((prev) =>
          prev != null ? { ...prev, likeCount: r.likeCount, likedByMe: r.likedByMe } : prev,
        );
      } else {
        Alert.alert("Couldn’t update like", r.errorMessage);
      }
    })();
  }, [row, user?.id, likeBusy]);

  useLayoutEffect(() => {
    if (row === undefined) {
      navigation.setOptions({ title: "Published outfit" });
      return;
    }
    if (row === null) {
      navigation.setOptions({ title: "Post" });
      return;
    }
    navigation.setOptions({ title: row.name.trim() || "Published outfit" });
  }, [navigation, row]);

  if (!publishedId || row === null) {
    return (
      <ScreenContainer scroll={false} omitTopSafeArea>
        <EmptyState
          title="Post not found"
          description="It may have been removed or the link is invalid."
        />
      </ScreenContainer>
    );
  }

  if (row === undefined) {
    return (
      <ScreenContainer scroll={false} omitTopSafeArea style={styles.centered}>
        <ActivityIndicator color={theme.colors.primary} />
        <Text style={styles.loadingText}>Loading…</Text>
      </ScreenContainer>
    );
  }

  const { snapshot } = row;
  const isAuthor = user?.id != null && user.id === row.authorUserId;
  const authorLabel = publishedOutfitAuthorLabel(row);
  const authorAvatar = row.authorAvatarUrl?.trim() ?? "";

  return (
    <ScreenContainer scroll omitTopSafeArea contentContainerStyle={styles.body}>
      <Text style={styles.lede}>
        {row.pieceCount} piece{row.pieceCount === 1 ? "" : "s"} · Published{" "}
        {formatPublishedLabel(row.publishedAt)}
      </Text>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`Open profile for ${authorLabel}`}
        accessibilityHint="Shows this creator’s public outfits on Discover"
        onPress={openAuthorProfile}
        style={({ pressed }) => [
          styles.authorByRowHit,
          pressed && styles.authorByRowPressed,
        ]}
      >
        <View style={styles.authorByRow}>
          {authorAvatar.length > 0 ? (
            <Image
              source={{ uri: authorAvatar }}
              style={styles.authorAvatar}
              contentFit="cover"
              transition={media.imageTransitionMs.card}
            />
          ) : (
            <View style={styles.authorAvatarPh} />
          )}
          <Text style={styles.authorLine}>By {authorLabel}</Text>
        </View>
      </Pressable>

      <Pressable
        accessibilityRole="button"
        accessibilityLabel={
          row.likedByMe
            ? `Unlike, ${row.likeCount} likes`
            : `Like, ${row.likeCount} likes`
        }
        accessibilityHint={
          user?.id != null
            ? row.likedByMe
              ? "Removes your like"
              : "Adds your like"
            : "Sign in to like this post"
        }
        onPress={toggleLike}
        disabled={likeBusy}
        style={({ pressed }) => [styles.likeRow, pressed && styles.likeRowPressed]}
      >
        <Text
          style={[styles.likeHeart, row.likedByMe ? styles.likeHeartActive : styles.likeHeartInactive]}
        >
          {row.likedByMe ? "♥" : "♡"}
        </Text>
        <View style={styles.likeTextBlock}>
          <Text style={styles.likeCountLine}>
            {row.likeCount} like{row.likeCount === 1 ? "" : "s"}
          </Text>
          <Text style={styles.likeHint}>
            {user?.id != null
              ? row.likedByMe
                ? "You liked this · tap to remove"
                : "Tap to like"
              : "Sign in to like"}
          </Text>
        </View>
      </Pressable>

      <Text style={styles.snapshotHint}>
        Snapshot from {new Date(snapshot.generatedAtIso).toLocaleDateString()} — edits to
        the original outfit won’t change this post.
      </Text>

      <Text style={styles.sectionLabel}>Pieces</Text>
      <View style={styles.list}>
        {snapshot.lines.map((line) => {
          const uri = line.imageUrl.trim();
          return (
            <View key={line.clothingItemId} style={styles.row}>
              {uri ? (
                <Image
                  source={{ uri }}
                  style={styles.thumb}
                  contentFit="cover"
                  transition={media.imageTransitionMs.card}
                />
              ) : (
                <View style={[styles.thumb, styles.thumbPlaceholder]}>
                  <Text style={styles.thumbPhText}>No photo</Text>
                </View>
              )}
              <View style={styles.rowText}>
                <Text style={styles.rowTitle} numberOfLines={2}>
                  {line.label}
                </Text>
                <Text style={styles.rowSub} numberOfLines={1}>
                  {line.categoryLabel}
                  {line.missingFromWardrobe ? " · removed at publish time" : ""}
                </Text>
              </View>
            </View>
          );
        })}
      </View>

      {isAuthor ? (
        <View style={styles.authorActions}>
          <AppButton
            label={removing ? "Removing…" : "Remove from Discover"}
            variant="secondary"
            fullWidth
            onPress={requestUnpublish}
            disabled={removing}
            accessibilityLabel="Remove from Discover"
            accessibilityHint="Deletes this public post; your saved outfit is unchanged"
          />
        </View>
      ) : null}
    </ScreenContainer>
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
  body: {
    paddingBottom: theme.spacing.xl,
    gap: theme.spacing.lg,
  },
  lede: {
    fontSize: theme.typography.fontSize.md,
    color: theme.colors.textMuted,
  },
  authorByRowHit: {
    alignSelf: "flex-start",
  },
  authorByRowPressed: {
    opacity: 0.85,
  },
  authorByRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.sm,
  },
  authorAvatar: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: theme.colors.border,
  },
  authorAvatarPh: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: theme.colors.border,
  },
  authorLine: {
    fontSize: theme.typography.fontSize.md,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.primary,
  },
  likeRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
  },
  likeRowPressed: {
    opacity: 0.85,
  },
  likeHeart: {
    fontSize: 28,
    lineHeight: 32,
  },
  likeHeartActive: {
    color: theme.colors.danger,
  },
  likeHeartInactive: {
    color: theme.colors.textMuted,
  },
  likeTextBlock: {
    flex: 1,
    minWidth: 0,
    gap: 2,
  },
  likeCountLine: {
    fontSize: theme.typography.fontSize.md,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  likeHint: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
  },
  snapshotHint: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
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
    paddingVertical: theme.spacing.sm,
    paddingHorizontal: theme.spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: theme.colors.border,
    gap: theme.spacing.md,
  },
  thumb: {
    width: 56,
    height: 56,
    borderRadius: theme.radii.sm,
    backgroundColor: theme.colors.border,
  },
  thumbPlaceholder: {
    alignItems: "center",
    justifyContent: "center",
  },
  thumbPhText: {
    fontSize: 10,
    color: theme.colors.textMuted,
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
  authorActions: {
    marginTop: theme.spacing.lg,
    paddingTop: theme.spacing.lg,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: theme.colors.border,
  },
});
