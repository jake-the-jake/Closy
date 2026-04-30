import * as THREE from "three";

import {
  buildProceduralGarmentFollowPoints,
  buildProceduralHumanoidJointMap,
  type ProceduralHumanoidJointMap,
} from "./procedural-humanoid-v2";
import { poseAngles } from "./avatar-pose-angles";
import type { AvatarRigInspection } from "./avatar-rig-inspector";

export const AVATAR_ANCHOR_NAMES = [
  "head",
  "neck",
  "chest",
  "waist",
  "hips",
  "shoulderL",
  "elbowL",
  "wristL",
  "shoulderR",
  "elbowR",
  "wristR",
  "thighL",
  "kneeL",
  "ankleL",
  "footL",
  "thighR",
  "kneeR",
  "ankleR",
  "footR",
] as const;

export type AvatarAnchorName = (typeof AVATAR_ANCHOR_NAMES)[number];

export type AvatarAnchorMap = Record<AvatarAnchorName, [number, number, number]>;

export type AvatarAnchorSource = "bones" | "named_nodes" | "bounds_fallback" | "procedural";

export type AvatarAnchorResolveReport = {
  anchors: AvatarAnchorMap;
  source: AvatarAnchorSource;
  missing: AvatarAnchorName[];
};

export type AvatarFitProxy =
  | {
      kind: "ellipsoid";
      name: string;
      center: [number, number, number];
      radius: [number, number, number];
    }
  | {
      kind: "capsule";
      name: string;
      start: [number, number, number];
      end: [number, number, number];
      radius: number;
    };

function tuple(v: THREE.Vector3): [number, number, number] {
  return [v.x, v.y, v.z];
}

function worldTuple(object: THREE.Object3D): [number, number, number] {
  return tuple(object.getWorldPosition(new THREE.Vector3()));
}

function proceduralAnchorMap(): AvatarAnchorMap {
  const jointMap = buildProceduralHumanoidJointMap({} as never, poseAngles("relaxed"));
  return {
    head: jointMap.head,
    neck: jointMap.neck,
    chest: jointMap.chest,
    waist: jointMap.waist,
    hips: jointMap.hips,
    shoulderL: jointMap.shoulderL,
    elbowL: jointMap.elbowL,
    wristL: jointMap.wristL,
    shoulderR: jointMap.shoulderR,
    elbowR: jointMap.elbowR,
    wristR: jointMap.wristR,
    thighL: jointMap.hipL,
    kneeL: jointMap.kneeL,
    ankleL: jointMap.ankleL,
    footL: jointMap.footL,
    thighR: jointMap.hipR,
    kneeR: jointMap.kneeR,
    ankleR: jointMap.ankleR,
    footR: jointMap.footR,
  };
}

function anchorsFromBounds(root: THREE.Object3D): AvatarAnchorMap {
  const box = new THREE.Box3().setFromObject(root);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const y = (t: number) => box.min.y + size.y * t;
  const sx = Math.max(0.16, size.x * 0.34);
  const hx = Math.max(0.1, size.x * 0.2);
  const z = center.z;
  return {
    head: [center.x, y(0.93), z],
    neck: [center.x, y(0.83), z],
    chest: [center.x, y(0.72), z],
    waist: [center.x, y(0.58), z],
    hips: [center.x, y(0.48), z],
    shoulderL: [center.x + sx, y(0.75), z],
    elbowL: [center.x + sx * 1.12, y(0.55), z],
    wristL: [center.x + sx, y(0.36), z],
    shoulderR: [center.x - sx, y(0.75), z],
    elbowR: [center.x - sx * 1.12, y(0.55), z],
    wristR: [center.x - sx, y(0.36), z],
    thighL: [center.x + hx, y(0.46), z],
    kneeL: [center.x + hx, y(0.25), z],
    ankleL: [center.x + hx, y(0.05), z],
    footL: [center.x + hx, box.min.y, z + Math.max(0.05, size.z * 0.16)],
    thighR: [center.x - hx, y(0.46), z],
    kneeR: [center.x - hx, y(0.25), z],
    ankleR: [center.x - hx, y(0.05), z],
    footR: [center.x - hx, box.min.y, z + Math.max(0.05, size.z * 0.16)],
  };
}

