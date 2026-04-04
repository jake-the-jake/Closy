import { resolveAuthorDisplayLabelForPublish } from "@/features/auth";
import { buildPublishedOutfitSnapshot } from "@/features/discover/lib/build-published-outfit-snapshot";
import { fetchPublicProfileByUserId } from "@/features/profile/lib/cloud-profiles";
import {
  deletePublishedOutfitCommentForAuthor,
  fetchPublishedOutfitComments,
  insertPublishedOutfitComment,
  type DeleteCommentResult,
  type FetchPublishedOutfitCommentsResult,
  type PostCommentResult,
} from "@/features/discover/lib/cloud-published-outfit-comments";
import {
  deletePublishedOutfitForAuthor,
  fetchPublishedOutfitById,
  fetchForYouPersonalizationSignals,
  fetchPublishedOutfitsFeed,
  fetchPublishedOutfitsFollowingFeed,
  fetchPublishedOutfitsForAuthor as fetchPublishedOutfitsForAuthorFromCloud,
  fetchPublishedOutfitsForYouFeed,
  insertPublishedOutfit,
  togglePublishedOutfitLike as applyPublishedOutfitLikeToggle,
  type DeletePublishedOutfitResult,
  type ForYouFeedSignalsRow,
  type TogglePublishedOutfitLikeResult,
} from "@/features/discover/lib/cloud-published-outfits";
import type { PublishedOutfit } from "@/features/discover/types/published-outfit";
import type { Outfit } from "@/features/outfits/types/outfit";
import { USER_FOLLOWS_TABLE } from "@/features/social";
import { findClothingItemById } from "@/features/wardrobe/data/find-clothing-item";
import type { ClothingItem } from "@/features/wardrobe/types/clothing-item";
import { getAuthedUser, getAuthedUserId } from "@/lib/supabase/get-authed-user-id";
import { supabase } from "@/lib/supabase/client";

export type {
  DeleteCommentResult,
  DeletePublishedOutfitResult,
  FetchPublishedOutfitCommentsResult,
  PostCommentResult,
  TogglePublishedOutfitLikeResult,
};

export type FollowingFeedResult = {
  items: PublishedOutfit[];
  /** People the signed-in user follows (for empty-state copy). */
  followedUserCount: number;
};

export type ForYouFeedResult = {
  items: PublishedOutfit[];
  /** Null when signed out or signals RPC failed. */
  signals: ForYouFeedSignalsRow | null;
};

