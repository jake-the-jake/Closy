/**
 * Lightweight garment pose follow (CPU, no cloth sim).
 *
 * Uses weighted pivot rotations in mesh-local space to approximate linear-blend
 * skinning for tops/bottoms when meshes are not parented under body bones (esp. GLTF).
 *
 * Bind pose: `relaxed` (see `poseAngles`). Order with fit: pose warp from rest → then regional fit offsets.
 */

import * as THREE from "three";

import type { BodySceneAnchors } from "@/features/avatar-export";
import type { DevAvatarPoseKey } from "@/features/avatar-export/dev-avatar-shared";

import { poseAngles, type PoseAngleSet } from "./avatar-pose-angles";

const _e = new THREE.Euler();
const _v = new THREE.Vector3();
const _v2 = new THREE.Vector3();
const _acc = new THREE.Vector3();

export type GarmentPoseSkinningParams = {
  rig: BodySceneAnchors;
  /** Bind joint angles (typically relaxed). */
  angBind: PoseAngleSet;
  /** Current pose angles. */
  angPose: PoseAngleSet;
};

export const GARMENT_POSE_BIND_POSE: DevAvatarPoseKey = "relaxed";

/** Full shoulder + upper-arm chain (matches `ProceduralRigBody` group order, XYZ Euler). */
export function armChainMatrix(
  side: 1 | -1,
  rig: BodySceneAnchors,
  ang: PoseAngleSet,
): THREE.Matrix4 {
  const shx = side * rig.shoulderHalf;
  const shy = rig.shoulderY;
  const laxz = side === 1 ? ang.laxz : -ang.laxz;
  const laz = side === 1 ? ang.laz : ang.raz;
  const lax = side === 1 ? ang.lax : -ang.rax;

  const mPos = new THREE.Matrix4().makeTranslation(shx, shy, 0);
  _e.set(laxz, 0, laz, "XYZ");
  const m1 = new THREE.Matrix4().makeRotationFromEuler(_e);
  _e.set(0, 0, lax, "XYZ");
  const m2 = new THREE.Matrix4().makeRotationFromEuler(_e);
  return new THREE.Matrix4().multiplyMatrices(mPos, m1).multiply(m2);
}

/** M_pose * inverse(M_bind) — rigid skin delta for the upper arm. */
export function upperArmSkinMatrix(
  side: 1 | -1,
  rig: BodySceneAnchors,
  angBind: PoseAngleSet,
  angPose: PoseAngleSet,
): THREE.Matrix4 {
  const bind = armChainMatrix(side, rig, angBind);
  const pose = armChainMatrix(side, rig, angPose);
  return new THREE.Matrix4().multiplyMatrices(pose, new THREE.Matrix4().copy(bind).invert());
}

/** Hip flex delta: rotation X around thigh root (matches procedural leg groups). */
export function thighSkinMatrix(
  side: 1 | -1,
  rig: BodySceneAnchors,
  angBind: PoseAngleSet,
  angPose: PoseAngleSet,
): THREE.Matrix4 {
  const M = rig.metrics;
  const lx = side === 1 ? M.legGroupOffsetX : -M.legGroupOffsetX;
  const ly = rig.pelvisY + M.hipPitchLocalY;
  const rxBind = side === 1 ? angBind.llx : angBind.rlx;
  const rxPose = side === 1 ? angPose.llx : angPose.rlx;
  const d = rxPose - rxBind;

  const tP = new THREE.Matrix4().makeTranslation(lx, ly, 0);
  const tN = new THREE.Matrix4().makeTranslation(-lx, -ly, 0);
  const rX = new THREE.Matrix4().makeRotationX(d);
  return new THREE.Matrix4().multiplyMatrices(tP, rX).multiply(tN);
}

function smoothstep(edge0: number, edge1: number, x: number): number {
  const t = Math.max(0, Math.min(1, (x - edge0) / (edge1 - edge0 + 1e-8)));
  return t * t * (3 - 2 * t);
}

/** Torso / sleeve weights in mesh space (aligned with `applyTopGarmentDeformation` masks). */
function topPoseWeights(
  ox: number,
  oy: number,
  oz: number,
  min: THREE.Vector3,
  max: THREE.Vector3,
  size: THREE.Vector3,
): { wTorso: number; wSL: number; wSR: number } {
  const cx = (min.x + max.x) * 0.5;
  const cz = (min.z + max.z) * 0.5;
  const sy = Math.max(size.y, 1e-6);
  const sx = Math.max(size.x, 1e-6);
  const ny = (oy - min.y) / sy;
  const ax = Math.abs(ox - cx) / (sx * 0.5 + 1e-6);

  const wTorsoCore =
    (1 - smoothstep(0.22, 0.55, ax)) *
    smoothstep(0.18, 0.42, ny) *
    (1 - smoothstep(0.72, 0.96, ny));

  const wSleeve =
    smoothstep(0.28, 0.55, ax) * smoothstep(0.38, 0.62, ny) * (1 - smoothstep(0.78, 0.98, ny));

  const sideL = ox >= cx ? 1 : 0;
  const sideR = ox < cx ? 1 : 0;
  const wSL = wSleeve * sideL;
  const wSR = wSleeve * sideR;

  return { wTorso: wTorsoCore, wSL, wSR };
}

/**
 * Pose-only warp for a top mesh (run before regional fit offsets).
 * `bases` = rest positions; writes `out` (same length).
 */
