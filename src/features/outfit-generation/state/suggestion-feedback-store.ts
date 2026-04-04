import AsyncStorage from "@react-native-async-storage/async-storage";
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import type {
  LocalOutfitSuggestionFeedbackEntry,
  OutfitSuggestionFeedbackPayload,
} from "@/features/outfit-generation/types/suggestion-feedback";

const STORAGE_KEY = "closy-outfit-suggestion-feedback-v1";
const MAX_ENTRIES = 250;

const asyncStorage = {
  getItem: (name: string) => AsyncStorage.getItem(name),
  setItem: (name: string, value: string) => AsyncStorage.setItem(name, value),
  removeItem: (name: string) => AsyncStorage.removeItem(name),
};

function createLocalId(): string {
  return `sfb-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

type SuggestionFeedbackState = {
  entries: LocalOutfitSuggestionFeedbackEntry[];
  append: (entry: OutfitSuggestionFeedbackPayload) => void;
};

export const useSuggestionFeedbackStore = create<SuggestionFeedbackState>()(
  persist(
    (set, get) => ({
      entries: [],
      append: (entry) => {
        const row: LocalOutfitSuggestionFeedbackEntry = {
          ...entry,
          localId: createLocalId(),
          createdAt: Date.now(),
        };
        set({ entries: [row, ...get().entries].slice(0, MAX_ENTRIES) });
      },
    }),
    {
      name: STORAGE_KEY,
      storage: createJSONStorage(() => asyncStorage),
      partialize: (s) => ({ entries: s.entries }),
    },
  ),
);
