/**
 * Shared parametric body configuration for live viewport, clipping, stress tests, and optional export JSON.
 * Values are multipliers around 1.0 (bounded for stable UX). Not anatomical units.
 */

/**
 * Base rig (meters-ish, ~1.78 m standing).
 * Pelvis height is derived from torso bottom + overlap so hips meet the torso base.
 * `shoulderHalf` is the max acromion span; arm bind uses the tighter of this and torso+arm.
 */
const RIG = {
  /** Torso (spine) capsule center — upper abdomen / lower chest. */
  chestY: 1.045,
  /** Acromion half-span at reference shoulder width (upper cap for arm lateral bind). */
  shoulderHalf: 0.178,
} as const;

export type BodyShapeParams = {
  /** Vertical scale of the figure (~1 = reference ~1.78m footprint). */
  height: number;
  /** Shoulder span (X at arm binds). */
  shoulderWidth: number;
  /** Chest / upper torso breadth. */
  chest: number;
  /** Waist / lower torso narrowness (pelvis box X). */
  waist: number;
  /** Hip width (pelvis + leg roots). */
  hips: number;
  /** Upper arm thickness. */
  armThickness: number;
  /** Thigh thickness. */
  legThickness: number;
  /** Spine / torso segment length (affects chest vs pelvis spacing). */
  torsoLength: number;
  /** Overall mass (uniform-ish scale on limbs + torso radius). */
  build: number;
};

export const DEFAULT_BODY_SHAPE: BodyShapeParams = {
  height: 1,
  shoulderWidth: 1,
  chest: 1,
  waist: 1,
  hips: 1,
  armThickness: 1,
  legThickness: 1,
  torsoLength: 1,
  build: 1,
};

export function cloneBodyShape(b: BodyShapeParams): BodyShapeParams {
  return { ...b };
}

export function bodyShapesEqual(a: BodyShapeParams, b: BodyShapeParams): boolean {
  return (
    a.height === b.height &&
    a.shoulderWidth === b.shoulderWidth &&
    a.chest === b.chest &&
    a.waist === b.waist &&
    a.hips === b.hips &&
    a.armThickness === b.armThickness &&
    a.legThickness === b.legThickness &&
    a.torsoLength === b.torsoLength &&
    a.build === b.build
  );
}

/** Serializable subset for `closy.bodyShape` in export JSON (engine may ignore). */
export type AvatarExportBodyShape = Partial<{
  height: number;
  shoulderWidth: number;
  chest: number;
  waist: number;
  hips: number;
  armThickness: number;
  legThickness: number;
  torsoLength: number;
  build: number;
}>;

export function bodyShapeToExportPatch(
  b: BodyShapeParams,
): AvatarExportBodyShape | undefined {
  if (bodyShapesEqual(b, DEFAULT_BODY_SHAPE)) return undefined;
  return {
    height: b.height,
    shoulderWidth: b.shoulderWidth,
    chest: b.chest,
    waist: b.waist,
    hips: b.hips,
    armThickness: b.armThickness,
    legThickness: b.legThickness,
    torsoLength: b.torsoLength,
    build: b.build,
  };
}

export function mergeExportBodyShapeIntoBodyShape(
  patch: AvatarExportBodyShape | undefined,
): BodyShapeParams {
  if (patch == null) return cloneBodyShape(DEFAULT_BODY_SHAPE);
  const o = cloneBodyShape(DEFAULT_BODY_SHAPE);
  if (typeof patch.height === "number") o.height = patch.height;
  if (typeof patch.shoulderWidth === "number") o.shoulderWidth = patch.shoulderWidth;
  if (typeof patch.chest === "number") o.chest = patch.chest;
  if (typeof patch.waist === "number") o.waist = patch.waist;
  if (typeof patch.hips === "number") o.hips = patch.hips;
  if (typeof patch.armThickness === "number") o.armThickness = patch.armThickness;
  if (typeof patch.legThickness === "number") o.legThickness = patch.legThickness;
  if (typeof patch.torsoLength === "number") o.torsoLength = patch.torsoLength;
  if (typeof patch.build === "number") o.build = patch.build;
  return o;
}

/**
 * Derived mesh-friendly values for procedural body + clipping proxies.
 * Single source so live body and clip spheres stay aligned.
 */
