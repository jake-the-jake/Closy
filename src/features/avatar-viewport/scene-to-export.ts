import {
  bodyShapeToExportPatch,
  buildAvatarExportRequest,
  fitDebugModeToExportFlags,
  fitStateToExportPatch,
  type BuildAvatarExportOptions,
} from "@/features/avatar-export";

import { DEV_AVATAR_PRESETS } from "@/features/avatar-export/dev-avatar-shared";

import type { AvatarSceneState } from "./avatar-scene-types";

/** Resolve the outfit description used for export and live garment coloring. */
export function resolveAvatarOutfit(state: Pick<AvatarSceneState, "presetKey" | "outfitOverride">) {
  return state.outfitOverride ?? DEV_AVATAR_PRESETS[state.presetKey];
}

/** Build options passed to `buildAvatarExportRequest` from shared scene state. */
export function avatarSceneToBuildOptions(
  state: AvatarSceneState,
  extra?: Partial<BuildAvatarExportOptions>,
): BuildAvatarExportOptions {
  const fitPatch = fitStateToExportPatch(state.garmentFit);
  const debug = fitDebugModeToExportFlags(state.offlineFitDebugMode);
  const bodyShapePatch = bodyShapeToExportPatch(state.bodyShape);
  return {
    pose: state.pose,
    width: 1024,
    height: 1024,
    camera: "three_quarter",
    ...(debug != null && Object.keys(debug).length > 0 ? { debug } : {}),
    ...(fitPatch != null ? { fit: fitPatch } : {}),
    ...(bodyShapePatch != null ? { bodyShape: bodyShapePatch } : {}),
    ...extra,
  };
}

export function buildExportRequestFromAvatarScene(
  state: AvatarSceneState,
  extra?: Partial<BuildAvatarExportOptions>,
) {
  const outfit = resolveAvatarOutfit(state);
  const options = avatarSceneToBuildOptions(state, extra);
  return buildAvatarExportRequest(outfit, options);
}
