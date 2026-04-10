import type { AvatarExportFit } from "./types";

/** Canonical garment fit state (UI + export). */
export type GarmentFitState = {
  global: {
    offset: [number, number, number];
    scale: [number, number, number];
    inflate: number;
  };
  regions: {
    torso: { offsetZ: number; inflate: number; scaleY: number };
    sleeves: { offset: [number, number, number]; inflate: number };
    waist: { offsetZ: number; tighten: number };
    hem: { offsetY: number };
  };
  legacy: {
    shrinkwrapStrength: number;
    bodyOffsetBias: number;
    /** Added to sleeve region Y (flat export compat). */
    sleeveOffsetY: number;
    /** Trouser hip Y (flat `waistAdjust`). */
    waistAdjustY: number;
  };
};

export const DEFAULT_GARMENT_FIT_STATE: GarmentFitState = {
  global: {
    offset: [0, 0, 0],
    scale: [1, 1, 1],
    inflate: 0,
  },
  regions: {
    torso: { offsetZ: 0, inflate: 0, scaleY: 1 },
    sleeves: { offset: [0, 0, 0], inflate: 0 },
    waist: { offsetZ: 0, tighten: 0 },
    hem: { offsetY: 0 },
  },
  legacy: {
    shrinkwrapStrength: 0,
    bodyOffsetBias: 0,
    sleeveOffsetY: 0,
    waistAdjustY: 0,
  },
};

const D = DEFAULT_GARMENT_FIT_STATE;

function veq(a: [number, number, number], b: [number, number, number]) {
  return a[0] === b[0] && a[1] === b[1] && a[2] === b[2];
}

export function cloneGarmentFitState(s: GarmentFitState): GarmentFitState {
  return {
    global: {
      offset: [...s.global.offset] as [number, number, number],
      scale: [...s.global.scale] as [number, number, number],
      inflate: s.global.inflate,
    },
    regions: {
      torso: { ...s.regions.torso },
      sleeves: {
        offset: [...s.regions.sleeves.offset] as [number, number, number],
        inflate: s.regions.sleeves.inflate,
      },
      waist: { ...s.regions.waist },
      hem: { ...s.regions.hem },
    },
    legacy: { ...s.legacy },
  };
}

export function garmentFitStatesEqual(a: GarmentFitState, b: GarmentFitState): boolean {
  return (
    veq(a.global.offset, b.global.offset) &&
    veq(a.global.scale, b.global.scale) &&
    a.global.inflate === b.global.inflate &&
    a.regions.torso.offsetZ === b.regions.torso.offsetZ &&
    a.regions.torso.inflate === b.regions.torso.inflate &&
    a.regions.torso.scaleY === b.regions.torso.scaleY &&
    veq(a.regions.sleeves.offset, b.regions.sleeves.offset) &&
    a.regions.sleeves.inflate === b.regions.sleeves.inflate &&
    a.regions.waist.offsetZ === b.regions.waist.offsetZ &&
    a.regions.waist.tighten === b.regions.waist.tighten &&
    a.regions.hem.offsetY === b.regions.hem.offsetY &&
    a.legacy.shrinkwrapStrength === b.legacy.shrinkwrapStrength &&
    a.legacy.bodyOffsetBias === b.legacy.bodyOffsetBias &&
    a.legacy.sleeveOffsetY === b.legacy.sleeveOffsetY &&
    a.legacy.waistAdjustY === b.legacy.waistAdjustY
  );
}

