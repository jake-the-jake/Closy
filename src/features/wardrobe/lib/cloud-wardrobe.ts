import type { SupabaseClient } from "@supabase/supabase-js";

import { useWardrobeStore } from "@/features/wardrobe/state/wardrobe-store";
import {
  CLOTHING_CATEGORIES,
  type ClothingCategory,
  type ClothingItem,
  type CreateClothingItemInput,
} from "@/features/wardrobe/types/clothing-item";
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
  tags: string[] | null;
  created_at: string;
  updated_at: string;
};

function parseCategory(raw: string): ClothingCategory | null {
  return CLOTHING_CATEGORIES.includes(raw as ClothingCategory)
    ? (raw as ClothingCategory)
    : null;
}

export function mapRowToClothingItem(row: WardrobeItemRow): ClothingItem | null {
  const category = parseCategory(row.category);
  if (!category) return null;
  return {
    id: row.id,
    name: row.name,
    category,
    colour: row.colour,
    brand: row.brand ?? "",
    imageUrl: (row.image_url ?? "").trim(),
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
 * When the server returns rows, they replace the in-memory list (device cache).
 * If the server has no rows, local items are left unchanged so first-time sign-in
 * does not wipe an existing offline wardrobe.
 */
export async function hydrateWardrobeFromCloud(userId: string): Promise<void> {
  if (!supabase) return;
  const { data, error } = await supabase
    .from(WARDROBE_ITEMS_TABLE)
    .select("*")
    .eq("user_id", userId)
    .order("created_at", { ascending: false });
  if (error) {
    console.warn("[Closy] Wardrobe fetch failed:", error.message);
    return;
  }
  const rows = (data ?? []) as WardrobeItemRow[];
  const items: ClothingItem[] = [];
  for (const row of rows) {
    const item = mapRowToClothingItem(row);
    if (item) items.push(item);
  }
  if (items.length > 0) {
    useWardrobeStore.getState().setItems(items);
  }
}

export async function insertWardrobeItemToCloud(
  client: SupabaseClient,
  userId: string,
  input: CreateClothingItemInput,
): Promise<ClothingItem | null> {
  const image_url = persistableImageUrlForCloud(input.localImageUri ?? "");
  const payload = {
    user_id: userId,
    name: input.name,
    category: input.category,
    colour: input.colour,
    brand: input.brand,
    image_url,
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
  const image_url = persistableImageUrlForCloud(item.imageUrl);
  const { error } = await client
    .from(WARDROBE_ITEMS_TABLE)
    .update({
      name: item.name,
      category: item.category,
      colour: item.colour,
      brand: item.brand,
      image_url,
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
