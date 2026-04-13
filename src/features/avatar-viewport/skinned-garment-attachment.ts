/**
 * Derives garment anchor points in `avatar_torso_region_fit` local space from the
 * posed skinned mesh skeleton (CesiumMan map). Used to seat proxies/GLB parents on
 * the actual body instead of only shared rig scalars + static nudges.
 */

import * as THREE from "three";

import type { BodySceneAnchors } from "@/features/avatar-export";

import {
  findFirstSkinnedMesh,
  resolveSkinnedBodyBones,
  type ResolvedSkinnedBones,
} from "./skinned-body-pose";

const _w = new THREE.Vector3();
const _a = new THREE.Vector3();
const _b = new THREE.Vector3();
const _invParent = new THREE.Matrix4();

export type SkinnedGarmentAttachmentPoints = {
  shoulderL: THREE.Vector3;
  shoulderR: THREE.Vector3;
  chest: THREE.Vector3;
  pelvisTop: THREE.Vector3;
  hipMid: THREE.Vector3;
};

function boneWorldToParentLocal(
  parent: THREE.Object3D,
  bone: THREE.Bone,
  out: THREE.Vector3,
): void {
  bone.getWorldPosition(out);
  _invParent.copy(parent.matrixWorld).invert();
  out.applyMatrix4(_invParent);
}

function chestFromBones(
  parent: THREE.Object3D,
  bones: ResolvedSkinnedBones,
  out: THREE.Vector3,
): void {
  if (bones.spineUpper && bones.neck1) {
    bones.spineUpper.getWorldPosition(_a);
    bones.neck1.getWorldPosition(_b);
    out.copy(_a).multiplyScalar(0.58).addScaledVector(_b, 0.42);
  } else if (bones.spineUpper) {
    bones.spineUpper.getWorldPosition(out);
  } else if (bones.spineLower) {
    bones.spineLower.getWorldPosition(out);
    out.y += 0.08;
  } else {
    out.set(0, 1.15, 0.02);
  }
  _invParent.copy(parent.matrixWorld).invert();
  out.applyMatrix4(_invParent);
}

/**
 * Returns attachment points in **parent** space (typically `avatar_torso_region_fit`).
 * Updates `parent.matrixWorld` first; call after body pose / skeleton update.
 */
export function computeSkinnedGarmentAttachmentPoints(
  parent: THREE.Object3D,
  bodyRoot: THREE.Object3D,
  rig: BodySceneAnchors,
): { points: SkinnedGarmentAttachmentPoints; bones: ResolvedSkinnedBones } | null {
  parent.updateMatrixWorld(true);
  bodyRoot.updateMatrixWorld(true);
  const skinned = findFirstSkinnedMesh(bodyRoot);
  if (!skinned?.skeleton) return null;
  const bones = resolveSkinnedBodyBones(skinned.skeleton);
  const fb = rigFallbackAttachmentPoints(rig);

  const shoulderL = new THREE.Vector3();
  const shoulderR = new THREE.Vector3();
  const chest = new THREE.Vector3();
  const pelvisTop = new THREE.Vector3();
  const hipMid = new THREE.Vector3();

  if (bones.armL_shoulder) boneWorldToParentLocal(parent, bones.armL_shoulder, shoulderL);
  else shoulderL.copy(fb.shoulderL);

  if (bones.armR_shoulder) boneWorldToParentLocal(parent, bones.armR_shoulder, shoulderR);
  else shoulderR.copy(fb.shoulderR);

  chestFromBones(parent, bones, chest);
  if (!bones.spineUpper && !bones.spineLower) chest.copy(fb.chest);

  const rootBone = bones.root ?? bones.spineLower;
  if (rootBone) boneWorldToParentLocal(parent, rootBone, pelvisTop);
  else pelvisTop.set(0, 0.98, 0);

  if (bones.legL_hip && bones.legR_hip) {
    bones.legL_hip.getWorldPosition(_a);
    bones.legR_hip.getWorldPosition(_b);
    hipMid.copy(_a).add(_b).multiplyScalar(0.5);
    hipMid.applyMatrix4(_invParent.copy(parent.matrixWorld).invert());
  } else {
    hipMid.copy(pelvisTop);
    hipMid.y -= 0.04;
  }

  return {
    points: { shoulderL, shoulderR, chest, pelvisTop, hipMid },
    bones,
  };
}

/** Rig-only fallback in parent space when skinned mesh is unavailable. */
export function rigFallbackAttachmentPoints(rig: BodySceneAnchors): SkinnedGarmentAttachmentPoints {
  const { shoulderHalf, shoulderY, chestY } = rig;
  const M = rig.metrics;
  const hipY = rig.pelvisY + M.hipPitchLocalY;
  return {
    shoulderL: new THREE.Vector3(shoulderHalf, shoulderY, 0),
    shoulderR: new THREE.Vector3(-shoulderHalf, shoulderY, 0),
    chest: new THREE.Vector3(0, chestY + M.torsoCapsuleLength * 0.06, 0.02),
    pelvisTop: new THREE.Vector3(0, rig.pelvisY + 0.04, 0),
    hipMid: new THREE.Vector3(0, hipY, 0),
  };
}
