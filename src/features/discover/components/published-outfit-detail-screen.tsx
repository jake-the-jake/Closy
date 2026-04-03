import { Image } from "expo-image";
import { type Href, useRouter } from "expo-router";
import { useCallback, useEffect, useLayoutEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useNavigation } from "@react-navigation/native";

import { formatRelativeTime } from "@/features/activity/lib/format-relative-time";
import { AppButton } from "@/components/ui/app-button";
import { EmptyState } from "@/components/ui/empty-state";
import { ScreenContainer } from "@/components/ui/screen-container";
import { useAuth } from "@/features/auth";
import { discoverService } from "@/features/discover/discover-service";
import { PUBLISHED_OUTFIT_COMMENT_BODY_MAX_LEN } from "@/features/discover/lib/cloud-published-outfit-comments";
import { publishedOutfitAuthorLabel } from "@/features/discover/lib/published-outfit-attribution";
import type { PublishedOutfitComment } from "@/features/discover/types/published-outfit-comment";
import type { PublishedOutfit } from "@/features/discover/types/published-outfit";
import { media } from "@/lib/constants";
import { theme } from "@/theme";

export type PublishedOutfitDetailScreenProps = {
  publishedId: string | null;
};

function formatCommentTime(ts: number): string {
  try {
    return formatRelativeTime(new Date(ts).toISOString());
  } catch {
    return "";
  }
}

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
  const [comments, setComments] = useState<PublishedOutfitComment[]>([]);
  const [commentsLoading, setCommentsLoading] = useState(false);
  const [commentsError, setCommentsError] = useState<string | null>(null);
  const [draftComment, setDraftComment] = useState("");
  const [postCommentBusy, setPostCommentBusy] = useState(false);
  const [postCommentError, setPostCommentError] = useState<string | null>(null);
  const [deletingCommentId, setDeletingCommentId] = useState<string | null>(null);

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

  const refreshComments = useCallback(
    async (opts?: { silent?: boolean }) => {
      if (!publishedId) {
        setComments([]);
        setCommentsError(null);
        return;
      }
      if (!opts?.silent) {
        setCommentsLoading(true);
        setCommentsError(null);
      }
      try {
        const r = await discoverService.fetchCommentsForPublishedOutfit(publishedId);
        if (r.ok) {
          setComments(r.comments);
          setCommentsError(null);
        } else {
          setCommentsError(r.errorMessage);
          if (!opts?.silent) {
            setComments([]);
          }
        }
      } finally {
        if (!opts?.silent) {
          setCommentsLoading(false);
        }
      }
    },
    [publishedId],
  );

  useEffect(() => {
    if (row === undefined) {
      return;
    }
    if (row === null) {
      setComments([]);
      setCommentsError(null);
      return;
    }
    void refreshComments();
  }, [row, refreshComments]);

  const submitComment = useCallback(() => {
    if (!publishedId) return;
    if (user?.id == null) {
      Alert.alert("Sign in", "Sign in to comment on this post.");
      return;
    }
    if (postCommentBusy) return;
    if (draftComment.trim().length === 0) return;
    setPostCommentError(null);
    setPostCommentBusy(true);
    void (async () => {
      const r = await discoverService.postCommentOnPublishedOutfit(
        publishedId,
        draftComment,
      );
      setPostCommentBusy(false);
      if (r.ok) {
        setDraftComment("");
        setPostCommentError(null);
        await refreshComments({ silent: true });
      } else {
        setPostCommentError(r.errorMessage);
      }
    })();
  }, [publishedId, user?.id, draftComment, postCommentBusy, refreshComments]);

  const requestDeleteComment = useCallback(
    (c: PublishedOutfitComment) => {
      Alert.alert("Delete comment?", "This will be removed for everyone.", [
        { text: "Cancel", style: "cancel" },
        {
          text: "Delete",
          style: "destructive",
          onPress: () => {
            setDeletingCommentId(c.id);
            void (async () => {
              const r = await discoverService.deleteMyCommentOnPublishedOutfit(c.id);
              setDeletingCommentId(null);
              if (r.ok) {
                setCommentsError(null);
                await refreshComments({ silent: true });
              } else {
                Alert.alert("Couldn’t delete comment", r.errorMessage);
              }
            })();
          },
        },
      ]);
    },
    [refreshComments],
  );

  const openCommentAuthor = useCallback(
    (c: PublishedOutfitComment) => {
      router.push({
        pathname: "/author/[userId]",
        params: {
          userId: c.authorUserId,
          displayName: c.authorDisplayName,
        },
      } as unknown as Href);
    },
    [router],
  );

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

      <View style={styles.commentsSection}>
        <Text style={styles.sectionLabel}>Comments</Text>
        <Text style={styles.commentsOrderHint}>
          Oldest at the top · Newest just above the box below
        </Text>
        {commentsLoading && comments.length === 0 && !commentsError ? (
          <View style={styles.commentsLoadingRow}>
            <ActivityIndicator color={theme.colors.primary} />
            <Text style={styles.commentsLoadingCaption}>Loading comments…</Text>
          </View>
        ) : null}
        {commentsError ? (
          <View style={styles.commentsErrorBox}>
            <Text style={styles.commentsErrorText}>{commentsError}</Text>
            <AppButton
              label="Try again"
              variant="secondary"
              fullWidth
              onPress={() => void refreshComments()}
              accessibilityHint="Reloads comments for this post"
            />
          </View>
        ) : null}
        <View style={styles.commentsList}>
          {!commentsLoading &&
          comments.length === 0 &&
          !commentsError ? (
            <Text style={styles.commentsEmpty}>
              No comments yet. Start the thread—your note is public on this post.
            </Text>
          ) : null}
          {comments.map((c) => {
            const av = c.authorAvatarUrl?.trim() ?? "";
            const canDelete = user?.id != null && user.id === c.authorUserId;
            const deleteBusy = deletingCommentId === c.id;
            const timeLabel = formatCommentTime(c.createdAt);
            return (
              <View key={c.id} style={styles.commentCard}>
                <View style={styles.commentRow}>
                  {av.length > 0 ? (
                    <Image
                      source={{ uri: av }}
                      style={styles.commentAvatar}
                      contentFit="cover"
                      transition={media.imageTransitionMs.card}
                    />
                  ) : (
                    <View style={styles.commentAvatarPh} />
                  )}
                  <View style={styles.commentBody}>
                    <View style={styles.commentHeader}>
                      <View style={styles.commentAuthorBlock}>
                        <Text style={styles.creatorMicro}>From</Text>
                        <Pressable
                          onPress={() => openCommentAuthor(c)}
                          hitSlop={6}
                          accessibilityRole="button"
                          accessibilityLabel={`Open profile for ${c.authorDisplayName}`}
                          accessibilityHint="Opens this person’s Discover profile"
                          style={({ pressed }) => [
                            styles.commentAuthorHit,
                            pressed && styles.commentAuthorPressed,
                          ]}
                        >
                          <Text style={styles.commentAuthor} numberOfLines={1}>
                            {c.authorDisplayName}
                          </Text>
                        </Pressable>
                      </View>
                      <View style={styles.commentMetaRight}>
                        {timeLabel.length > 0 ? (
                          <Text style={styles.commentTime}>{timeLabel}</Text>
                        ) : null}
                        {canDelete ? (
                          <Pressable
                            onPress={() => requestDeleteComment(c)}
                            disabled={deleteBusy}
                            hitSlop={8}
                            accessibilityRole="button"
                            accessibilityLabel="Delete your comment"
                            accessibilityHint="Removes this comment for everyone"
                          >
                            <Text style={styles.commentDelete}>
                              {deleteBusy ? "…" : "Delete"}
                            </Text>
                          </Pressable>
                        ) : null}
                      </View>
                    </View>
                    <Text style={styles.commentText}>{c.body}</Text>
                  </View>
                </View>
              </View>
            );
          })}
        </View>
      </View>

      {user?.id != null ? (
        <View style={styles.composeBlock}>
          <Text style={styles.composeLabel}>Add a comment</Text>
          <TextInput
            value={draftComment}
            onChangeText={(t) => {
              setDraftComment(t);
              if (postCommentError) setPostCommentError(null);
            }}
            placeholder="Say something nice or ask a question…"
            placeholderTextColor={theme.colors.textMuted}
            style={styles.commentInput}
            multiline
            maxLength={PUBLISHED_OUTFIT_COMMENT_BODY_MAX_LEN}
            editable={!postCommentBusy}
            accessibilityLabel="Write a comment"
          />
          <View style={styles.composeFooter}>
            <Text style={styles.charCount}>
              {draftComment.length}/{PUBLISHED_OUTFIT_COMMENT_BODY_MAX_LEN}
            </Text>
          </View>
          {postCommentError ? (
            <Text style={styles.postCommentError}>{postCommentError}</Text>
          ) : null}
          <AppButton
            label={postCommentBusy ? "Posting…" : "Post comment"}
            variant="secondary"
            fullWidth
            onPress={submitComment}
            loading={postCommentBusy}
            disabled={
              postCommentBusy || draftComment.trim().length === 0
            }
            accessibilityHint="Publishes your comment on this post"
          />
        </View>
      ) : (
        <Text style={styles.signInHint}>
          Sign in to leave a comment on this post.
        </Text>
      )}

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
  commentsSection: {
    gap: theme.spacing.sm,
  },
  commentsOrderHint: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    lineHeight: 18,
  },
  commentsLoadingRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
  },
  commentsLoadingCaption: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
  },
  commentsErrorBox: {
    gap: theme.spacing.sm,
    padding: theme.spacing.md,
    borderRadius: theme.radii.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
  },
  commentsErrorText: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.danger,
    lineHeight: 20,
  },
  commentsList: {
    gap: theme.spacing.sm,
  },
  commentsEmpty: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
    lineHeight: 20,
    paddingVertical: theme.spacing.xs,
  },
  commentCard: {
    borderRadius: theme.radii.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
    padding: theme.spacing.md,
  },
  commentRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: theme.spacing.md,
  },
  commentAvatar: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: theme.colors.border,
  },
  commentAvatarPh: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: theme.colors.border,
  },
  commentBody: {
    flex: 1,
    minWidth: 0,
    gap: theme.spacing.sm,
  },
  commentHeader: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: theme.spacing.md,
  },
  commentAuthorBlock: {
    flex: 1,
    minWidth: 0,
    gap: 2,
  },
  creatorMicro: {
    fontSize: 10,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  commentAuthorHit: {
    alignSelf: "flex-start",
  },
  commentAuthor: {
    fontSize: theme.typography.fontSize.sm,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.primary,
  },
  commentAuthorPressed: {
    opacity: 0.88,
  },
  commentMetaRight: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.sm,
    flexShrink: 0,
  },
  commentTime: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
  },
  commentDelete: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.danger,
    fontWeight: theme.typography.fontWeight.semibold,
  },
  commentText: {
    fontSize: theme.typography.fontSize.md,
    color: theme.colors.text,
    lineHeight: 22,
  },
  composeBlock: {
    gap: theme.spacing.sm,
    paddingTop: theme.spacing.xs,
  },
  composeLabel: {
    fontSize: theme.typography.fontSize.sm,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  composeFooter: {
    flexDirection: "row",
    justifyContent: "flex-end",
  },
  charCount: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
  },
  postCommentError: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.danger,
    lineHeight: 18,
  },
  commentInput: {
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radii.sm,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    fontSize: theme.typography.fontSize.md,
    color: theme.colors.text,
    backgroundColor: theme.colors.surface,
    minHeight: 72,
    textAlignVertical: "top",
  },
  signInHint: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
  },
});
