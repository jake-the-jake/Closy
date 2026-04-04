/**
 * First-pass **closet gap** heuristics: category counts and simple keyword checks only.
 * Not a stylist, not complete coverage — intentionally conservative labels in UI copy.
 */
import type { ClothingCategory, ClothingItem } from "@/features/wardrobe/types/clothing-item";
import { CLOTHING_CATEGORIES } from "@/features/wardrobe/types/clothing-item";

import type {
  ClosetCategoryCounts,
  ClosetGapInsight,
  ClosetGapReport,
} from "./closet-gap-types";

const INSIGHT_ORDER: readonly string[] = [
  "gap-no-shoes",
  "gap-no-lower-body",
  "gap-no-upper-with-bottoms",
  "gap-bottoms-vs-tops",
  "gap-no-outerwear",
  "gap-formal-shoes-heuristic",
  "gap-one-pair-shoes",
  "gap-no-accessories",
  "gap-weak-dress-option",
];

function emptyCounts(): ClosetCategoryCounts {
  const c = {} as Record<ClothingCategory, number>;
  for (const cat of CLOTHING_CATEGORIES) c[cat] = 0;
  return c;
}

function countByCategory(items: readonly ClothingItem[]): ClosetCategoryCounts {
  const c = emptyCounts();
  for (const item of items) {
    c[item.category] = (c[item.category] ?? 0) + 1;
  }
  return c;
}

function shoeHaystack(item: ClothingItem): string {
  return [item.name, item.colour, item.brand, ...item.tags]
    .join(" ")
    .trim()
    .toLowerCase();
}

/** Dressier footwear cue from text only — many real shoes won’t match; we under-claim in UI. */
function looksDressierShoe(item: ClothingItem): boolean {
  if (item.category !== "shoes") return false;
  const h = shoeHaystack(item);
  if (
    /sneaker|trainer|run|running|athletic|sport|basket|cleat|flip-flop|flipflop|slide|pool|crocs/i.test(
      h,
    )
  ) {
    return false;
  }
  if (/hiking|trail|snow boot|work boot/i.test(h)) return false;
  return /oxford|loafer|brogue|heel|pump|stiletto|ankle boot|dress shoe|ballet|mary jane|mule|derby|monk|chelsea|boot/i.test(
    h,
  );
}

/**
 * Returns sorted, deduped insights for the current wardrobe list.
 */
export function analyzeClosetGaps(
  items: readonly ClothingItem[],
): ClosetGapReport {
  const totalPieces = items.length;
  const counts = countByCategory(items);
  const shoes = counts.shoes;
  const tops = counts.tops;
  const bottoms = counts.bottoms;
  const dresses = counts.dresses;
  const outerwear = counts.outerwear;
  const accessories = counts.accessories;

  const insights: ClosetGapInsight[] = [];
  const push = (ins: ClosetGapInsight) => insights.push(ins);

  if (totalPieces === 0) {
    return {
      totalPieces: 0,
      counts,
      insights: [],
      balanceNote: null,
    };
  }

  if (shoes === 0) {
    push({
      id: "gap-no-shoes",
      kind: "missing_category",
      title: "No shoes logged",
      detail:
        "We don’t see any shoes yet—most outfits need at least one pair (any style).",
    });
  }

  const hasLower = bottoms > 0 || dresses > 0;
  if (!hasLower && tops > 0) {
    push({
      id: "gap-no-lower-body",
      kind: "missing_category",
      title: "No bottoms or dresses",
      detail:
        "You have tops but no bottoms or dresses recorded—add a lower layer or a dress to build looks.",
    });
  }

  if (bottoms > 0 && tops === 0 && dresses === 0) {
    push({
      id: "gap-no-upper-with-bottoms",
      kind: "missing_category",
      title: "No tops or dresses with bottoms",
      detail:
        "Bottoms need something above—tops or a dress that pairs with them.",
    });
  }

  if (tops >= 4 && bottoms < 2) {
    push({
      id: "gap-bottoms-vs-tops",
      kind: "imbalance",
      title: "Few bottoms vs tops",
      detail:
        "Several tops but only one (or zero) bottom type—extra jeans, trousers, or skirts make mixing easier.",
    });
  }

  if (
    outerwear === 0 &&
    tops + dresses >= 2 &&
    totalPieces >= 4
  ) {
    push({
      id: "gap-no-outerwear",
      kind: "missing_category",
      title: "No outerwear",
      detail:
        "No jacket or coat saved—layers help for weather and dressing outfits up/down.",
    });
  }

  if (shoes >= 1) {
    const shoeItems = items.filter((i) => i.category === "shoes");
    const anyDressy = shoeItems.some(looksDressierShoe);
    if (!anyDressy) {
      push({
        id: "gap-formal-shoes-heuristic",
        kind: "keyword_heuristic",
        title: "No dressier shoes detected (quick text check)",
        detail:
          "Names/tags look casual or athletic only. If you dress up sometimes, add loafers, heels, or plain leather shoes—the app isn’t judging photos.",
      });
    }
  }

  if (shoes === 1 && totalPieces >= 8) {
    push({
      id: "gap-one-pair-shoes",
      kind: "variety",
      title: "Only one pair of shoes in a bigger closet",
      detail:
        "With many pieces, a second pair (different colour or formality) often unlocks more outfits.",
    });
  }

  if (accessories === 0 && totalPieces >= 6) {
    push({
      id: "gap-no-accessories",
      kind: "low_count",
      title: "No accessories saved",
      detail:
        "Optional: belts, bags, scarves, or jewellery aren’t required but finish looks.",
    });
  }

  if (dresses === 0 && hasLower && tops >= 2) {
    push({
      id: "gap-weak-dress-option",
      kind: "low_count",
      title: "No dress for one-piece looks",
      detail:
        "Everything is separates so far—a dress can simplify planning when you want it.",
    });
  }

  const orderIndex = (id: string) => {
    const i = INSIGHT_ORDER.indexOf(id);
    return i === -1 ? 999 : i;
  };
  insights.sort((a, b) => orderIndex(a.id) - orderIndex(b.id));

  const balanceNote =
    insights.length === 0
      ? "On these simple category checks, nothing obvious is missing—still shop for what you love, not just gaps a counter finds."
      : null;

  return {
    totalPieces,
    counts,
    insights,
    balanceNote,
  };
}
