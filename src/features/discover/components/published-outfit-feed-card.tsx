import { Image } from "expo-image";
import { type Href, useRouter } from "expo-router";
import { useCallback, useState } from "react";
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

const IMAGE_W = 96;
const AUTHOR_AVATAR = 22;

export function PublishedOutfitFeedCard({
  item,
  onLikeUpdated,
  showAuthorAttribution = true,
}: PublishedOutfitFeedCardProps) {
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const [likeBusy, setLikeBusy] = useState(false);
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
    if (likeBusy) return;
    setLikeBusy(true);
    void (async () => {
      const r = await discoverService.togglePublishedOutfitLike(item.id, {
        currentlyLiked: item.likedByMe,
      });
      setLikeBusy(false);
      if (r.ok) {
        onLikeUpdated(item.id, { likeCount: r.likeCount, likedByMe: r.likedByMe });
      } else {
        Alert.alert("Couldn’t update like", r.errorMessage);
      }
    })();
  }, [isAuthenticated, item.id, item.likedByMe, likeBusy, onLikeUpdated]);

  const likeA11y = item.likedByMe
    ? `Unlike, ${item.likeCount} likes`
    : `Like, ${item.likeCount} likes`;

  return (
    <View style={styles.card}>
      <View style={styles.cardMainColumn}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Open published outfit ${item.name}`}
          onPress={openOutfit}
          style={({ pressed }) => [styles.cardMainRow, pressed && styles.cardMainPressed]}
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
        {showAuthorAttribution ? (
          <View style={styles.cardAuthorRow}>
            <View style={styles.cardAuthorSpacer} />
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`Open profile for ${authorLabel}`}
              accessibilityHint="Shows this creator’s public outfits on Discover"
              onPress={openAuthor}
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
                  <View style={styles.cardAuthorAvatarPh} />
                )}
                <Text style={styles.cardAuthor} numberOfLines={1}>
                  By {authorLabel}
                </Text>
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
        style={({ pressed }) => [
          styles.cardLikeColumn,
          pressed && styles.cardLikeColumnPressed,
          likeBusy && styles.cardLikeColumnBusy,
        ]}
      >
        <Text style={[styles.heart, item.likedByMe ? styles.heartActive : styles.heartInactive]}>
          {item.likedByMe ? "♥" : "♡"}
        </Text>
        <Text style={styles.likeCount}>{item.likeCount}</Text>
      </Pressable>
    </View>
  );
}

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
    alignItems: "stretch",
  },
  cardMainPressed: {
    opacity: 0.92,
  },
  cardImage: {
    width: IMAGE_W,
    minHeight: IMAGE_W,
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
  cardAuthorRow: {
    flexDirection: "row",
    alignItems: "center",
  },
  cardAuthorSpacer: {
    width: IMAGE_W,
  },
  cardAuthorHit: {
    flex: 1,
    paddingHorizontal: theme.spacing.md,
    paddingBottom: theme.spacing.sm,
  },
  cardAuthorHitPressed: {
    opacity: 0.85,
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
  cardAuthor: {
    flex: 1,
    minWidth: 0,
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.primary,
    fontWeight: theme.typography.fontWeight.semibold,
  },
  cardMeta: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
  },
  cardLikeColumn: {
    justifyContent: "center",
    alignItems: "center",
    paddingHorizontal: theme.spacing.sm,
    minWidth: 52,
    borderLeftWidth: StyleSheet.hairlineWidth,
    borderLeftColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
  },
  cardLikeColumnPressed: {
    opacity: 0.85,
  },
  cardLikeColumnBusy: {
    opacity: 0.6,
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
    marginTop: 2,
  },
});