export function resolveAvatarAnchors(
  root: THREE.Object3D | null | undefined,
  rigInspection?: AvatarRigInspection | null,
): AvatarAnchorResolveReport {
  if (!root) {
    return { anchors: proceduralAnchorMap(), source: "procedural", missing: [] };
  }

  const bones = rigInspection?.boneMap;
  if (bones) {
    const anchors = anchorsFromBounds(root);
    const map: Partial<Record<AvatarAnchorName, THREE.Object3D | undefined>> = {
      head: bones.head,
      neck: bones.neck,
      chest: bones.chest,
      waist: bones.spine,
      hips: bones.hips,
      shoulderL: bones.shoulderL ?? bones.upperArmL,
      elbowL: bones.lowerArmL,
      wristL: bones.handL,
      shoulderR: bones.shoulderR ?? bones.upperArmR,
      elbowR: bones.lowerArmR,
      wristR: bones.handR,
      thighL: bones.thighL,
      kneeL: bones.shinL,
      ankleL: bones.footL,
      footL: bones.footL,
      thighR: bones.thighR,
      kneeR: bones.shinR,
      ankleR: bones.footR,
      footR: bones.footR,
    };
    const missing: AvatarAnchorName[] = [];
    for (const anchor of AVATAR_ANCHOR_NAMES) {
      const object = map[anchor];
      if (object) anchors[anchor] = worldTuple(object);
      else missing.push(anchor);
    }
    if (missing.length < AVATAR_ANCHOR_NAMES.length) {
      return { anchors, source: "bones", missing };
    }
  }

  return {
    anchors: anchorsFromBounds(root),
    source: "bounds_fallback",
    missing: [],
  };
}

export function buildFitProxiesFromAnchors(anchors: AvatarAnchorMap): AvatarFitProxy[] {
  const follow = buildProceduralGarmentFollowPoints({
    pelvis: anchors.hips,
    spine: anchors.waist,
    waist: anchors.waist,
    chest: anchors.chest,
    neck: anchors.neck,
    head: anchors.head,
    shoulderL: anchors.shoulderL,
    elbowL: anchors.elbowL,
    wristL: anchors.wristL,
    shoulderR: anchors.shoulderR,
    elbowR: anchors.elbowR,
    wristR: anchors.wristR,
    hips: anchors.hips,
    hipL: anchors.thighL,
    kneeL: anchors.kneeL,
    ankleL: anchors.ankleL,
    footL: anchors.footL,
    hipR: anchors.thighR,
    kneeR: anchors.kneeR,
    ankleR: anchors.ankleR,
    footR: anchors.footR,
  } satisfies ProceduralHumanoidJointMap);
  return [
    { kind: "ellipsoid", name: "torso_fit", center: tuple(follow.topCenter), radius: [0.2, 0.34, 0.12] },
    { kind: "ellipsoid", name: "pelvis_fit", center: tuple(follow.bottomCenter), radius: [0.18, 0.14, 0.12] },
    { kind: "capsule", name: "upper_arm_l_fit", start: anchors.shoulderL, end: anchors.elbowL, radius: 0.055 },
    { kind: "capsule", name: "lower_arm_l_fit", start: anchors.elbowL, end: anchors.wristL, radius: 0.043 },
    { kind: "capsule", name: "upper_arm_r_fit", start: anchors.shoulderR, end: anchors.elbowR, radius: 0.055 },
    { kind: "capsule", name: "lower_arm_r_fit", start: anchors.elbowR, end: anchors.wristR, radius: 0.043 },
    { kind: "capsule", name: "thigh_l_fit", start: anchors.thighL, end: anchors.kneeL, radius: 0.075 },
    { kind: "capsule", name: "shin_l_fit", start: anchors.kneeL, end: anchors.ankleL, radius: 0.055 },
    { kind: "capsule", name: "thigh_r_fit", start: anchors.thighR, end: anchors.kneeR, radius: 0.075 },
    { kind: "capsule", name: "shin_r_fit", start: anchors.kneeR, end: anchors.ankleR, radius: 0.055 },
  ];
}
