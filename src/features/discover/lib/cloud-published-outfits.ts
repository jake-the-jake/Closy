/**
 * Supabase `published_outfits`: world-readable feed rows; insert = authenticated author only.
 */
import type { SupabaseClient } from "@supabase/supabase-js";

import {
  parsePublishedOutfitSnapshot,
  type PublishedOutfit,
  type PublishedOutfitSnapshot,
} from "@/features/discover/types/published-outfit";
import { supabase } from "@/lib/supabase/client";

export const PUBLISHED_OUTFITS_TABLE = "published_outfits";

export type PublishedOutfitRow = {
  id: string;
  user_id: string;
  source_outfit_id: string;
  name: string;
  piece_count: number;
  snapshot: unknown;
  created_at: string;
};

export function mapRowToPublishedOutfit(row: PublishedOutfitRow): PublishedOutfit | null {
  const snapshot = parsePublishedOutfitSnapshot(row.snapshot);
  if (!snapshot) return null;
  return {
    id: row.id,
    authorUserId: row.user_id,
    sourceOutfitId: row.source_outfit_id,
    name: row.name,
    pieceCount: row.piece_count,
    snapshot,
    publishedAt: new Date(row.created_at).getTime(),
  };
}

export async function insertPublishedOutfit(
  client: SupabaseClient,
  userId: string,
  snapshot: PublishedOutfitSnapshot,
): Promise<PublishedOutfit | null> {
  const payload = {
    user_id: userId,
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
  return mapRowToPublishedOutfit(data as PublishedOutfitRow);
}

export async function fetchPublishedOutfitsFeed(limit = 50): Promise<PublishedOutfit[]> {
  if (!supabase) return [];
  const { data, error } = await supabase
    .from(PUBLISHED_OUTFITS_TABLE)
    .select("*")
    .order("created_at", { ascending: false })
    .limit(limit);
  if (error) {
    console.warn("[Closy] Discover feed failed:", error.message);
    return [];
  }
  const rows = (data ?? []) as PublishedOutfitRow[];
  const out: PublishedOutfit[] = [];
  for (const row of rows) {
    const mapped = mapRowToPublishedOutfit(row);
    if (mapped) out.push(mapped);
  }
  return out;
}

export async function fetchPublishedOutfitById(
  id: string,
): Promise<PublishedOutfit | null> {
  if (!supabase) return null;
  const { data, error } = await supabase
    .from(PUBLISHED_OUTFITS_TABLE)
    .select("*")
    .eq("id", id)
    .maybeSingle();
  if (error) {
    console.warn("[Closy] Published outfit fetch failed:", error.message);
    return null;
  }
  if (!data) return null;
  return mapRowToPublishedOutfit(data as PublishedOutfitRow);
}
