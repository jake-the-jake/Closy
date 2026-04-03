import type { User } from "@supabase/supabase-js";

/**
 * Stable app-level view of account data from Supabase Auth (`user_metadata`).
 * Discover-facing name/avatar are read from `public.profiles` when present.
 */
export type AccountProfile = {
  userId: string;
  email: string | null;
  /** Prefer `user_metadata.display_name`; falls back to email local-part. */
  displayName: string;
  /** Reserved for `user_metadata.avatar_url` (e.g. Storage public URL). */
  avatarUrl: string | null;
  emailConfirmed: boolean;
};

function readMetaString(
  meta: Record<string, unknown>,
  key: string,
): string | null {
  const v = meta[key];
  if (typeof v !== "string") return null;
  const t = v.trim();
  return t.length > 0 ? t : null;
}

export function buildAccountProfile(user: User): AccountProfile {
  const meta = (user.user_metadata ?? {}) as Record<string, unknown>;
  const email = user.email ?? null;
  const displayFromMeta = readMetaString(meta, "display_name");
  const fallback =
    email != null && email.includes("@")
      ? (email.split("@")[0]?.trim() || "You")
      : "You";

  return {
    userId: user.id,
    email,
    displayName: displayFromMeta ?? fallback,
    avatarUrl: readMetaString(meta, "avatar_url"),
    emailConfirmed: user.email_confirmed_at != null,
  };
}

export function displayInitials(displayName: string): string {
  const name = displayName.trim();
  if (!name) return "?";
  const parts = name.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    const a = parts[0]!.charAt(0);
    const b = parts[1]!.charAt(0);
    return (a + b).toUpperCase();
  }
  if (name.length >= 2) return name.slice(0, 2).toUpperCase();
  return name.charAt(0).toUpperCase();
}
