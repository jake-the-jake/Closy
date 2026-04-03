/**
 * Shared constants for wardrobe image uploads and Edge derivative generation.
 * Keep in sync with `supabase/functions/process-wardrobe-image/index.ts`.
 */
export const WARDROBE_ORIGINAL_MAX_BYTES = 15 * 1024 * 1024;

export const WARDROBE_ALLOWED_UPLOAD_MIME_TYPES = new Set([
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/gif",
]);
