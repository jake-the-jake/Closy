import { buildPublishedOutfitSnapshot } from "@/features/discover/lib/build-published-outfit-snapshot";
import {
  fetchPublishedOutfitById,
  fetchPublishedOutfitsFeed,
  insertPublishedOutfit,
} from "@/features/discover/lib/cloud-published-outfits";
import type { PublishedOutfit } from "@/features/discover/types/published-outfit";
import type { Outfit } from "@/features/outfits/types/outfit";
import { findClothingItemById } from "@/features/wardrobe/data/find-clothing-item";
import type { ClothingItem } from "@/features/wardrobe/types/clothing-item";
import { getAuthedUserId } from "@/lib/supabase/get-authed-user-id";
import { supabase } from "@/lib/supabase/client";

export const discoverService = {
  async fetchFeed(limit = 50): Promise<PublishedOutfit[]> {
    return fetchPublishedOutfitsFeed(limit);
  },

  async fetchPublishedById(id: string): Promise<PublishedOutfit | null> {
    return fetchPublishedOutfitById(id);
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
    if (!client || !userId) return null;

    const resolved = outfit.clothingItemIds.map((id) => ({
      id,
      item: findClothingItemById(wardrobeItems, id),
    }));
    const snapshot = buildPublishedOutfitSnapshot(outfit, resolved);
    return insertPublishedOutfit(client, userId, snapshot);
  },
} as const;
