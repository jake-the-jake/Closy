/**
 * Align normalized skinned mesh (feet ~y=0) vertically so pelvis band matches shared rig `pelvisY`.
 * CesiumMan–specific ratio is approximate; keeps one coherent figure vs procedural anchors.
 */

import * as THREE from "three";

import type { BodyRigMetrics } from "@/features/avatar-export";

/** Estimated pelvis height as fraction of total height above feet (bind pose, post-normalize). */
const PELVIS_HEIGHT_FRAC = 0.47;

/**
 * After `normalizeRootToHeight`, nudge root so estimated pelvis Y matches `metrics.pelvisY`
 * (scene space matches procedural rig).
 */
export function alignSkinnedRootToPelvisMetric(root: THREE.Object3D, metrics: BodyRigMetrics) {
  root.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(root);
  const h = box.max.y - box.min.y;
  if (h < 1e-4) return;
  const estPelvisY = box.min.y + h * PELVIS_HEIGHT_FRAC;
  const dy = metrics.pelvisY - estPelvisY;
  root.position.y += dy;
}
