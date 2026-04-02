/**
 * Wardrobe domain API for routes and components.
 *
 * - **UI state**: Always reads/writes `useWardrobeStore` so screens stay unchanged.
 * - **Signed in + Supabase**: `createItem` inserts then `addItem`s the returned UUID
 *   row; `hydrateWardrobeFromCloud` replaces the cache from `wardrobe_items`; UUID
 *   rows sync on update/delete (best effort).
 * - **No session or failed remote op**: `createItem` falls back to local `local-…` ids.
 */
import { createClothingItem } from "@/features/wardrobe/lib/create-clothing-item";
import {
  deleteWardrobeItemFromCloud,
  insertWardrobeItemToCloud,
  isCloudWardrobeItemId,
  persistableImageUrlForCloud,
  updateWardrobeItemInCloud,
} from "@/features/wardrobe/lib/cloud-wardrobe";
import {
  deleteWardrobeItemImageByPublicUrl,
  isWardrobeImagePublicObjectUrl,
  newCloudWardrobeRowId,
  uploadWardrobeItemImage,
} from "@/features/wardrobe/lib/wardrobe-image-storage";
import { useWardrobeStore } from "@/features/wardrobe/state/wardrobe-store";
import type { ClothingItem, CreateClothingItemInput } from "@/features/wardrobe/types/clothing-item";
import { getAuthedUserId } from "@/lib/supabase/get-authed-user-id";
import { supabase } from "@/lib/supabase/client";

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
      const id = newCloudWardrobeRowId();
      let imageUrl = "";
      if (input.localImageUri?.trim()) {
        const up = await uploadWardrobeItemImage(
          client,
          userId,
          id,
          input.localImageUri,
        );
        if (up.ok) {
          imageUrl = up.publicUrl;
        } else {
          console.warn("[Closy] Wardrobe image upload failed:", up.errorMessage);
        }
      }
      const remote = await insertWardrobeItemToCloud(client, userId, input, {
        id,
        imageUrl,
      });
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
    const prev = useWardrobeStore
      .getState()
      .items.find((row) => row.id === item.id);
    useWardrobeStore.getState().updateItem(item);

    const client = supabase;
    const userId = await getAuthedUserId();
    if (!client || !userId || !isCloudWardrobeItemId(item.id)) {
      return;
    }

    let syncItem = item;
    if (item.imageUrl.trim() && !persistableImageUrlForCloud(item.imageUrl)) {
      const up = await uploadWardrobeItemImage(
        client,
        userId,
        item.id,
        item.imageUrl,
      );
      if (up.ok) {
        syncItem = { ...item, imageUrl: up.publicUrl };
        useWardrobeStore.getState().updateItem(syncItem);
      } else {
        console.warn("[Closy] Wardrobe image upload failed:", up.errorMessage);
        const fallbackUrl = prev?.imageUrl ?? "";
        syncItem = { ...item, imageUrl: fallbackUrl };
        useWardrobeStore.getState().updateItem(syncItem);
      }
    }

    const prevRemote = (prev?.imageUrl ?? "").trim();
    const nextRemote = syncItem.imageUrl.trim();
    if (
      prevRemote &&
      isWardrobeImagePublicObjectUrl(prevRemote) &&
      prevRemote !== nextRemote
    ) {
      await deleteWardrobeItemImageByPublicUrl(client, prevRemote);
    }

    await updateWardrobeItemInCloud(client, userId, syncItem);
  },

  async deleteItem(id: string): Promise<void> {
    const client = supabase;
    const userId = await getAuthedUserId();
    const existing = useWardrobeStore.getState().items.find((row) => row.id === id);
    if (client && userId && isCloudWardrobeItemId(id)) {
      const url = existing?.imageUrl?.trim() ?? "";
      if (url && isWardrobeImagePublicObjectUrl(url)) {
        await deleteWardrobeItemImageByPublicUrl(client, url);
      }
      await deleteWardrobeItemFromCloud(client, userId, id);
    }
    useWardrobeStore.getState().deleteItem(id);
  },
} as const;

export function useWardrobeItems(): readonly ClothingItem[] {
  return useWardrobeStore((s) => s.items);
}
