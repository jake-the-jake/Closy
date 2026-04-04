import type { ClothingItem } from "@/features/wardrobe/types/clothing-item";

const OCCASION_HINTS = [
  "casual",
  "work",
  "office",
  "formal",
  "party",
  "wedding",
  "sport",
  "evening",
  "weekend",
  "date",
  "vacation",
  "travel",
  "beach",
] as const;

function normalizedTags(item: ClothingItem): Set<string> {
  const s = new Set<string>();
  for (const t of item.tags) {
    const x = t.trim().toLowerCase();
    if (x.length > 0) s.add(x);
  }
  return s;
}

/**
 * Returns ~0–6+ bonus weight: shared concrete tags and “occasion” vocabulary overlap.
 */
export function tagCohesionWeight(items: readonly ClothingItem[]): number {
  if (items.length < 2) return 0;
  const sets = items.map(normalizedTags);
  if (sets.every((x) => x.size === 0)) return 0;

  let weight = 0;
  const freq = new Map<string, number>();
  for (const st of sets) {
    for (const t of st) {
      freq.set(t, (freq.get(t) ?? 0) + 1);
    }
  }

  for (const [word, c] of freq) {
    if (c < 2) continue;
    const isOccasion = OCCASION_HINTS.some((h) => word.includes(h) || h === word);
    weight += isOccasion ? 2.2 : 1.2;
  }

  return Math.min(weight, 8);
}

export function tagCohesionHints(items: readonly ClothingItem[]): string[] {
  const freq = new Map<string, number>();
  for (const item of items) {
    for (const t of normalizedTags(item)) {
      freq.set(t, (freq.get(t) ?? 0) + 1);
    }
  }
  const shared = [...freq.entries()]
    .filter(([, c]) => c >= 2)
    .map(([w]) => w)
    .slice(0, 3);
  if (shared.length === 0) return [];
  return [
    `Shared tags: ${shared.join(", ")}`,
  ];
}
