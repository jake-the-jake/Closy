/** Expo inlines `EXPO_PUBLIC_*` at bundle time from `.env` — reference for editors. */
declare namespace NodeJS {
  interface ProcessEnv {
    EXPO_PUBLIC_SUPABASE_URL?: string;
    EXPO_PUBLIC_SUPABASE_ANON_KEY?: string;
  }
}
