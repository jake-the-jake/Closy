/**
 * Supabase `user_follows`: follower_id → followed_id (RLS: read all, mutate own follower_id only).
 */
import type { SupabaseClient } from "@supabase/supabase-js";

import { supabase } from "@/lib/supabase/client";

export const USER_FOLLOWS_TABLE = "user_follows";

export type AuthorFollowSnapshot = {
  followerCount: number;
  followingCount: number;
  isFollowing: boolean;
};

export type UserFollowStats = {
  followerCount: number;
  followingCount: number;
};

async function countFollowersForUser(
  client: SupabaseClient,
  userId: string,
): Promise<number> {
  const { count, error } = await client
    .from(USER_FOLLOWS_TABLE)
    .select("*", { count: "exact", head: true })
    .eq("followed_id", userId);
  if (error) {
    console.warn("[Closy] Follower count failed:", error.message);
    return 0;
  }
  return count ?? 0;
}

async function countFollowingForUser(
  client: SupabaseClient,
  userId: string,
): Promise<number> {
  const { count, error } = await client
    .from(USER_FOLLOWS_TABLE)
    .select("*", { count: "exact", head: true })
    .eq("follower_id", userId);
  if (error) {
    console.warn("[Closy] Following count failed:", error.message);
    return 0;
  }
  return count ?? 0;
}

async function viewerFollowsAuthor(
  client: SupabaseClient,
  viewerUserId: string,
  authorUserId: string,
): Promise<boolean> {
  const { data, error } = await client
    .from(USER_FOLLOWS_TABLE)
    .select("follower_id")
    .eq("follower_id", viewerUserId)
    .eq("followed_id", authorUserId)
    .maybeSingle();
  if (error) {
    console.warn("[Closy] Follow state lookup failed:", error.message);
    return false;
  }
  return data != null;
}

/** Followers + how many accounts `userId` follows (for profile stats). */
export async function fetchFollowStatsForUser(
  userId: string,
): Promise<UserFollowStats | null> {
  if (!supabase) return null;
  const [followerCount, followingCount] = await Promise.all([
    countFollowersForUser(supabase, userId),
    countFollowingForUser(supabase, userId),
  ]);
  return { followerCount, followingCount };
}

/** Snapshot for an author profile card (includes whether the viewer follows them). */
export async function fetchAuthorFollowSnapshot(
  authorUserId: string,
  viewerUserId: string | null,
): Promise<AuthorFollowSnapshot | null> {
  if (!supabase) return null;
  const [followerCount, followingCount, isFollowing] = await Promise.all([
    countFollowersForUser(supabase, authorUserId),
    countFollowingForUser(supabase, authorUserId),
    viewerUserId
      ? viewerFollowsAuthor(supabase, viewerUserId, authorUserId)
      : Promise.resolve(false),
  ]);
  return { followerCount, followingCount, isFollowing };
}

export type FollowMutationResult =
  | { ok: true }
  | { ok: false; message: string };

export async function followAuthor(
  client: SupabaseClient,
  followerUserId: string,
  authorUserId: string,
): Promise<FollowMutationResult> {
  if (followerUserId === authorUserId) {
    return { ok: false, message: "You can’t follow yourself." };
  }
  const { error } = await client.from(USER_FOLLOWS_TABLE).insert({
    follower_id: followerUserId,
    followed_id: authorUserId,
  });
  if (!error) {
    return { ok: true };
  }
  const code = (error as { code?: string }).code;
  if (code === "23505") {
    return { ok: true };
  }
  return { ok: false, message: error.message };
}

export async function unfollowAuthor(
  client: SupabaseClient,
  followerUserId: string,
  authorUserId: string,
): Promise<FollowMutationResult> {
  const { error } = await client
    .from(USER_FOLLOWS_TABLE)
    .delete()
    .eq("follower_id", followerUserId)
    .eq("followed_id", authorUserId);
  if (error) {
    return { ok: false, message: error.message };
  }
  return { ok: true };
}
