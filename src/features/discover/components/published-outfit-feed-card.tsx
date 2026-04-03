import { Image } from "expo-image";
import { type Href, useRouter } from "expo-router";
import { memo, useCallback, useRef, useState } from "react";
import { Alert, Pressable, StyleSheet, Text, View } from "react-native";

import { useAuth } from "@/features/auth";
import { discoverService } from "@/features/discover/discover-service";
import { publishedOutfitAuthorLabel } from "@/features/discover/lib/published-outfit-attribution";
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

export type PublishedOutfitFeedCardProps = {
  item: PublishedOutfit;
  onLikeUpdated: (
    id: string,
    next: { likeCount: number; likedByMe: boolean },
  ) => void;
  /**
   * When false, hides the “By …” row (e.g. on an author profile where every post is theirs).
   * @default true
   */
  showAuthorAttribution?: boolean;
};

/** Fixed square thumb — every card uses the same size for a stable grid-like rhythm. */
const THUMB = 108;
const AUTHOR_AVATAR = 26;

function PublishedOutfitFeedCardInner({
  item,
  onLikeUpdated,
  showAuthorAttribution = true,
}: PublishedOutfitFeedCardProps) {
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const [likeBusy, setLikeBusy] = useState(false);
  const likeGuardRef = useRef(false);
  const previewLine = item.snapshot.lines.find((l) => l.imageUrl.trim().length > 0);
  const imageUri = previewLine?.imageUrl.trim() ?? "";
  const authorLabel = publishedOutfitAuthorLabel(item);
  const authorAvatar = item.authorAvatarUrl?.trim() ?? "";

  const openOutfit = useCallback(() => {
    router.push({
      pathname: "/published-outfit/[id]",
      params: { id: item.id },
    } as unknown as Href);
  }, [item.id, router]);

  const openAuthor = useCallback(() => {
    router.push({
      pathname: "/author/[userId]",
      params: {
        userId: item.authorUserId,
        displayName: authorLabel,
      },
    } as unknown as Href);
  }, [authorLabel, item.authorUserId, router]);

  const onHeartPress = useCallback(() => {
    if (!isAuthenticated) {
      Alert.alert("Sign in", "Sign in to like posts on Discover.");
      return;
    }
    if (likeGuardRef.current) return;
    likeGuardRef.current = true;
    setLikeBusy(true);
    void (async () => {
      try {
        const r = await discoverService.togglePublishedOutfitLike(item.id, {
          currentlyLiked: item.likedByMe,
        });
        if (r.ok) {
          onLikeUpdated(item.id, {
            likeCount: r.likeCount,
            likedByMe: r.likedByMe,
          });
        } else {
          Alert.alert("Couldn’t update like", r.errorMessage);
        }
      } finally {
        likeGuardRef.current = false;
        setLikeBusy(false);
      }
    })();
  }, [isAuthenticated, item.id, item.likedByMe, onLikeUpdated]);

  const likeA11y = item.likedByMe
    ? `Unlike, ${item.likeCount} likes`
    : `Like, ${item.likeCount} likes`;

  return (
    <View style={styles.card}>
      <View style={styles.cardMainColumn}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Open outfit: ${item.name.trim() || "Untitled outfit"}`}
          accessibilityHint="Opens the full published outfit"
          onPress={openOutfit}
          style={({ pressed }) => [styles.cardMainRow, pressed && styles.cardMainPressed]}
        >
          <View style={styles.thumbWrap}>
            {imageUri ? (
              <Image
                source={{ uri: imageUri }}
                style={styles.thumbImage}
                contentFit="cover"
                transition={media.imageTransitionMs.card}
              />
            ) : (
              <View style={styles.thumbPlaceholder}>
                <Text style={styles.thumbPlaceholderText}>No preview</Text>
              </View>
            )}
          </View>
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
        {showAuthorAttribution ? (
          <View style={styles.cardAuthorBlock}>
            <View style={styles.cardAuthorSpacer} />
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`Creator: ${authorLabel}. Open profile.`}
              accessibilityHint="Opens this creator’s profile and their public posts"
              onPress={openAuthor}
              hitSlop={8}
              style={({ pressed }) => [
                styles.cardAuthorHit,
                pressed && styles.cardAuthorHitPressed,
              ]}
            >
              <View style={styles.cardAuthorInner}>
                {authorAvatar.length > 0 ? (
                  <Image
                    source={{ uri: authorAvatar }}
                    style={styles.cardAuthorAvatar}
                    contentFit="cover"
                    transition={media.imageTransitionMs.card}
                    accessibilityIgnoresInvertColors
                  />
                ) : (
                  <View style={styles.cardAuthorAvatarPh} accessibilityRole="image" />
                )}
                <View style={styles.cardAuthorTextCol}>
                  <Text style={styles.creatorLabel}>Creator</Text>
                  <Text style={styles.cardAuthorName} numberOfLines={1}>
                    {authorLabel}
                  </Text>
                </View>
              </View>
            </Pressable>
          </View>
        ) : null}
      </View>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={likeA11y}
        accessibilityHint={
          isAuthenticated
            ? item.likedByMe
              ? "Removes your like"
              : "Adds your like"
            : "Sign in to like this post"
        }
        onPress={onHeartPress}
        disabled={likeBusy}
        hitSlop={4}
        style={({ pressed }) => [
          styles.cardLikeColumn,
          pressed && styles.cardLikeColumnPressed,
          likeBusy && styles.cardLikeColumnBusy,
        ]}
      >
        <Text
          style={[styles.heart, item.likedByMe ? styles.heartActive : styles.heartInactive]}
        >
          {item.likedByMe ? "♥" : "♡"}
        </Text>
        <Text style={styles.likeCount}>{item.likeCount}</Text>
      </Pressable>
    </View>
  );
}

function propsEqual(
  a: PublishedOutfitFeedCardProps,
  b: PublishedOutfitFeedCardProps,
): boolean {
  if (a.item !== b.item) return false;
  if (a.showAuthorAttribution !== b.showAuthorAttribution) return false;
  return a.onLikeUpdated === b.onLikeUpdated;
}

export const PublishedOutfitFeedCard = memo(
  PublishedOutfitFeedCardInner,
  propsEqual,
);

const styles = StyleSheet.create({
  card: {
    flexDirection: "row",
    borderRadius: theme.radii.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
    overflow: "hidden",
    alignItems: "stretch",
  },
  cardMainColumn: {
    flex: 1,
    minWidth: 0,
  },
  cardMainRow: {
    flexDirection: "row",
    alignItems: "center",
  },
  cardMainPressed: {
    opacity: 0.94,
  },
  thumbWrap: {
    width: THUMB,
    height: THUMB,
    borderRadius: theme.radii.sm,
    overflow: "hidden",
    margin: theme.spacing.md,
    marginRight: theme.spacing.sm,
    backgroundColor: theme.colors.border,
    alignSelf: "center",
  },
  thumbImage: {
    width: "100%",
    height: "100%",
  },
  thumbPlaceholder: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: theme.spacing.xs,
    backgroundColor: theme.colors.background,
  },
  thumbPlaceholderText: {
    fontSize: theme.typography.fontSize.xs,
    color: theme.colors.textMuted,
    textAlign: "center",
  },
  cardBody: {
    flex: 1,
    minWidth: 0,
    paddingVertical: theme.spacing.md,
    paddingRight: theme.spacing.sm,
    justifyContent: "center",
    gap: 6,
  },
  cardTitle: {
    fontSize: theme.typography.fontSize.md,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
    lineHeight: 22,
  },
  cardAuthorBlock: {
    flexDirection: "row",
    alignItems: "stretch",
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: theme.colors.border,
    marginLeft: 0,
  },
  /** Aligns creator row with title block (thumb margin + thumb + gap). */
  cardAuthorSpacer: {
    width: theme.spacing.md + THUMB + theme.spacing.sm,
  },
  cardAuthorHit: {
    flex: 1,
    paddingVertical: theme.spacing.sm,
    paddingRight: theme.spacing.md,
  },
  cardAuthorHitPressed: {
    opacity: 0.88,
  },
  cardAuthorInner: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.sm,
    minWidth: 0,
  },
  cardAuthorAvatar: {
    width: AUTHOR_AVATAR,
    height: AUTHOR_AVATAR,
    borderRadius: AUTHOR_AVATAR / 2,
    backgroundColor: theme.colors.border,
  },
  cardAuthorAvatarPh: {
    width: AUTHOR_AVATAR,
    height: AUTHOR_AVATAR,
    borderRadius: AUTHOR_AVATAR / 2,
    backgroundColor: theme.colors.border,
  },
  creatorLabel: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.4,
    marginBottom: 2,
  },
  cardAuthorTextCol: {
    flex: 1,
    minWidth: 0,
  },
  cardAuthorName: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.primary,
    fontWeight: theme.typography.fontWeight.semibold,
  },
  cardMeta: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    lineHeight: 18,
  },
  cardLikeColumn: {
    justifyContent: "center",
    alignItems: "center",
    paddingHorizontal: theme.spacing.md,
    minWidth: 56,
    borderLeftWidth: StyleSheet.hairlineWidth,
    borderLeftColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
  },
  cardLikeColumnPressed: {
    opacity: 0.88,
  },
  cardLikeColumnBusy: {
    opacity: 0.55,
  },
  heart: {
    fontSize: 22,
    lineHeight: 26,
  },
  heartActive: {
    color: theme.colors.danger,
  },
  heartInactive: {
    color: theme.colors.textMuted,
  },
  likeCount: {
    fontSize: theme.typography.fontSize.caption,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
    marginTop: 4,
  },
});
