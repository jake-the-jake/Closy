import { resolveAuthorDisplayLabelForPublish } from "@/features/auth";
import { buildPublishedOutfitSnapshot } from "@/features/discover/lib/build-published-outfit-snapshot";
import {
  deletePublishedOutfitForAuthor,
  fetchPublishedOutfitById,
  fetchPublishedOutfitsFeed,
  fetchPublishedOutfitsForAuthor as fetchPublishedOutfitsForAuthorFromCloud,
  insertPublishedOutfit,
  togglePublishedOutfitLike as applyPublishedOutfitLikeToggle,
  type DeletePublishedOutfitResult,
  type TogglePublishedOutfitLikeResult,
} from "@/features/discover/lib/cloud-published-outfits";
import type { PublishedOutfit } from "@/features/discover/types/published-outfit";
import type { Outfit } from "@/features/outfits/types/outfit";
import { findClothingItemById } from "@/features/wardrobe/data/find-clothing-item";
import type { ClothingItem } from "@/features/wardrobe/types/clothing-item";
import { getAuthedUser, getAuthedUserId } from "@/lib/supabase/get-authed-user-id";
import { supabase } from "@/lib/supabase/client";

export type { DeletePublishedOutfitResult, TogglePublishedOutfitLikeResult };

export const discoverService = {
  async fetchFeed(limit = 50): Promise<PublishedOutfit[]> {
    return fetchPublishedOutfitsFeed(limit);
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
    const authorDisplayName = resolveAuthorDisplayLabelForPublish(user);
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
} as const;
