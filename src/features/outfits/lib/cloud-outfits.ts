/**
 * Supabase access for `outfits`. UI cache: `useOutfitsStore` — hydrate replaces the
 * list on successful fetch; mutations go through `outfits-service`.
 */
import type { SupabaseClient } from "@supabase/supabase-js";

import { useOutfitsStore } from "@/features/outfits/state/outfits-store";
import type { CreateOutfitInput, Outfit } from "@/features/outfits/types/outfit";
import { useRemoteSyncStore } from "@/lib/sync";
import { supabase } from "@/lib/supabase/client";

export const OUTFITS_TABLE = "outfits";

const CLOUD_OUTFIT_ID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

/** Supabase-assigned outfit ids are UUIDs; legacy client ids use `outfit-…`. */
export function isCloudOutfitId(id: string): boolean {
  return CLOUD_OUTFIT_ID_RE.test(id);
}

export type OutfitRow = {
  id: string;
  user_id: string;
  name: string;
  clothing_item_ids: string[] | null;
  created_at: string;
  updated_at: string;
};

export function mapRowToOutfit(row: OutfitRow): Outfit {
  const ids = row.clothing_item_ids ?? [];
  const createdAt = new Date(row.created_at).getTime();
  const updatedRaw = new Date(row.updated_at).getTime();
  return {
    id: row.id,
    name: row.name,
    clothingItemIds: [...ids],
    createdAt,
    updatedAt: Number.isFinite(updatedRaw) ? updatedRaw : createdAt,
  };
}

/**
 * On success, replaces the outfits cache with the server list (including empty).
 * On error, leaves the cache unchanged.
 */
export async function hydrateOutfitsFromCloud(userId: string): Promise<void> {
  if (!supabase) return;
  const patchOutfits = useRemoteSyncStore.getState().patchOutfits;
  patchOutfits({ phase: "syncing", errorMessage: null });

  const { data, error } = await supabase
    .from(OUTFITS_TABLE)
    .select("*")
    .eq("user_id", userId)
    .order("created_at", { ascending: false });
  if (error) {
    console.warn("[Closy] Outfits fetch failed:", error.message);
    patchOutfits({
      phase: "error",
      errorMessage: error.message,
      updatedAt: Date.now(),
    });
    return;
  }
  const rows = (data ?? []) as OutfitRow[];
  const outfits: Outfit[] = rows.map(mapRowToOutfit);
  useOutfitsStore.getState().setOutfits(outfits);
  patchOutfits({
    phase: "success",
    errorMessage: null,
    updatedAt: Date.now(),
  });
}

export async function insertOutfitToCloud(
  client: SupabaseClient,
  userId: string,
  input: CreateOutfitInput,
): Promise<Outfit | null> {
  const payload = {
    user_id: userId,
    name: input.name.trim(),
    clothing_item_ids: [...input.clothingItemIds],
  };
  const { data, error } = await client
    .from(OUTFITS_TABLE)
    .insert(payload)
    .select()
    .single();
  if (error) {
    console.warn("[Closy] Outfits insert failed:", error.message);
    return null;
  }
  return mapRowToOutfit(data as OutfitRow);
}

export async function updateOutfitInCloud(
  client: SupabaseClient,
  userId: string,
  outfitId: string,
  input: CreateOutfitInput,
): Promise<boolean> {
  const { error } = await client
    .from(OUTFITS_TABLE)
    .update({
      name: input.name.trim(),
      clothing_item_ids: [...input.clothingItemIds],
      updated_at: new Date().toISOString(),
    })
    .eq("user_id", userId)
    .eq("id", outfitId);
  if (error) {
    console.warn("[Closy] Outfits update failed:", error.message);
    return false;
  }
  return true;
}

export async function deleteOutfitFromCloud(
  client: SupabaseClient,
  userId: string,
  id: string,
): Promise<boolean> {
  const { error } = await client
    .from(OUTFITS_TABLE)
    .delete()
    .eq("user_id", userId)
    .eq("id", id);
  if (error) {
    console.warn("[Closy] Outfits delete failed:", error.message);
    return false;
  }
  return true;
}
