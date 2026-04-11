/**
 * Thin adapter: map shared `poseAngles` + optional shape scaling onto a skinned skeleton.
 * First-class support for Khronos CesiumMan bone naming; fuzzy fallback for common Mixamo-style names.
 */

import * as THREE from "three";

import type { BodyRigMetrics } from "@/features/avatar-export";
import { BODY_SHAPE_REF_METRICS } from "@/features/avatar-export";

import type { PoseAngleSet } from "./avatar-pose-angles";

const _e = new THREE.Euler(0, 0, 0, "XYZ");
const _q = new THREE.Quaternion();

/** Canonical slots → exact names on CesiumMan.glb (see Khronos sample). */
export const CESIUM_MAN_BONE_MAP = {
  root: "Skeleton_torso_joint_1",
  spineLower: "Skeleton_torso_joint_2",
  spineUpper: "torso_joint_3",
  neck1: "Skeleton_neck_joint_1",
  neck2: "Skeleton_neck_joint_2",
  armL_shoulder: "Skeleton_arm_joint_L__4_",
  armL_upper: "Skeleton_arm_joint_L__3_",
  armL_fore: "Skeleton_arm_joint_L__2_",
  armR_shoulder: "Skeleton_arm_joint_R",
  armR_upper: "Skeleton_arm_joint_R__2_",
  armR_fore: "Skeleton_arm_joint_R__3_",
  legL_hip: "leg_joint_L_1",
  legL_knee: "leg_joint_L_2",
  legL_ankle: "leg_joint_L_5",
  legR_hip: "leg_joint_R_1",
  legR_knee: "leg_joint_R_2",
  legR_ankle: "leg_joint_R_5",
} as const;

export type SkinnedBodyBoneMap = typeof CESIUM_MAN_BONE_MAP;

const MIXAMO_HINTS: Partial<Record<keyof SkinnedBodyBoneMap, string[]>> = {
  root: ["Hips", "mixamorigHips", "hip", "pelvis"],
  spineLower: ["Spine", "mixamorigSpine"],
  spineUpper: ["Spine2", "Chest", "mixamorigSpine2", "mixamorigChest"],
  neck1: ["Neck", "mixamorigNeck"],
  neck2: ["Head", "mixamorigHead"],
  armL_shoulder: ["LeftArm", "mixamorigLeftArm", "shoulder_l"],
  armL_upper: ["LeftForeArm", "mixamorigLeftForeArm"],
  armL_fore: ["LeftHand", "mixamorigLeftHand"],
  armR_shoulder: ["RightArm", "mixamorigRightArm"],
  armR_upper: ["RightForeArm", "mixamorigRightForeArm"],
  armR_fore: ["RightHand", "mixamorigRightHand"],
  legL_hip: ["LeftUpLeg", "mixamorigLeftUpLeg"],
  legL_knee: ["LeftLeg", "mixamorigLeftLeg"],
  legL_ankle: ["LeftFoot", "mixamorigLeftFoot"],
  legR_hip: ["RightUpLeg", "mixamorigRightUpLeg"],
  legR_knee: ["RightLeg", "mixamorigRightLeg"],
  legR_ankle: ["RightFoot", "mixamorigRightFoot"],
};

function boneByName(skeleton: THREE.Skeleton, name: string): THREE.Bone | null {
  const b = skeleton.bones.find((x) => x.name === name);
  return b ?? null;
}

function resolveBone(
  skeleton: THREE.Skeleton,
  slot: keyof SkinnedBodyBoneMap,
  map: SkinnedBodyBoneMap,
): THREE.Bone | null {
  const primary = boneByName(skeleton, map[slot]);
  if (primary) return primary;
  const hints = MIXAMO_HINTS[slot];
  if (hints) {
    for (const h of hints) {
      const b = boneByName(skeleton, h);
      if (b) return b;
    }
  }
  return null;
}

export type ResolvedSkinnedBones = Partial<Record<keyof SkinnedBodyBoneMap, THREE.Bone>>;

export function resolveSkinnedBodyBones(
  skeleton: THREE.Skeleton,
  map: SkinnedBodyBoneMap = CESIUM_MAN_BONE_MAP,
): ResolvedSkinnedBones {
  const out: ResolvedSkinnedBones = {};
  (Object.keys(map) as (keyof SkinnedBodyBoneMap)[]).forEach((k) => {
    const b = resolveBone(skeleton, k, map);
    if (b) out[k] = b;
  });
  return out;
}

export function captureSkeletonRestQuats(skeleton: THREE.Skeleton): Map<string, THREE.Quaternion> {
  const m = new Map<string, THREE.Quaternion>();
  for (const b of skeleton.bones) {
    m.set(b.name, b.quaternion.clone());
  }
  return m;
}

export function captureSkeletonRestScales(skeleton: THREE.Skeleton): Map<string, THREE.Vector3> {
  const m = new Map<string, THREE.Vector3>();
  for (const b of skeleton.bones) {
    m.set(b.name, b.scale.clone());
  }
  return m;
}

function setBoneDelta(
  bone: THREE.Bone,
  rest: Map<string, THREE.Quaternion>,
  ex: number,
  ey: number,
  ez: number,
) {
  const base = rest.get(bone.name);
  if (!base) return;
  _e.set(ex, ey, ez);
  _q.setFromEuler(_e);
  bone.quaternion.copy(base).multiply(_q);
}

