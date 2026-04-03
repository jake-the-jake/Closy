import type { Outfit } from "@/features/outfits/types/outfit";
import type { ResolvedOutfitPiece } from "@/features/outfits/sharing/outfit-share-payload";
import { clothingItemDisplayUri } from "@/features/wardrobe/lib/clothing-item-images";
import { formatCategoryLabel } from "@/features/wardrobe/lib/format-category";
import { persistableImageUrlForCloud } from "@/features/wardrobe/lib/cloud-wardrobe";
import {
  PUBLISHED_OUTFIT_SNAPSHOT_VERSION,
  type PublishedOutfitSnapshot,
  type PublishedOutfitSnapshotLine,
} from "@/features/discover/types/published-outfit";

function lineFromResolved(
  id: string,
  item: ResolvedOutfitPiece["item"],
): PublishedOutfitSnapshotLine {
  if (item == null) {
    return {
      clothingItemId: id,
      label: "Removed from wardrobe",
      categoryLabel: "—",
      imageUrl: "",
      missingFromWardrobe: true,
    };
  }
  const name = item.name.trim() || "Untitled piece";
  const remote = persistableImageUrlForCloud(clothingItemDisplayUri(item));
  return {
    clothingItemId: id,
    label: name,
    categoryLabel: formatCategoryLabel(item.category),
    imageUrl: remote,
    missingFromWardrobe: false,
  };
}

export function buildPublishedOutfitSnapshot(
  outfit: Outfit,
  resolved: readonly ResolvedOutfitPiece[],
): PublishedOutfitSnapshot {
  const lines = resolved.map(({ id, item }) => lineFromResolved(id, item));
  return {
    schemaVersion: PUBLISHED_OUTFIT_SNAPSHOT_VERSION,
    sourceOutfitId: outfit.id,
    outfitName: outfit.name.trim() || "Untitled outfit",
    generatedAtIso: new Date().toISOString(),
    lines,
  };
}
