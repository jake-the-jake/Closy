import type { SupabaseClient } from "@supabase/supabase-js";

import type { PublicUserProfile } from "@/features/profile/types/public-user-profile";
import { supabase } from "@/lib/supabase/client";

export const PROFILES_TABLE = "profiles";

const BATCH = 100;

type ProfileRow = {
  id: string;
  display_name: string | null;
  avatar_url: string | null;
};

function mapRow(row: ProfileRow): PublicUserProfile {
  const name = (row.display_name ?? "").trim();
  const avatarRaw = (row.avatar_url ?? "").trim();
  return {
    userId: row.id,
    displayName: name,
    avatarUrl: avatarRaw.length > 0 ? avatarRaw : null,
  };
}

/** Public read; safe for anon and authenticated clients. */
export async function fetchPublicProfilesByUserIds(
  client: SupabaseClient,
  userIds: readonly string[],
): Promise<Map<string, PublicUserProfile>> {
  const map = new Map<string, PublicUserProfile>();
  const unique = [...new Set(userIds.filter(Boolean))];
  if (unique.length === 0) return map;

  for (let i = 0; i < unique.length; i += BATCH) {
    const chunk = unique.slice(i, i + BATCH);
    const { data, error } = await client
      .from(PROFILES_TABLE)
      .select("id, display_name, avatar_url")
      .in("id", chunk);
    if (error) {
      console.warn("[Closy] Profile batch fetch failed:", error.message);
      continue;
    }
    const rows = (data ?? []) as ProfileRow[];
    for (const row of rows) {
      map.set(row.id, mapRow(row));
    }
  }
  return map;
}

export async function fetchPublicProfileByUserId(
  userId: string,
): Promise<PublicUserProfile | null> {
  if (!supabase || !userId) return null;
  const { data, error } = await supabase
    .from(PROFILES_TABLE)
    .select("id, display_name, avatar_url")
    .eq("id", userId)
    .maybeSingle();
  if (error) {
    console.warn("[Closy] Profile fetch failed:", error.message);
    return null;
  }
  if (!data) return null;
  return mapRow(data as ProfileRow);
}

export type ProfilePatch = {
  displayName?: string;
  /** Pass `null` to clear. Omit to keep existing when merging from DB. */
  avatarUrl?: string | null;
};

/**
 * Creates or replaces the signed-in user's profile row. When only one field is
 * sent, the other is loaded first so we do not wipe avatar/display name.
 */
export async function upsertMyProfile(
  client: SupabaseClient,
  userId: string,
  patch: ProfilePatch,
): Promise<{ error: Error | null }> {
  let displayName: string;
  let avatarUrl: string | null;

  const hasBoth =
    patch.displayName !== undefined && patch.avatarUrl !== undefined;
  if (hasBoth) {
    displayName = patch.displayName!.trim();
    const av = patch.avatarUrl;
    avatarUrl =
      av != null && String(av).trim().length > 0 ? String(av).trim() : null;
  } else {
    const { data, error } = await client
      .from(PROFILES_TABLE)
      .select("display_name, avatar_url")
      .eq("id", userId)
      .maybeSingle();
    if (error) {
      return { error: new Error(error.message) };
    }
    const row = data as Pick<ProfileRow, "display_name" | "avatar_url"> | null;
    displayName =
      patch.displayName !== undefined
        ? patch.displayName.trim()
        : (row?.display_name ?? "").trim();
    if (patch.avatarUrl !== undefined) {
      const av = patch.avatarUrl;
      avatarUrl =
        av != null && String(av).trim().length > 0 ? String(av).trim() : null;
    } else {
      const existing = (row?.avatar_url ?? "").trim();
      avatarUrl = existing.length > 0 ? existing : null;
    }
  }

  const { error: upErr } = await client.from(PROFILES_TABLE).upsert(
    {
      id: userId,
      display_name: displayName,
      avatar_url: avatarUrl,
    },
    { onConflict: "id" },
  );
  return { error: upErr ? new Error(upErr.message) : null };
}
