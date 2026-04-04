/**
 * Local outfits cache. Signed-in users: `hydrateOutfitsFromCloud` → `setOutfits`.
 * Mutations go through `outfits-service` (remote when id is a Supabase UUID).
 */
import AsyncStorage from "@react-native-async-storage/async-storage";
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import { createLocalOutfitId } from "@/features/outfits/lib/local-outfit-id";
import type {
  CreateOutfitInput,
  Outfit,
} from "@/features/outfits/types/outfit";

const OUTFITS_STORAGE_KEY = "closy-outfits-v1";

const asyncStorage = {
  getItem: (name: string) => AsyncStorage.getItem(name),
  setItem: (name: string, value: string) => AsyncStorage.setItem(name, value),
  removeItem: (name: string) => AsyncStorage.removeItem(name),
};

export type OutfitsState = {
  outfits: Outfit[];
  /** Replace list after a remote fetch (or clear). */
  setOutfits: (outfits: Outfit[]) => void;
  /** Prepend a row returned from Supabase insert. */
  ingestOutfit: (outfit: Outfit) => void;
  addOutfit: (input: CreateOutfitInput) => Outfit;
  updateOutfit: (id: string, input: CreateOutfitInput) => void;
  deleteOutfit: (id: string) => void;
};

type PersistedOutfitsSlice = Pick<OutfitsState, "outfits">;

function mergePersistedOutfits(
  persistedState: unknown,
  currentState: OutfitsState,
): OutfitsState {
  if (
    persistedState == null ||
    typeof persistedState !== "object" ||
    Array.isArray(persistedState)
  ) {
    return currentState;
  }
  const p = persistedState as Partial<PersistedOutfitsSlice>;
  return {
    ...currentState,
    ...(Array.isArray(p.outfits) ? { outfits: p.outfits } : {}),
  };
}

export const useOutfitsStore = create<OutfitsState>()(
  persist(
    (set) => ({
      outfits: [],
      setOutfits: (outfits) => set({ outfits }),
      ingestOutfit: (outfit) =>
        set((s) => ({ outfits: [outfit, ...s.outfits] })),
      addOutfit: (input) => {
        const now = Date.now();
        const outfit: Outfit = {
          id: createLocalOutfitId(),
          name: input.name.trim(),
          clothingItemIds: [...input.clothingItemIds],
          createdAt: now,
          updatedAt: now,
        };
        set((s) => ({ outfits: [outfit, ...s.outfits] }));
        return outfit;
      },
      updateOutfit: (id, input) =>
        set((s) => ({
          outfits: s.outfits.map((o) =>
            o.id === id
              ? {
                  ...o,
                  name: input.name.trim(),
                  clothingItemIds: [...input.clothingItemIds],
                  updatedAt: Date.now(),
                }
              : o,
          ),
        })),
      deleteOutfit: (id) =>
        set((s) => ({
          outfits: s.outfits.filter((o) => o.id !== id),
        })),
    }),
    {
      name: OUTFITS_STORAGE_KEY,
      version: 1,
      storage: createJSONStorage(() => asyncStorage),
      partialize: (s): PersistedOutfitsSlice => ({ outfits: s.outfits }),
      merge: mergePersistedOutfits,
    },
  ),
);
