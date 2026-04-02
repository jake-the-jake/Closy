import { create } from "zustand";

export type RemoteSyncPhase = "idle" | "syncing" | "success" | "error";

/**
 * Last-known remote hydration attempt for a domain. Ephemeral — not persisted.
 * Drives non-blocking banners while lists stay interactive.
 */
export type RemoteDomainSnapshot = {
  phase: RemoteSyncPhase;
  errorMessage: string | null;
  updatedAt: number | null;
};

const emptyDomain = (): RemoteDomainSnapshot => ({
  phase: "idle",
  errorMessage: null,
  updatedAt: null,
});

type RemoteSyncStore = {
  wardrobe: RemoteDomainSnapshot;
  outfits: RemoteDomainSnapshot;
  patchWardrobe: (patch: Partial<RemoteDomainSnapshot>) => void;
  patchOutfits: (patch: Partial<RemoteDomainSnapshot>) => void;
  reset: () => void;
  dismissWardrobeError: () => void;
  dismissOutfitsError: () => void;
};

export const useRemoteSyncStore = create<RemoteSyncStore>((set) => ({
  wardrobe: emptyDomain(),
  outfits: emptyDomain(),
  patchWardrobe: (patch) =>
    set((s) => ({ wardrobe: { ...s.wardrobe, ...patch } })),
  patchOutfits: (patch) =>
    set((s) => ({ outfits: { ...s.outfits, ...patch } })),
  reset: () =>
    set({ wardrobe: emptyDomain(), outfits: emptyDomain() }),
  dismissWardrobeError: () =>
    set((s) => ({
      wardrobe: {
        ...s.wardrobe,
        phase: "success",
        errorMessage: null,
      },
    })),
  dismissOutfitsError: () =>
    set((s) => ({
      outfits: {
        ...s.outfits,
        phase: "success",
        errorMessage: null,
      },
    })),
}));
