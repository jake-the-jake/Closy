import { useFocusEffect } from "@react-navigation/native";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { useCallback, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { EmptyState } from "@/components/ui/empty-state";
import { ScreenContainer } from "@/components/ui/screen-container";
import { useActivityUnread } from "@/features/activity/context/activity-unread-context";
import {
  fetchMyActivityFeedWithDefaultClient,
  markAllMyActivityReadWithDefaultClient,
} from "@/features/activity/lib/cloud-user-activity";
import { formatRelativeTime } from "@/features/activity/lib/format-relative-time";
import type {
  UserActivityListItem,
  UserActivityType,
} from "@/features/activity/types/user-activity";
import { useAuth } from "@/features/auth";
import { displayInitials } from "@/features/profile";
import { media } from "@/lib/constants";
import { theme } from "@/theme";

const AVATAR = 44;

function actionSummary(
  item: UserActivityListItem,
): { headline: string; detail: string | null } {
  const who = item.actorDisplayName;
  const outfit =
    item.publishedOutfitName != null && item.publishedOutfitName.trim().length > 0
      ? item.publishedOutfitName.trim()
      : null;

  const type: UserActivityType = item.activityType;
  switch (type) {
    case "follow":
      return {
        headline: `${who} started following you`,
        detail: null,
      };
    case "like":
      return {
        headline: `${who} liked your outfit`,
        detail: outfit,
      };
    case "comment":
      return {
        headline: `${who} commented on your outfit`,
        detail: outfit,
      };
  }
}

export function ActivityFeedScreen() {
  const router = useRouter();
  const { refreshUnreadCount } = useActivityUnread();
  const { user, supabaseConfigured, isAuthenticated } = useAuth();
  const lastActivityUserRef = useRef<string | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [items, setItems] = useState<UserActivityListItem[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const load = useCallback(
    async (mode: "initial" | "refresh" = "initial") => {
      if (!supabaseConfigured || !isAuthenticated) {
        setLoading(false);
        setRefreshing(false);
        setItems([]);
        setErrorMessage(null);
        void refreshUnreadCount();
        return;
      }
      if (mode === "refresh") setRefreshing(true);
      else setLoading(true);
      setErrorMessage(null);
      const result = await fetchMyActivityFeedWithDefaultClient();
      if (!result.ok) {
        setErrorMessage(result.errorMessage);
        setItems([]);
      } else {
        setItems(result.items);
        const nowIso = new Date().toISOString();
        const mark = await markAllMyActivityReadWithDefaultClient();
        if (mark.ok) {
          setItems((prev) =>
            prev.map((i) =>
              i.readAt == null ? { ...i, readAt: nowIso } : i,
            ),
          );
        }
      }
      setLoading(false);
      setRefreshing(false);
      void refreshUnreadCount();
    },
    [supabaseConfigured, isAuthenticated, refreshUnreadCount],
  );

  useFocusEffect(
    useCallback(() => {
      const uid = user?.id;
      if (!uid) {
        lastActivityUserRef.current = undefined;
        void load("initial");
        return;
      }
      const switched = uid !== lastActivityUserRef.current;
      lastActivityUserRef.current = uid;
      void load(switched ? "initial" : "refresh");
    }, [load, user?.id]),
  );

  const onPressRow = useCallback(
    (item: UserActivityListItem) => {
      if (item.activityType === "follow") {
        router.push(`/author/${item.actorUserId}` as `/author/${string}`);
        return;
      }
      if (item.publishedOutfitId != null) {
        router.push(`/published-outfit/${item.publishedOutfitId}` as `/published-outfit/${string}`);
      }
    },
    [router],
  );

  if (!supabaseConfigured) {
    return (
      <ScreenContainer scroll={false} style={styles.body}>
        <EmptyState
          title="Activity unavailable"
          description="Configure Supabase in your environment to sync social activity."
        />
      </ScreenContainer>
    );
  }

  if (!isAuthenticated) {
    return (
      <ScreenContainer scroll={false} style={styles.body}>
        <EmptyState title="Sign in required" description="Activity appears after you sign in." />
      </ScreenContainer>
    );
  }

  if (loading) {
    return (
      <ScreenContainer scroll={false} style={styles.centered}>
        <ActivityIndicator size="large" color={theme.colors.primary} />
        <Text style={styles.muted}>Loading activity…</Text>
      </ScreenContainer>
    );
  }

  if (errorMessage) {
    return (
      <ScreenContainer scroll={false} style={styles.body}>
        <EmptyState
          title="Couldn’t load activity"
          description={errorMessage}
          actionLabel="Try again"
          onActionPress={() => void load("initial")}
        />
      </ScreenContainer>
    );
  }

  if (items.length === 0) {
    return (
      <ScreenContainer scroll={false} style={styles.body}>
        <EmptyState
          title="No activity yet"
          description="When people follow you or interact with your published outfits, it shows up here."
        />
      </ScreenContainer>
    );
  }

  return (
    <ScreenContainer scroll={false} style={styles.listWrap}>
      <FlatList
        data={items}
        keyExtractor={(it) => it.id}
        contentContainerStyle={styles.listContent}
        refreshing={refreshing}
        onRefresh={() => void load("refresh")}
        renderItem={({ item }) => {
          const { headline, detail } = actionSummary(item);
          const when = formatRelativeTime(item.createdAt);
          const avatarUrl = item.actorAvatarUrl?.trim() ?? "";
          const hasAvatar = avatarUrl.length > 0;
          const initials = displayInitials(item.actorDisplayName);

          return (
            <Pressable
              onPress={() => onPressRow(item)}
              style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
              accessibilityRole="button"
              accessibilityLabel={[headline, detail, when].filter(Boolean).join(". ")}
            >
              {hasAvatar ? (
                <Image
                  source={{ uri: avatarUrl }}
                  style={styles.avatar}
                  contentFit="cover"
                  transition={media.imageTransitionMs.card}
                />
              ) : (
                <View style={styles.avatarFallback}>
                  <Text style={styles.initials}>{initials}</Text>
                </View>
              )}
              <View style={styles.rowText}>
                <Text style={styles.headline}>{headline}</Text>
                {detail ? <Text style={styles.detail} numberOfLines={2}>{detail}</Text> : null}
                <Text style={styles.time}>{when}</Text>
              </View>
            </Pressable>
          );
        }}
      />
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  body: {
    flex: 1,
  },
  listWrap: {
    flex: 1,
  },
  listContent: {
    paddingBottom: theme.spacing.xl,
    gap: theme.spacing.xs,
  },
  centered: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    gap: theme.spacing.md,
    paddingHorizontal: theme.spacing.lg,
  },
  muted: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
  },
  row: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: theme.spacing.md,
    paddingVertical: theme.spacing.md,
    paddingHorizontal: theme.spacing.sm,
    borderRadius: theme.radii.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
  },
  rowPressed: {
    opacity: 0.85,
  },
  avatar: {
    width: AVATAR,
    height: AVATAR,
    borderRadius: AVATAR / 2,
    backgroundColor: theme.colors.border,
  },
  avatarFallback: {
    width: AVATAR,
    height: AVATAR,
    borderRadius: AVATAR / 2,
    backgroundColor: theme.colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  initials: {
    fontSize: theme.typography.fontSize.sm,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.surface,
  },
  rowText: {
    flex: 1,
    minWidth: 0,
    gap: 4,
  },
  headline: {
    fontSize: theme.typography.fontSize.md,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  detail: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
  },
  time: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
  },
});
