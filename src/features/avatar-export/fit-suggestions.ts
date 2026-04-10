import type { GarmentFitState } from "./garment-fit-state";
import { cloneGarmentFitState } from "./garment-fit-state";

/** Engine-written `*_clipping_stats.json` (v1). */
export type ClippingStatsV1 = {
  version: number;
  width?: number;
  height?: number;
  overlapFrac?: number;
  nearFrac?: number;
  bands?: { upper?: number; middle?: number; lower?: number };
  yellowBands?: { upper?: number; middle?: number; lower?: number };
  halves?: { left?: number; right?: number };
  yellowHalves?: { left?: number; right?: number };
};

export type FitSuggestion = {
  id: string;
  message: string;
  /** Human-readable delta for diagnostics. */
  detail: string;
  apply: (s: GarmentFitState) => GarmentFitState;
};

const STEP_Z = 0.02;
const STEP_TORSO = 0.02;
const STEP_INFL = 0.01;
const STEP_TIGHTEN = 0.05;
const STEP_HEM = 0.015;

function bumpGlobalZ(s: GarmentFitState, dz: number): GarmentFitState {
  const c = cloneGarmentFitState(s);
  c.global.offset[2] = Math.round((c.global.offset[2] + dz) * 1000) / 1000;
  return c;
}

function bumpTorsoZ(s: GarmentFitState, dz: number): GarmentFitState {
  const c = cloneGarmentFitState(s);
  c.regions.torso.offsetZ =
    Math.round((c.regions.torso.offsetZ + dz) * 1000) / 1000;
  return c;
}

function bumpSleeveInfl(s: GarmentFitState, di: number): GarmentFitState {
  const c = cloneGarmentFitState(s);
  c.regions.sleeves.inflate =
    Math.round((c.regions.sleeves.inflate + di) * 1000) / 1000;
  return c;
}

function bumpWaistLoosen(s: GarmentFitState): GarmentFitState {
  const c = cloneGarmentFitState(s);
  c.regions.waist.tighten = Math.max(
    0,
    Math.round((c.regions.waist.tighten - STEP_TIGHTEN) * 1000) / 1000,
  );
  c.regions.waist.offsetZ =
    Math.round((c.regions.waist.offsetZ + STEP_Z) * 1000) / 1000;
  return c;
}

function bumpHemY(s: GarmentFitState, dy: number): GarmentFitState {
  const c = cloneGarmentFitState(s);
  c.regions.hem.offsetY =
    Math.round((c.regions.hem.offsetY + dy) * 1000) / 1000;
  return c;
}

/** Rule-based hints from band histograms (three-quarter view is ambiguous). */
export function suggestionsFromClippingStats(
  stats: ClippingStatsV1 | null,
): FitSuggestion[] {
  if (stats == null || stats.version !== 1) return [];
  const b = stats.bands ?? {};
  const u = b.upper ?? 0;
  const m = b.middle ?? 0;
  const l = b.lower ?? 0;
  const h = stats.halves ?? {};
  const left = h.left ?? 0;
  const right = h.right ?? 0;
  const out: FitSuggestion[] = [];

  if (u > 0.04 && u > m * 1.25) {
    out.push({
      id: "clip_upper_torso_back",
      message: "Upper band shows heavy overlap — try nudging shirt torso back",
      detail: `regions.torso.offsetZ −${STEP_TORSO}`,
      apply: (s) => bumpTorsoZ(s, -STEP_TORSO),
    });
  }
  if (m > u && m > l && m > 0.035) {
    out.push({
      id: "clip_mid_waist",
      message: "Mid band overlap — try loosening waist / shifting hip piece",
      detail: `waist tighten −${STEP_TIGHTEN}, waist.offsetZ +${STEP_Z}`,
      apply: bumpWaistLoosen,
    });
  }
  if (l > 0.035 && l > u * 0.9) {
    out.push({
      id: "clip_lower_hem",
      message: "Lower band overlap — hem / trouser legs may be penetrating",
      detail: `regions.hem.offsetY +${STEP_HEM}`,
      apply: (s) => bumpHemY(s, STEP_HEM),
    });
  }
  if (left > right * 1.35 && left > 0.03) {
    out.push({
      id: "clip_left_dominant",
      message: "Left half shows more overlap (view-dependent) — try small global Z tweak",
      detail: `global.offsetZ +${STEP_Z}`,
      apply: (s) => bumpGlobalZ(s, STEP_Z),
    });
  } else if (right > left * 1.35 && right > 0.03) {
    out.push({
      id: "clip_right_dominant",
      message: "Right half shows more overlap — try small global Z tweak the other way",
      detail: `global.offsetZ −${STEP_Z}`,
      apply: (s) => bumpGlobalZ(s, -STEP_Z),
    });
  }
  if (u > 0.025 && (stats.yellowBands?.upper ?? 0) > 0.06) {
    out.push({
      id: "clip_sleeve_near_upper",
      message: "Tight yellow rim in upper band — slight sleeve inflate",
      detail: `regions.sleeves.inflate +${STEP_INFL}`,
      apply: (s) => bumpSleeveInfl(s, STEP_INFL),
    });
  }
  return out;
}

const CHECKLIST_TO_SUGGESTIONS: Record<
  string,
  () => { id: string; message: string; detail: string; apply: (s: GarmentFitState) => GarmentFitState }