/** Build `closy.fit` patch (nested + legacy flat). Omits default branches. */
export function garmentFitStateToExportPatch(
  s: GarmentFitState,
): AvatarExportFit | undefined {
  const patch: AvatarExportFit = {};
  const g = s.global;
  const r = s.regions;
  const l = s.legacy;

  if (!veq(g.offset, D.global.offset) || !veq(g.scale, D.global.scale) || g.inflate !== D.global.inflate) {
    patch.global = {};
    if (!veq(g.offset, D.global.offset)) patch.global.offset = [...g.offset] as [number, number, number];
    if (!veq(g.scale, D.global.scale)) patch.global.scale = [...g.scale] as [number, number, number];
    if (g.inflate !== D.global.inflate) patch.global.inflate = g.inflate;
  }

  const regOut: NonNullable<AvatarExportFit["regions"]> = {};
  let hasReg = false;
  if (
    r.torso.offsetZ !== D.regions.torso.offsetZ ||
    r.torso.inflate !== D.regions.torso.inflate ||
    r.torso.scaleY !== D.regions.torso.scaleY
  ) {
    regOut.torso = {};
    if (r.torso.offsetZ !== D.regions.torso.offsetZ) regOut.torso.offsetZ = r.torso.offsetZ;
    if (r.torso.inflate !== D.regions.torso.inflate) regOut.torso.inflate = r.torso.inflate;
    if (r.torso.scaleY !== D.regions.torso.scaleY) regOut.torso.scaleY = r.torso.scaleY;
    hasReg = true;
  }
  if (
    !veq(r.sleeves.offset, D.regions.sleeves.offset) ||
    r.sleeves.inflate !== D.regions.sleeves.inflate
  ) {
    regOut.sleeves = {};
    if (!veq(r.sleeves.offset, D.regions.sleeves.offset))
      regOut.sleeves.offset = [...r.sleeves.offset] as [number, number, number];
    if (r.sleeves.inflate !== D.regions.sleeves.inflate) regOut.sleeves.inflate = r.sleeves.inflate;
    hasReg = true;
  }
  if (r.waist.offsetZ !== D.regions.waist.offsetZ || r.waist.tighten !== D.regions.waist.tighten) {
    regOut.waist = {};
    if (r.waist.offsetZ !== D.regions.waist.offsetZ) regOut.waist.offsetZ = r.waist.offsetZ;
    if (r.waist.tighten !== D.regions.waist.tighten) regOut.waist.tighten = r.waist.tighten;
    hasReg = true;
  }
  if (r.hem.offsetY !== D.regions.hem.offsetY) {
    regOut.hem = { offsetY: r.hem.offsetY };
    hasReg = true;
  }
  if (hasReg) patch.regions = regOut;

  if (l.shrinkwrapStrength !== D.legacy.shrinkwrapStrength)
    patch.shrinkwrapStrength = l.shrinkwrapStrength;
  if (l.bodyOffsetBias !== D.legacy.bodyOffsetBias) patch.bodyOffsetBias = l.bodyOffsetBias;
  if (l.sleeveOffsetY !== D.legacy.sleeveOffsetY) patch.sleeveOffset = l.sleeveOffsetY;
  if (l.waistAdjustY !== D.legacy.waistAdjustY) patch.waistAdjust = l.waistAdjustY;

  return Object.keys(patch).length > 0 ? patch : undefined;
}

export function mergeExportFitIntoGarmentState(patch: AvatarExportFit | undefined): GarmentFitState {
  if (patch == null) return cloneGarmentFitState(DEFAULT_GARMENT_FIT_STATE);
  const out = cloneGarmentFitState(DEFAULT_GARMENT_FIT_STATE);

  if (patch.global) {
    if (patch.global.offset && patch.global.offset.length >= 3) {
      out.global.offset = [
        patch.global.offset[0],
        patch.global.offset[1],
        patch.global.offset[2],
      ];
    }
    if (patch.global.scale && patch.global.scale.length >= 3) {
      out.global.scale = [
        patch.global.scale[0],
        patch.global.scale[1],
        patch.global.scale[2],
      ];
    }
    if (patch.global.inflate != null) out.global.inflate = patch.global.inflate;
  }

  if (patch.regions) {
    const rr = patch.regions;
    if (rr.torso) {
      if (rr.torso.offsetZ != null) out.regions.torso.offsetZ = rr.torso.offsetZ;
      if (rr.torso.inflate != null) out.regions.torso.inflate = rr.torso.inflate;
      if (rr.torso.scaleY != null) out.regions.torso.scaleY = rr.torso.scaleY;
    }
    if (rr.sleeves) {
      if (rr.sleeves.offset && rr.sleeves.offset.length >= 3) {
        out.regions.sleeves.offset = [
          rr.sleeves.offset[0],
          rr.sleeves.offset[1],
          rr.sleeves.offset[2],
        ];
      }
      if (rr.sleeves.inflate != null) out.regions.sleeves.inflate = rr.sleeves.inflate;
    }
    if (rr.waist) {
      if (rr.waist.offsetZ != null) out.regions.waist.offsetZ = rr.waist.offsetZ;
      if (rr.waist.tighten != null) out.regions.waist.tighten = rr.waist.tighten;
    }
    if (rr.hem?.offsetY != null) out.regions.hem.offsetY = rr.hem.offsetY;
  }

  if (patch.offsetX != null) out.global.offset[0] = patch.offsetX;
  if (patch.offsetY != null) out.global.offset[1] = patch.offsetY;
  if (patch.offsetZ != null) out.global.offset[2] = patch.offsetZ;
  if (patch.scaleX != null) out.global.scale[0] = patch.scaleX;
  if (patch.scaleY != null) out.global.scale[1] = patch.scaleY;
  if (patch.scaleZ != null) out.global.scale[2] = patch.scaleZ;
  if (patch.inflate != null) out.global.inflate = patch.inflate;
  if (patch.shrinkwrapStrength != null) out.legacy.shrinkwrapStrength = patch.shrinkwrapStrength;
  if (patch.bodyOffsetBias != null) out.legacy.bodyOffsetBias = patch.bodyOffsetBias;
  if (patch.torsoOffsetZ != null) out.regions.torso.offsetZ = patch.torsoOffsetZ;
  if (patch.sleeveOffset != null) out.legacy.sleeveOffsetY = patch.sleeveOffset;
  if (patch.waistAdjust != null) out.legacy.waistAdjustY = patch.waistAdjust;

  return out;
}

