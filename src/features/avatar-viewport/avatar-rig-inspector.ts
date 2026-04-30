import * as THREE from "three";

export const AVATAR_RIG_SLOTS = [
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
] as const;

export type AvatarRigSlot = (typeof AVATAR_RIG_SLOTS)[number];

export type AvatarRigTypeGuess =
  | "mixamo"
  | "ready_player_me"
  | "vrm_like"
  | "smpl_like"
  | "cesium_man"
  | "blender_generic"
  | "unknown";

export type AvatarRigInspection = {
  boneMap: Partial<Record<AvatarRigSlot, THREE.Bone>>;
  missingRequiredBones: AvatarRigSlot[];
  confidence: number;
  rigTypeGuess: AvatarRigTypeGuess;
  boneCount: number;
};

const REQUIRED_BONES: AvatarRigSlot[] = [
  "hips",
  "spine",
  "chest",
  "head",
  "upperArmL",
  "upperArmR",
  "thighL",
  "thighR",
];

const SLOT_HINTS: Record<AvatarRigSlot, RegExp[]> = {
  hips: [/mixamorighips/i, /^hips?$/i, /pelvis/i, /root/i, /skeleton_torso_joint_1/i],
  spine: [/mixamorigspine$/i, /^spine$/i, /spine_?01/i, /torso_joint_2/i],
  chest: [/mixamorigspine2/i, /chest/i, /upperchest/i, /torso_joint_3/i],
  neck: [/mixamorigneck/i, /^neck/i, /neck_joint/i],
  head: [/mixamorighead/i, /^head$/i, /head/i],
  shoulderL: [/leftshoulder/i, /shoulder_l/i, /clavicle_l/i, /arm_joint_l__4_/i],
  upperArmL: [/mixamorigleftarm/i, /leftarm/i, /upperarm_l/i, /arm_l/i, /arm_joint_l__3_/i],
  lowerArmL: [/mixamorigleftforearm/i, /leftforearm/i, /lowerarm_l/i, /forearm_l/i, /arm_joint_l__2_/i],
  handL: [/mixamoriglefthand/i, /lefthand/i, /hand_l/i],
  shoulderR: [/rightshoulder/i, /shoulder_r/i, /clavicle_r/i, /skeleton_arm_joint_r$/i],
  upperArmR: [/mixamorgrightarm/i, /mixamorigrightarm/i, /rightarm/i, /upperarm_r/i, /arm_r/i, /arm_joint_r__2_/i],
  lowerArmR: [/mixamorigrightforearm/i, /rightforearm/i, /lowerarm_r/i, /forearm_r/i, /arm_joint_r__3_/i],
  handR: [/mixamorigright_hand/i, /mixamorigright hand/i, /mixamorigrightHand/i, /righthand/i, /hand_r/i],
  thighL: [/mixamorigleftupleg/i, /leftupleg/i, /thigh_l/i, /upperleg_l/i, /leg_joint_l_1/i],
  shinL: [/mixamorigleftleg/i, /leftleg/i, /shin_l/i, /lowerleg_l/i, /leg_joint_l_2/i],
  footL: [/mixamorigleftfoot/i, /leftfoot/i, /foot_l/i, /leg_joint_l_5/i],
  thighR: [/mixamorigrightupleg/i, /rightupleg/i, /thigh_r/i, /upperleg_r/i, /leg_joint_r_1/i],
  shinR: [/mixamorigrightleg/i, /rightleg/i, /shin_r/i, /lowerleg_r/i, /leg_joint_r_2/i],
  footR: [/mixamorigrightfoot/i, /rightfoot/i, /foot_r/i, /leg_joint_r_5/i],
};

function collectBones(root: THREE.Object3D): THREE.Bone[] {
  const bones: THREE.Bone[] = [];
  root.traverse((o) => {
    if (o instanceof THREE.Bone) bones.push(o);
  });
  return bones;
}

function findBone(bones: THREE.Bone[], slot: AvatarRigSlot): THREE.Bone | undefined {
  return bones.find((bone) => SLOT_HINTS[slot].some((hint) => hint.test(bone.name)));
}

function guessRigType(bones: THREE.Bone[]): AvatarRigTypeGuess {
  const names = bones.map((b) => b.name).join("|");
  if (/mixamorig/i.test(names)) return "mixamo";
  if (/wolf3d|avatarroot|readyplayer/i.test(names)) return "ready_player_me";
  if (/j_bip|humanoid|vrm/i.test(names)) return "vrm_like";
  if (/smpl|pelvis|left_hip|right_hip/i.test(names)) return "smpl_like";
  if (/Skeleton_torso_joint|leg_joint_L_1/i.test(names)) return "cesium_man";
  if (/armature|spine|upperarm/i.test(names)) return "blender_generic";
  return "unknown";
}

export function inspectAvatarRig(root: THREE.Object3D): AvatarRigInspection {
  const bones = collectBones(root);
  const boneMap: Partial<Record<AvatarRigSlot, THREE.Bone>> = {};
  for (const slot of AVATAR_RIG_SLOTS) {
    const bone = findBone(bones, slot);
    if (bone) boneMap[slot] = bone;
  }
  const missingRequiredBones = REQUIRED_BONES.filter((slot) => !boneMap[slot]);
  const mappedRequired = REQUIRED_BONES.length - missingRequiredBones.length;
  const mappedAll = AVATAR_RIG_SLOTS.filter((slot) => !!boneMap[slot]).length;
  const confidence = Math.min(
    1,
    mappedRequired / REQUIRED_BONES.length * 0.72 + mappedAll / AVATAR_RIG_SLOTS.length * 0.28,
  );
  return {
    boneMap,
    missingRequiredBones,
    confidence,
    rigTypeGuess: guessRigType(bones),
    boneCount: bones.length,
  };
}
