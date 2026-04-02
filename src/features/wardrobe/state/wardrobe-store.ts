import AsyncStorage from "@react-native-async-storage/async-storage";
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import { MOCK_CLOTHING_ITEMS } from "@/features/wardrobe/data/mock-clothing-items";
import type { ClothingItem } from "@/features/wardrobe/types/clothing-item";

const WARDROBE_STORAGE_KEY = "closy-wardrobe-v1";

const asyncStorage = {
  getItem: (name: string) => AsyncStorage.getItem(name),
  setItem: (name: string, value: string) => AsyncStorage.setItem(name, value),
  removeItem: (name: string) => AsyncStorage.removeItem(name),
};

/**
 * Client wardrobe cache (Zustand + AsyncStorage). For signed-in users, Supabase
 * `wardrobe_items` is loaded via `hydrateWardrobeFromCloud` → `setItems`; the UI
 * still reads this store through `wardrobe-service` / `useWardrobeItems`.
 */
export type WardrobeState = {
  items: ClothingItem[];
  /**
   * Once true, demo seed data is never applied again — including when the user removes every item.
   */
  hasSeededMockItems: boolean;
  addItem: (item: ClothingItem) => void;
  /** Replace one row by `id` (no-op if missing). */
  updateItem: (item: ClothingItem) => void;
  /** Drop a row by `id` (no-op if missing). */
  deleteItem: (id: string) => void;
  /** Apply server snapshot — main hook-in after `select` or full refetch. */
  setItems: (items: ClothingItem[]) => void;
};

type PersistedWardrobeSlice = Pick<
  WardrobeState,
  "items" | "hasSeededMockItems"
>;

function mergePersistedWardrobe(
  persistedState: unknown,
  currentState: WardrobeState,
): WardrobeState {
  if (
    persistedState == null ||
    typeof persistedState !== "object" ||
    Array.isArray(persistedState)
  ) {
    return currentState;
  }
  const p = persistedState as Partial<PersistedWardrobeSlice>;
  return {
    ...currentState,
    ...(Array.isArray(p.items) ? { items: p.items } : {}),
    ...(typeof p.hasSeededMockItems === "boolean"
      ? { hasSeededMockItems: p.hasSeededMockItems }
      : {}),
  };
}

export const useWardrobeStore = create<WardrobeState>()(
  persist(
    (set) => ({
      items: [],
      hasSeededMockItems: false,
      addItem: (item) => set((s) => ({ items: [item, ...s.items] })),
      updateItem: (item) =>
        set((s) => ({
          items: s.items.map((row) => (row.id === item.id ? item : row)),
        })),
      deleteItem: (id) =>
        set((s) => ({
          items: s.items.filter((row) => row.id !== id),
        })),
      setItems: (items) => set({ items }),
    }),
    {
      name: WARDROBE_STORAGE_KEY,
      version: 1,
      storage: createJSONStorage(() => asyncStorage),
      partialize: (s): PersistedWardrobeSlice => ({
        items: s.items,
        hasSeededMockItems: s.hasSeededMockItems,
      }),
      merge: mergePersistedWardrobe,
      /**
       * First launch (no storage): after hydration, `items` is empty and `hasSeededMockItems` is false
       * → inject demo items once and flip the flag (persisted on next write).
       *
       * User already has data: `items.length > 0` but flag was missing (e.g. old builds) → set flag only.
       * Returning user: `hasSeededMockItems` true → never touch items (empty wardrobe stays empty).
       */
      onRehydrateStorage: () => (_state, error) => {
        if (error) return;
        const state = useWardrobeStore.getState();
        if (state.hasSeededMockItems) return;

        if (state.items.length > 0) {
          useWardrobeStore.setState({ hasSeededMockItems: true });
          return;
        }

        useWardrobeStore.setState({
          items: [...MOCK_CLOTHING_ITEMS],
          hasSeededMockItems: true,
        });
      },
    },
  ),
);
