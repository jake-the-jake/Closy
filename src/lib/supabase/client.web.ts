/**
 * Web Supabase client: no AsyncStorage (avoids `window` during SSR).
 * - Server / SSR (`window` undefined): in-memory storage (session not persisted on server).
 * - Browser: `localStorage`.
 */
import "react-native-url-polyfill/auto";

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

import { isSupabaseConfigured, supabaseAnonKey, supabaseUrl } from "./env";

type AuthStorage = {
  getItem: (key: string) => Promise<string | null>;
  setItem: (key: string, value: string) => Promise<void>;
  removeItem: (key: string) => Promise<void>;
};

function createWebServerAuthStorage(): AuthStorage {
  const memory = new Map<string, string>();
  return {
    getItem: async (key) => memory.get(key) ?? null,
    setItem: async (key, value) => {
      memory.set(key, value);
    },
    removeItem: async (key) => {
      memory.delete(key);
    },
  };
}

function createBrowserLocalStorageAdapter(): AuthStorage {
  return {
    getItem: async (key) => {
      try {
        return window.localStorage.getItem(key);
      } catch {
        return null;
      }
    },
    setItem: async (key, value) => {
      try {
        window.localStorage.setItem(key, value);
      } catch {
        /* quota / private mode */
      }
    },
    removeItem: async (key) => {
      try {
        window.localStorage.removeItem(key);
      } catch {
        /* ignore */
      }
    },
  };
}

function createAuthStorage(): AuthStorage {
  if (typeof window === "undefined") {
    return createWebServerAuthStorage();
  }
  return createBrowserLocalStorageAdapter();
}

export const supabase: SupabaseClient | null = isSupabaseConfigured
  ? createClient(supabaseUrl!, supabaseAnonKey!, {
      auth: {
        storage: createAuthStorage(),
        persistSession: true,
        autoRefreshToken: typeof window !== "undefined",
        detectSessionInUrl: false,
      },
    })
  : null;

export function requireSupabase(): SupabaseClient {
  if (!supabase) {
    throw new Error(
      "Supabase is not configured. Add EXPO_PUBLIC_SUPABASE_URL and EXPO_PUBLIC_SUPABASE_ANON_KEY to .env",
    );
  }
  return supabase;
}
