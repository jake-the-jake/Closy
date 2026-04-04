import type { Outfit } from "@/features/outfits/types/outfit";
import type { ClothingCategory, ClothingItem } from "@/features/wardrobe/types/clothing-item";
import { normalizedItemSetKey } from "@/features/wardrobe-intelligence/simple-suggestions";

import {
  OUTFIT_OCCASION_LABELS,
  type OutfitOccasion,
} from "./occasion-presets";
import { itemOccasionAffinity } from "./occasion-scoring";
import { computeSuggestionScoring } from "./suggestion-scoring";
import type { GeneratedOutfitSuggestion, GenerateOutfitsOptions } from "./types";

function compareItemsByDisplayName(a: ClothingItem, b: ClothingItem): number {
  const an = (a.name.trim().toLowerCase() || a.id) as string;
  const bn = (b.name.trim().toLowerCase() || b.id) as string;
  if (an !== bn) return an < bn ? -1 : 1;
  return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
}

function bucketByCategory(
  items: readonly ClothingItem[],
): Map<ClothingCategory, ClothingItem[]> {
  const m = new Map<ClothingCategory, ClothingItem[]>();
  for (const item of items) {
    const list = m.get(item.category);
    if (list == null) m.set(item.category, [item]);
    else list.push(item);
  }
  for (const list of m.values()) list.sort(compareItemsByDisplayName);
  return m;
}

function sortBucketForOccasion(
  items: ClothingItem[],
  occasion: OutfitOccasion,
): ClothingItem[] {
  return [...items].sort((a, b) => {
    const d =
      itemOccasionAffinity(b, occasion) - itemOccasionAffinity(a, occasion);
    if (d !== 0) return d;
    return compareItemsByDisplayName(a, b);
  });
}

function pickBestAddition(
  base: ClothingItem[],
  candidates: readonly ClothingItem[],
  occasion: OutfitOccasion,
): ClothingItem | null {
  if (candidates.length === 0) return null;
  let best: ClothingItem | null = null;
  let bestDelta = -Infinity;
  const baseScore = computeSuggestionScoring(base, occasion).score;
  for (const c of candidates) {
    const next = [...base, c];
    const nextScore = computeSuggestionScoring(next, occasion).score;
    const delta = nextScore - baseScore;
    if (delta > bestDelta) {
      bestDelta = delta;
      best = c;
    }
  }
  if (best == null || bestDelta < 0.5) return null;
  return best;
}

function suggestedTitle(pieces: ClothingItem[], occasion: OutfitOccasion): string {
  const label = OUTFIT_OCCASION_LABELS[occasion];
  const dress = pieces.find((p) => p.category === "dresses");
  const top = pieces.find((p) => p.category === "tops");
  const anchor = dress ?? top ?? pieces[0]!;
  const words = anchor.colour.trim().split(/\s+/).filter(Boolean);
  const chip = words.slice(0, 2).join(" ");
  const cap =
    chip.length > 0
      ? chip.charAt(0).toUpperCase() + chip.slice(1).toLowerCase()
      : "Wardrobe";
  const base = dress != null ? `${cap} dress outfit` : `${cap} layered outfit`;
  return `${label} · ${base}`;
}

type RawCandidate = {
  pieces: ClothingItem[];
};

function expandDressOutfits(
  dresses: readonly ClothingItem[],
  shoes: readonly ClothingItem[],
  accessories: readonly ClothingItem[],
  occasion: OutfitOccasion,
  maxRaw: number,
  out: RawCandidate[],
): void {
  for (const dress of dresses) {
    for (const shoe of shoes) {
      if (out.length >= maxRaw) return;
      const base: ClothingItem[] = [dress, shoe];
      const extra = pickBestAddition(base, accessories, occasion);
      out.push({ pieces: extra ? [...base, extra] : base });
    }
  }
}

