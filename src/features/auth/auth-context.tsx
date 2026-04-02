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

import { hydrateWardrobeFromCloud } from "@/features/wardrobe/lib/cloud-wardrobe";
import { useWardrobeStore } from "@/features/wardrobe/state/wardrobe-store";
import { supabase } from "@/lib/supabase/client";

export type AuthContextValue = {
  session: Session | null;
  user: User | null;
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
};

const AuthContext = createContext<AuthContextValue | null>(null);

function scheduleWardrobeHydration(userId: string): (() => void) | undefined {
  const run = () => void hydrateWardrobeFromCloud(userId);
  if (useWardrobeStore.persist.hasHydrated()) {
    run();
    return undefined;
  }
  return useWardrobeStore.persist.onFinishHydration(() => {
    run();
  });
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
    if (!userId || !supabase) return;
    return scheduleWardrobeHydration(userId);
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

  const value = useMemo(
    (): AuthContextValue => ({
      session,
      user: session?.user ?? null,
      initializing,
      supabaseConfigured,
      signInWithPassword,
      signUpWithPassword,
      signOut,
    }),
    [
      initializing,
      session,
      signInWithPassword,
      signOut,
      signUpWithPassword,
      supabaseConfigured,
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