export type BodyRigMetrics = {
  pelvisY: number;
  chestY: number;
  shoulderY: number;
  headY: number;
  shoulderHalf: number;
  /** World-space top of torso capsule (in avatar root space). */
  torsoTopY: number;
  /** World-space bottom of neck / top of torso (clavicle insertion band). */
  neckBaseY: number;
  /** Hip joint Y offset inside pelvis group (negative = below pelvis origin). */
  hipPitchLocalY: number;
  /** World-space bottom of torso capsule (avatar root). */
  torsoBotY: number;
  /** World-space top of pelvis box (avatar root). */
  pelvisTopY: number;
  /** Acromion half-span (parametric cap); scene `shoulderHalf` is usually tighter `armBind`. */
  acromionHalf: number;
  pelvisBox: [number, number, number];
  torsoCapsuleRadius: number;
  torsoCapsuleLength: number;
  neckCylinder: [number, number, number];
  headRadius: number;
  upperArmCapsule: [number, number];
  /** Forearm capsule [radius, length] (elbow→wrist). */
  forearmCapsule: [number, number];
  armMeshOffsetX: number;
  upperLegCapsule: [number, number];
  /** Shin capsule [radius, length] below knee. */
  shinCapsule: [number, number];
  legMeshOffsetX: number;
  legGroupOffsetX: number;
  /** GLTF body root scale (approximate parametric response). */
  gltfBodyScale: [number, number, number];
  /** Normalized height target after shape (for loader). */
  gltfNormalizeY: number;
};

function clamp(n: number, lo: number, hi: number) {
  return Math.min(hi, Math.max(lo, n));
}

export function deriveBodyRigMetrics(b: BodyShapeParams): BodyRigMetrics {
  const H = clamp(b.height, 0.88, 1.12);
  const sw = clamp(b.shoulderWidth, 0.82, 1.22);
  const ch = clamp(b.chest, 0.82, 1.25);
  const w = clamp(b.waist, 0.82, 1.2);
  const hp = clamp(b.hips, 0.82, 1.28);
  const arm = clamp(b.armThickness, 0.82, 1.25);
  const leg = clamp(b.legThickness, 0.82, 1.25);
  const tl = clamp(b.torsoLength, 0.88, 1.15);
  const bd = clamp(b.build, 0.88, 1.15);

  const torsoStretch = H * (0.92 + 0.08 * tl);
  const chestY = RIG.chestY * torsoStretch * (0.97 + 0.03 * tl);

  const pelvisW = 0.262 * w * hp * bd;
  const pelvisH = 0.152 * bd;
  const pelvisD = 0.192 * hp * bd;
  const pelvisBox: [number, number, number] = [pelvisW, pelvisH, pelvisD];

  const torsoR = 0.114 * ch * bd;
  const torsoLen = 0.368 * tl * bd;
  const torsoTopY = chestY + torsoLen * 0.5;
  const torsoBotY = chestY - torsoLen * 0.5;

  /**
   * Pelvis top meets torso bottom with a small intentional overlap so the midsection
   * reads as one unit (no floating hips, no huge torso–pelvis gap).
   */
  const pelvisTorsoOverlap = 0.022 * bd + 0.012 * tl + 0.006 * ch;
  const pelvisY = torsoBotY + pelvisTorsoOverlap - pelvisH * 0.5;
  const pelvisTopY = pelvisY + pelvisH * 0.5;

  /** Hip pivot: upper–mid pelvis (thighs leave the hip block, not the pelvis floor). */
  const hipPitchLocalY = -pelvisH * (0.22 + 0.06 * hp) - 0.006 * bd;

  /** Shoulder bind lowered vs torso top so arms meet the torso, not float above it. */
  const shoulderLift = 0.02 * H * bd + 0.005 * sw;
  const shoulderY = torsoTopY + shoulderLift;

  const neckRt = 0.062 * ch * bd;
  const neckRb = 0.08 * ch * bd;
  const neckH = 0.09 * (0.96 + 0.04 * tl);
  const neckBaseY = torsoTopY - 0.007 * ch * bd;
  const headR = 0.101 * bd * (0.97 + 0.03 * H);
  const headY = neckBaseY + neckH + headR * 0.72;

  const armRad = 0.051 * arm * bd;
  const upperArmLen = 0.332 * bd;
  const forearmLen = 0.278 * bd;
  const forearmRad = armRad * 0.93;
  const armMeshX = 0.108 * (0.93 + 0.07 * arm);

  const acromionHalf = RIG.shoulderHalf * sw;
  const armBindMedial = torsoR + armRad * 0.66;
  const shoulderHalf = Math.min(
    acromionHalf,
    Math.max(armBindMedial, acromionHalf * 0.78),
  );

  const legRad = 0.066 * leg * hp * bd;
  const thighLen = 0.428 * bd;
  const shinLen = 0.382 * bd;
  const shinRad = legRad * 0.9;
  const legMeshX = 0.017 * (0.9 + 0.1 * hp);
  const legGroupX = 0.07 * (0.86 + 0.14 * hp);

  const gx = sw * 0.55 + ch * 0.45;
  const gy = H * bd;
  const gz = hp * 0.4 + w * 0.35 + bd * 0.25;
  const gltfNormalizeY = 1.85 * H * bd;

  return {
    pelvisY,
    chestY,
    shoulderY,
    headY,
    shoulderHalf,
    torsoTopY,
    neckBaseY,
    hipPitchLocalY,
    torsoBotY,
    pelvisTopY,
    acromionHalf,
    pelvisBox,
    torsoCapsuleRadius: torsoR,
    torsoCapsuleLength: torsoLen,
    neckCylinder: [neckRt, neckRb, neckH],
    headRadius: headR,
    upperArmCapsule: [armRad, upperArmLen],
    forearmCapsule: [forearmRad, forearmLen],
    armMeshOffsetX: armMeshX,
    upperLegCapsule: [legRad, thighLen],
    shinCapsule: [shinRad, shinLen],
    legMeshOffsetX: legMeshX,
    legGroupOffsetX: legGroupX,
    gltfBodyScale: [gx, gy, gz],
    gltfNormalizeY,
  };
}