function expandLayeredOutfits(
  tops: readonly ClothingItem[],
  bottoms: readonly ClothingItem[],
  shoes: readonly ClothingItem[],
  outerwear: readonly ClothingItem[],
  accessories: readonly ClothingItem[],
  occasion: OutfitOccasion,
  maxRaw: number,
  out: RawCandidate[],
): void {
  for (const top of tops) {
    for (const bottom of bottoms) {
      if (out.length >= maxRaw) return;
      let pieces: ClothingItem[] = [top, bottom];
      if (shoes.length > 0) {
        const shoe = pickBestAddition(pieces, shoes, occasion);
        if (shoe) pieces = [...pieces, shoe];
      }
      if (outerwear.length > 0) {
        const ow = pickBestAddition(pieces, outerwear, occasion);
        if (ow) pieces = [...pieces, ow];
      }
      if (accessories.length > 0) {
        const acc = pickBestAddition(pieces, accessories, occasion);
        if (acc) pieces = [...pieces, acc];
      }
      out.push({ pieces });
    }
  }
}

/**
 * Generates ranked outfit suggestions using **only** on-device rules:
 * valid category templates, colour harmony, tag overlap, occasion keywords,
 * and completeness bonuses.
 */
export function generateRankedOutfitSuggestions(
  items: readonly ClothingItem[],
  existingOutfits: readonly Outfit[],
  options?: GenerateOutfitsOptions,
): GeneratedOutfitSuggestion[] {
  const occasion: OutfitOccasion = options?.occasion ?? "casual";
  const maxRaw = options?.maxRawCandidates ?? 140;
  const maxResults = options?.maxResults ?? 24;
  const skipExisting = options?.skipExistingExact ?? true;

  const existing = skipExisting
    ? new Set(existingOutfits.map((o) => normalizedItemSetKey(o.clothingItemIds)))
    : new Set<string>();

  const buckets = bucketByCategory(items);
  const dresses = sortBucketForOccasion(
    buckets.get("dresses") ?? [],
    occasion,
  );
  const shoes = sortBucketForOccasion(buckets.get("shoes") ?? [], occasion);
  const tops = sortBucketForOccasion(buckets.get("tops") ?? [], occasion);
  const bottoms = sortBucketForOccasion(
    buckets.get("bottoms") ?? [],
    occasion,
  );
  const outerwear = sortBucketForOccasion(
    buckets.get("outerwear") ?? [],
    occasion,
  );
  const accessories = sortBucketForOccasion(
    buckets.get("accessories") ?? [],
    occasion,
  );

  const raw: RawCandidate[] = [];
  const dressBudget = Math.ceil(maxRaw / 2);

  if (dresses.length > 0 && shoes.length > 0) {
    expandDressOutfits(
      dresses,
      shoes,
      accessories,
      occasion,
      dressBudget,
      raw,
    );
  }
  if (tops.length > 0 && bottoms.length > 0) {
    expandLayeredOutfits(
      tops,
      bottoms,
      shoes,
      outerwear,
      accessories,
      occasion,
      maxRaw,
      raw,
    );
  }

  const seen = new Set<string>();
  const scored: GeneratedOutfitSuggestion[] = [];

  for (const { pieces } of raw) {
    const setKey = normalizedItemSetKey(pieces.map((p) => p.id));
    if (existing.has(setKey)) continue;
    const compositeId = `${occasion}\u0001${setKey}`;
    if (seen.has(compositeId)) continue;
    seen.add(compositeId);
    const { score, hints, explanation } = computeSuggestionScoring(
      pieces,
      occasion,
    );
    scored.push({
      id: compositeId,
      occasion,
      suggestedName: suggestedTitle(pieces, occasion),
      clothingItemIds: pieces.map((p) => p.id),
      hints,
      score,
      explanation,
      categoriesUsed: [...new Set(pieces.map((p) => p.category))],
    });
  }

  scored.sort((a, b) =>
    b.score !== a.score ? b.score - a.score : a.id.localeCompare(b.id),
  );
  return scored.slice(0, maxResults);
}
