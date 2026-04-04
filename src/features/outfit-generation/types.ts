import type { ClothingCategory } from "@/features/wardrobe/types/clothing-item";

import type { OutfitOccasion } from "./occasion-presets";

export type OutfitSuggestionScoreBand =
  | "strong"
  | "solid"
  | "okay"
  | "mixed";

/**
 * Structured, deterministic copy for the suggest-outfit UI. See `suggestion-scoring.ts`
 * for how bands and bullets are derived.
 */
export type GeneratedOutfitExplanation = {
  scoringVersion: number;
  band: OutfitSuggestionScoreBand;
  bandLabel: string;
  summaryLine: string;
  pointsDisclaimer: string;
  sections: readonly {
    heading: string;
    bullets: readonly string[];
  }[];
  /** Compact reference to additive formula (honest, no fake precision). */
  formulaNote: string;
};

/**
 * A single ranked wardrobe combination produced by the on-device generator.
 * Ordering is deterministic for the same inputs (stable sorts, fixed score formula).
 */
export type GeneratedOutfitSuggestion = {
  /** Stable id for React keys / regenerate cursor (includes occasion). */
  id: string;
  /** User-selected context for this suggestion run. */
  occasion: OutfitOccasion;
  suggestedName: string;
  clothingItemIds: readonly string[];
  /** Short bullets for logs / feedback (subset of structured explanation). */
  hints: readonly string[];
  /** Internal sort key — not a probability; see `explanation.pointsDisclaimer`. */
  score: number;
  /** Bands + section copy for transparency. */
  explanation: GeneratedOutfitExplanation;
  /** Categories included, for debugging / future UI. */
  categoriesUsed: readonly ClothingCategory[];
};

export type GenerateOutfitsOptions = {
  /**
   * Drives scoring, bucket ordering, and hints. Defaults to `casual`
   * when omitted so call sites stay simple.
   */
  occasion?: OutfitOccasion;
  /** Max raw candidates before scoring (caps work on large wardrobes). */
  maxRawCandidates?: number;
  /** Max suggestions returned after sort. */
  maxResults?: number;
  /** Exclude combos whose item set already exists as a saved outfit. */
  skipExistingExact?: boolean;
};
