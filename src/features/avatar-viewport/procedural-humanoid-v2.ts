import * as THREE from "three";

import type { BodySceneAnchors } from "@/features/avatar-export";

import type { PoseAngleSet } from "./avatar-pose-angles";

/**
 * Temporary procedural development mannequin.
 *
 * This keeps Avatar preview immediately visible and poseable while the longer-term
 * path remains:
 * - SMPL-style parametric body model
 * - MediaPipe/OpenPose-style body keypoints and optional image/body estimation
 * - image-to-avatar reconstruction
 * - garment segmentation / fitting pipeline
 * - later cloth simulation or learned garment deformation
 * - later native renderer or server-side avatar generation
 */
export const PROCEDURAL_AVATAR_MODEL_ID = "proceduralHumanoidV3" as const;
export const PROCEDURAL_GARMENT_FOLLOW_MODE = "weightedJointBlendV1" as const;
export const PROCEDURAL_PROPORTIONS_VERSION = "mannequin_v1" as const;
export const PROCEDURAL_HUMANOID_JOINTS = [
  "pelvis",
  "spine",
  "chest",
  "neck",
  "head",
  "shoulderL",
  "elbowL",
  "wristL",
  "shoulderR",
  "elbowR",
  "wristR",
  "hipL",
  "kneeL",
  "ankleL",
  "hipR",
  "kneeR",
  "ankleR",
] as const;

export type ProceduralHumanoidJointName = (typeof PROCEDURAL_HUMANOID_JOINTS)[number];
export type ProceduralHumanoidJointMap = Record<
  ProceduralHumanoidJointName,
  [number, number, number]
>;

export const PROCEDURAL_HUMANOID_JOINT_COUNT = PROCEDURAL_HUMANOID_JOINTS.length;
export const PROCEDURAL_HUMANOID_BODY_PART_COUNT = 19;
export const PROCEDURAL_HUMANOID_GARMENT_PART_COUNT = 8;

export const HUMANOID_PROPORTIONS = {
  version: PROCEDURAL_PROPORTIONS_VERSION,
  totalHeight: 1.78,
  groundY: 0,
  headRadius: 0.118,
  headScale: [1, 1.08, 0.98] as [number, number, number],
  neckRadius: 0.046,
  shoulderHalf: 0.242,
  hipHalf: 0.156,
  chestY: 1.33,
  neckY: 1.49,
  headY: 1.645,
  shoulderY: 1.435,
  spineY: 1.16,
  pelvisY: 0.95,
  hipY: 0.915,
  kneeY: 0.5,
  ankleY: 0.095,
  chestWidth: 0.33,
  chestDepth: 0.2,
  chestHeight: 0.245,
  abdomenWidth: 0.265,
  abdomenDepth: 0.17,
  abdomenHeight: 0.205,
  pelvisWidth: 0.305,
  pelvisDepth: 0.195,
  pelvisHeight: 0.16,
  shoulderCapScale: [0.072, 0.055, 0.06] as [number, number, number],
  upperArmLength: 0.355,
  forearmLength: 0.305,
  upperArmRadius: 0.05,
  forearmRadius: 0.041,
  thighLength: 0.44,
  calfLength: 0.42,
  thighRadius: 0.078,
  calfRadius: 0.058,
  handScale: [0.05, 0.072, 0.04] as [number, number, number],
  footScale: [0.08, 0.038, 0.17] as [number, number, number],
  topShellScale: [0.36, 0.29, 0.22] as [number, number, number],
  bottomShellScale: [0.31, 0.23, 0.2] as [number, number, number],
} as const;

function rotateOffset(
  offset: THREE.Vector3,
  x: number,
  y: number,
  z: number,
): THREE.Vector3 {
  return offset.clone().applyEuler(new THREE.Euler(x, y, z, "XYZ"));
}

function asTuple(v: THREE.Vector3): [number, number, number] {
  return [v.x, v.y, v.z];
}

function average(...points: THREE.Vector3[]): THREE.Vector3 {
  const out = new THREE.Vector3();
  for (const point of points) out.add(point);
  return out.multiplyScalar(1 / Math.max(1, points.length));
}

