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
  | "clipping_hotspot"
  | "wireframe"
  | "skeleton";

/** Defaults baked into dev UI + request JSON for clipping hotspot until sliders exist. */
export const CLIPPING_HOTSPOT_DEFAULTS = {
  clippingThreshold: 0.35,
  clippingVisualization: "hotspot" as const,
  showBaseRenderUnderlay: true,
};

/** If false, the mode is still written into `closy.debug` but the engine likely renders like `normal`. */
export const FIT_DEBUG_MODE_ENGINE_WIRED: Record<FitDebugViewMode, boolean> = {
  normal: true,
  body_only: false,
  garment_only: false,
  overlay: true,
  silhouette: true,
  clipping_hotspot: true,
  wireframe: false,
  skeleton: false,
};

export const FIT_DEBUG_MODE_LABELS: Record<FitDebugViewMode, string> = {
  normal: "Normal",
  body_only: "Body only",
  garment_only: "Garment only",
  overlay: "Overlay",
  silhouette: "Silhouette compare",
  clipping_hotspot: "Clipping hotspot",
  wireframe: "Wireframe",
  skeleton: "Skeleton",
};

const ORDER: FitDebugViewMode[] = [
  "normal",
  "body_only",
  "garment_only",
  "overlay",
  "silhouette",
  "clipping_hotspot",
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
      flags.debugMode = "overlay";
      flags.overlayOpacity = 0.55;
      break;
    case "silhouette":
      flags.showSilhouette = true;
      flags.debugMode = "silhouette";
      break;
    case "clipping_hotspot":
      flags.debugMode = "clipping";
      flags.showClipping = true;
      flags.clippingThreshold = CLIPPING_HOTSPOT_DEFAULTS.clippingThreshold;
      flags.clippingVisualization = CLIPPING_HOTSPOT_DEFAULTS.clippingVisualization;
      flags.showBaseRenderUnderlay = CLIPPING_HOTSPOT_DEFAULTS.showBaseRenderUnderlay;
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
