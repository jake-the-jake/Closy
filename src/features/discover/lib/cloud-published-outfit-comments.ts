/**
 * Supabase `published_outfit_comments`: world read; insert/delete own `user_id` only.
 */
import type { SupabaseClient } from "@supabase/supabase-js";

import { commentAuthorDisplayLabel } from "@/features/discover/lib/comment-author-label";
import type { PublishedOutfitComment } from "@/features/discover/types/published-outfit-comment";
import { fetchPublicProfilesByUserIds } from "@/features/profile/lib/cloud-profiles";
import type { PublicUserProfile } from "@/features/profile/types/public-user-profile";
import { supabase } from "@/lib/supabase/client";

export const PUBLISHED_OUTFIT_COMMENTS_TABLE = "published_outfit_comments";

export const PUBLISHED_OUTFIT_COMMENT_BODY_MAX_LEN = 2000;

export type PublishedOutfitCommentRow = {
  id: string;
  published_outfit_id: string;
  user_id: string;
  body: string;
  created_at: string;
  updated_at: string | null;
};

function mapRowsToComments(
  rows: PublishedOutfitCommentRow[],
  profileMap: Map<string, PublicUserProfile>,
): PublishedOutfitComment[] {
  return rows.map((row) => {
    const prof = profileMap.get(row.user_id);
    const displayFromProfile = prof?.displayName?.trim() ?? "";
    return {
      id: row.id,
      publishedOutfitId: row.published_outfit_id,
      authorUserId: row.user_id,
      body: row.body,
      createdAt: new Date(row.created_at).getTime(),
      updatedAt: row.updated_at ? new Date(row.updated_at).getTime() : null,
      authorDisplayName: commentAuthorDisplayLabel(displayFromProfile, row.user_id),
      authorAvatarUrl: prof?.avatarUrl ?? null,
    };
  });
}

export type FetchPublishedOutfitCommentsResult =
  | { ok: true; comments: PublishedOutfitComment[] }
  | { ok: false; errorMessage: string };

/**
 * Comments for a post: **oldest first** (chronological), so the list reads top-to-bottom
 * and the newest comment sits above the composer.
 */
export async function fetchPublishedOutfitComments(
  publishedOutfitId: string,
): Promise<FetchPublishedOutfitCommentsResult> {
  if (!supabase || !publishedOutfitId) {
    return { ok: true, comments: [] };
  }
  const { data, error } = await supabase
    .from(PUBLISHED_OUTFIT_COMMENTS_TABLE)
    .select("id, published_outfit_id, user_id, body, created_at, updated_at")
    .eq("published_outfit_id", publishedOutfitId)
    .order("created_at", { ascending: true });
  if (error) {
    console.warn("[Closy] Published outfit comments fetch failed:", error.message);
    return { ok: false, errorMessage: error.message };
  }
  const rows = (data ?? []) as PublishedOutfitCommentRow[];
  if (rows.length === 0) {
    return { ok: true, comments: [] };
  }
  const profileMap = await fetchPublicProfilesByUserIds(
    supabase,
    rows.map((r) => r.user_id),
  );
  return { ok: true, comments: mapRowsToComments(rows, profileMap) };
}

export type PostCommentResult =
  | { ok: true }
  | { ok: false; errorMessage: string };

export async function insertPublishedOutfitComment(
  client: SupabaseClient,
  userId: string,
  publishedOutfitId: string,
  body: string,
): Promise<PostCommentResult> {
  const trimmed = body.trim();
  if (trimmed.length === 0) {
    return { ok: false, errorMessage: "Comment cannot be empty." };
  }
  if (trimmed.length > PUBLISHED_OUTFIT_COMMENT_BODY_MAX_LEN) {
    return {
      ok: false,
      errorMessage: `Comment is too long (max ${PUBLISHED_OUTFIT_COMMENT_BODY_MAX_LEN} characters).`,
    };
  }
  const { error } = await client.from(PUBLISHED_OUTFIT_COMMENTS_TABLE).insert({
    published_outfit_id: publishedOutfitId,
    user_id: userId,
    body: trimmed,
  });
  if (error) {
    return { ok: false, errorMessage: error.message };
  }
  return { ok: true };
}

export type DeleteCommentResult =
  | { ok: true }
  | { ok: false; errorMessage: string };

export async function deletePublishedOutfitCommentForAuthor(
  client: SupabaseClient,
  userId: string,
  commentId: string,
): Promise<DeleteCommentResult> {
  const { data, error } = await client
    .from(PUBLISHED_OUTFIT_COMMENTS_TABLE)
    .delete()
    .eq("id", commentId)
    .eq("user_id", userId)
    .select("id");
  if (error) {
    return { ok: false, errorMessage: error.message };
  }
  if (!data?.length) {
    return { ok: false, errorMessage: "Comment not found or you can’t remove it." };
  }
  return { ok: true };
}
