import type { ReactNode } from "react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { Session, User } from "@supabase/supabase-js";

import { hydrateOutfitsFromCloud } from "@/features/outfits/lib/cloud-outfits";
import { useOutfitsStore } from "@/features/outfits/state/outfits-store";
import { hydrateWardrobeFromCloud } from "@/features/wardrobe/lib/cloud-wardrobe";
import { useWardrobeStore } from "@/features/wardrobe/state/wardrobe-store";
import { supabase } from "@/lib/supabase/client";
import { useRemoteSyncStore } from "@/lib/sync";

export type AuthContextValue = {
  session: Session | null;
  user: User | null;
  /** True when `user` is non-null (Supabase session present). */
  isAuthenticated: boolean;
  initializing: boolean;
  supabaseConfigured: boolean;
  signInWithPassword: (
    email: string,
    password: string,
  ) => Promise<{ error: Error | null }>;
  signUpWithPassword: (
    email: string,
    password: string,
  ) => Promise<{ error: Error | null }>;
  signOut: () => Promise<void>;
  /** Persists `display_name` in Supabase Auth `user_metadata`. */
  updateProfileDisplayName: (
    displayName: string,
  ) => Promise<{ error: Error | null }>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function scheduleSignedInRemoteHydration(userId: string): (() => void) | undefined {
  const runBoth = () => {
    if (
      !useWardrobeStore.persist.hasHydrated() ||
      !useOutfitsStore.persist.hasHydrated()
    ) {
      return;
    }
    void hydrateWardrobeFromCloud(userId);
    void hydrateOutfitsFromCloud(userId);
  };

  runBoth();

  const unsubs: (() => void)[] = [];
  if (!useWardrobeStore.persist.hasHydrated()) {
    unsubs.push(useWardrobeStore.persist.onFinishHydration(runBoth));
  }
  if (!useOutfitsStore.persist.hasHydrated()) {
    unsubs.push(useOutfitsStore.persist.onFinishHydration(runBoth));
  }
  if (unsubs.length === 0) return undefined;
  return () => unsubs.forEach((u) => u());
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [initializing, setInitializing] = useState(true);

  const supabaseConfigured = supabase != null;

  useEffect(() => {
    if (!supabase) {
      setInitializing(false);
      return;
    }

    let cancelled = false;

    void supabase.auth.getSession().then(({ data: { session: next } }) => {
      if (!cancelled) {
        setSession(next);
        setInitializing(false);
      }
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
    });

    return () => {
      cancelled = true;
      subscription.unsubscribe();
    };
  }, []);

  useEffect(() => {
    const userId = session?.user?.id;
    if (!supabase) {
      return;
    }
    if (!userId) {
      useRemoteSyncStore.getState().reset();
      return;
    }
    useRemoteSyncStore.getState().reset();
    return scheduleSignedInRemoteHydration(userId);
  }, [session?.user?.id]);

  const signInWithPassword = useCallback(
    async (email: string, password: string) => {
      if (!supabase) {
        return { error: new Error("Supabase is not configured.") };
      }
      const { error } = await supabase.auth.signInWithPassword({
        email: email.trim(),
        password,
      });
      return { error: error ? new Error(error.message) : null };
    },
    [],
  );

  const signUpWithPassword = useCallback(
    async (email: string, password: string) => {
      if (!supabase) {
        return { error: new Error("Supabase is not configured.") };
      }
      const { error } = await supabase.auth.signUp({
        email: email.trim(),
        password,
      });
      return { error: error ? new Error(error.message) : null };
    },
    [],
  );

  const signOut = useCallback(async () => {
    if (!supabase) return;
    await supabase.auth.signOut();
  }, []);

  const updateProfileDisplayName = useCallback(async (displayName: string) => {
    if (!supabase) {
      return { error: new Error("Supabase is not configured.") };
    }
    const trimmed = displayName.trim();
    const { data: fresh, error: getErr } = await supabase.auth.getUser();
    if (getErr) {
      return { error: new Error(getErr.message) };
    }
    const meta = (fresh.user?.user_metadata ?? {}) as Record<string, unknown>;
    const { error } = await supabase.auth.updateUser({
      data: {
        ...meta,
        display_name: trimmed,
      },
    });
    return { error: error ? new Error(error.message) : null };
  }, []);

  const value = useMemo(
    (): AuthContextValue => ({
      session,
      user: session?.user ?? null,
      isAuthenticated: session?.user != null,
      initializing,
      supabaseConfigured,
      signInWithPassword,
      signUpWithPassword,
      signOut,
      updateProfileDisplayName,
    }),
    [
      initializing,
      session,
      signInWithPassword,
      signOut,
      signUpWithPassword,
      supabaseConfigured,
      updateProfileDisplayName,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider.");
  }
  return ctx;
}
