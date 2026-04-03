import type { SupabaseClient } from "@supabase/supabase-js";

import { fetchPublicProfilesByUserIds } from "@/features/profile/lib/cloud-profiles";
import { supabase } from "@/lib/supabase/client";

import type { UserActivityListItem, UserActivityRow, UserActivityType } from "../types/user-activity";
import { isUserActivityType } from "../types/user-activity";

const TABLE = "user_activity";
const FEED_LIMIT = 100;

type UserActivityDbRow = {
  id: string;
  recipient_user_id: string;
  actor_user_id: string;
  activity_type: string;
  published_outfit_id: string | null;
  comment_id: string | null;
  created_at: string;
  read_at: string | null;
};

function mapRow(row: UserActivityDbRow): UserActivityRow | null {
  if (!isUserActivityType(row.activity_type)) return null;
  const activityType: UserActivityType = row.activity_type;
  return {
    id: row.id,
    recipientUserId: row.recipient_user_id,
    actorUserId: row.actor_user_id,
    activityType,
    publishedOutfitId: row.published_outfit_id,
    commentId: row.comment_id,
    createdAt: row.created_at,
    readAt: row.read_at ?? null,
  };
}

async function fetchOutfitNamesByIds(
  client: SupabaseClient,
  outfitIds: readonly string[],
): Promise<Map<string, string>> {
  const map = new Map<string, string>();
  const unique = [...new Set(outfitIds.filter(Boolean))];
  if (unique.length === 0) return map;

  const { data, error } = await client
    .from("published_outfits")
    .select("id, name")
    .in("id", unique);

  if (error) {
    console.warn("[Closy] Activity outfit titles failed:", error.message);
    return map;
  }

  for (const row of data ?? []) {
    const r = row as { id: string; name: string };
    const name = (r.name ?? "").trim();
    if (name.length > 0) map.set(r.id, name);
  }
  return map;
}

export type FetchMyActivityFeedResult =
  | { ok: true; items: UserActivityListItem[] }
  | { ok: false; errorMessage: string };

/**
 * Loads the signed-in user's activity feed (RLS restricts to `recipient_user_id = auth.uid()`).
 */
export async function fetchMyActivityFeed(
  client: SupabaseClient,
): Promise<FetchMyActivityFeedResult> {
  const { data, error } = await client
    .from(TABLE)
    .select(
      "id, recipient_user_id, actor_user_id, activity_type, published_outfit_id, comment_id, created_at, read_at",
    )
    .order("created_at", { ascending: false })
    .limit(FEED_LIMIT);

  if (error) {
    return { ok: false, errorMessage: error.message };
  }

  const rows = (data ?? []) as UserActivityDbRow[];
  const mapped: UserActivityRow[] = [];
  for (const r of rows) {
    const m = mapRow(r);
    if (m) mapped.push(m);
  }

  const actorIds = mapped.map((m) => m.actorUserId);
  const outfitIds = mapped
    .map((m) => m.publishedOutfitId)
    .filter((id): id is string => id != null);

  const [profiles, outfitNames] = await Promise.all([
    fetchPublicProfilesByUserIds(client, actorIds),
    fetchOutfitNamesByIds(client, outfitIds),
  ]);

  const items: UserActivityListItem[] = mapped.map((m) => {
    const profile = profiles.get(m.actorUserId);
    const display = (profile?.displayName ?? "").trim();
    const outfitName =
      m.publishedOutfitId != null
        ? outfitNames.get(m.publishedOutfitId) ?? null
        : null;
    return {
      ...m,
      actorDisplayName: display.length > 0 ? display : "Someone",
      actorAvatarUrl: profile?.avatarUrl ?? null,
      publishedOutfitName: outfitName,
    };
  });

  return { ok: true, items };
}

export async function fetchMyActivityFeedWithDefaultClient(): Promise<FetchMyActivityFeedResult> {
  if (!supabase) {
    return { ok: false, errorMessage: "Supabase is not configured." };
  }
  return fetchMyActivityFeed(supabase);
}

export type CountUnreadActivityResult =
  | { ok: true; count: number }
  | { ok: false; errorMessage: string };

/** Rows with `read_at is null` for the current user (RLS). */
export async function countUnreadActivity(
  client: SupabaseClient,
): Promise<CountUnreadActivityResult> {
  const { count, error } = await client
    .from(TABLE)
    .select("*", { count: "exact", head: true })
    .is("read_at", null);

  if (error) {
    return { ok: false, errorMessage: error.message };
  }
  return { ok: true, count: count ?? 0 };
}

export async function countUnreadActivityWithDefaultClient(): Promise<CountUnreadActivityResult> {
  if (!supabase) {
    return { ok: false, errorMessage: "Supabase is not configured." };
  }
  return countUnreadActivity(supabase);
}

export type MarkAllActivityReadResult =
  | { ok: true }
  | { ok: false; errorMessage: string };

/** Sets `read_at = now()` for all unread rows for the current user. */
export async function markAllMyActivityRead(
  client: SupabaseClient,
): Promise<MarkAllActivityReadResult> {
  const nowIso = new Date().toISOString();
  const { error } = await client
    .from(TABLE)
    .update({ read_at: nowIso })
    .is("read_at", null);

  if (error) {
    return { ok: false, errorMessage: error.message };
  }
  return { ok: true };
}

export async function markAllMyActivityReadWithDefaultClient(): Promise<MarkAllActivityReadResult> {
  if (!supabase) {
    return { ok: false, errorMessage: "Supabase is not configured." };
  }
  return markAllMyActivityRead(supabase);
}
