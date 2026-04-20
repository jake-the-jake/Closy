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

/** Throttled world-space snapshot from the live GL canvas (dev / framing proof). */
export type LiveViewportSceneDiagnostics = {
  bodyLoaded: boolean;
  bodyRootWorld: [number, number, number];
  boundsCenter: [number, number, number];
  boundsSize: [number, number, number];
  cameraPosition: [number, number, number];
  cameraTarget: [number, number, number];
  distTargetToBodyCenter: number;
  /** Rough: body center in front of camera and within a plausible framing band. */
  framedHeuristic: boolean;
  skeletonRootWorld: [number, number, number] | null;
};

/** Live body path + intent (dev diagnostics; avoids silent bundled↔procedural drift). */
export type LiveViewportBodySourceDebug = {
  /** What the viewport is actually drawing for the body mesh. */
  active:
    | "bundled_skinned"
    | "external_skinned_url"
    | "procedural_user"
    | "procedural_env_forced"
    | "procedural_fallback_error"
    | "procedural_scene_default";
  /** User-facing intent from props (before runtime failure fallback). */
  userIntent: "bundled_or_url" | "procedural";
  /** High-level cause for the current active body source. */
  sourceReason: "startup" | "user_toggle" | "hard_fallback";
  loadStatus: "idle" | "pending" | "loaded" | "failed";
  reason:
    | "default_bundled"
    | "user_procedural_toggle"
    | "env_force_procedural"
    | "runtime_url_override"
    | "skinned_load_failed_fallback";
};

export type LiveViewportPoseFitDebug = {
  pose: DevAvatarPoseKey;
  preset: DevAvatarPresetKey;
  garmentPoseMatchesBody: boolean;
  skinned: SkinnedRigPoseReport | null;
  anchors: GarmentAnchorFitDebug | null;
  attachment?: GarmentAttachmentSnapshot | null;
  bodySource?: LiveViewportBodySourceDebug | null;
  /** Dev workstation: startup baseline + camera generation from preview screen. */
  startup?: {
    visibleBaselineApplied: boolean;
    viewportBaselineNonce: number;
    combinedViewOk: boolean;
    cameraFramedHint: boolean;
    startupRecoveryTriggered: boolean;
    exactBaselineOk: boolean;
    warning: string | null;
  } | null;
  visibility?: {
    mode: "combined" | "body_only" | "garment_only" | "invalid";
    bodyVisible: boolean;
    garmentsVisible: boolean;
    safeDefaultActive: boolean;
    cameraTargetValid: boolean;
  };
  interaction?: {
    zoomInputMode: "idle" | "native_pinch" | "wheel_fallback" | "emulator_fallback";
  };
  /** Present when dev scene inspect is enabled (throttled, not every React frame). */
  scene?: LiveViewportSceneDiagnostics | null;
};
