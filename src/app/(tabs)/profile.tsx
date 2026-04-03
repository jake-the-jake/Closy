import { useFocusEffect, useNavigation } from "@react-navigation/native";
import { useCallback, useLayoutEffect } from "react";

import { useActivityUnread } from "@/features/activity/context/activity-unread-context";
import { ProfileAccountView } from "@/features/profile";

function formatTabBadge(count: number): string {
  if (count > 99) return "99+";
  return String(count);
}

export default function ProfileTab() {
  const navigation = useNavigation();
  const { unreadCount, refreshUnreadCount } = useActivityUnread();

  useLayoutEffect(() => {
    navigation.setOptions({
      tabBarBadge: unreadCount > 0 ? formatTabBadge(unreadCount) : undefined,
    });
  }, [navigation, unreadCount]);

  useFocusEffect(
    useCallback(() => {
      void refreshUnreadCount();
    }, [refreshUnreadCount]),
  );

  return <ProfileAccountView />;
}
