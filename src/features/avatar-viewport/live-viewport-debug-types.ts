import type { DevAvatarPoseKey, DevAvatarPresetKey } from "@/features/avatar-export/dev-avatar-shared";

import type { SkinnedBoneMapStatus } from "./skinned-body-pose";

/** Report from skinned GLTF body pose application (dev / diagnostics). */
export type SkinnedRigPoseReport = {
  activePose: DevAvatarPoseKey;
  /** True when skinned rig ran bone pose (not root-euler-only fallback). */
  bodyPoseApplied: boolean;
  boneMapStatus: SkinnedBoneMapStatus;
  /** Resolved named slots (full map includes spine, fingers, etc.). */
  mappedBoneSlots: number;
  /** How many of the critical limb/torso slots are mapped. */
  criticalMapped: number;
  criticalTotal: number;
};

/** Snapshot of garment anchor groups under `avatar_torso_region_fit` (dev). */
export type GarmentAnchorFitDebug = {
  bodyAnchorPos: [number, number, number];
  bodyAnchorScale: [number, number, number];
  topAnchorLocal: [number, number, number];
  bottomAnchorLocal: [number, number, number];
  waistTighten: number;
  hemOffsetY: number;
  legacyWaistAdjustY: number;
  torsoOffsetZ: number;
  skinnedBodyActive: boolean;
};

/** Resolved garment attachment (torso region space) from skinned bones or rig fallback. */
export type GarmentAttachmentSnapshot = {
  shoulderL: [number, number, number];
  shoulderR: [number, number, number];
  chest: [number, number, number];
  pelvisTop: [number, number, number];
  hipMid: [number, number, number];
  source: "skinned_bones" | "rig_fallback";
  topAnchor: [number, number, number];
  bottomAnchor: [number, number, number];
  leftSleevePivot: [number, number, number];
  rightSleevePivot: [number, number, number];
};

export type LiveViewportPoseFitDebug = {
  pose: DevAvatarPoseKey;
  preset: DevAvatarPresetKey;
  garmentPoseMatchesBody: boolean;
  skinned: SkinnedRigPoseReport | null;
  anchors: GarmentAnchorFitDebug | null;
  attachment?: GarmentAttachmentSnapshot | null;
};