export function parseGarmentFitFromClosyJson(json: string): GarmentFitState {
  try {
    const o = JSON.parse(json) as { closy?: { fit?: AvatarExportFit } };
    return mergeExportFitIntoGarmentState(o?.closy?.fit);
  } catch {
    return cloneGarmentFitState(DEFAULT_GARMENT_FIT_STATE);
  }
}

/** @deprecated Pre-region flat UI; maps into `GarmentFitState` for history restore. */
export type LegacyGarmentFitAdjustState = {
  offsetX: number;
  offsetY: number;
  offsetZ: number;
  scaleX: number;
  scaleY: number;
  scaleZ: number;
  inflate: number;
  shrinkwrapStrength: number;
  bodyOffsetBias: number;
  torsoOffsetZ: number;
  sleeveOffset: number;
  waistAdjust: number;
};

export function garmentFitFromLegacyFlat(f: LegacyGarmentFitAdjustState): GarmentFitState {
  return mergeExportFitIntoGarmentState({
    offsetX: f.offsetX,
    offsetY: f.offsetY,
    offsetZ: f.offsetZ,
    scaleX: f.scaleX,
    scaleY: f.scaleY,
    scaleZ: f.scaleZ,
    inflate: f.inflate,
    shrinkwrapStrength: f.shrinkwrapStrength,
    bodyOffsetBias: f.bodyOffsetBias,
    torsoOffsetZ: f.torsoOffsetZ,
    sleeveOffset: f.sleeveOffset,
    waistAdjust: f.waistAdjust,
  });
}

type FitPresetFn = (prev?: GarmentFitState) => GarmentFitState;

function r(v: number, step: number): number {
  const n = Math.round(v / step);
  return n * step;
}

export const GARMENT_FIT_PRESETS: Record<string, FitPresetFn> = {
  reset: () => cloneGarmentFitState(DEFAULT_GARMENT_FIT_STATE),
  tight_fit: () =>
    cloneGarmentFitState({
      ...DEFAULT_GARMENT_FIT_STATE,
      global: {
        offset: [0, 0, 0],
        scale: [0.96, 0.96, 0.96],
        inflate: -0.015,
      },
    }),
  loose_fit: () =>
    cloneGarmentFitState({
      ...DEFAULT_GARMENT_FIT_STATE,
      global: {
        offset: [0, 0, 0],
        scale: [1.06, 1.06, 1.06],
        inflate: 0.035,
      },
    }),
  inflate_test: () =>
    cloneGarmentFitState({
      ...DEFAULT_GARMENT_FIT_STATE,
      global: { offset: [0, 0, 0], scale: [1, 1, 1], inflate: 0.08 },
    }),
  offset_back: (prev = DEFAULT_GARMENT_FIT_STATE) => {
    const c = cloneGarmentFitState(prev);
    c.global.offset[2] = r(c.global.offset[2] - 0.02, 0.01);
    return c;
  },
  offset_forward: (prev = DEFAULT_GARMENT_FIT_STATE) => {
    const c = cloneGarmentFitState(prev);
    c.global.offset[2] = r(c.global.offset[2] + 0.02, 0.01);
    return c;
  },
};
