import type { PublishedOutfit } from "@/features/discover/types/published-outfit";

/** Single place for Discover card/detail “by …” text. */
export function publishedOutfitAuthorLabel(post: PublishedOutfit): string {
  const t = post.authorDisplayName.trim();
  if (t.length > 0) return t;
  const compact = post.authorUserId.replace(/-/g, "");
  return `Member ${compact.slice(0, 8)}`;
}
