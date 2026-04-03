/**
 * Generates wardrobe image derivatives from the stored original:
 * - thumb.jpg — longest edge scaled to THUMB_PX, centered on white square canvas
 * - display.jpg — longest edge scaled to DISPLAY_MAX_PX (aspect preserved, no pad)
 * Original object is never modified.
 *
 * Deploy: `supabase functions deploy process-wardrobe-image --no-verify-jwt` is NOT used; keep verify_jwt.
 * Secrets: SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY (set automatically when linked).
 */
import "jsr:@supabase/functions-js/edge-runtime.d.ts";

import { createClient } from "npm:@supabase/supabase-js@2.49.8";
import sharp from "npm:sharp@0.33.5";

const BUCKET = "wardrobe-images";
const THUMB_PX = 320;
const DISPLAY_MAX_PX = 1080;
const MAX_ORIGINAL_BYTES = 15 * 1024 * 1024;

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
};

type ImageRefs = {
  original: string;
  thumbnail: string;
  display: string;
};

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...cors, "Content-Type": "application/json" },
  });
}

function publicUrl(
  supabaseUrl: string,
  path: string,
): string {
  const base = supabaseUrl.replace(/\/$/, "");
  return `${base}/storage/v1/object/public/${BUCKET}/${path}`;
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: cors });
  }

  const supabaseUrl = Deno.env.get("SUPABASE_URL") ?? "";
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
  const anonKey = Deno.env.get("SUPABASE_ANON_KEY") ?? "";

  if (!supabaseUrl || !serviceKey || !anonKey) {
    return json({ error: "Server misconfigured" }, 500);
  }

  if (req.method !== "POST") {
    return json({ error: "Method not allowed" }, 405);
  }

  const authHeader = req.headers.get("Authorization") ?? "";
  if (!authHeader.startsWith("Bearer ")) {
    return json({ error: "Missing authorization" }, 401);
  }

  const supabaseUser = createClient(supabaseUrl, anonKey, {
    global: { headers: { Authorization: authHeader } },
  });
  const {
    data: { user },
    error: userErr,
  } = await supabaseUser.auth.getUser();
  if (userErr || !user) {
    return json({ error: "Invalid session" }, 401);
  }

  const userId = user.id;
  let body: { itemId?: string };
  try {
    body = (await req.json()) as { itemId?: string };
  } catch {
    return json({ error: "Invalid JSON body" }, 400);
  }

  const itemId = typeof body.itemId === "string" ? body.itemId.trim() : "";
  if (!itemId || !UUID_RE.test(itemId)) {
    return json({ error: "itemId must be a UUID" }, 400);
  }

  const admin = createClient(supabaseUrl, serviceKey);

  const folderPath = `${userId}/${itemId}`;
  const { data: listed, error: listErr } = await admin.storage
    .from(BUCKET)
    .list(folderPath, { limit: 100 });

  if (listErr) {
    console.error(listErr);
    return json({ error: "Could not list storage folder" }, 500);
  }

  const originalEntry = (listed ?? []).find((f) =>
    /^original\.(jpe?g|png|webp|gif)$/i.test(f.name)
  );
  if (!originalEntry) {
    return json(
      { error: "No original image found. Upload the original first." },
      404,
    );
  }

  const originalPath = `${folderPath}/${originalEntry.name}`;

  const { data: blob, error: dlErr } = await admin.storage
    .from(BUCKET)
    .download(originalPath);

  if (dlErr || !blob) {
    console.error(dlErr);
    return json({ error: "Could not download original" }, 500);
  }

  const buf = new Uint8Array(await blob.arrayBuffer());
  if (buf.byteLength > MAX_ORIGINAL_BYTES) {
    return json(
      { error: `Image too large (max ${MAX_ORIGINAL_BYTES / 1024 / 1024} MB)` },
      413,
    );
  }

  try {
    await sharp(buf, { failOn: "none" }).rotate().metadata();
  } catch (e) {
    console.error(e);
    return json(
      {
        error:
          "Unsupported or corrupt image. Use JPEG, PNG, WebP, or GIF.",
      },
      400,
    );
  }

  const thumbPath = `${folderPath}/thumb.jpg`;
  const displayPath = `${folderPath}/display.jpg`;

  let thumbBytes: Uint8Array;
  let displayBytes: Uint8Array;
  try {
    const [t, d] = await Promise.all([
      sharp(buf, { failOn: "none" })
        .rotate()
        .resize(THUMB_PX, THUMB_PX, {
          fit: "contain",
          position: "centre",
          background: { r: 255, g: 255, b: 255, alpha: 1 },
          kernel: sharp.kernel.lanczos3,
        })
        .jpeg({ quality: 82, mozjpeg: true })
        .toBuffer(),
      sharp(buf, { failOn: "none" })
        .rotate()
        .resize(DISPLAY_MAX_PX, DISPLAY_MAX_PX, {
          fit: "inside",
          withoutEnlargement: true,
          kernel: sharp.kernel.lanczos3,
        })
        .jpeg({ quality: 86, mozjpeg: true })
        .toBuffer(),
    ]);
    thumbBytes = new Uint8Array(t);
    displayBytes = new Uint8Array(d);
  } catch (e) {
    console.error(e);
    return json({ error: "Image processing failed" }, 500);
  }

  const { error: upThumb } = await admin.storage.from(BUCKET).upload(
    thumbPath,
    thumbBytes,
    { contentType: "image/jpeg", upsert: true },
  );
  const { error: upDisp } = await admin.storage.from(BUCKET).upload(
    displayPath,
    displayBytes,
    { contentType: "image/jpeg", upsert: true },
  );

  if (upThumb || upDisp) {
    console.error(upThumb, upDisp);
    return json({ error: "Could not upload derivatives" }, 500);
  }

  const refs: ImageRefs = {
    original: publicUrl(supabaseUrl, originalPath),
    thumbnail: publicUrl(supabaseUrl, thumbPath),
    display: publicUrl(supabaseUrl, displayPath),
  };

  return json({ ok: true, imageRefs: refs });
});
