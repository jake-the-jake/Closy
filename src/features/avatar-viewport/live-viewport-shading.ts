/**
 * First-pass live viewport shading — independent from offline engine `FitDebugViewMode`.
 * Mirrors useful ideas (overlay colors, focus body/garment) without GPU-heavy composites.
 */
export type LiveViewportShadingMode =
  | "normal"
  | "body_focus"
  | "garment_focus"
  | "overlay_style"
  | "overlay_debug";

export const LIVE_VIEWPORT_SHADING_LABELS: Record<LiveViewportShadingMode, string> =
  {
    normal: "Normal",
    body_focus: "Body focus",
    garment_focus: "Garment focus",
    overlay_style: "Overlay (debug)",
    overlay_debug: "Overlay debug",
  };

export function listLiveViewportShadingModes(): LiveViewportShadingMode[] {
  return ["normal", "body_focus", "garment_focus", "overlay_debug"];
}
