import {
  AVATAR_EXPORT_CONTRACT_VERSION,
  renderRelativePathForRenderId,
  requestRelativePathForRenderId,
} from "./contract";
import type {
  AvatarEngineOutfitFile,
  AvatarEngineOutfitItem,
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

  return {
    renderId,
    engine,
    closy: {
      contractVersion: AVATAR_EXPORT_CONTRACT_VERSION,
      expectedOutputRelativePath: renderRelativePathForRenderId(renderId),
      requestRelativePath: requestRelativePathForRenderId(renderId),
    },
  };
}

/** JSON string passed to `avatar_export` (includes `closy` meta; engine ignores unknown keys). */
export function serializeAvatarExportRequestForDisk(request: AvatarExportRequest): string {
  const payload = {
    ...request.engine,
    closy: request.closy,
  };
  return `${JSON.stringify(payload, null, 2)}\n`;
}
