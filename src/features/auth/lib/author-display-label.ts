import type { User } from "@supabase/supabase-js";

const MAX_LEN = 80;

/**
 * Label stored on published posts at insert time (`author_display_name`).
 * Uses `user_metadata.display_name`, else email local-part, else a short id fallback.
 */
export function resolveAuthorDisplayLabelForPublish(user: User): string {
  const meta = user.user_metadata as Record<string, unknown> | undefined;
  const rawName =
    typeof meta?.display_name === "string" ? meta.display_name.trim() : "";
  if (rawName.length > 0) {
    return rawName.length > MAX_LEN ? rawName.slice(0, MAX_LEN) : rawName;
  }

  const email = user.email?.trim();
  if (email && email.includes("@")) {
    const local = email.split("@")[0]?.trim() ?? "";
    if (local.length > 0) {
      return local.length > MAX_LEN ? local.slice(0, MAX_LEN) : local;
    }
  }

  const id = user.id.replace(/-/g, "");
  const short = id.slice(0, 8);
  return `Member ${short}`;
}
