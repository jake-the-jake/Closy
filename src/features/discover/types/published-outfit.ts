/**
 * Frozen snapshot for a Discover post. Wardrobe edits after publish do not change this object.
 */
export const PUBLISHED_OUTFIT_SNAPSHOT_VERSION = 1 as const;

export type PublishedOutfitSnapshotLine = {
  clothingItemId: string;
  label: string;
  categoryLabel: string;
  /** Stable remote URL or empty (e.g. no photo or non-persistable URI at publish time). */
  imageUrl: string;
  missingFromWardrobe: boolean;
};

export type PublishedOutfitSnapshot = {
  schemaVersion: typeof PUBLISHED_OUTFIT_SNAPSHOT_VERSION;
  sourceOutfitId: string;
  outfitName: string;
  generatedAtIso: string;
  lines: PublishedOutfitSnapshotLine[];
};

export type PublishedOutfit = {
  id: string;
  authorUserId: string;
  /**
   * Resolved for display: `profiles.display_name` when set, else denormalized
   * `author_display_name` from the post row. Use `publishedOutfitAuthorLabel` for UI.
   */
  authorDisplayName: string;
  /** From `profiles.avatar_url` when present; null if no profile photo. */
  authorAvatarUrl: string | null;
  sourceOutfitId: string;
  name: string;
  pieceCount: number;
  snapshot: PublishedOutfitSnapshot;
  publishedAt: number;
  /** Total likes (all users). */
  likeCount: number;
  /** Current session user has liked this post (false when signed out). */
  likedByMe: boolean;
};

function isSnapshotLine(v: unknown): v is PublishedOutfitSnapshotLine {
  if (!v || typeof v !== "object" || Array.isArray(v)) return false;
  const o = v as Record<string, unknown>;
  return (
    typeof o.clothingItemId === "string" &&
    typeof o.label === "string" &&
    typeof o.categoryLabel === "string" &&
    typeof o.imageUrl === "string" &&
    typeof o.missingFromWardrobe === "boolean"
  );
}

/** Best-effort parse for jsonb from Supabase; returns null if shape is wrong. */
export function parsePublishedOutfitSnapshot(
  raw: unknown,
): PublishedOutfitSnapshot | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const o = raw as Record<string, unknown>;
  if (o.schemaVersion !== PUBLISHED_OUTFIT_SNAPSHOT_VERSION) return null;
  if (
    typeof o.sourceOutfitId !== "string" ||
    typeof o.outfitName !== "string" ||
    typeof o.generatedAtIso !== "string" ||
    !Array.isArray(o.lines)
  ) {
    return null;
  }
  const lines = o.lines.filter(isSnapshotLine);
  if (lines.length !== o.lines.length) return null;
  return {
    schemaVersion: PUBLISHED_OUTFIT_SNAPSHOT_VERSION,
    sourceOutfitId: o.sourceOutfitId,
    outfitName: o.outfitName,
    generatedAtIso: o.generatedAtIso,
    lines,
  };
}
