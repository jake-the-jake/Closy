export type AvatarRigProfile = "mixamo" | "vrm" | "readyplayerme" | "custom" | "unknown";

export type AvatarRigProfileDefinition = {
  profile: AvatarRigProfile;
  label: string;
  rootHints: RegExp[];
};

export const AVATAR_RIG_PROFILES: AvatarRigProfileDefinition[] = [
  { profile: "mixamo", label: "Mixamo", rootHints: [/mixamorig/i] },
  { profile: "vrm", label: "VRM-ish", rootHints: [/j_bip|vrm|humanoid/i] },
  { profile: "readyplayerme", label: "Ready Player Me-ish", rootHints: [/wolf3d|avatarroot|readyplayer/i] },
  { profile: "custom", label: "Custom humanoid", rootHints: [/hips|pelvis|spine/i] },
];
