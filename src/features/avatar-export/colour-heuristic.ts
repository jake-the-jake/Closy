import type { ClothingItem } from "@/features/wardrobe/types/clothing-item";

import type { AvatarOutfitLike } from "./types";

type Rgb = [number, number, number];

const NAMED: Record<string, Rgb> = {
  black: [0.08, 0.08, 0.09],
  white: [0.92, 0.92, 0.9],
  navy: [0.12, 0.18, 0.42],
  blue: [0.25, 0.4, 0.78],
  red: [0.75, 0.22, 0.22],
  green: [0.22, 0.5, 0.28],
  grey: [0.45, 0.46, 0.48],
  gray: [0.45, 0.46, 0.48],
  charcoal: [0.15, 0.16, 0.2],
  beige: [0.78, 0.72, 0.64],
  brown: [0.4, 0.28, 0.2],
  tan: [0.62, 0.5, 0.38],
  pink: [0.85, 0.45, 0.58],
  yellow: [0.86, 0.76, 0.28],
  orange: [0.86, 0.5, 0.22],
  purple: [0.45, 0.28, 0.62],
  cream: [0.94, 0.9, 0.82],
  olive: [0.38, 0.42, 0.28],
};

/** Very rough mapping from wardrobe colour labels to RGB for exporter tint only. */
export function colourStringToApproxRgb(colour: string): Rgb | undefined {
  const key = colour.trim().toLowerCase();
  if (key.length === 0) return undefined;
  for (const [name, rgb] of Object.entries(NAMED)) {
    if (key.includes(name)) return rgb;
  }
  return undefined;
}

export function clothingItemsToOutfitLike(
  items: readonly ClothingItem[],
): AvatarOutfitLike {
  const like: AvatarOutfitLike = {};
  for (const it of items) {
    const rgb = colourStringToApproxRgb(it.colour);
    if (it.category === "tops" || it.category === "dresses") {
      like.top = {
        kind: it.category === "dresses" ? "shirt" : "jumper",
        color: rgb,
      };
    } else if (it.category === "bottoms") {
      like.bottom = { kind: "trousers", color: rgb };
    } else if (it.category === "shoes") {
      like.shoes = { kind: "shoes", color: rgb };
    }
  }
  return like;
}
