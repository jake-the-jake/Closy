/**
 * Supabase Storage uploads for wardrobe item photos (public bucket, stable URLs).
 * Layout per item: `{userId}/{itemId}/original.ext`, `thumb.jpg`, `display.jpg`.
 */
import type { SupabaseClient } from "@supabase/supabase-js";

import type { ClothingItemImageRefs } from "@/features/wardrobe/types/clothing-item";
import {
  WARDROBE_ALLOWED_UPLOAD_MIME_TYPES,
  WARDROBE_ORIGINAL_MAX_BYTES,
} from "@/features/wardrobe/lib/wardrobe-image-pipeline";

/** Must match `supabase/migrations/*_wardrobe_images_storage.sql` bucket id. */
export const WARDROBE_IMAGES_BUCKET = "wardrobe-images";

const PUBLIC_SEGMENT = `/object/public/${WARDROBE_IMAGES_BUCKET}/`;

export type WardrobeOriginalUploadResult =
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
 * Object path inside the bucket, e.g. `{userId}/{itemId}.jpg` (legacy)
 * or `{userId}/{itemId}/display.jpg`.
 */
export function tryParseWardrobeImageStoragePath(publicUrl: string): string | null {
  const i = publicUrl.indexOf(PUBLIC_SEGMENT);
  if (i === -1) return null;
  return publicUrl.slice(i + PUBLIC_SEGMENT.length).split("?")[0] ?? null;
}

export function isWardrobeImagePublicObjectUrl(url: string): boolean {
  return tryParseWardrobeImageStoragePath(url) != null;
}

function wardrobeItemFolderPrefix(userId: string, itemId: string): string {
  return `${userId}/${itemId}`;
}

/**
 * Deletes nested `{userId}/{itemId}/*` objects and a legacy flat `{userId}/{itemId}.ext` file if `legacyPrimaryPublicUrl` parses to one.
 */
export async function deleteAllWardrobeImagesForItem(
  client: SupabaseClient,
  userId: string,
  itemId: string,
  legacyPrimaryPublicUrl: string,
): Promise<void> {
  const folder = wardrobeItemFolderPrefix(userId, itemId);
  const { data: entries, error: listErr } = await client.storage
    .from(WARDROBE_IMAGES_BUCKET)
    .list(folder, { limit: 100 });
  if (listErr) {
    console.warn("[Closy] Wardrobe storage list failed:", listErr.message);
  } else if (entries?.length) {
    const paths = entries.map((e) => `${folder}/${e.name}`).filter(Boolean);
    if (paths.length > 0) {
      const { error } = await client.storage.from(WARDROBE_IMAGES_BUCKET).remove(paths);
      if (error) {
        console.warn("[Closy] Wardrobe storage remove folder failed:", error.message);
      }
    }
  }

  const legacyPath = tryParseWardrobeImageStoragePath(legacyPrimaryPublicUrl.trim());
  if (!legacyPath) return;
  if (legacyPath.startsWith(`${folder}/`)) return;
  const { error: legacyErr } = await client.storage
    .from(WARDROBE_IMAGES_BUCKET)
    .remove([legacyPath]);
  if (legacyErr) {
    console.warn("[Closy] Wardrobe legacy image delete failed:", legacyErr.message);
  }
}

/**
 * Read a picked image (native `file://` / `content://`, web `blob:`) and upload as **original** only.
 */
export async function uploadWardrobeItemOriginal(
  client: SupabaseClient,
  userId: string,
  itemId: string,
  localUri: string,
): Promise<WardrobeOriginalUploadResult> {
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
    if (blob.size > WARDROBE_ORIGINAL_MAX_BYTES) {
      return {
        ok: false,
        errorMessage: `Photo is too large (max ${WARDROBE_ORIGINAL_MAX_BYTES / 1024 / 1024} MB).`,
      };
    }
    const rawType = blob.type?.trim() ?? "";
    const contentType =
      rawType && rawType !== "application/octet-stream" ? rawType : "image/jpeg";
    if (!WARDROBE_ALLOWED_UPLOAD_MIME_TYPES.has(contentType.split(";")[0]?.trim() ?? "")) {
      return {
        ok: false,
        errorMessage: "Use a JPG, PNG, WebP, or GIF photo.",
      };
    }
    const ext = extensionForMime(contentType);
    const path = `${wardrobeItemFolderPrefix(userId, itemId)}/original.${ext}`;

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

export type ProcessWardrobeDerivativesResult =
  | { ok: true; imageRefs: ClothingItemImageRefs }
  | { ok: false; errorMessage: string };

/**
 * Invokes Edge Function `process-wardrobe-image` (requires deployed function + DB migration).
 */
export async function invokeProcessWardrobeDerivatives(
  client: SupabaseClient,
  itemId: string,
): Promise<ProcessWardrobeDerivativesResult> {
  const { data, error } = await client.functions.invoke("process-wardrobe-image", {
    body: { itemId },
  });
  if (error) {
    return { ok: false, errorMessage: error.message };
  }
  const d = data as {
    ok?: boolean;
    imageRefs?: ClothingItemImageRefs;
    error?: string;
  } | null;
  if (d && typeof d.error === "string" && d.error.length > 0) {
    return { ok: false, errorMessage: d.error };
  }
  if (
    d?.ok &&
    d.imageRefs &&
    d.imageRefs.original?.trim() &&
    d.imageRefs.display?.trim() &&
    d.imageRefs.thumbnail?.trim()
  ) {
    return { ok: true, imageRefs: d.imageRefs };
  }
  return { ok: false, errorMessage: "Unexpected response from image processor" };
}
