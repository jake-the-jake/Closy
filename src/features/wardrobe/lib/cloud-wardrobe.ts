/**
 * Supabase data access for `wardrobe_items` (RLS-scoped to `auth.uid()`).
 * The Zustand wardrobe store is the UI cache: hydrate replaces the snapshot
 * after a successful read; create/update/delete go through `wardrobe-service`.
 */
import type { SupabaseClient } from "@supabase/supabase-js";

import { useWardrobeStore } from "@/features/wardrobe/state/wardrobe-store";
import { clothingItemDisplayUri } from "@/features/wardrobe/lib/clothing-item-images";
import {
  CLOTHING_CATEGORIES,
  type ClothingCategory,
  type ClothingItem,
  type ClothingItemImageRefs,
  type CreateClothingItemInput,
} from "@/features/wardrobe/types/clothing-item";
import { useRemoteSyncStore } from "@/lib/sync";
import { supabase } from "@/lib/supabase/client";

export const WARDROBE_ITEMS_TABLE = "wardrobe_items";

/** Rows created in Supabase use UUID ids; local-only rows use `local-…` or demo ids. */
const CLOUD_WARDROBE_ID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function isCloudWardrobeItemId(id: string): boolean {
  return CLOUD_WARDROBE_ID_RE.test(id);
}

export type WardrobeItemRow = {
  id: string;
  user_id: string;
  name: string;
  category: string;
  colour: string;
  brand: string;
  image_url: string | null;
  image_refs: unknown | null;
  tags: string[] | null;
  created_at: string;
  updated_at: string;
};

function parseImageRefsFromRow(raw: unknown): ClothingItemImageRefs | null {
  if (raw == null) return null;
  if (typeof raw !== "object" || Array.isArray(raw)) return null;
  const o = raw as Record<string, unknown>;
  const original = typeof o.original === "string" ? o.original.trim() : "";
  const thumbnail = typeof o.thumbnail === "string" ? o.thumbnail.trim() : "";
  const display = typeof o.display === "string" ? o.display.trim() : "";
  if (!original && !thumbnail && !display) return null;
  return { original, thumbnail, display };
}

function parseCategory(raw: string): ClothingCategory | null {
  return CLOTHING_CATEGORIES.includes(raw as ClothingCategory)
    ? (raw as ClothingCategory)
    : null;
}

export function mapRowToClothingItem(row: WardrobeItemRow): ClothingItem | null {
  const category = parseCategory(row.category);
  if (!category) return null;
  const imageRefs = parseImageRefsFromRow(row.image_refs);
  const legacyUrl = (row.image_url ?? "").trim();
  const displayUrl =
    (imageRefs?.display?.trim() || legacyUrl).trim();
  return {
    id: row.id,
    name: row.name,
    category,
    colour: row.colour,
    brand: row.brand ?? "",
    imageUrl: displayUrl,
    imageRefs,
    tags: row.tags ?? [],
  };
}

/** Only http(s) URLs are stored remotely; local file URIs are skipped until image upload exists. */
export function persistableImageUrlForCloud(uri: string): string {
  const t = uri.trim();
  if (!t) return "";
  if (t.startsWith("https://") || t.startsWith("http://")) return t;
  return "";
}

/**
 * Replace the wardrobe cache with the server snapshot after a successful fetch.
 * Empty results mean an empty wardrobe in Supabase (not “keep old cache”).
 * On fetch error, the cache is left unchanged.
 */
export async function hydrateWardrobeFromCloud(userId: string): Promise<void> {
  if (!supabase) return;
  const patchWardrobe = useRemoteSyncStore.getState().patchWardrobe;
  patchWardrobe({ phase: "syncing", errorMessage: null });

  const { data, error } = await supabase
    .from(WARDROBE_ITEMS_TABLE)
    .select("*")
    .eq("user_id", userId)
    .order("created_at", { ascending: false });
  if (error) {
    console.warn("[Closy] Wardrobe fetch failed:", error.message);
    patchWardrobe({
      phase: "error",
      errorMessage: error.message,
      updatedAt: Date.now(),
    });
    return;
  }
  const rows = (data ?? []) as WardrobeItemRow[];
  const items: ClothingItem[] = [];
  for (const row of rows) {
    const item = mapRowToClothingItem(row);
    if (item) items.push(item);
  }
  useWardrobeStore.getState().setItems(items);
  patchWardrobe({
    phase: "success",
    errorMessage: null,
    updatedAt: Date.now(),
  });
}

export type InsertWardrobeItemCloudMeta = {
  /** Client-generated UUID — must match the Storage object folder `{userId}/{id}/`. */
  id: string;
  /** Legacy column: canonical display URL (HTTP). */
  imageUrl: string;
  imageRefs?: ClothingItemImageRefs | null;
};

export async function insertWardrobeItemToCloud(
  client: SupabaseClient,
  userId: string,
  input: CreateClothingItemInput,
  meta: InsertWardrobeItemCloudMeta,
): Promise<ClothingItem | null> {
  const image_url = persistableImageUrlForCloud(meta.imageUrl);
  const image_refs = meta.imageRefs ?? null;
  const payload = {
    id: meta.id,
    user_id: userId,
    name: input.name,
    category: input.category,
    colour: input.colour,
    brand: input.brand,
    image_url,
    image_refs,
    tags: [] as string[],
  };
  const { data, error } = await client
    .from(WARDROBE_ITEMS_TABLE)
    .insert(payload)
    .select()
    .single();
  if (error) {
    console.warn("[Closy] Wardrobe insert failed:", error.message);
    return null;
  }
  return mapRowToClothingItem(data as WardrobeItemRow);
}

export async function updateWardrobeItemInCloud(
  client: SupabaseClient,
  userId: string,
  item: ClothingItem,
): Promise<boolean> {
  const display = clothingItemDisplayUri(item);
  const image_url = persistableImageUrlForCloud(display);
  const image_refs = item.imageRefs ?? null;
  const { error } = await client
    .from(WARDROBE_ITEMS_TABLE)
    .update({
      name: item.name,
      category: item.category,
      colour: item.colour,
      brand: item.brand,
      image_url,
      image_refs,
      tags: [...item.tags],
      updated_at: new Date().toISOString(),
    })
    .eq("user_id", userId)
    .eq("id", item.id);
  if (error) {
    console.warn("[Closy] Wardrobe update failed:", error.message);
    return false;
  }
  return true;
}

export async function deleteWardrobeItemFromCloud(
  client: SupabaseClient,
  userId: string,
  id: string,
): Promise<boolean> {
  const { error } = await client
    .from(WARDROBE_ITEMS_TABLE)
    .delete()
    .eq("user_id", userId)
    .eq("id", id);
  if (error) {
    console.warn("[Closy] Wardrobe delete failed:", error.message);
    return false;
  }
  return true;
}
