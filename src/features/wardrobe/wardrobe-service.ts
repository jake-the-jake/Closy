/**
 * Wardrobe domain API for routes and components.
 *
 * - **UI state**: Always reads/writes `useWardrobeStore` so screens stay unchanged.
 * - **Signed in + Supabase**: `createItem` inserts then `addItem`s the returned UUID
 *   row; `hydrateWardrobeFromCloud` replaces the cache from `wardrobe_items`; UUID
 *   rows sync on update/delete (best effort).
 * - **No session or failed remote op**: `createItem` falls back to local `local-…` ids.
 */
import {
  clothingItemDisplayUri,
  normalizeImageRefs,
} from "@/features/wardrobe/lib/clothing-item-images";
import { createClothingItem } from "@/features/wardrobe/lib/create-clothing-item";
import {
  deleteWardrobeItemFromCloud,
  insertWardrobeItemToCloud,
  isCloudWardrobeItemId,
  persistableImageUrlForCloud,
  updateWardrobeItemInCloud,
} from "@/features/wardrobe/lib/cloud-wardrobe";
import {
  deleteAllWardrobeImagesForItem,
  invokeProcessWardrobeDerivatives,
  newCloudWardrobeRowId,
  uploadWardrobeItemOriginal,
} from "@/features/wardrobe/lib/wardrobe-image-storage";
import { useWardrobeStore } from "@/features/wardrobe/state/wardrobe-store";
import type { ClothingItem, CreateClothingItemInput } from "@/features/wardrobe/types/clothing-item";
import { getAuthedUserId } from "@/lib/supabase/get-authed-user-id";
import { supabase } from "@/lib/supabase/client";

function isPublicWardrobeUrl(url: string): boolean {
  const t = url.trim();
  return t.startsWith("https://") || t.startsWith("http://");
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
      const id = newCloudWardrobeRowId();
      let imageUrl = "";
      let imageRefs: ClothingItem["imageRefs"] = null;

      if (input.localImageUri?.trim()) {
        const up = await uploadWardrobeItemOriginal(
          client,
          userId,
          id,
          input.localImageUri,
        );
        if (up.ok) {
          const proc = await invokeProcessWardrobeDerivatives(client, id);
          if (proc.ok) {
            imageRefs = proc.imageRefs;
            imageUrl = proc.imageRefs.display;
          } else {
            console.warn(
              "[Closy] Wardrobe derivative pipeline failed:",
              proc.errorMessage,
            );
            imageRefs = normalizeImageRefs(null, up.publicUrl);
            imageUrl = up.publicUrl;
          }
        } else {
          console.warn("[Closy] Wardrobe image upload failed:", up.errorMessage);
        }
      }

      const remote = await insertWardrobeItemToCloud(client, userId, input, {
        id,
        imageUrl,
        imageRefs,
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
      const legacyUrl =
        prev?.imageRefs?.original?.trim() ||
        prev?.imageUrl?.trim() ||
        "";
      if (isPublicWardrobeUrl(legacyUrl)) {
        await deleteAllWardrobeImagesForItem(client, userId, item.id, legacyUrl);
      }

      const up = await uploadWardrobeItemOriginal(
        client,
        userId,
        item.id,
        item.imageUrl,
      );
      if (up.ok) {
        const proc = await invokeProcessWardrobeDerivatives(client, item.id);
        if (proc.ok) {
          syncItem = {
            ...item,
            imageUrl: proc.imageRefs.display,
            imageRefs: proc.imageRefs,
          };
        } else {
          console.warn(
            "[Closy] Wardrobe derivative pipeline failed:",
            proc.errorMessage,
          );
          syncItem = {
            ...item,
            imageUrl: up.publicUrl,
            imageRefs: normalizeImageRefs(null, up.publicUrl),
          };
        }
        useWardrobeStore.getState().updateItem(syncItem);
      } else {
        console.warn("[Closy] Wardrobe image upload failed:", up.errorMessage);
        const fallbackUrl = prev ? clothingItemDisplayUri(prev) : "";
        syncItem = { ...item, imageUrl: fallbackUrl, imageRefs: prev?.imageRefs };
        useWardrobeStore.getState().updateItem(syncItem);
      }
    }

    await updateWardrobeItemInCloud(client, userId, syncItem);
  },

  async deleteItem(id: string): Promise<void> {
    const client = supabase;
    const userId = await getAuthedUserId();
    const existing = useWardrobeStore.getState().items.find((row) => row.id === id);
    if (client && userId && isCloudWardrobeItemId(id)) {
      const legacyUrl =
        existing?.imageRefs?.original?.trim() ||
        existing?.imageUrl?.trim() ||
        "";
      if (legacyUrl && isPublicWardrobeUrl(legacyUrl)) {
        await deleteAllWardrobeImagesForItem(client, userId, id, legacyUrl);
      }
      await deleteWardrobeItemFromCloud(client, userId, id);
    }
    useWardrobeStore.getState().deleteItem(id);
  },
} as const;

export function useWardrobeItems(): readonly ClothingItem[] {
  return useWardrobeStore((s) => s.items);
}
