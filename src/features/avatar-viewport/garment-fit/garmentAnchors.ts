import {
  buildProceduralGarmentFollowPoints,
  jointVector,
  type ProceduralHumanoidJointMap,
} from "../procedural-humanoid-v2";
import { THREE } from "../three";

export type AvatarGarmentAnchorSet = ReturnType<typeof buildProceduralGarmentFollowPoints> & {
  chest: THREE.Vector3;
  waist: THREE.Vector3;
  hip: THREE.Vector3;
  shoulderL: THREE.Vector3;
  shoulderR: THREE.Vector3;
  wristL: THREE.Vector3;
  wristR: THREE.Vector3;
  ankleL: THREE.Vector3;
  ankleR: THREE.Vector3;
  hem: THREE.Vector3;
};

/**
 * V1 garment binding layer.
 *
 * Garments should seat from named body anchors rather than free-floating world offsets.
 * This currently derives from the procedural joint map; later this function can be backed
 * by GLB bones, named empties, or body-estimation landmarks while preserving garment code.
 */
export function buildGarmentAnchorsFromProceduralJoints(
  jointMap: ProceduralHumanoidJointMap,
): AvatarGarmentAnchorSet {
  const follow = buildProceduralGarmentFollowPoints(jointMap);
  const ankleL = jointVector(jointMap, "ankleL");
  const ankleR = jointVector(jointMap, "ankleR");
  return {
    ...follow,
    chest: jointVector(jointMap, "chest"),
    waist: jointVector(jointMap, "waist"),
    hip: jointVector(jointMap, "hips"),
    shoulderL: jointVector(jointMap, "shoulderL"),
    shoulderR: jointVector(jointMap, "shoulderR"),
    wristL: jointVector(jointMap, "wristL"),
    wristR: jointVector(jointMap, "wristR"),
    ankleL,
    ankleR,
    hem: ankleL.clone().lerp(ankleR, 0.5),
  };
}
