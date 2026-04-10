import {
  cloneFitState,
  cloneGarmentFitState,
  type FitSuggestion,
  type GarmentFitState,
} from "@/features/avatar-export";

import type { LiveViewportShadingMode } from "./live-viewport-shading";
import type { RuntimeClippingReport } from "./runtime-clipping-approx";

const Z = 0.02;
const TZ = 0.015;
const INFL = 0.012;
const TIGHT = 0.06;
const HEM = 0.012;

/**
 * Lightweight rule-based hints from current live fit (no engine PNG).
 * IDs use `live_` prefix; safe to merge with clipping-stats suggestions.
 */
export function suggestionsFromLiveHeuristics(
  fit: GarmentFitState,
  liveShading: LiveViewportShadingMode,
): FitSuggestion[] {
  const out: FitSuggestion[] = [];
  const g = fit.global;
  const r = fit.regions;

  if (g.offset[2] > 0.055) {
    out.push({
      id: "live_global_forward",
      message: "Global fit is strongly forward — nudge garments back (−Z)",
      detail: `global.offset[2] −${Z}`,
      suggestionSource: "live_heuristic",
      apply: (s) => {
        const c = cloneFitState(s);
        c.global.offset[2] = Math.round((c.global.offset[2] - Z) * 1000) / 1000;
        return c;
      },
    });
  }
  if (g.offset[2] < -0.055) {
    out.push({
      id: "live_global_back",
      message: "Global fit is far back — try +Z toward camera",
      detail: `global.offset[2] +${Z}`,
      suggestionSource: "live_heuristic",
      apply: (s) => {
        const c = cloneFitState(s);
        c.global.offset[2] = Math.round((c.global.offset[2] + Z) * 1000) / 1000;
        return c;
      },
    });
  }

  if (r.torso.offsetZ > 0.045) {
    out.push({
      id: "live_torso_forward",
      message: "Torso region forward — slide torso garment back",
      detail: `regions.torso.offsetZ −${TZ}`,
      suggestionSource: "live_heuristic",
      apply: (s) => {
        const c = cloneFitState(s);
        c.regions.torso.offsetZ =
          Math.round((c.regions.torso.offsetZ - TZ) * 1000) / 1000;
        return c;
      },
    });
  }
  if (r.torso.offsetZ < -0.045) {
    out.push({
      id: "live_torso_back",
      message: "Torso region too far back — bring shirt forward slightly",
      detail: `regions.torso.offsetZ +${TZ}`,
      suggestionSource: "live_heuristic",
      apply: (s) => {
        const c = cloneFitState(s);
        c.regions.torso.offsetZ =
          Math.round((c.regions.torso.offsetZ + TZ) * 1000) / 1000;
        return c;
      },
    });
  }

  if (r.sleeves.inflate < -0.025) {
    out.push({
      id: "live_sleeves_tight",
      message: "Sleeves look glued / tight — add a little sleeve inflate",
      detail: `regions.sleeves.inflate +${INFL * 2}`,
      suggestionSource: "live_heuristic",
      apply: (s) => {
        const c = cloneFitState(s);
        c.regions.sleeves.inflate =
          Math.round((c.regions.sleeves.inflate + INFL * 2) * 1000) / 1000;
        return c;
      },
    });
  }
  if (r.sleeves.inflate > 0.085) {
    out.push({
      id: "live_sleeves_bulky",
      message: "Sleeves very inflated — reduce sleeve bulk",
      detail: `regions.sleeves.inflate −${INFL * 2}`,
      suggestionSource: "live_heuristic",
      apply: (s) => {
        const c = cloneFitState(s);
        c.regions.sleeves.inflate =
          Math.round((c.regions.sleeves.inflate - INFL * 2) * 1000) / 1000;
        return c;
      },
    });
  }

  if (r.waist.tighten > 0.22) {
    out.push({
      id: "live_waist_tight",
      message: "Waist very cinched — loosen for hip clearance",
      detail: `waist.tighten −${TIGHT}`,
      suggestionSource: "live_heuristic",
      apply: (s) => {
        const c = cloneFitState(s);
        c.regions.waist.tighten = Math.max(
          0,
          Math.round((c.regions.waist.tighten - TIGHT) * 1000) / 1000,
        );
        return c;
      },
    });
  }

  if (r.hem.offsetY > 0.045) {
    out.push({
      id: "live_hem_high",
      message: "Hem reads high — lower pant hem (offset Y)",
      detail: `regions.hem.offsetY −${HEM}`,
      suggestionSource: "live_heuristic",
      apply: (s) => {
        const c = cloneFitState(s);
        c.regions.hem.offsetY =
          Math.round((c.regions.hem.offsetY - HEM) * 1000) / 1000;
        return c;
      },
    });
  }
  if (r.hem.offsetY < -0.045) {
    out.push({
      id: "live_hem_low",
      message: "Hem reads low — raise pant hem slightly",
      detail: `regions.hem.offsetY +${HEM}`,
      suggestionSource: "live_heuristic",
      apply: (s) => {
        const c = cloneFitState(s);
        c.regions.hem.offsetY =
          Math.round((c.regions.hem.offsetY + HEM) * 1000) / 1000;
        return c;
      },
    });
  }

  if (g.inflate < -0.04) {
    out.push({
      id: "live_global_deflate",
      message: "Strong negative global inflate — ease toward neutral",
      detail: `global.inflate +${INFL * 2}`,
      suggestionSource: "live_heuristic",
      apply: (s) => {
        const c = cloneFitState(s);
        c.global.inflate =
          Math.round((c.global.inflate + INFL * 2) * 1000) / 1000;
        return c;
      },
    });
  }

  if (liveShading === "garment_focus" && g.scale[0] < 0.94) {
    out.push({
      id: "live_scale_narrow",
      message: "Garment focus + narrow scale — try slightly wider global X",
      detail: `global.scale[0] +0.02`,
      suggestionSource: "live_heuristic",
      apply: (s) => {
        const c = cloneFitState(s);
        c.global.scale[0] = Math.min(1.2, Math.round((c.global.scale[0] + 0.02) * 100) / 100);
        return c;
      },
    });
  }

  return out;
}

