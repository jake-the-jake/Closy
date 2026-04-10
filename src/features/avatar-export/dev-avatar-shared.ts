import type { AvatarOutfitLike } from "./types";

/** Poses aligned with engine export naming. */
export type DevAvatarPoseKey = "relaxed" | "walk" | "tpose" | "apose";

export type DevAvatarPresetKey = "default" | "navy" | "casual";

/** Outfit preset catalog — shared by live viewport and offline export dev UI. */
export const DEV_AVATAR_PRESETS: Record<DevAvatarPresetKey, AvatarOutfitLike> = {
  default: {
    top: { kind: "jumper" },
    bottom: { kind: "trousers" },
  },
  navy: {
    top: { kind: "jumper", color: [0.12, 0.18, 0.42] },
    bottom: { kind: "trousers", color: [0.15, 0.16, 0.2] },
  },
  casual: {
    top: { kind: "shirt", color: [0.85, 0.35, 0.32] },
    bottom: { kind: "trousers", color: [0.28, 0.32, 0.38] },
    shoes: { kind: "shoes", color: [0.65, 0.64, 0.62] },
  },
};

export function presetGarmentColors(preset: DevAvatarPresetKey): {
  top: [number, number, number];
  bottom: [number, number, number];
  shoes: [number, number, number];
} {
  const o = DEV_AVATAR_PRESETS[preset];
  const top = o.top?.color ?? [0.78, 0.72, 0.68];
  const bottom = o.bottom?.color ?? [0.35, 0.34, 0.38];
  const shoes = o.shoes?.color ?? [0.15, 0.15, 0.16];
  return { top, bottom, shoes };
}
