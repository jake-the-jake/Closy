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

export type LiveViewportPoseFitDebug = {
  pose: DevAvatarPoseKey;
  preset: DevAvatarPresetKey;
  garmentPoseMatchesBody: boolean;
  skinned: SkinnedRigPoseReport | null;
  anchors: GarmentAnchorFitDebug | null;
};
