/**
 * Comment on a Discover `published_outfits` row (flat list, oldest first in UI).
 */
export type PublishedOutfitComment = {
  id: string;
  publishedOutfitId: string;
  authorUserId: string;
  body: string;
  createdAt: number;
  updatedAt: number | null;
  /** From `profiles` when set; else empty until fallback label. */
  authorDisplayName: string;
  authorAvatarUrl: string | null;
};
