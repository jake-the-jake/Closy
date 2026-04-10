import type { AvatarExportDebugFlags } from "./types";

/**
 * Dev-only fit / garment debug view mode (avatar preview screen).
 * Staged for engine: optional `closy.debug` in export JSON; host `avatar_export` may ignore until wired.
 */
export type FitDebugViewMode =
  | "normal"
  | "body_only"
  | "garment_only"
  | "overlay"
  | "silhouette"
  | "wireframe"
  | "skeleton";

/** If false, the mode is still written into `closy.debug` but the engine likely renders like `normal`. */
export const FIT_DEBUG_MODE_ENGINE_WIRED: Record<FitDebugViewMode, boolean> = {
  normal: true,
  body_only: false,
  garment_only: false,
  overlay: false,
  silhouette: false,
  wireframe: false,
  skeleton: false,
};

export const FIT_DEBUG_MODE_LABELS: Record<FitDebugViewMode, string> = {
  normal: "Normal",
  body_only: "Body only",
  garment_only: "Garment only",
  overlay: "Overlay",
  silhouette: "Silhouette compare",
  wireframe: "Wireframe",
  skeleton: "Skeleton",
};

const ORDER: FitDebugViewMode[] = [
  "normal",
  "body_only",
  "garment_only",
  "overlay",
  "silhouette",
  "wireframe",
  "skeleton",
];

export function listFitDebugModes(): FitDebugViewMode[] {
  return ORDER;
}

/** Maps the single-select dev mode to optional JSON flags (omitted entirely for normal). */
export function fitDebugModeToExportFlags(
  mode: FitDebugViewMode,
): AvatarExportDebugFlags | undefined {
  if (mode === "normal") return undefined;
  const flags: AvatarExportDebugFlags = {};
  switch (mode) {
    case "body_only":
      flags.showBodyOnly = true;
      break;
    case "garment_only":
      flags.showGarmentOnly = true;
      break;
    case "overlay":
      flags.showOverlay = true;
      break;
    case "silhouette":
      flags.showSilhouette = true;
      break;
    case "wireframe":
      flags.showWireframe = true;
      break;
    case "skeleton":
      flags.showSkeleton = true;
      break;
    default:
      break;
  }
  return Object.keys(flags).length > 0 ? flags : undefined;
}

export function isFitDebugModeEngineWired(mode: FitDebugViewMode): boolean {
  return FIT_DEBUG_MODE_ENGINE_WIRED[mode] === true;
}