export function applyTopGarmentPoseSkinning(
  bases: Float32Array,
  out: Float32Array,
  min: THREE.Vector3,
  max: THREE.Vector3,
  size: THREE.Vector3,
  skin: GarmentPoseSkinningParams,
): void {
  const mL = upperArmSkinMatrix(1, skin.rig, skin.angBind, skin.angPose);
  const mR = upperArmSkinMatrix(-1, skin.rig, skin.angBind, skin.angPose);

  for (let i = 0; i < bases.length; i += 3) {
    const ox = bases[i];
    const oy = bases[i + 1];
    const oz = bases[i + 2];
    _v.set(ox, oy, oz);
    const { wTorso, wSL, wSR } = topPoseWeights(ox, oy, oz, min, max, size);
    const wSum = wTorso + wSL + wSR;
    if (wSum < 1e-6) {
      out[i] = ox;
      out[i + 1] = oy;
      out[i + 2] = oz;
      continue;
    }
    _acc.set(0, 0, 0);
    _acc.addScaledVector(_v, wTorso);
    if (wSL > 1e-6) {
      _v2.copy(_v).applyMatrix4(mL);
      _acc.addScaledVector(_v2, wSL);
    }
    if (wSR > 1e-6) {
      _v2.copy(_v).applyMatrix4(mR);
      _acc.addScaledVector(_v2, wSR);
    }
    _acc.multiplyScalar(1 / wSum);
    out[i] = _acc.x;
    out[i + 1] = _acc.y;
    out[i + 2] = _acc.z;
  }
}

function bottomPoseWeights(
  ox: number,
  oy: number,
  min: THREE.Vector3,
  max: THREE.Vector3,
  size: THREE.Vector3,
): { wWaist: number; wLegL: number; wLegR: number } {
  const cx = (min.x + max.x) * 0.5;
  const sy = Math.max(size.y, 1e-6);
  const ny = (oy - min.y) / sy;

  const wWaist =
    smoothstep(0.45, 0.58, ny) * (1 - smoothstep(0.58, 0.72, ny));

  const wLeg = smoothstep(0.15, 0.45, ny) * (1 - smoothstep(0.65, 0.92, ny));

  const sideL = ox >= cx ? 1 : 0;
  const sideR = ox < cx ? 1 : 0;

  return {
    wWaist,
    wLegL: wLeg * sideL,
    wLegR: wLeg * sideR,
  };
}

export function applyBottomGarmentPoseSkinning(
  bases: Float32Array,
  out: Float32Array,
  min: THREE.Vector3,
  max: THREE.Vector3,
  size: THREE.Vector3,
  skin: GarmentPoseSkinningParams,
): void {
  const mL = thighSkinMatrix(1, skin.rig, skin.angBind, skin.angPose);
  const mR = thighSkinMatrix(-1, skin.rig, skin.angBind, skin.angPose);

  for (let i = 0; i < bases.length; i += 3) {
    const ox = bases[i];
    const oy = bases[i + 1];
    const oz = bases[i + 2];
    _v.set(ox, oy, oz);
    const { wWaist, wLegL, wLegR } = bottomPoseWeights(ox, oy, min, max, size);
    const wSum = wWaist + wLegL + wLegR;
    if (wSum < 1e-6) {
      out[i] = ox;
      out[i + 1] = oy;
      out[i + 2] = oz;
      continue;
    }
    _acc.set(0, 0, 0);
    _acc.addScaledVector(_v, wWaist);
    if (wLegL > 1e-6) {
      _v2.copy(_v).applyMatrix4(mL);
      _acc.addScaledVector(_v2, wLegL);
    }
    if (wLegR > 1e-6) {
      _v2.copy(_v).applyMatrix4(mR);
      _acc.addScaledVector(_v2, wLegR);
    }
    _acc.multiplyScalar(1 / wSum);
    out[i] = _acc.x;
    out[i + 1] = _acc.y;
    out[i + 2] = _acc.z;
  }
}

/** Extra twist on sleeve capsule verts around mesh X (approx upper-arm roll). */
export function applySleeveGarmentPoseSkinning(
  bases: Float32Array,
  out: Float32Array,
  min: THREE.Vector3,
  max: THREE.Vector3,
  size: THREE.Vector3,
  side: 1 | -1,
  skin: GarmentPoseSkinningParams,
): void {
  const mArm = upperArmSkinMatrix(side, skin.rig, skin.angBind, skin.angPose);
  const cx = (min.x + max.x) * 0.5;
  const cy = (min.y + max.y) * 0.5;
  const cz = (min.z + max.z) * 0.5;

  const sx = Math.max(size.x, 1e-6);
  const sy = Math.max(size.y, 1e-6);
  for (let i = 0; i < bases.length; i += 3) {
    const ox = bases[i];
    const oy = bases[i + 1];
    const oz = bases[i + 2];
    const tArm = Math.abs(ox - cx) / (sx * 0.5 + 1e-6);
    const ny = (oy - min.y) / sy;
    const w = smoothstep(0.15, 0.85, tArm) * smoothstep(0.1, 0.9, ny);

    _v.set(ox, oy, oz);
    _v2.copy(_v).applyMatrix4(mArm);
    out[i] = ox + (_v2.x - ox) * w;
    out[i + 1] = oy + (_v2.y - oy) * w;
    out[i + 2] = oz + (_v2.z - oz) * w;
  }
}
