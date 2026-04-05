import Constants from "expo-constants";

function normalizeRepoRoot(raw: string): string {
  const trimmed = raw.trim();
  if (trimmed.length === 0) return "";
  const unified = trimmed.replace(/\\/g, "/");
  return unified.replace(/\/+$/, "");
}

/**
 * Absolute filesystem path to the Closy repo root (normalized slashes, no trailing slash).
 * Configure via `EXPO_PUBLIC_CLOSY_REPO_ROOT` or `expo.extra.closyRepoRoot` in app config.
 */
export function getClosyRepoRoot(): string | null {
  const fromEnv = process.env.EXPO_PUBLIC_CLOSY_REPO_ROOT ?? "";
  const fromExtra =
    (Constants.expoConfig?.extra as { closyRepoRoot?: string } | undefined)
      ?.closyRepoRoot ?? "";
  const merged = fromEnv.trim().length > 0 ? fromEnv : fromExtra;
  const normalized = normalizeRepoRoot(merged);
  if (normalized.length === 0) return null;
  return normalized;
}
