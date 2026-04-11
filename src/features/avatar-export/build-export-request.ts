import {
  AVATAR_EXPORT_CONTRACT_VERSION,
  renderRelativePathForRenderId,
  requestRelativePathForRenderId,
} from "./contract";
import type { AvatarExportBodyShape } from "./body-shape-state";
import type {
  AvatarEngineOutfitFile,
  AvatarEngineOutfitItem,
  AvatarExportDebugFlags,
  AvatarExportFit,
  AvatarExportRequest,
  AvatarOutfitLike,
} from "./types";

export type BuildAvatarExportOptions = {
  pose?: string;
  width?: number;
  height?: number;
  camera?: string;
  /** Defaults to `outfit_${Date.now()}`. */
  renderId?: string;
  /**
   * Dev-only optional flags under `closy.debug`.
   * Prefer `fitDebugModeToExportFlags` from `avatar-fit-debug.ts` when using the preview screen modes.
   */
  debug?: AvatarExportDebugFlags;
  /** Dev-only; written under `closy.fit` when non-empty. */
  fit?: AvatarExportFit;
  /** Dev-only; written under `closy.bodyShape` when non-empty. */
  bodyShape?: AvatarExportBodyShape;
};

function pushItem(items: AvatarEngineOutfitItem[], slotLike: AvatarEngineOutfitItem) {
  items.push(slotLike);
}

/**
 * Maps a minimal outfit description to the native exporter JSON payload.
 */
export function buildAvatarExportRequest(
  outfit: AvatarOutfitLike,
  options: BuildAvatarExportOptions = {},
): AvatarExportRequest {
  const renderId = options.renderId ?? `outfit_${Date.now()}`;
  const items: AvatarEngineOutfitItem[] = [];

  if (outfit.top) {
    pushItem(items, {
      slot: "top",
      type: outfit.top.kind,
      ...(outfit.top.color ? { color: outfit.top.color } : {}),
    });
  }
  if (outfit.bottom) {
    pushItem(items, {
      slot: "bottom",
      type: outfit.bottom.kind,
      ...(outfit.bottom.color ? { color: outfit.bottom.color } : {}),
    });
  }
  if (outfit.shoes) {
    pushItem(items, {
      slot: "shoes",
      type: outfit.shoes.kind,
      ...(outfit.shoes.color ? { color: outfit.shoes.color } : {}),
    });
  }
  if (items.length === 0) {
    items.push({ slot: "top", type: "jumper" });
    items.push({ slot: "bottom", type: "trousers" });
  }

  const engine: AvatarEngineOutfitFile = {
    pose: options.pose ?? "relaxed",
    width: options.width ?? 1024,
    height: options.height ?? 1024,
    camera: options.camera ?? "three_quarter",
    items,
  };

  const closy: AvatarExportRequest["closy"] = {
    contractVersion: AVATAR_EXPORT_CONTRACT_VERSION,
    expectedOutputRelativePath: renderRelativePathForRenderId(renderId),
    requestRelativePath: requestRelativePathForRenderId(renderId),
  };
  if (options.debug != null && Object.keys(options.debug).length > 0) {
    closy.debug = options.debug;
  }
  if (options.fit != null && Object.keys(options.fit).length > 0) {
    closy.fit = options.fit;
  }
  if (options.bodyShape != null && Object.keys(options.bodyShape).length > 0) {
    closy.bodyShape = options.bodyShape;
  }

  return {
    renderId,
    engine,
    closy,
  };
}

/**
 * JSON string passed to `avatar_export` (includes `closy` meta and optional `closy.debug`;
 * engine ignores keys it does not understand).
 */
export function serializeAvatarExportRequestForDisk(request: AvatarExportRequest): string {
  const closy: Record<string, unknown> = { ...request.closy };
  if (request.closy.debug == null) {
    delete closy.debug;
  }
  if (request.closy.fit == null || Object.keys(request.closy.fit).length === 0) {
    delete closy.fit;
  }
  const payload = {
    ...request.engine,
    closy,
  };
  return `${JSON.stringify(payload, null, 2)}\n`;
}