/**
 * Lightweight FK rig for the stylized mannequin. Limbs intentionally bias toward
 * readable, connected shapes over anatomical accuracy.
 */
export function buildProceduralHumanoidJointMap(
  rig: BodySceneAnchors,
  ang: PoseAngleSet,
): ProceduralHumanoidJointMap {
  void rig;
  const P = HUMANOID_PROPORTIONS;

  const pelvis = new THREE.Vector3(0, P.pelvisY, 0);
  const spine = new THREE.Vector3(0, P.spineY, 0.008 + ang.spineRx * 0.03);
  const chest = new THREE.Vector3(0, P.chestY, 0.018 + ang.spineUpperRx * 0.04);
  const neck = new THREE.Vector3(0, P.neckY, 0.028 + ang.neckRx * 0.025);
  const head = new THREE.Vector3(0, P.headY, 0.04 + ang.neckRx * 0.025);

  const shoulderL = new THREE.Vector3(P.shoulderHalf, P.shoulderY, 0.012);
  const shoulderR = new THREE.Vector3(-P.shoulderHalf, P.shoulderY, 0.012);

  const elbowL = shoulderL
    .clone()
    .add(
      rotateOffset(
        new THREE.Vector3(0.034, -P.upperArmLength, 0.012),
        ang.laxz * 0.7,
        ang.spineTwistY * 0.16,
        ang.laz + ang.lax * 0.55,
      ),
    );
  const elbowR = shoulderR
    .clone()
    .add(
      rotateOffset(
        new THREE.Vector3(-0.034, -P.upperArmLength, 0.012),
        -ang.laxz * 0.7,
        -ang.spineTwistY * 0.16,
        ang.raz - ang.rax * 0.55,
      ),
    );
  const wristL = elbowL
    .clone()
    .add(
      rotateOffset(
        new THREE.Vector3(0.02, -P.forearmLength, 0.012),
        ang.laxz * 0.28,
        ang.spineTwistY * 0.09,
        ang.laz + ang.lax * 0.92,
      ),
    );
  const wristR = elbowR
    .clone()
    .add(
      rotateOffset(
        new THREE.Vector3(-0.02, -P.forearmLength, 0.012),
        -ang.laxz * 0.28,
        -ang.spineTwistY * 0.09,
        ang.raz - ang.rax * 0.92,
      ),
    );
  const hipL = new THREE.Vector3(P.hipHalf, P.hipY, 0);
  const hipR = new THREE.Vector3(-P.hipHalf, P.hipY, 0);
  const kneeL = hipL
    .clone()
    .add(
      rotateOffset(new THREE.Vector3(0.008, -P.thighLength, 0.018), ang.llx, 0, 0.012),
    );
  const kneeR = hipR
    .clone()
    .add(
      rotateOffset(new THREE.Vector3(-0.008, -P.thighLength, 0.018), ang.rlx, 0, -0.012),
    );
  const ankleL = kneeL
    .clone()
    .add(
      rotateOffset(
        new THREE.Vector3(0.004, -P.calfLength, 0.026),
        Math.max(0, -ang.llx * 0.46),
        0,
        0.01,
      ),
    );
  const ankleR = kneeR
    .clone()
    .add(
      rotateOffset(
        new THREE.Vector3(-0.004, -P.calfLength, 0.026),
        Math.max(0, ang.rlx * 0.46),
        0,
        -0.01,
      ),
    );

  return {
    pelvis: asTuple(pelvis),
    spine: asTuple(spine),
    chest: asTuple(chest),
    neck: asTuple(neck),
    head: asTuple(head),
    shoulderL: asTuple(shoulderL),
    elbowL: asTuple(elbowL),
    wristL: asTuple(wristL),
    shoulderR: asTuple(shoulderR),
    elbowR: asTuple(elbowR),
    wristR: asTuple(wristR),
    hipL: asTuple(hipL),
    kneeL: asTuple(kneeL),
    ankleL: asTuple(ankleL),
    hipR: asTuple(hipR),
    kneeR: asTuple(kneeR),
    ankleR: asTuple(ankleR),
  };
}

