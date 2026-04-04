/**
 * Outfit suggestion scoring — **100% rule-based**, deterministic for the same inputs.
 *
 * ## What the number means
 * The `score` is an **internal sort key** only. It is **not** a probability, fit
 * percentage, or “AI confidence.” Higher = ranked earlier among candidates for this
 * wardrobe snapshot. Typical range in practice is about **70–190** depending on
 * wardrobe and occasion.
 *
 * ## Formula (additive)
 * All terms use fixed weights so behaviour stays auditable:
 *
 * 1. **Base** — `+40` per outfit (neutral starting point).
 *
 * 2. **Colour harmony** — average pairwise harmony on `item.colour` strings (0–3
 *    scale from `colour-heuristic.ts`), times **`14`**. (~0–42)
 *
 * 3. **Tag cohesion** — `tagCohesionWeight(pieces)` (~0–8) times **`4`**.
 *
 * 4. **Completeness** — **`+18`** if outfit has **shoes** and **(bottoms or dress)**.
 *
 * 5. **Layering** — **`+12`** if **outerwear** and **tops** both present.
 *
 * 6. **Category variety** — `min(distinctCategories × 2.5, 10)`.
 *
 * 7. **Piece count** — **`+6`** if **≥4** pieces; **`-10`** if **>5** (soft anti-clutter).
 *
 * 8. **Occasion fit** — full delta from `occasionPiecesModifier` (keyword affinity on
 *    tags/names/colours, cold/warm/gym tweaks — see `occasion-scoring.ts`).
 *
 * Final score is rounded to **one decimal** for display stability only.
 *
 * ## Bands (user-facing, no fake precision)
 * Raw score is mapped to **Strong / Solid / Okay / Mixed** using fixed thresholds
 * (`SCORE_BAND_*`). Labels explicitly say **rule-based** in the UI.
 */
import type { ClothingCategory, ClothingItem } from "@/features/wardrobe/types/clothing-item";

import { formatCategoryLabel } from "@/features/wardrobe/lib/format-category";
import { aggregateColourHarmony } from "./colour-heuristic";
import {
  OUTFIT_OCCASION_LABELS,
  type OutfitOccasion,
} from "./occasion-presets";
import { itemOccasionAffinity, occasionPiecesModifier } from "./occasion-scoring";
import type {
  GeneratedOutfitExplanation,
  OutfitSuggestionScoreBand,
} from "./types";
import { tagCohesionHints, tagCohesionWeight } from "./tag-heuristic";

/** Tunable band cutoffs on raw internal score (see module doc above). */
export const SCORE_BAND_STRONG_MIN = 135;
export const SCORE_BAND_SOLID_MIN = 118;
export const SCORE_BAND_OKAY_MIN = 100;

export const SUGGESTION_SCORING_VERSION = 1 as const;

export function rawScoreToBand(score: number): OutfitSuggestionScoreBand {
  if (score >= SCORE_BAND_STRONG_MIN) return "strong";
  if (score >= SCORE_BAND_SOLID_MIN) return "solid";
  if (score >= SCORE_BAND_OKAY_MIN) return "okay";
  return "mixed";
}

function bandPresentation(
  band: OutfitSuggestionScoreBand,
): { bandLabel: string; summaryLine: string } {
  switch (band) {
    case "strong":
      return {
        bandLabel: "Strong match (rules)",
        summaryLine:
          "Several rule checks line up well — colours, categories, occasion cues, or completeness.",
      };
    case "solid":
      return {
        bandLabel: "Solid match (rules)",
        summaryLine:
          "A reasonable mix by our fixed rules; still worth your eye in the mirror.",
      };
    case "okay":
      return {
        bandLabel: "Okay match (rules)",
        summaryLine:
          "Passes templates but some signals are average — tags or occasion fit may be thin.",
      };
    case "mixed":
      return {
        bandLabel: "Mixed (rules)",
        summaryLine:
          "We still suggest it, but scores are lower — contrasting colours, sparse tags, or weak occasion keywords.",
      };
  }
}

