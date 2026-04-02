import { createClothingItem } from "@/features/wardrobe/lib/create-clothing-item";
import {
  deleteWardrobeItemFromCloud,
  insertWardrobeItemToCloud,
  isCloudWardrobeItemId,
  updateWardrobeItemInCloud,
} from "@/features/wardrobe/lib/cloud-wardrobe";
import { useWardrobeStore } from "@/features/wardrobe/state/wardrobe-store";
import type { ClothingItem, CreateClothingItemInput } from "@/features/wardrobe/types/clothing-item";
import { supabase } from "@/lib/supabase/client";

async function getAuthedUserId(): Promise<string | null> {
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session?.user.id ?? null;
}

/**
 * Wardrobe reads/writes. Local Zustand + AsyncStorage is always updated for UI;
 * when a Supabase session exists, wardrobe_items rows are kept in sync (best effort).
 */
export const wardrobeService = {
  getItems(): readonly ClothingItem[] {
    return useWardrobeStore.getState().items;
  },

  async createItem(input: CreateClothingItemInput): Promise<ClothingItem> {
    const client = supabase;
    const userId = await getAuthedUserId();
    if (client && userId) {
      const remote = await insertWardrobeItemToCloud(client, userId, input);
      if (remote) {
        useWardrobeStore.getState().addItem(remote);
        return remote;
      }
    }
    const item = createClothingItem(input);
    useWardrobeStore.getState().addItem(item);
    return item;
  },

  async updateItem(item: ClothingItem): Promise<void> {
    useWardrobeStore.getState().updateItem(item);
    const client = supabase;
    const userId = await getAuthedUserId();
    if (client && userId && isCloudWardrobeItemId(item.id)) {
      await updateWardrobeItemInCloud(client, userId, item);
    }
  },

  async deleteItem(id: string): Promise<void> {
    const client = supabase;
    const userId = await getAuthedUserId();
    if (client && userId && isCloudWardrobeItemId(id)) {
      await deleteWardrobeItemFromCloud(client, userId, id);
    }
    useWardrobeStore.getState().deleteItem(id);
  },
} as const;

export function useWardrobeItems(): readonly ClothingItem[] {
  return useWardrobeStore((s) => s.items);
}
