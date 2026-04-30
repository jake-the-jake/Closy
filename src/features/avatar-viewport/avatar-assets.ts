export const DEFAULT_STYLISED_AVATAR_GLTF = require("../../../assets/models/avatar/default-stylised-avatar.glb");

export const DEFAULT_STYLISED_AVATAR_ID = "defaultStylisedAvatarGlb" as const;
export const REALISTIC_AVATAR_ASSET_SLOT = "assets/avatar/realistic/default-avatar.glb" as const;
export const STYLISED_AVATAR_ASSET_SLOT = "assets/avatar/stylised/default-mannequin.glb" as const;

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
  /**
   * Bridge slot: Metro cannot require a missing GLB, so this points at the
   * existing bundled mannequin until `assets/avatar/stylised/default-mannequin.glb`
   * is added and wired as the canonical static asset.
   */
  bundledAssetModule: DEFAULT_STYLISED_AVATAR_GLTF,
  expectedRig: DEFAULT_STYLISED_AVATAR_EXPECTED_RIG,
  futureAssetSlot: STYLISED_AVATAR_ASSET_SLOT,
} as const;
