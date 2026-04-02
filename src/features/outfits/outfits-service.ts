import {
  deleteOutfitFromCloud,
  insertOutfitToCloud,
  isCloudOutfitId,
  updateOutfitInCloud,
} from "@/features/outfits/lib/cloud-outfits";
import { useOutfitsStore } from "@/features/outfits/state/outfits-store";
import type { CreateOutfitInput, Outfit } from "@/features/outfits/types/outfit";
import { getAuthedUserId } from "@/lib/supabase/get-authed-user-id";
import { supabase } from "@/lib/supabase/client";

/**
 * Outfits domain API. Store is the UI cache; when signed in, UUID rows sync to `outfits`.
 * Legacy `outfit-…` ids stay local-only. Missing wardrobe ids are handled at display time.
 */
export const outfitsService = {
  getOutfits(): readonly Outfit[] {
    return useOutfitsStore.getState().outfits;
  },

  async addOutfit(input: CreateOutfitInput): Promise<Outfit> {
    const client = supabase;
    const userId = await getAuthedUserId();
    if (client && userId) {
      const remote = await insertOutfitToCloud(client, userId, input);
      if (remote) {
        useOutfitsStore.getState().ingestOutfit(remote);
        return remote;
      }
    }
    return useOutfitsStore.getState().addOutfit(input);
  },

  async updateOutfit(id: string, input: CreateOutfitInput): Promise<void> {
    useOutfitsStore.getState().updateOutfit(id, input);
    const client = supabase;
    const userId = await getAuthedUserId();
    if (client && userId && isCloudOutfitId(id)) {
      await updateOutfitInCloud(client, userId, id, input);
    }
  },

  async deleteOutfit(id: string): Promise<void> {
    const client = supabase;
    const userId = await getAuthedUserId();
    if (client && userId && isCloudOutfitId(id)) {
      await deleteOutfitFromCloud(client, userId, id);
    }
    useOutfitsStore.getState().deleteOutfit(id);
  },
} as const;

export function useOutfits(): readonly Outfit[] {
  return useOutfitsStore((s) => s.outfits);
}
