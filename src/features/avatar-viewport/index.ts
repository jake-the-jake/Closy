export {
  AvatarViewportLive,
  type AvatarViewportDevSceneInspect,
  type AvatarViewportLiveProps,
} from "./avatar-viewport-live";
export { AvatarExperienceScreen } from "./avatar-experience-screen";
export {
  DEFAULT_STYLISED_AVATAR,
  DEFAULT_STYLISED_AVATAR_GLTF,
  DEFAULT_STYLISED_AVATAR_ID,
  DEFAULT_STYLISED_AVATAR_EXPECTED_RIG,
  REALISTIC_AVATAR_ASSET_SLOT,
  STYLISED_AVATAR_ASSET_SLOT,
} from "./avatar-assets";
export {
  AVATAR_ASSET_MANIFESTS,
  avatarAssetAvailabilityLabel,
  getAvatarAssetManifest,
  type AvatarAssetKind,
  type AvatarAssetManifest,
  type AvatarAssetManifestId,
  type AvatarAssetNamingProfile,
} from "./assets/avatarAssetManifest";
export type {
  AvatarRenderAudit,
  GarmentAnchorFitDebug,
  GarmentAttachmentSnapshot,
  LiveViewportBodySourceDebug,
  LiveViewportPoseFitDebug,
  LiveViewportSceneDiagnostics,
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
  avatarSourceLoadStateLabel,
  AVATAR_SOURCE_OPTIONS,
  getAvatarSourceOptionsForRoute,
  resolveAvatarSourceForRoute,
  resolveAvatarSource,
  type AvatarResolvedSource,
  type AvatarResolvedRouteSource,
  type AvatarRouteActiveSource,
  type AvatarRouteMode,
  type AvatarSourceOption,
  type AvatarSourceRouteOption,
  type AvatarSourceRouteOptions,
  type AvatarSourceLoadState,
  type AvatarSourcePreference,
  type AvatarSourceType,
} from "./avatarSourceResolver";
export {
  resolveAvatarSource as resolveUnifiedAvatarSource,
  avatarSourcePreferenceToLegacyLabel,
  type AvatarSelectedSourceType,
  type AvatarSourceResolution,
} from "./avatar-source/resolveAvatarSource";
export {
  resolveAvatarStartupPhase,
  type AvatarStartupMachineInput,
} from "./avatar-startup-state";
export {
  AVATAR_ANCHOR_NAMES,
  buildFitProxiesFromAnchors,
  resolveAvatarAnchors,
  type AvatarAnchorMap,
  type AvatarAnchorName,
  type AvatarAnchorResolveReport,
  type AvatarFitProxy,
} from "./avatar-anchors";
export {
  buildGarmentAnchorsFromProceduralJoints,
  type AvatarGarmentAnchorSet,
} from "./garment-fit/garmentAnchors";
export {
  BODY_ANCHOR_NAMES,
  hasCoreGarmentAnchors,
  type BodyAnchorMap,
  type BodyAnchorName,
} from "./garment-fit/bodyAnchors";
export {
  solveGarmentFitFromBodyAnchors,
  type SolvedGarmentFit,
} from "./garment-fit/garmentFitSolver";
export {
  auditAvatarObject3D,
  type AvatarAssetAudit,
} from "./avatar-loader/avatarAssetAudit";
export { auditAvatarAsset } from "./avatar-loader/auditAvatarAsset";
export {
  loadAvatarAsset,
  type LoadedAvatarAsset,
} from "./avatar-loader/loadAvatarAsset";
export {
  clearAvatarAssetCache,
  loadPreparedAvatarAsset,
  type PreparedAvatarAsset,
} from "./avatar-loader/avatarAssetCache";
export {
  normalizeAvatarScene,
  type NormalizeAvatarSceneOptions,
} from "./avatar-loader/normalizeAvatarScene";
export { prepareAvatarMaterials } from "./avatar-loader/prepareAvatarMaterials";
export { prepareAvatarRig } from "./avatar-loader/prepareAvatarRig";
export {
  normalizeAvatarPbrMaterials,
  type AvatarMaterialNormalizeReport,
  type AvatarMaterialRole,
} from "./materials/avatarPbrMaterials";
export {
  localPlaceholderZeroOneAvatarBridge,
} from "./zeroone/zerooneAvatarBridge";
export type {
  ZeroOneAvatarOutputRequest,
  ZeroOneAvatarQuality,
  ZeroOneAvatarRenderRequest,
  ZeroOneAvatarRenderResult,
} from "./zeroone/zerooneAvatarBridgeTypes";
export {
  LOCAL_PLACEHOLDER_ZEROONE_AVATAR_BRIDGE,
  type ZeroOneAvatarBridge,
  type ZeroOneAvatarBridgeMode,
  type ZeroOneAvatarCamera,
  type ZeroOneAvatarRequest,
  type ZeroOneAvatarResult,
  type ZeroOneFitDiagnostics,
  type ZeroOneGarmentSource,
  type ZeroOneOutfitItem,
  type ZeroOneRenderQuality,
  type ZeroOneRequestedOutput,
  type ZeroOneSimulationMetadata,
  type ZeroOneTargetPlatform,
} from "./zeroone/zerooneAvatarTypes";
export {
  computeAvatarBodyLandmarks,
  type AvatarBodyLandmarks,
} from "./fit/avatarBodyLandmarks";
export { extractAvatarLandmarks } from "./fit/extractAvatarLandmarks";
export {
  solveAvatarGarmentAttachment,
  type AvatarGarmentAttachmentSolve,
} from "./fit/avatarGarmentAttachment";
export {
  AVATAR_RIG_SLOTS,
  inspectAvatarRig,
  type AvatarRigInspection,
  type AvatarRigSlot,
  type AvatarRigTypeGuess,
} from "./avatar-rig-inspector";
export {
  normalizeAvatarRoot,
  type AvatarNormalizeOptions,
  type AvatarNormalizeReport,
} from "./avatar-normalize";
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
