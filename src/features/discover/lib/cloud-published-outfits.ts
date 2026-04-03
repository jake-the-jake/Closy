/**
 * Supabase `published_outfits`: world-readable feed rows; insert = authenticated author only.
 * `published_outfit_likes`: world-readable counts; insert/delete own row only (RLS).
 */
import type { SupabaseClient } from "@supabase/supabase-js";

import {
  parsePublishedOutfitSnapshot,
  type PublishedOutfit,
  type PublishedOutfitSnapshot,
} from "@/features/discover/types/published-outfit";
import { fetchPublicProfilesByUserIds } from "@/features/profile/lib/cloud-profiles";
import { supabase } from "@/lib/supabase/client";

export const PUBLISHED_OUTFITS_TABLE = "published_outfits";
export const PUBLISHED_OUTFIT_LIKES_TABLE = "published_outfit_likes";

const FEED_SELECT = `
  *,
  published_outfit_likes(count)
`;

export type PublishedOutfitRow = {
  id: string;
  user_id: string;
  author_display_name: string | null;
  source_outfit_id: string;
  name: string;
  piece_count: number;
  snapshot: unknown;
  created_at: string;
};

export type PublishedOutfitRowWithLikeCount = PublishedOutfitRow & {
  published_outfit_likes?: { count: number }[] | null;
};

function readEmbeddedLikeCount(row: PublishedOutfitRowWithLikeCount): number {
  const nested = row.published_outfit_likes;
  if (!Array.isArray(nested) || nested.length < 1) return 0;
  const raw = nested[0]?.count;
  return typeof raw === "number" ? raw : 0;
}

export function mapRowToPublishedOutfit(
  row: PublishedOutfitRow,
  likes: { likeCount: number; likedByMe: boolean },
): PublishedOutfit | null {
  const snapshot = parsePublishedOutfitSnapshot(row.snapshot);
  if (!snapshot) return null;
  return {
    id: row.id,
    authorUserId: row.user_id,
    authorDisplayName: (row.author_display_name ?? "").trim(),
    authorAvatarUrl: null,
    sourceOutfitId: row.source_outfit_id,
    name: row.name,
    pieceCount: row.piece_count,
    snapshot,
    publishedAt: new Date(row.created_at).getTime(),
    likeCount: likes.likeCount,
    likedByMe: likes.likedByMe,
  };
}

function applyProfileToPublishedOutfit(
  post: PublishedOutfit,
  profile:
    | { displayName: string; avatarUrl: string | null }
    | null
    | undefined,
): PublishedOutfit {
  if (!profile) return post;
  const fromProfileName = profile.displayName.trim();
  const fromRow = post.authorDisplayName.trim();
  const authorDisplayName =
    fromProfileName.length > 0 ? fromProfileName : fromRow;
  return {
    ...post,
    authorDisplayName,
    authorAvatarUrl: profile.avatarUrl,
  };
}

async function mergeAuthorProfilesIntoOutfits(
  client: SupabaseClient,
  outfits: PublishedOutfit[],
): Promise<PublishedOutfit[]> {
  if (outfits.length === 0) return outfits;
  const profileMap = await fetchPublicProfilesByUserIds(
    client,
    outfits.map((o) => o.authorUserId),
  );
  return outfits.map((p) =>
    applyProfileToPublishedOutfit(p, profileMap.get(p.authorUserId)),
  );
}

async function fetchPublishedOutfitIdsLikedByUser(
  client: SupabaseClient,
  userId: string,
  outfitIds: string[],
): Promise<Set<string>> {
  if (outfitIds.length === 0) return new Set();
  const { data, error } = await client
    .from(PUBLISHED_OUTFIT_LIKES_TABLE)
    .select("published_outfit_id")
    .eq("user_id", userId)
    .in("published_outfit_id", outfitIds);
  if (error) {
    console.warn("[Closy] Discover like state failed:", error.message);
    return new Set();
  }
  const rows = (data ?? []) as { published_outfit_id: string }[];
  return new Set(rows.map((r) => r.published_outfit_id).filter(Boolean));
}

export async function countLikesForPublishedOutfit(
  client: SupabaseClient,
  publishedOutfitId: string,
): Promise<number> {
  const { count, error } = await client
    .from(PUBLISHED_OUTFIT_LIKES_TABLE)
    .select("*", { count: "exact", head: true })
    .eq("published_outfit_id", publishedOutfitId);
  if (error) {
    console.warn("[Closy] Like count failed:", error.message);
    return 0;
  }
  return count ?? 0;
}

export async function insertPublishedOutfit(
  client: SupabaseClient,
  userId: string,
  snapshot: PublishedOutfitSnapshot,
  authorDisplayName: string,
): Promise<PublishedOutfit | null> {
  const payload = {
    user_id: userId,
    author_display_name: authorDisplayName.trim(),
    source_outfit_id: snapshot.sourceOutfitId,
    name: snapshot.outfitName,
    piece_count: snapshot.lines.length,
    snapshot,
  };
  const { data, error } = await client
    .from(PUBLISHED_OUTFITS_TABLE)
    .insert(payload)
    .select()
    .single();
  if (error) {
    console.warn("[Closy] Publish outfit failed:", error.message);
    return null;
  }
  const base = mapRowToPublishedOutfit(data as PublishedOutfitRow, {
    likeCount: 0,
    likedByMe: false,
  });
  if (!base) return null;
  const merged = await mergeAuthorProfilesIntoOutfits(client, [base]);
  return merged[0] ?? base;
}

