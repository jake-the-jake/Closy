import { THREE } from "../three";
import type { BodyAnchorMap } from "./bodyAnchors";

export type SolvedGarmentFit = {
  topCenter: [number, number, number];
  topScale: [number, number, number];
  bottomCenter: [number, number, number];
  bottomScale: [number, number, number];
  sleeveLStart: [number, number, number];
  sleeveRStart: [number, number, number];
  reliable: boolean;
};

function vecToArray(v: THREE.Vector3): [number, number, number] {
  return [v.x, v.y, v.z];
}

function midpoint(a: THREE.Vector3, b: THREE.Vector3): THREE.Vector3 {
  return a.clone().lerp(b, 0.5);
}

/**
 * First-pass garment seating solve.
 *
 * This intentionally stays transform-based: shirt, sleeves, and bottoms follow named
 * body anchors now, while future GLB garment skinning can replace these proxy scales.
 */
export function solveGarmentFitFromBodyAnchors(anchors: BodyAnchorMap): SolvedGarmentFit {
  const chest = anchors.chest ?? new THREE.Vector3(0, 1.26, 0);
  const waist = anchors.waist ?? new THREE.Vector3(0, 0.95, 0);
  const hips = anchors.hips ?? new THREE.Vector3(0, 0.82, 0);
  const shoulderL = anchors.shoulderL ?? new THREE.Vector3(-0.34, 1.36, 0);
  const shoulderR = anchors.shoulderR ?? new THREE.Vector3(0.34, 1.36, 0);
  const hipL = anchors.hipL ?? new THREE.Vector3(-0.16, 0.78, 0);
  const hipR = anchors.hipR ?? new THREE.Vector3(0.16, 0.78, 0);
  const ankleL = anchors.ankleL ?? new THREE.Vector3(-0.13, 0.08, 0);
  const ankleR = anchors.ankleR ?? new THREE.Vector3(0.13, 0.08, 0);

  const shoulderSpan = shoulderL.distanceTo(shoulderR);
  const hipSpan = hipL.distanceTo(hipR);
  const torsoHeight = Math.max(0.28, chest.y - waist.y + 0.18);
  const legHeight = Math.max(0.55, hips.y - midpoint(ankleL, ankleR).y);

  return {
    topCenter: vecToArray(chest.clone().lerp(waist, 0.58)),
    topScale: [shoulderSpan * 1.08, torsoHeight, 0.2],
    bottomCenter: vecToArray(hips.clone().lerp(midpoint(ankleL, ankleR), 0.35)),
    bottomScale: [Math.max(hipSpan * 1.18, 0.34), legHeight, 0.18],
    sleeveLStart: vecToArray(shoulderL),
    sleeveRStart: vecToArray(shoulderR),
    reliable: Boolean(
      anchors.chest &&
        anchors.waist &&
        anchors.hips &&
        anchors.shoulderL &&
        anchors.shoulderR,
    ),
  };
}
