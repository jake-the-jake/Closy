/**
 * Supabase Storage uploads for wardrobe item photos (public bucket, stable URLs).
 */
import type { SupabaseClient } from "@supabase/supabase-js";

/** Must match `supabase/migrations/*_wardrobe_images_storage.sql` bucket id. */
export const WARDROBE_IMAGES_BUCKET = "wardrobe-images";

const PUBLIC_SEGMENT = `/object/public/${WARDROBE_IMAGES_BUCKET}/`;

export type WardrobeImageUploadResult =
  | { ok: true; publicUrl: string }
  | { ok: false; errorMessage: string };

function extensionForMime(contentType: string): string {
  const t = contentType.toLowerCase().split(";")[0]?.trim() ?? "";
  if (t === "image/png") return "png";
  if (t === "image/webp") return "webp";
  if (t === "image/gif") return "gif";
  return "jpg";
}

/** New UUID for a cloud `wardrobe_items` row (upload path uses the same id as the row). */
export function newCloudWardrobeRowId(): string {
  const c = globalThis.crypto;
  if (c && typeof c.randomUUID === "function") {
    return c.randomUUID();
  }
  throw new Error("crypto.randomUUID is not available in this runtime");
}

/**
 * Object path inside the bucket, e.g. `{userId}/{itemId}.jpg`.
 * Returns null if the URL is not a public URL for this bucket (safe for arbitrary URLs).
 */
export function tryParseWardrobeImageStoragePath(publicUrl: string): string | null {
  const i = publicUrl.indexOf(PUBLIC_SEGMENT);
  if (i === -1) return null;
  return publicUrl.slice(i + PUBLIC_SEGMENT.length).split("?")[0] ?? null;
}

export function isWardrobeImagePublicObjectUrl(url: string): boolean {
  return tryParseWardrobeImageStoragePath(url) != null;
}

/**
 * Read a picked image (native `file://` / `content://`, web `blob:`) and upload.
 */
export async function uploadWardrobeItemImage(
  client: SupabaseClient,
  userId: string,
  itemId: string,
  localUri: string,
): Promise<WardrobeImageUploadResult> {
  const uri = localUri.trim();
  if (!uri) {
    return { ok: false, errorMessage: "Missing image URI" };
  }

  try {
    const res = await fetch(uri);
    if (!res.ok) {
      return {
        ok: false,
        errorMessage: `Could not read image (HTTP ${res.status})`,
      };
    }
    const blob = await res.blob();
    const rawType = blob.type?.trim() ?? "";
    const contentType =
      rawType && rawType !== "application/octet-stream" ? rawType : "image/jpeg";
    const ext = extensionForMime(contentType);
    const path = `${userId}/${itemId}.${ext}`;

    const { error } = await client.storage
      .from(WARDROBE_IMAGES_BUCKET)
      .upload(path, blob, { contentType, upsert: true });

    if (error) {
      return { ok: false, errorMessage: error.message };
    }

    const { data } = client.storage.from(WARDROBE_IMAGES_BUCKET).getPublicUrl(path);
    return { ok: true, publicUrl: data.publicUrl };
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Unknown error";
    return { ok: false, errorMessage: msg };
  }
}

export async function deleteWardrobeItemImageByPublicUrl(
  client: SupabaseClient,
  publicUrl: string,
): Promise<void> {
  const path = tryParseWardrobeImageStoragePath(publicUrl);
  if (!path) return;
  const { error } = await client.storage.from(WARDROBE_IMAGES_BUCKET).remove([path]);
  if (error) {
    console.warn("[Closy] Wardrobe storage delete failed:", error.message);
  }
}