function buildExplanationSections(
  pieces: readonly ClothingItem[],
  occasion: OutfitOccasion,
  harmony: number,
  cats: Set<ClothingCategory>,
  occasionScoreDelta: number,
): GeneratedOutfitExplanation["sections"] {
  const occLabel = OUTFIT_OCCASION_LABELS[occasion];
  const affinities = pieces.map((p) => itemOccasionAffinity(p, occasion));
  const avgAff =
    affinities.reduce((a, b) => a + b, 0) / Math.max(affinities.length, 1);

  const templateBullets: string[] = [];
  const hasDress = cats.has("dresses");
  if (hasDress) {
    templateBullets.push(
      "Uses the dress + shoes pattern first; an accessory is added only if it bumps the score.",
    );
  } else if (cats.has("tops") && cats.has("bottoms")) {
    templateBullets.push(
      "Uses top + bottom, then adds shoes, outerwear, or an accessory only when each step improves the rule score.",
    );
  } else {
    templateBullets.push("Built from valid category slots in your wardrobe.");
  }

  const colourBullets: string[] = [];
  if (harmony >= 2.35) {
    colourBullets.push(
      "Colour labels read as compatible under simple keyword families (not photo analysis).",
    );
  } else if (harmony < 1.85) {
    colourBullets.push(
      "Colours are high-contrast in our text heuristic — fine if intentional, easy to swap one piece.",
    );
  } else {
    colourBullets.push(
      "Colour mix is middle-of-the-road in our keyword-based harmony check.",
    );
  }

  const categoryList = [...cats].sort();
  const categoryBullets = [
    `Categories included: ${categoryList.map((c) => formatCategoryLabel(c)).join(", ")}.`,
  ];
  if (cats.has("shoes") && (cats.has("bottoms") || cats.has("dresses"))) {
    categoryBullets.push(
      "Has footwear plus a lower layer or dress — we reward that as a more complete outfit.",
    );
  }
  if (cats.has("outerwear") && cats.has("tops")) {
    categoryBullets.push("Outerwear + top layering is present.");
  }

  const occasionBullets: string[] = [
    `Occasion preset: ${occLabel} (drives keyword boosts and item ordering).`,
  ];
  if (avgAff >= 14) {
    occasionBullets.push(
      "Item names/tags lean toward this occasion in our keyword lists.",
    );
  } else if (avgAff < 6) {
    occasionBullets.push(
      "Weak keyword link to this occasion — add tags like gym, office, or casual to items to sharpen this.",
    );
  } else {
    occasionBullets.push("Occasion fit is moderate from text cues on your pieces.");
  }
  if (Math.abs(occasionScoreDelta) >= 12) {
    occasionBullets.push(
      `Occasion rules moved the raw score by about ${occasionScoreDelta > 0 ? "+" : ""}${Math.round(occasionScoreDelta)} points (see suggestion-scoring.ts).`,
    );
  }

  return [
    { heading: "Why these pieces", bullets: templateBullets },
    { heading: "Colours (text heuristics)", bullets: colourBullets },
    { heading: "Categories & balance", bullets: categoryBullets },
    { heading: "Occasion fit", bullets: occasionBullets },
  ];
}

export type SuggestionScoringResult = {
  score: number;
  hints: string[];
  explanation: GeneratedOutfitExplanation;
};

/**
 * Compute sort score, compact hints (legacy / feedback), and structured explanation.
 */
export function computeSuggestionScoring(
  pieces: ClothingItem[],
  occasion: OutfitOccasion,
): SuggestionScoringResult {
  const harmony = aggregateColourHarmony(pieces.map((p) => p.colour));
  let score = 40;
  score += harmony * 14;
  score += tagCohesionWeight(pieces) * 4;

  const cats = new Set(pieces.map((p) => p.category));
  const hasShoes = cats.has("shoes");
  const hasBottomOrDress = cats.has("bottoms") || cats.has("dresses");
  if (hasShoes && hasBottomOrDress) score += 18;
  if (cats.has("outerwear") && cats.has("tops")) score += 12;

  const tagsOnlyWeight = tagCohesionWeight(pieces);

  const catVariety = cats.size;
  score += Math.min(catVariety * 2.5, 10);
  if (pieces.length >= 4) score += 6;
  if (pieces.length > 5) score -= 10;

  const occMod = occasionPiecesModifier(pieces, occasion);
  const occasionScoreDelta = occMod.scoreDelta;
  score += occasionScoreDelta;

  const rounded = Math.round(score * 10) / 10;

  const hints: string[] = [
    `Occasion: ${OUTFIT_OCCASION_LABELS[occasion]}`,
  ];
  if (harmony >= 2.35) {
    hints.push("Colour mix looks easy to wear together (heuristic).");
  } else if (harmony < 1.85) {
    hints.push("High-contrast colours — swap one piece if it feels loud.");
  }
  hints.push(...tagCohesionHints(pieces));
  if (hasShoes && hasBottomOrDress) hints.push("Includes shoes for a complete outfit.");
  if (cats.has("outerwear")) hints.push("Layered with outerwear.");
  hints.push(...occMod.hints);
  if (hints.length < 3) {
    hints.push("Built from category rules plus your occasion choice.");
  }

  const uniq: string[] = [];
  const seen = new Set<string>();
  for (const h of hints) {
    if (seen.has(h)) continue;
    seen.add(h);
    uniq.push(h);
  }

  const band = rawScoreToBand(rounded);
  const { bandLabel, summaryLine } = bandPresentation(band);

  const explanation: GeneratedOutfitExplanation = {
    scoringVersion: SUGGESTION_SCORING_VERSION,
    band,
    bandLabel,
    summaryLine,
    pointsDisclaimer:
      `Internal sort points: ${rounded} — used only to order suggestions in this app, not a guarantee of how it will look or feel on you.`,
    sections: buildExplanationSections(
      pieces,
      occasion,
      harmony,
      cats,
      occasionScoreDelta,
    ),
    formulaNote: `Colour avg harmony ×14 (${harmony.toFixed(2)}), tags ×4 (${tagsOnlyWeight.toFixed(1)}), +completeness/layers/variety, +occasion delta (${occasionScoreDelta > 0 ? "+" : ""}${Math.round(occasionScoreDelta * 10) / 10}). Base +40.`,
  };

  return {
    score: rounded,
    hints: uniq.slice(0, 10),
    explanation,
  };
}
