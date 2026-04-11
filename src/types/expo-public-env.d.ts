/** Expo inlines `EXPO_PUBLIC_*` at bundle time from `.env` — reference for editors. */
declare namespace NodeJS {
  interface ProcessEnv {
    EXPO_PUBLIC_SUPABASE_URL?: string;
    EXPO_PUBLIC_SUPABASE_ANON_KEY?: string;
    /** Absolute filesystem path to Closy repo root (avatar export handoff). */
    EXPO_PUBLIC_CLOSY_REPO_ROOT?: string;
    /** When "1", `runAvatarExport` returns a placeholder image without the native binary. */
    EXPO_PUBLIC_AVATAR_EXPORT_MOCK?: string;
    EXPO_PUBLIC_AVATAR_EXPORT_MOCK_URI?: string;
    /** When "1", live viewport uses procedural body only (skip bundled skinned GLB). */
    EXPO_PUBLIC_AVATAR_USE_PROCEDURAL_BODY?: string;
    EXPO_PUBLIC_AVATAR_RUNTIME_BODY_GLTF_URL?: string;
    EXPO_PUBLIC_AVATAR_RUNTIME_TOP_GLTF_URL?: string;
    EXPO_PUBLIC_AVATAR_RUNTIME_BOTTOM_GLTF_URL?: string;
  }
}