export const discoverService = {
  async fetchFeed(limit = 50): Promise<PublishedOutfit[]> {
    return fetchPublishedOutfitsFeed(limit);
  },

  /**
   * Discover posts authored by users you follow. Requires session; returns empty when signed out.
   */
  async fetchFollowingFeed(limit = 50): Promise<FollowingFeedResult> {
    const client = supabase;
    if (!client) {
      return { items: [], followedUserCount: 0 };
    }
    const userId = await getAuthedUserId();
    if (!userId) {
      return { items: [], followedUserCount: 0 };
    }
    const { count, error } = await client
      .from(USER_FOLLOWS_TABLE)
      .select("*", { count: "exact", head: true })
      .eq("follower_id", userId);
    const followedUserCount = error ? 0 : (count ?? 0);
    const items = await fetchPublishedOutfitsFollowingFeed(limit);
    return { items, followedUserCount };
  },

  /**
   * For You: ranked Discover posts for the signed-in user (RPC). Requires session.
   * See `supabase/migrations/*_for_you_feed_rpc.sql` for the explicit scoring recipe.
   */
  async fetchForYouFeed(limit = 50): Promise<ForYouFeedResult> {
    const client = supabase;
    if (!client) {
      return { items: [], signals: null };
    }
    const userId = await getAuthedUserId();
    if (!userId) {
      return { items: [], signals: null };
    }
    const [signals, items] = await Promise.all([
      fetchForYouPersonalizationSignals(),
      fetchPublishedOutfitsForYouFeed(limit),
    ]);
    return { items, signals };
  },

  async fetchPublishedById(id: string): Promise<PublishedOutfit | null> {
    return fetchPublishedOutfitById(id);
  },

  async fetchPublishedOutfitsForAuthor(
    authorUserId: string,
    limit = 50,
  ): Promise<PublishedOutfit[]> {
    return fetchPublishedOutfitsForAuthorFromCloud(authorUserId, limit);
  },

  /**
   * Builds a frozen snapshot from the current wardrobe and inserts a Discover row.
   */
  async publishOutfitFromCurrentWardrobe(
    outfit: Outfit,
    wardrobeItems: readonly ClothingItem[],
  ): Promise<PublishedOutfit | null> {
    const client = supabase;
    const userId = await getAuthedUserId();
    const user = await getAuthedUser();
    if (!client || !userId || !user) return null;

    const resolved = outfit.clothingItemIds.map((id) => ({
      id,
      item: findClothingItemById(wardrobeItems, id),
    }));
    const snapshot = buildPublishedOutfitSnapshot(outfit, resolved);
    const profileRow = await fetchPublicProfileByUserId(userId);
    const fromProfile = profileRow?.displayName?.trim() ?? "";
    const authorDisplayName =
      fromProfile.length > 0
        ? fromProfile.length > 80
          ? fromProfile.slice(0, 80)
          : fromProfile
        : resolveAuthorDisplayLabelForPublish(user);
    return insertPublishedOutfit(client, userId, snapshot, authorDisplayName);
  },

  /** Author-only (RLS). Removes the row from Discover for everyone. */
  async unpublishPublishedOutfit(id: string): Promise<DeletePublishedOutfitResult> {
    const client = supabase;
    if (!client) {
      return { ok: false, errorMessage: "Supabase is not configured." };
    }
    const userId = await getAuthedUserId();
    if (!userId) {
      return { ok: false, errorMessage: "Sign in to manage your posts." };
    }
    return deletePublishedOutfitForAuthor(client, id);
  },

  /** Signed-in only (RLS). Toggles the current user’s single like on this post. */
  async togglePublishedOutfitLike(
    publishedOutfitId: string,
    options: { currentlyLiked: boolean },
  ): Promise<TogglePublishedOutfitLikeResult> {
    const client = supabase;
    if (!client) {
      return { ok: false, errorMessage: "Supabase is not configured." };
    }
    const userId = await getAuthedUserId();
    if (!userId) {
      return { ok: false, errorMessage: "Sign in to like posts." };
    }
    return applyPublishedOutfitLikeToggle(
      client,
      userId,
      publishedOutfitId,
      options.currentlyLiked,
    );
  },

  async fetchCommentsForPublishedOutfit(
    publishedOutfitId: string,
  ): Promise<FetchPublishedOutfitCommentsResult> {
    return fetchPublishedOutfitComments(publishedOutfitId);
  },

  async postCommentOnPublishedOutfit(
    publishedOutfitId: string,
    body: string,
  ): Promise<PostCommentResult> {
    const client = supabase;
    if (!client) {
      return { ok: false, errorMessage: "Supabase is not configured." };
    }
    const userId = await getAuthedUserId();
    if (!userId) {
      return { ok: false, errorMessage: "Sign in to comment." };
    }
    return insertPublishedOutfitComment(client, userId, publishedOutfitId, body);
  },

  async deleteMyCommentOnPublishedOutfit(
    commentId: string,
  ): Promise<DeleteCommentResult> {
    const client = supabase;
    if (!client) {
      return { ok: false, errorMessage: "Supabase is not configured." };
    }
    const userId = await getAuthedUserId();
    if (!userId) {
      return { ok: false, errorMessage: "Sign in to manage comments." };
    }
    return deletePublishedOutfitCommentForAuthor(client, userId, commentId);
  },
} as const;
