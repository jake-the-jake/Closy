import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { AppState, type AppStateStatus } from "react-native";

import { countUnreadActivityWithDefaultClient } from "@/features/activity/lib/cloud-user-activity";
import { useAuth } from "@/features/auth";
import { supabase } from "@/lib/supabase/client";

export type ActivityUnreadContextValue = {
  unreadCount: number;
  refreshUnreadCount: () => Promise<void>;
};

const ActivityUnreadContext = createContext<ActivityUnreadContextValue | null>(
  null,
);

export function ActivityUnreadProvider({ children }: { children: ReactNode }) {
  const { supabaseConfigured, isAuthenticated } = useAuth();
  const [unreadCount, setUnreadCount] = useState(0);

  const refreshUnreadCount = useCallback(async () => {
    if (!supabaseConfigured || !isAuthenticated || !supabase) {
      setUnreadCount(0);
      return;
    }
    const r = await countUnreadActivityWithDefaultClient();
    if (!r.ok) {
      console.warn("[Closy] Unread activity count failed:", r.errorMessage);
      return;
    }
    setUnreadCount(r.count);
  }, [supabaseConfigured, isAuthenticated]);

  useEffect(() => {
    void refreshUnreadCount();
  }, [refreshUnreadCount]);

  useEffect(() => {
    const onChange = (state: AppStateStatus) => {
      if (state === "active") void refreshUnreadCount();
    };
    const sub = AppState.addEventListener("change", onChange);
    return () => sub.remove();
  }, [refreshUnreadCount]);

  const value = useMemo(
    () => ({ unreadCount, refreshUnreadCount }),
    [unreadCount, refreshUnreadCount],
  );

  return (
    <ActivityUnreadContext.Provider value={value}>
      {children}
    </ActivityUnreadContext.Provider>
  );
}

export function useActivityUnread(): ActivityUnreadContextValue {
  const ctx = useContext(ActivityUnreadContext);
  if (!ctx) {
    throw new Error("useActivityUnread must be used within ActivityUnreadProvider");
  }
  return ctx;
}