async function publishedOutfitsFromFeedRows(
  client: SupabaseClient,
  sessionUserId: string | null,
  rows: PublishedOutfitRowWithLikeCount[],
): Promise<PublishedOutfit[]> {
  const ids = rows.map((r) => r.id);
  const likedSet = sessionUserId
    ? await fetchPublishedOutfitIdsLikedByUser(client, sessionUserId, ids)
    : new Set<string>();

  const out: PublishedOutfit[] = [];
  for (const row of rows) {
    const likeCount = readEmbeddedLikeCount(row);
    const likedByMe = sessionUserId != null && likedSet.has(row.id);
    const { published_outfit_likes: _drop, ...base } = row;
    const mapped = mapRowToPublishedOutfit(base as PublishedOutfitRow, {
      likeCount,
      likedByMe,
    });
    if (mapped) out.push(mapped);
  }
  return mergeAuthorProfilesIntoOutfits(client, out);
}

export async function fetchPublishedOutfitsFeed(limit = 50): Promise<PublishedOutfit[]> {
  if (!supabase) return [];
  const { data: sessionData } = await supabase.auth.getSession();
  const sessionUserId = sessionData.session?.user?.id ?? null;

  const { data, error } = await supabase
    .from(PUBLISHED_OUTFITS_TABLE)
    .select(FEED_SELECT)
    .order("created_at", { ascending: false })
    .limit(limit);
  if (error) {
    console.warn("[Closy] Discover feed failed:", error.message);
    return [];
  }
  const rows = (data ?? []) as PublishedOutfitRowWithLikeCount[];
  return publishedOutfitsFromFeedRows(supabase, sessionUserId, rows);
}

/** Public posts by `user_id` (RLS: global read on `published_outfits`). */
export async function fetchPublishedOutfitsForAuthor(
  authorUserId: string,
  limit = 50,
): Promise<PublishedOutfit[]> {
  if (!supabase) return [];
  const { data: sessionData } = await supabase.auth.getSession();
  const sessionUserId = sessionData.session?.user?.id ?? null;

  const { data, error } = await supabase
    .from(PUBLISHED_OUTFITS_TABLE)
    .select(FEED_SELECT)
    .eq("user_id", authorUserId)
    .order("created_at", { ascending: false })
    .limit(limit);
  if (error) {
    console.warn("[Closy] Author published outfits failed:", error.message);
    return [];
  }
  const rows = (data ?? []) as PublishedOutfitRowWithLikeCount[];
  return publishedOutfitsFromFeedRows(supabase, sessionUserId, rows);
}

export async function fetchPublishedOutfitById(id: string): Promise<PublishedOutfit | null> {
  if (!supabase) return null;
  const { data: sessionData } = await supabase.auth.getSession();
  const sessionUserId = sessionData.session?.user?.id ?? null;

  const { data, error } = await supabase
    .from(PUBLISHED_OUTFITS_TABLE)
    .select(FEED_SELECT)
    .eq("id", id)
    .maybeSingle();
  if (error) {
    console.warn("[Closy] Published outfit fetch failed:", error.message);
    return null;
  }
  if (!data) return null;
  const row = data as PublishedOutfitRowWithLikeCount;
  const likeCount = readEmbeddedLikeCount(row);
  let likedByMe = false;
  if (sessionUserId) {
    const set = await fetchPublishedOutfitIdsLikedByUser(supabase, sessionUserId, [id]);
    likedByMe = set.has(id);
  }
  const { published_outfit_likes: _drop, ...base } = row;
  const mapped = mapRowToPublishedOutfit(base as PublishedOutfitRow, {
    likeCount,
    likedByMe,
  });
  if (!mapped) return null;
  const merged = await mergeAuthorProfilesIntoOutfits(supabase, [mapped]);
  return merged[0] ?? mapped;
}

export type DeletePublishedOutfitResult =
  | { ok: true }
  | { ok: false; errorMessage: string };

export async function deletePublishedOutfitForAuthor(
  client: SupabaseClient,
  id: string,
): Promise<DeletePublishedOutfitResult> {
  const { data, error } = await client
    .from(PUBLISHED_OUTFITS_TABLE)
    .delete()
    .eq("id", id)
    .select("id");
  if (error) {
    return { ok: false, errorMessage: error.message };
  }
  if (!data?.length) {
    return {
      ok: false,
      errorMessage: "Post not found or you can’t remove it.",
    };
  }
  return { ok: true };
}

export type TogglePublishedOutfitLikeResult =
  | { ok: true; likedByMe: boolean; likeCount: number }
  | { ok: false; errorMessage: string };

export async function togglePublishedOutfitLike(
  client: SupabaseClient,
  userId: string,
  publishedOutfitId: string,
  currentlyLiked: boolean,
): Promise<TogglePublishedOutfitLikeResult> {
  if (currentlyLiked) {
    const { error } = await client
      .from(PUBLISHED_OUTFIT_LIKES_TABLE)
      .delete()
      .eq("published_outfit_id", publishedOutfitId)
      .eq("user_id", userId);
    if (error) {
      return { ok: false, errorMessage: error.message };
    }
  } else {
    const { error } = await client.from(PUBLISHED_OUTFIT_LIKES_TABLE).insert({
      published_outfit_id: publishedOutfitId,
      user_id: userId,
    });
    if (error) {
      const code = (error as { code?: string }).code;
      if (code === "23505") {
        const likeCount = await countLikesForPublishedOutfit(client, publishedOutfitId);
        return { ok: true, likedByMe: true, likeCount: likeCount };
      }
      return { ok: false, errorMessage: error.message };
    }
  }

  const likeCount = await countLikesForPublishedOutfit(client, publishedOutfitId);
  return { ok: true, likedByMe: !currentlyLiked, likeCount: likeCount };
}
