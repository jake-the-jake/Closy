/**
 * Stable handoff between the Closy app and the native `avatar_export` tool.
 *
 * Contract (v1):
 * - Input:  one JSON file per render under `generated/avatar_requests/{renderId}.json`
 *          (same schema the engine accepts: pose, width, height, camera, items[]).
 * - Output: one PNG under `generated/avatar_renders/{renderId}.png`
 * - Invoke: `npm run closy:avatar-export -- <renderId>`
 *           (from repo root; resolves `avatar_export` inside `scripts/closy-avatar-export.mjs`).
 *
 * Optional app env:
 * - `EXPO_PUBLIC_CLOSY_REPO_ROOT` — absolute path to repo root so the app can read/write
 *   the same `generated/` tree (desktop/dev; may fail on device sandboxes).
 * - `EXPO_PUBLIC_AVATAR_EXPORT_MOCK=1` — `runAvatarExport` succeeds with a placeholder image.
 */

export const AVATAR_EXPORT_CONTRACT_VERSION = 1 as const;

/** Relative to repository root (forward slashes). */
export const AVATAR_REQUESTS_DIR = "generated/avatar_requests" as const;
export const AVATAR_RENDERS_DIR = "generated/avatar_renders" as const;

export function joinPathSegments(base: string, ...segments: string[]): string {
  const b = base.replace(/[/\\]+$/, "");
  const rest = segments
    .map((s) => s.replace(/^[/\\]+/, "").replace(/\\/g, "/"))
    .filter((s) => s.length > 0)
    .join("/");
  return rest.length > 0 ? `${b}/${rest}` : b;
}

export function requestFilenameForRenderId(renderId: string): string {
  const safe = renderId.replace(/[/\\]/g, "_");
  return `${safe}.json`;
}

export function renderFilenameForRenderId(renderId: string): string {
  const safe = renderId.replace(/[/\\]/g, "_");
  return `${safe}.png`;
}

export function requestRelativePathForRenderId(renderId: string): string {
  return joinPathSegments(AVATAR_REQUESTS_DIR, requestFilenameForRenderId(renderId));
}

export function renderRelativePathForRenderId(renderId: string): string {
  return joinPathSegments(AVATAR_RENDERS_DIR, renderFilenameForRenderId(renderId));
}