/** Optional radians / pose tweaks so skinned mesh matches shared rig intent (CesiumMan bind differs from procedural). */
export type SkinnedPoseBias = {
  /** Extra shoulder pitch (X) on top of `laxz` — negative lowers arms. */
  shoulderDropRx?: number;
  /** Added hip flex (X) so thighs read lower / more grounded. */
  legHipPitchBoost?: number;
};

const DEFAULT_SHOULDER_DROP = -0.17;
const DEFAULT_LEG_HIP_BOOST = 0.065;

/**
 * Apply pose angles consistent with `ProceduralRigBody` / `garment-rig-pose` conventions.
 */
export function applySkinnedPoseToBones(
  bones: ResolvedSkinnedBones,
  rest: Map<string, THREE.Quaternion>,
  ang: PoseAngleSet,
  bias: SkinnedPoseBias = {},
): void {
  const kf = 0.52;
  const elbowZ = 0.32;
  const shoulderDrop = bias.shoulderDropRx ?? DEFAULT_SHOULDER_DROP;
  const legBoost = bias.legHipPitchBoost ?? DEFAULT_LEG_HIP_BOOST;

  const Lh = bones.legL_hip;
  const Rh = bones.legR_hip;
  const Lk = bones.legL_knee;
  const Rk = bones.legR_knee;
  if (Lh) setBoneDelta(Lh, rest, ang.llx + legBoost, 0, 0);
  if (Rh) setBoneDelta(Rh, rest, ang.rlx + legBoost, 0, 0);
  if (Lk) setBoneDelta(Lk, rest, -ang.llx * kf, 0, 0);
  if (Rk) setBoneDelta(Rk, rest, -ang.rlx * kf, 0, 0);

  const Las = bones.armL_shoulder;
  const Lau = bones.armL_upper;
  const Laf = bones.armL_fore;
  if (Las) setBoneDelta(Las, rest, ang.laxz + shoulderDrop, ang.laz, 0);
  if (Lau) setBoneDelta(Lau, rest, 0, 0, ang.lax);
  if (Laf) setBoneDelta(Laf, rest, 0, 0, ang.lax * elbowZ);

  const Ras = bones.armR_shoulder;
  const Rau = bones.armR_upper;
  const Raf = bones.armR_fore;
  if (Ras) setBoneDelta(Ras, rest, -ang.laxz + shoulderDrop, ang.raz, 0);
  if (Rau) setBoneDelta(Rau, rest, 0, 0, -ang.rax);
  if (Raf) setBoneDelta(Raf, rest, 0, 0, -ang.rax * elbowZ);
}

/**
 * Approximate shared body-shape metrics as local bone scales (rest × multiplier).
 * Keeps one source of truth (`deriveBodyRigMetrics`) while the mesh provides silhouette.
 */
export function applySkinnedShapeScales(
  bones: ResolvedSkinnedBones,
  restScale: Map<string, THREE.Vector3>,
  metrics: BodyRigMetrics,
  ref: BodyRigMetrics = BODY_SHAPE_REF_METRICS,
): void {
  const spineY = THREE.MathUtils.clamp(
    0.88 + 0.24 * (metrics.torsoCapsuleLength / ref.torsoCapsuleLength),
    0.86,
    1.18,
  );
  const chestXZ = THREE.MathUtils.clamp(
    0.9 + 0.2 * (metrics.torsoCapsuleRadius / ref.torsoCapsuleRadius),
    0.85,
    1.22,
  );
  const hipW = THREE.MathUtils.clamp(
    0.9 + 0.22 * (metrics.pelvisBox[0] / ref.pelvisBox[0]),
    0.84,
    1.25,
  );
  const thighT = THREE.MathUtils.clamp(
    0.9 + 0.28 * (metrics.upperLegCapsule[0] / ref.upperLegCapsule[0]),
    0.82,
    1.28,
  );
  const armT = THREE.MathUtils.clamp(
    0.9 + 0.28 * (metrics.upperArmCapsule[0] / ref.upperArmCapsule[0]),
    0.82,
    1.28,
  );

  const apply = (b: THREE.Bone | undefined, sx: number, sy: number, sz: number) => {
    if (!b) return;
    const rs = restScale.get(b.name);
    if (!rs) return;
    b.scale.set(rs.x * sx, rs.y * sy, rs.z * sz);
  };

  apply(bones.spineLower, chestXZ, spineY, chestXZ);
  apply(bones.spineUpper, chestXZ, spineY * 0.98, chestXZ);
  apply(bones.root, hipW, 1, hipW * 0.96);
  apply(bones.legL_hip, thighT, 1, thighT);
  apply(bones.legR_hip, thighT, 1, thighT);
  apply(bones.armL_shoulder, 1, 0.9, 1);
  apply(bones.armR_shoulder, 1, 0.9, 1);
  apply(bones.armL_upper, armT, 1, armT);
  apply(bones.armR_upper, armT, 1, armT);
}

export function findFirstSkinnedMesh(root: THREE.Object3D): THREE.SkinnedMesh | null {
  let found: THREE.SkinnedMesh | null = null;
  root.traverse((o) => {
    if (found) return;
    if (o instanceof THREE.SkinnedMesh && o.skeleton) found = o;
  });
  return found;
}