> = {
  torso_alignment: () => ({
    id: "chk_torso_align",
    message: "Torso alignment (checklist)",
    detail: `global.offsetZ −${STEP_Z}`,
    apply: (s) => bumpGlobalZ(s, -STEP_Z),
  }),
  chest_clipping: () => ({
    id: "chk_chest",
    message: "Chest clipping (checklist)",
    detail: `torso.offsetZ −${STEP_TORSO}`,
    apply: (s) => bumpTorsoZ(s, -STEP_TORSO),
  }),
  back_clipping: () => ({
    id: "chk_back",
    message: "Back clipping (checklist)",
    detail: `global.offsetZ +${STEP_Z}`,
    apply: (s) => bumpGlobalZ(s, STEP_Z),
  }),
  shoulder_alignment: () => ({
    id: "chk_shoulder",
    message: "Shoulder / sleeve zone (checklist)",
    detail: `sleeves.offset Y +${STEP_HEM}`,
    apply: (s) => {
      const c = cloneGarmentFitState(s);
      c.regions.sleeves.offset[1] =
        Math.round((c.regions.sleeves.offset[1] + STEP_HEM) * 1000) / 1000;
      return c;
    },
  }),
  sleeve_fit: () => ({
    id: "chk_sleeve_fit",
    message: "Sleeve fit (checklist)",
    detail: `sleeves.inflate +${STEP_INFL}`,
    apply: (s) => bumpSleeveInfl(s, STEP_INFL),
  }),
  armpit_clipping: () => ({
    id: "chk_armpit",
    message: "Armpit clipping (checklist)",
    detail: `sleeves.inflate +${STEP_INFL} · global.inflate −0.01`,
    apply: (s) => {
      const c = bumpSleeveInfl(s, STEP_INFL);
      c.global.inflate = Math.round((c.global.inflate - 0.01) * 1000) / 1000;
      return c;
    },
  }),
  waist_fit: () => ({
    id: "chk_waist_fit",
    message: "Waist fit (checklist)",
    detail: "waist loosen preset",
    apply: bumpWaistLoosen,
  }),
  hem_alignment: () => ({
    id: "chk_hem_align",
    message: "Hem alignment (checklist)",
    detail: `hem.offsetY +${STEP_HEM}`,
    apply: (s) => bumpHemY(s, STEP_HEM),
  }),
  torso_forward: () => ({
    id: "chk_torso_forward",
    message: "Torso too far forward (checklist)",
    detail: `torso.offsetZ −${STEP_TORSO}`,
    apply: (s) => bumpTorsoZ(s, -STEP_TORSO),
  }),
  clipping_back: () => ({
    id: "chk_clipping_back",
    message: "Back clipping (checklist)",
    detail: `global.offsetZ +${STEP_Z}`,
    apply: (s) => bumpGlobalZ(s, STEP_Z),
  }),
  neckline_offset: () => ({
    id: "chk_neckline",
    message: "Neckline offset (checklist)",
    detail: `global.offsetY +${STEP_HEM}`,
    apply: (s) => {
      const c = cloneGarmentFitState(s);
      c.global.offset[1] =
        Math.round((c.global.offset[1] + STEP_HEM) * 1000) / 1000;
      return c;
    },
  }),
  hem_high: () => ({
    id: "chk_hem_high",
    message: "Hem too high (checklist)",
    detail: `hem.offsetY −${STEP_HEM}`,
    apply: (s) => bumpHemY(s, -STEP_HEM),
  }),
  hem_low: () => ({
    id: "chk_hem_low",
    message: "Hem too low (checklist)",
    detail: `hem.offsetY +${STEP_HEM}`,
    apply: (s) => bumpHemY(s, STEP_HEM),
  }),
  waist_mismatch: () => ({
    id: "chk_waist",
    message: "Waist mismatch (checklist)",
    detail: "waist tighten / offsetZ",
    apply: bumpWaistLoosen,
  }),
  pose_specific: () => ({
    id: "chk_pose",
    message: "Pose-specific (checklist) — compare another pose export",
    detail: "global.inflate −0.01 (slight shrink)",
    apply: (s) => {
      const c = cloneGarmentFitState(s);
      c.global.inflate =
        Math.round((c.global.inflate - 0.01) * 1000) / 1000;
      return c;
    },
  }),
  sleeves_ok: () => ({
    id: "chk_sleeves_hypo",
    message: "If sleeves were OK but armpit clips, try sleeve inflate +0.01",
    detail: `sleeves.inflate +${STEP_INFL}`,
    apply: (s) => bumpSleeveInfl(s, STEP_INFL),
  }),
};

export function suggestionsFromChecklistTagIds(tagIds: string[]): FitSuggestion[] {
  const out: FitSuggestion[] = [];
  const seen = new Set<string>();
  for (const id of tagIds) {
    const fn = CHECKLIST_TO_SUGGESTIONS[id];
    if (!fn) continue;
    const s = fn();
    if (seen.has(s.id)) continue;
    seen.add(s.id);
    out.push({
      id: s.id,
      message: s.message,
      detail: s.detail,
      apply: s.apply,
    });
  }
  return out;
}

export async function fetchClippingStatsV1(
  renderId: string,
  resolveUrl: (id: string) => string | null,
): Promise<ClippingStatsV1 | null> {
  const url = resolveUrl(renderId);
  if (!url) return null;
  try {
    const res = await fetch(url);
    if (!res.ok) return null;
    const j = (await res.json()) as ClippingStatsV1;
    if (j.version !== 1) return null;
    return j;
  } catch {
    return null;
  }
}