const RT_TORSO = 0.02;
const RT_INFL = 0.01;
const RT_TIGHT = 0.05;
const RT_HEM = 0.015;
const RT_Z = 0.02;

function rtBumpTorsoZ(s: GarmentFitState, dz: number): GarmentFitState {
  const c = cloneGarmentFitState(s);
  c.regions.torso.offsetZ =
    Math.round((c.regions.torso.offsetZ + dz) * 1000) / 1000;
  return c;
}

function rtBumpSleeveInfl(s: GarmentFitState, di: number): GarmentFitState {
  const c = cloneGarmentFitState(s);
  c.regions.sleeves.inflate =
    Math.round((c.regions.sleeves.inflate + di) * 1000) / 1000;
  return c;
}

function rtBumpWaistLoosen(s: GarmentFitState): GarmentFitState {
  const c = cloneGarmentFitState(s);
  c.regions.waist.tighten = Math.max(
    0,
    Math.round((c.regions.waist.tighten - RT_TIGHT) * 1000) / 1000,
  );
  c.regions.waist.offsetZ =
    Math.round((c.regions.waist.offsetZ + RT_Z) * 1000) / 1000;
  return c;
}

function rtBumpHemY(s: GarmentFitState, dy: number): GarmentFitState {
  const c = cloneGarmentFitState(s);
  c.regions.hem.offsetY =
    Math.round((c.regions.hem.offsetY + dy) * 1000) / 1000;
  return c;
}

/** Rule-based fixes from `analyzeRuntimeClipping` (proxy overlap, ~same steps as offline stats). */
export function suggestionsFromRuntimeClipping(
  report: RuntimeClippingReport,
): FitSuggestion[] {
  const out: FitSuggestion[] = [];

  if (report.torso.severity === "clip") {
    out.push({
      id: "runtime_clip_torso",
      message:
        "Live proxy: torso / shirt likely intersecting — pull shirt back (−torso Z) or add slight torso inflate",
      detail: `torso.offsetZ −${RT_TORSO} · torso.inflate +${RT_INFL}`,
      suggestionSource: "runtime_clip",
      apply: (s) => {
        const c = rtBumpTorsoZ(s, -RT_TORSO);
        c.regions.torso.inflate =
          Math.round((c.regions.torso.inflate + RT_INFL) * 1000) / 1000;
        return c;
      },
    });
  } else if (report.torso.severity === "near") {
    out.push({
      id: "runtime_near_torso",
      message: "Live proxy: torso / shirt close — small back-off on torso Z",
      detail: `torso.offsetZ −${(RT_TORSO * 0.65).toFixed(3)}`,
      suggestionSource: "runtime_clip",
      apply: (s) => rtBumpTorsoZ(s, -RT_TORSO * 0.65),
    });
  }

  if (report.sleeves.severity === "clip") {
    out.push({
      id: "runtime_clip_sleeve",
      message:
        "Live proxy: sleeve / arm likely intersecting — more sleeve inflate or adjust sleeve offsets",
      detail: `sleeves.inflate +${RT_INFL * 1.5}`,
      suggestionSource: "runtime_clip",
      apply: (s) => rtBumpSleeveInfl(s, RT_INFL * 1.5),
    });
  } else if (report.sleeves.severity === "near") {
    out.push({
      id: "runtime_near_sleeve",
      message: "Live proxy: sleeve zone tight — slight sleeve inflate",
      detail: `sleeves.inflate +${RT_INFL}`,
      suggestionSource: "runtime_clip",
      apply: (s) => rtBumpSleeveInfl(s, RT_INFL),
    });
  }

  if (report.waist.severity === "clip") {
    out.push({
      id: "runtime_clip_waist",
      message: "Live proxy: waist / hip likely intersecting — loosen waist and ease +Z",
      detail: "waist loosen + offsetZ",
      suggestionSource: "runtime_clip",
      apply: rtBumpWaistLoosen,
    });
  } else if (report.waist.severity === "near") {
    out.push({
      id: "runtime_near_waist",
      message: "Live proxy: waist band close to body — small loosen",
      detail: `waist.tighten −${(RT_TIGHT * 0.55).toFixed(3)}`,
      suggestionSource: "runtime_clip",
      apply: (s) => {
        const c = cloneGarmentFitState(s);
        c.regions.waist.tighten = Math.max(
          0,
          Math.round((c.regions.waist.tighten - RT_TIGHT * 0.55) * 1000) / 1000,
        );
        return c;
      },
    });
  }

  if (report.hem.severity === "clip") {
    out.push({
      id: "runtime_clip_hem",
      message: "Live proxy: hem / legs likely intersecting — raise hem slightly",
      detail: `hem.offsetY +${RT_HEM}`,
      suggestionSource: "runtime_clip",
      apply: (s) => rtBumpHemY(s, RT_HEM),
    });
  } else if (report.hem.severity === "near") {
    out.push({
      id: "runtime_near_hem",
      message: "Live proxy: pant legs close to thighs — tiny hem raise",
      detail: `hem.offsetY +${(RT_HEM * 0.6).toFixed(3)}`,
      suggestionSource: "runtime_clip",
      apply: (s) => rtBumpHemY(s, RT_HEM * 0.6),
    });
  }

  return out;
}
