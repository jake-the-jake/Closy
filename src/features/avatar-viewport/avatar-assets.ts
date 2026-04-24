export const DEFAULT_STYLISED_AVATAR_GLTF = require("../../../assets/models/avatar/default-stylised-avatar.glb");

export const DEFAULT_STYLISED_AVATAR_ID = "defaultStylisedAvatarGlb" as const;

export const DEFAULT_STYLISED_AVATAR_EXPECTED_RIG = [
  "hips/root",
  "spine",
  "chest",
  "neck",
  "head",
  "upperArm_L/R",
  "lowerArm_L/R",
  "hand_L/R",
  "upperLeg_L/R",
  "lowerLeg_L/R",
  "foot_L/R",
] as const;

export const DEFAULT_STYLISED_AVATAR = {
  id: DEFAULT_STYLISED_AVATAR_ID,
  label: "Default stylised avatar",
  bundledAssetModule: DEFAULT_STYLISED_AVATAR_GLTF,
  expectedRig: DEFAULT_STYLISED_AVATAR_EXPECTED_RIG,
} as const;