/** Scene anchors + metrics: single object for procedural mesh, GLB mounts, and clipping proxies. */
export type BodySceneAnchors = {
  pelvisY: number;
  chestY: number;
  shoulderY: number;
  shoulderHalf: number;
  headY: number;
  /** Procedural pants proxy / hem reference Y (standing). */
  pantsProxyHemY: number;
  /** GLB shirt parent offset under garment top anchor. */
  gltfTopMountY: number;
  /** GLB pants parent offset under garment bottom anchor. */
  gltfBottomMountY: number;
  metrics: BodyRigMetrics;
};

const REF_PANTS_HEM = 0.56;
const REF_GLTF_TOP = 1.12;
const REF_GLTF_BOTTOM = 0.44;

/** Reference rig for garment mount ratios (default shape, after full derivation). */
export const BODY_SHAPE_REF_METRICS: BodyRigMetrics =
  deriveBodyRigMetrics(DEFAULT_BODY_SHAPE);

export function bodySceneAnchorsFromShape(b: BodyShapeParams): BodySceneAnchors {
  const m = deriveBodyRigMetrics(b);
  const refP = BODY_SHAPE_REF_METRICS.pelvisY;
  const refC = BODY_SHAPE_REF_METRICS.chestY;
  return {
    pelvisY: m.pelvisY,
    chestY: m.chestY,
    shoulderY: m.shoulderY,
    shoulderHalf: m.shoulderHalf,
    headY: m.headY,
    pantsProxyHemY: (REF_PANTS_HEM * m.pelvisY) / refP,
    gltfTopMountY: REF_GLTF_TOP + (m.chestY - refC),
    gltfBottomMountY: REF_GLTF_BOTTOM + (m.pelvisY - refP),
    metrics: m,
  };
}

export type BodyShapePresetId =
  | "slim"
  | "regular"
  | "broad_shoulders"
  | "curvy"
  | "athletic"
  | "short"
  | "tall";

export const BODY_SHAPE_PRESET_LABELS: Record<BodyShapePresetId, string> = {
  slim: "Slim",
  regular: "Regular",
  broad_shoulders: "Broad shoulders",
  curvy: "Curvy / wider hips",
  athletic: "Athletic",
  short: "Short",
  tall: "Tall",
};

export const BODY_SHAPE_PRESETS: Record<BodyShapePresetId, BodyShapeParams> = {
  slim: {
    ...DEFAULT_BODY_SHAPE,
    chest: 0.9,
    waist: 0.92,
    hips: 0.9,
    armThickness: 0.9,
    legThickness: 0.9,
    build: 0.92,
  },
  regular: { ...DEFAULT_BODY_SHAPE },
  broad_shoulders: {
    ...DEFAULT_BODY_SHAPE,
    shoulderWidth: 1.14,
    chest: 1.08,
    armThickness: 1.06,
    build: 1.04,
  },
  curvy: {
    ...DEFAULT_BODY_SHAPE,
    waist: 0.94,
    hips: 1.12,
    legThickness: 1.05,
    chest: 1.04,
  },
  athletic: {
    ...DEFAULT_BODY_SHAPE,
    chest: 1.06,
    shoulderWidth: 1.06,
    armThickness: 1.1,
    legThickness: 1.08,
    build: 1.06,
  },
  short: {
    ...DEFAULT_BODY_SHAPE,
    height: 0.92,
    torsoLength: 0.94,
    legThickness: 0.95,
  },
  tall: {
    ...DEFAULT_BODY_SHAPE,
    height: 1.08,
    torsoLength: 1.06,
    legThickness: 1.04,
  },
};
