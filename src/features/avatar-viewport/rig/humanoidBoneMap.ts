import type { AvatarRigSlot } from "../avatar-rig-inspector";
import { THREE } from "../three";

export const HUMANOID_BONE_SLOTS = [
  "hips",
  "spine",
  "chest",
  "neck",
  "head",
  "shoulderL",
  "upperArmL",
  "lowerArmL",
  "handL",
  "shoulderR",
  "upperArmR",
  "lowerArmR",
  "handR",
  "thighL",
  "shinL",
  "footL",
  "thighR",
  "shinR",
  "footR",
] as const satisfies readonly AvatarRigSlot[];

export type HumanoidBoneMap = Partial<Record<AvatarRigSlot, THREE.Bone>>;
