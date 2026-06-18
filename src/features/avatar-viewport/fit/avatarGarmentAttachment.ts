import { solveGarmentFitFromBodyAnchors, type SolvedGarmentFit } from "../garment-fit/garmentFitSolver";
import type { BodyAnchorMap } from "../garment-fit/bodyAnchors";
import type { AvatarBodyLandmarks } from "./avatarBodyLandmarks";
import { THREE } from "../three";

export type AvatarGarmentAttachmentSolve = SolvedGarmentFit & {
  landmarkSource: AvatarBodyLandmarks["source"] | "procedural";
};

export function solveAvatarGarmentAttachment(
  landmarks: AvatarBodyLandmarks | BodyAnchorMap,
): AvatarGarmentAttachmentSolve {
  const source = "source" in landmarks ? landmarks.source : "procedural";
  const anchors: BodyAnchorMap = "source" in landmarks
    ? {
        head: new THREE.Vector3(...landmarks.head),
        neck: new THREE.Vector3(...landmarks.neck),
        chest: new THREE.Vector3(...landmarks.chest),
        waist: new THREE.Vector3(...landmarks.waist),
        hips: new THREE.Vector3(...landmarks.hips),
        shoulderL: new THREE.Vector3(...landmarks.shoulderL),
        shoulderR: new THREE.Vector3(...landmarks.shoulderR),
        elbowL: new THREE.Vector3(...landmarks.elbowL),
        elbowR: new THREE.Vector3(...landmarks.elbowR),
        wristL: new THREE.Vector3(...landmarks.wristL),
        wristR: new THREE.Vector3(...landmarks.wristR),
        hipL: new THREE.Vector3(...landmarks.thighL),
        hipR: new THREE.Vector3(...landmarks.thighR),
        kneeL: new THREE.Vector3(...landmarks.kneeL),
        kneeR: new THREE.Vector3(...landmarks.kneeR),
        ankleL: new THREE.Vector3(...landmarks.ankleL),
        ankleR: new THREE.Vector3(...landmarks.ankleR),
        footL: new THREE.Vector3(...landmarks.footL),
        footR: new THREE.Vector3(...landmarks.footR),
      }
    : landmarks;
  return {
    ...solveGarmentFitFromBodyAnchors(anchors),
    landmarkSource: source,
  };
}
