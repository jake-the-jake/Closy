import type { ClothingCategory } from "@/features/wardrobe/types/clothing-item";

export type ClosetGapKind =
  | "missing_category"
  | "low_count"
  | "imbalance"
  | "keyword_heuristic"
  | "variety";

/**
 * One deterministic gap line. Copy stays humble — counts and heuristics only.
 */
export type ClosetGapInsight = {
  id: string;
  kind: ClosetGapKind;
  title: string;
  detail: string;
};

export type ClosetCategoryCounts = Record<ClothingCategory, number>;

export type ClosetGapReport = {
  totalPieces: number;
  counts: ClosetCategoryCounts;
  insights: readonly ClosetGapInsight[];
  /** When non-empty, closet looks roughly balanced on these crude checks. */
  balanceNote: string | null;
};