function fromTuple(tuple: [number, number, number]): THREE.Vector3 {
  return new THREE.Vector3(tuple[0], tuple[1], tuple[2]);
}

export function jointVector(
  jointMap: ProceduralHumanoidJointMap,
  joint: ProceduralHumanoidJointName,
): THREE.Vector3 {
  return fromTuple(jointMap[joint]);
}

export function averageJoints(
  jointMap: ProceduralHumanoidJointMap,
  ...joints: ProceduralHumanoidJointName[]
): THREE.Vector3 {
  return average(...joints.map((joint) => jointVector(jointMap, joint)));
}

type GarmentWeight = {
  joint: ProceduralHumanoidJointName;
  weight: number;
};

function blendJoints(
  jointMap: ProceduralHumanoidJointMap,
  weights: readonly GarmentWeight[],
): THREE.Vector3 {
  const out = new THREE.Vector3();
  let total = 0;
  for (const { joint, weight } of weights) {
    out.addScaledVector(jointVector(jointMap, joint), weight);
    total += weight;
  }
  return total > 0 ? out.multiplyScalar(1 / total) : out;
}

/**
 * Garment follow weights:
 * - top shell: chest dominant, spine secondary, pelvis stabilizer
 * - sleeves: shoulder dominant, elbow secondary, wrist stabilizer
 * - bottoms: pelvis dominant, hips secondary, knees stabilizer
 */
export function buildProceduralGarmentFollowPoints(
  jointMap: ProceduralHumanoidJointMap,
) {
  const topCenter = blendJoints(jointMap, [
    { joint: "chest", weight: 0.52 },
    { joint: "spine", weight: 0.28 },
    { joint: "pelvis", weight: 0.2 },
  ]);
  const topLeftShoulder = blendJoints(jointMap, [
    { joint: "shoulderL", weight: 0.72 },
    { joint: "chest", weight: 0.18 },
    { joint: "elbowL", weight: 0.1 },
  ]);
  const topRightShoulder = blendJoints(jointMap, [
    { joint: "shoulderR", weight: 0.72 },
    { joint: "chest", weight: 0.18 },
    { joint: "elbowR", weight: 0.1 },
  ]);
  const sleeveUpperL = blendJoints(jointMap, [
    { joint: "shoulderL", weight: 0.58 },
    { joint: "elbowL", weight: 0.32 },
    { joint: "wristL", weight: 0.1 },
  ]);
  const sleeveLowerL = blendJoints(jointMap, [
    { joint: "shoulderL", weight: 0.14 },
    { joint: "elbowL", weight: 0.46 },
    { joint: "wristL", weight: 0.4 },
  ]);
  const sleeveUpperR = blendJoints(jointMap, [
    { joint: "shoulderR", weight: 0.58 },
    { joint: "elbowR", weight: 0.32 },
    { joint: "wristR", weight: 0.1 },
  ]);
  const sleeveLowerR = blendJoints(jointMap, [
    { joint: "shoulderR", weight: 0.14 },
    { joint: "elbowR", weight: 0.46 },
    { joint: "wristR", weight: 0.4 },
  ]);
  const bottomCenter = blendJoints(jointMap, [
    { joint: "pelvis", weight: 0.56 },
    { joint: "hipL", weight: 0.16 },
    { joint: "hipR", weight: 0.16 },
    { joint: "spine", weight: 0.12 },
  ]);
  const bottomLegL = blendJoints(jointMap, [
    { joint: "hipL", weight: 0.52 },
    { joint: "kneeL", weight: 0.32 },
    { joint: "pelvis", weight: 0.16 },
  ]);
  const bottomLegR = blendJoints(jointMap, [
    { joint: "hipR", weight: 0.52 },
    { joint: "kneeR", weight: 0.32 },
    { joint: "pelvis", weight: 0.16 },
  ]);

  return {
    topCenter,
    topLeftShoulder,
    topRightShoulder,
    sleeveUpperL,
    sleeveLowerL,
    sleeveUpperR,
    sleeveLowerR,
    bottomCenter,
    bottomLegL,
    bottomLegR,
  };
}
