import type { ReactNode } from "react";
import { StyleSheet, Text, View } from "react-native";

import { AppButton } from "@/components/ui/app-button";
import { theme } from "@/theme";

export type AuthorProfileHeaderProps = {
  profileTitle: string;
  headerAvatar: ReactNode;
  postsSummary: string;
  followerCount: number;
  followingCount: number;
  /** Hide follow when viewing your own user id. */
  showFollowChrome: boolean;
  isAuthenticated: boolean;
  isFollowing: boolean;
  followBusy: boolean;
  onFollowPress: () => void;
};

export function AuthorProfileHeader({
  profileTitle,
  headerAvatar,
  postsSummary,
  followerCount,
  followingCount,
  showFollowChrome,
  isAuthenticated,
  isFollowing,
  followBusy,
  onFollowPress,
}: AuthorProfileHeaderProps) {
  const countsLine = `${followerCount} follower${
    followerCount === 1 ? "" : "s"
  } · ${followingCount} following`;

  return (
    <View style={styles.header}>
      <Text style={styles.headerKicker}>Discover creator</Text>
      <View style={styles.headerHero}>
        {headerAvatar}
        <View style={styles.headerNameBlock}>
          <Text style={styles.headerName}>{profileTitle}</Text>
          <Text style={styles.countsMuted}>{countsLine}</Text>
        </View>
      </View>
      {showFollowChrome ? (
        <AppButton
          label={isFollowing ? "Following" : "Follow"}
          variant={isFollowing ? "secondary" : "secondary"}
          fullWidth
          loading={followBusy}
          disabled={followBusy}
          onPress={onFollowPress}
          accessibilityHint={
            isAuthenticated
              ? isFollowing
                ? "Unfollow this creator"
                : "Follow this creator"
              : "Sign in to follow this creator"
          }
          accessibilityLabel={
            isFollowing ? "Following, tap to unfollow" : "Follow creator"
          }
        />
      ) : null}
      <Text style={styles.headerSummary}>{postsSummary}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    marginBottom: theme.spacing.lg,
    gap: theme.spacing.sm,
  },
  headerHero: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.md,
  },
  headerNameBlock: {
    flex: 1,
    minWidth: 0,
    gap: 4,
  },
  headerKicker: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  headerName: {
    fontSize: theme.typography.fontSize.xxl,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
    lineHeight: theme.typography.lineHeight.title,
  },
  countsMuted: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
  },
  headerSummary: {
    fontSize: theme.typography.fontSize.md,
    color: theme.colors.textMuted,
  },
});
