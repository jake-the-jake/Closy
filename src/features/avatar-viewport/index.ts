export { AvatarViewportLive, type AvatarViewportLiveProps } from "./avatar-viewport-live";
export type {
  GarmentAnchorFitDebug,
  GarmentAttachmentSnapshot,
  LiveViewportPoseFitDebug,
  SkinnedRigPoseReport,
} from "./live-viewport-debug-types";
export {
  AVATAR_RIG_ANCHORS,
  CameraRig,
  AvatarProceduralScene,
  poseAngles,
  type OrbitSpherical,
} from "./avatar-procedural-scene";
export {
  DEFAULT_AVATAR_VIEWPORT_NAV,
  mergeAvatarViewportNav,
  type AvatarViewportNavSettings,
} from "./avatar-viewport-nav-settings";
export type { PoseAngleSet } from "./avatar-pose-angles";
export type { GarmentPoseSkinningParams } from "./garment-deformation";
export {
  GARMENT_POSE_BIND_POSE,
  armChainMatrix,
  thighSkinMatrix,
  upperArmSkinMatrix,
} from "./garment-rig-pose";
export {
  listLiveViewportShadingModes,
  LIVE_VIEWPORT_SHADING_LABELS,
  type LiveViewportShadingMode,
} from "./live-viewport-shading";
export type {
  AvatarSceneState,
  AvatarSceneSnapshot,
  GarmentFitRegionKey,
  LiveFitSessionSnapshot,
} from "./avatar-scene-types";
export {
  DEFAULT_AVATAR_SCENE_STATE,
  useAvatarSceneStore,
  type AvatarSceneStore,
} from "./avatar-scene-store";
export {
  resolveAvatarOutfit,
  avatarSceneToBuildOptions,
  buildExportRequestFromAvatarScene,
} from "./scene-to-export";
export {
  getAvatarRuntimeAssetUrls,
  runtimeAssetSummary,
  type AvatarRuntimeAssetUrls,
} from "./runtime-asset-sources";
export {
  GltfErrorBoundary,
  GltfRuntimeBody,
  GltfRuntimeGarment,
  poseRootEulerApprox,
  applyLiveShadingToGltfMaterials,
} from "./gltf-runtime-body";
export {
  applyGarmentDeformationForProfile,
  applyBottomGarmentDeformation,
  applySleeveGarmentDeformation,
  applyTopGarmentDeformation,
  deformGarmentObject3D,
  deformationSummary,
  forgetGarmentRest,
  getOrCaptureGarmentRest,
  type GarmentDeformProfile,
} from "./garment-deformation";
export {
  suggestionsFromLiveHeuristics,
  suggestionsFromRuntimeClipping,
} from "./live-fit-heuristics";
export {
  analyzeRuntimeClipping,
  clipSeverityToEmissive,
  worstGarmentClipSeverity,
  type RuntimeClipRegion,
  type RuntimeClippingReport,
  type RuntimeClipSeverity,
  type RuntimeClippingAnalyzeInput,
} from "./runtime-clipping-approx";
export {
  aggregateStressResults,
  runPoseStressTest,
  stabilizeFitAcrossPoses,
  stressReportToSnapshotMeta,
  STRESS_TEST_POSES,
  type AggregatedStressAnalysis,
  type LiveFitStressSnapshotMeta,
  type PoseStressPoseResult,
  type PoseStressTestReport,
  type RuntimeClippingFlags,
  type StabilizeFitResult,
  type StressFailLevel,
  type StressRegionKey,
} from "./pose-stress-test";
export { resetGarmentFitRegion } from "./garment-fit-region-reset";
