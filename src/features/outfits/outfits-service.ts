import { useOutfitsStore } from "@/features/outfits/state/outfits-store";
import type { CreateOutfitInput, Outfit } from "@/features/outfits/types/outfit";

export const outfitsService = {
  getOutfits(): readonly Outfit[] {
    return useOutfitsStore.getState().outfits;
  },

  addOutfit(input: CreateOutfitInput): Outfit {
    return useOutfitsStore.getState().addOutfit(input);
  },

  updateOutfit(id: string, input: CreateOutfitInput): void {
    useOutfitsStore.getState().updateOutfit(id, input);
  },

  deleteOutfit(id: string): void {
    useOutfitsStore.getState().deleteOutfit(id);
  },
} as const;

export function useOutfits(): readonly Outfit[] {
  return useOutfitsStore((s) => s.outfits);
}
