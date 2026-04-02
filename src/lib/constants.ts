/**
 * App-wide constants (not visual tokens). Use `theme` for colours, spacing, etc.
 */

export const APP_NAME = "Closy";

/** Layout numbers shared across features (FAB, list shells, …). */
export const layout = {
  fabSize: 56,
  wardrobeEmptyMinHeight: 360,
} as const;

/** Media placeholders until uploads and CDN paths are unified. */
export const media = {
  cardAspect: 3 / 4,
  detailHeroAspect: 4 / 5,
  imageTransitionMs: {
    card: 120,
    detail: 180,
  },
} as const;

const MOCK_PICSUM_W = 600;
const MOCK_PICSUM_H = 800;

/** Stable placeholder images for mock wardrobe data. */
export function mockPicsumImageUrl(seed: string): string {
  return `https://picsum.photos/seed/${encodeURIComponent(seed)}/${MOCK_PICSUM_W}/${MOCK_PICSUM_H}`;
}
