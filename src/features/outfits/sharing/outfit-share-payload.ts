import type { Outfit } from "@/features/outfits/types/outfit";
import { formatCategoryLabel } from "@/features/wardrobe/lib/format-category";
import type { ClothingItem } from "@/features/wardrobe/types/clothing-item";

/** Increment when the share JSON/text shape changes so future APIs can migrate. */
export const OUTFIT_SHARE_SCHEMA_VERSION = 1 as const;

/**
 * One row in an outfit share — stable for logs, future deep links, and social posts.
 */
export type OutfitShareLineItem = {
  clothingItemId: string;
  /** Human-readable title for the piece or a fallback when missing. */
  label: string;
  categoryLabel: string;
  missingFromWardrobe: boolean;
};

/**
 * Serializable outfit summary for Share sheet, exports, and a future social graph.
 */
export type OutfitSharePayload = {
  schemaVersion: typeof OUTFIT_SHARE_SCHEMA_VERSION;
  outfitId: string;
  outfitName: string;
  generatedAtIso: string;
  lines: OutfitShareLineItem[];
};

export type ResolvedOutfitPiece = {
  id: string;
  item: ClothingItem | null | undefined;
};

export function buildOutfitSharePayload(
  outfit: Outfit,
  resolved: readonly ResolvedOutfitPiece[],
): OutfitSharePayload {
  const lines: OutfitShareLineItem[] = resolved.map(({ id, item }) => {
    if (item == null) {
      return {
        clothingItemId: id,
        label: "Removed from wardrobe",
        categoryLabel: "—",
        missingFromWardrobe: true,
      };
    }
    const name = item.name.trim() || "Untitled piece";
    return {
      clothingItemId: id,
      label: name,
      categoryLabel: formatCategoryLabel(item.category),
      missingFromWardrobe: false,
    };
  });

  return {
    schemaVersion: OUTFIT_SHARE_SCHEMA_VERSION,
    outfitId: outfit.id,
    outfitName: outfit.name.trim() || "Untitled outfit",
    generatedAtIso: new Date().toISOString(),
    lines,
  };
}

/** Copy-friendly plain text for the OS share sheet and messaging apps. */
export function outfitSharePlainText(payload: OutfitSharePayload): string {
  const title = `Closy — ${payload.outfitName}`;
  const pieceLines = payload.lines.map((line) => {
    if (line.missingFromWardrobe) {
      return `• ${line.label} (id: ${line.clothingItemId.slice(0, 8)}…)`;
    }
    return `• ${line.label} (${line.categoryLabel})`;
  });

  return [
    title,
    "",
    `${payload.lines.length} piece${payload.lines.length === 1 ? "" : "s"}:`,
    ...pieceLines,
    "",
    "— Shared from Closy",
  ].join("\n");
}

/**
 * Compact JSON for a future “share link” / activity API without changing call sites.
 */
export function outfitShareToJson(payload: OutfitSharePayload): string {
  return JSON.stringify(payload, null, 0);
}
