import type { ClothingCategory, ClothingItem } from "@/features/wardrobe/types/clothing-item";

import type { OutfitOccasion } from "./occasion-presets";

/** Keyword groups: item matches if any token appears in tags, name, or colour field. */
type OccasionProfile = {
  boost: readonly string[];
  /** Subtract weight when these appear (e.g. gym + office). */
  clash?: readonly string[];
};

const PROFILES: Record<OutfitOccasion, OccasionProfile> = {
  casual: {
    boost: [
      "casual",
      "weekend",
      "everyday",
      "relaxed",
      "lounge",
      "denim",
      "jean",
      "tee",
      "tshirt",
      "sneaker",
      "trainer",
    ],
    clash: ["formal", "gown", "tailored suit"],
  },
  smart_casual: {
    boost: [
      "smart",
      "smart casual",
      "chino",
      "blazer",
      "loafer",
      "oxford",
      "button",
      "shirt",
      "desk",
      "business casual",
    ],
    clash: ["sport", "gym", "sweat", "track"],
  },
  office: {
    boost: [
      "office",
      "work",
      "business",
      "professional",
      "tailored",
      "trouser",
      "slacks",
      "blouse",
      "suit",
      "pencil",
    ],
    clash: ["gym", "sport", "beach", "party sequin", "sweatpant"],
  },
  date_night: {
    boost: [
      "date",
      "evening",
      "dressy",
      "romantic",
      "heel",
      "midi",
      "satin",
      "wrap dress",
      "cocktail",
      "nice",
    ],
    clash: ["sport", "gym", "activewear"],
  },
  going_out: {
    boost: [
      "party",
      "club",
      "night out",
      "going out",
      "festival",
      "bold",
      "statement",
      "sequin",
      "leather",
      "mini",
    ],
    clash: ["sport", "gym", "office"],
  },
  gym: {
    boost: [
      "gym",
      "workout",
      "sport",
      "active",
      "training",
      "run",
      "running",
      "yoga",
      "athletic",
      "jogger",
      "tech fleece",
      "dri",
    ],
    clash: ["heel", "blazer", "tailored"],
  },
  warm_weather: {
    boost: [
      "summer",
      "linen",
      "cotton",
      "short",
      "tank",
      "sand",
      "beach",
      "vacation",
      "lightweight",
      "breathable",
    ],
    clash: ["wool coat", "puffer", "fleece", "thermal"],
  },
  cold_weather: {
    boost: [
      "winter",
      "cold",
      "knit",
      "wool",
      "fleece",
      "puffer",
      "layer",
      "coat",
      "boot",
      "thermal",
      "sweater",
      "chunky",
    ],
    clash: ["sand", "bikini", "linen short"],
  },
};

const FORMALISH_CATEGORIES: ClothingCategory[] = ["dresses"];

function itemHaystack(item: ClothingItem): string {
  const tagPart = item.tags.join(" ").trim();
  return [item.name, item.colour, item.brand, tagPart]
    .join(" ")
    .trim()
    .toLowerCase();
}

function countHits(haystack: string, needles: readonly string[]): number {
  let n = 0;
  for (const needle of needles) {
    if (needle.length > 0 && haystack.includes(needle)) n++;
  }
  return n;
}

/**
 * Per-item affinity for an occasion (roughly 0–40). Used to sort buckets and add outfit-level bonus.
 */
export function itemOccasionAffinity(
  item: ClothingItem,
  occasion: OutfitOccasion,
): number {
  const profile = PROFILES[occasion];
  const h = itemHaystack(item);
  let score = countHits(h, profile.boost) * 4;
  if (profile.clash != null) {
    score -= countHits(h, profile.clash) * 3;
  }

  if (occasion === "date_night" || occasion === "going_out") {
    if (item.category === "dresses") score += 8;
    if (item.category === "shoes" && /heel|boot|loafer|mule/.test(h)) score += 4;
  }
  if (occasion === "gym") {
    if (item.category === "shoes" && /run|train|sport|cross/i.test(h)) score += 10;
    if (item.category === "bottoms" && /short|legging|jogger|track/i.test(h))
      score += 6;
    if (item.category === "tops" && /tank|tee|performance|tech/i.test(h))
      score += 4;
  }
  if (occasion === "office") {
    if (item.category === "bottoms" && /jean|denim/i.test(h) && !/black|dark/i.test(h))
      score -= 4;
    if (FORMALISH_CATEGORIES.includes(item.category)) score += 2;
  }
  if (occasion === "cold_weather") {
    if (item.category === "outerwear") score += 12;
    if (item.category === "shoes" && /boot/i.test(h)) score += 6;
  }
  if (occasion === "warm_weather") {
    if (item.category === "outerwear") score -= 4;
    if (item.category === "bottoms" && /short/i.test(h)) score += 8;
  }

  return Math.max(0, score);
}

export type OccasionModifier = {
  scoreDelta: number;
  hints: string[];
};

export function occasionPiecesModifier(
  pieces: readonly ClothingItem[],
  occasion: OutfitOccasion,
): OccasionModifier {
  const hints: string[] = [];
  let scoreDelta = 0;
  const affinities = pieces.map((p) => itemOccasionAffinity(p, occasion));
  const avg =
    affinities.reduce((a, b) => a + b, 0) / Math.max(affinities.length, 1);
  scoreDelta += Math.min(avg * 1.2, 28);

  const cats = new Set(pieces.map((p) => p.category));

  if (occasion === "cold_weather" && cats.has("outerwear")) {
    scoreDelta += 14;
    hints.push("Outerwear included for cold weather.");
  } else if (occasion === "cold_weather" && !cats.has("outerwear")) {
    scoreDelta -= 8;
    hints.push("No outerwear yet — add a coat if needed.");
  }

  if (occasion === "warm_weather" && cats.has("outerwear")) {
    scoreDelta -= 5;
    hints.push("Jacket/outer layer present — optional if it’s hot.");
  }

  if (occasion === "gym" && affinities.every((x) => x < 6)) {
    hints.push("Few sporty cues in names/tags — tag items gym or training.");
    scoreDelta -= 6;
  }

  if (avg >= 14) {
    hints.push("Item labels/tags line up well with this occasion.");
  } else if (avg < 5) {
    hints.push("Loose keyword match — try tags like office, casual, gym.");
  }

  return { scoreDelta, hints };
}
