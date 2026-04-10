export {
  getAvatarClippingStatsHttpUrl,
  getAvatarRenderHttpUrl,
  getDevAvatarRenderBaseUrl,
  pollAvatarRenderHttp,
  probeAvatarRenderHttp,
  type AvatarRenderHttpProbe,
  type PollAvatarRenderHttpResult,
} from "./avatar-render-http";
export {
  CLIPPING_HOTSPOT_DEFAULTS,
  FIT_DEBUG_MODE_ENGINE_WIRED,
  FIT_DEBUG_MODE_LABELS,
  fitDebugModeToExportFlags,
  isFitDebugModeEngineWired,
  listFitDebugModes,
  type FitDebugViewMode,
} from "./avatar-fit-debug";
export {
  AVATAR_EXPORT_CONTRACT_VERSION,
  AVATAR_REQUESTS_DIR,
  AVATAR_RENDERS_DIR,
  clippingStatsRelativePathForRenderId,
  joinPathSegments,
  requestFilenameForRenderId,
  requestRelativePathForRenderId,
  renderRelativePathForRenderId,
} from "./contract";
export {
  buildAvatarExportRequest,
  serializeAvatarExportRequestForDisk,
  type BuildAvatarExportOptions,
} from "./build-export-request";
export {
  cloneFitState,
  DEFAULT_GARMENT_FIT_STATE,
  FIT_ADJUST_PRESETS,
  fitStateToExportPatch,
  fitStatesEqual,
  garmentFitFromLegacyFlat,
  type GarmentFitState,
  type LegacyGarmentFitAdjustState,
  mergeExportFitIntoState,
  parseFitFromClosyJson,
} from "./fit-adjust";
export {
  type ClippingStatsV1,
  type FitSuggestion,
  fetchClippingStatsV1,
  suggestionsFromChecklistTagIds,
  suggestionsFromClippingStats,
} from "./fit-suggestions";
export {
  cloneGarmentFitState,
  garmentFitStateToExportPatch,
  garmentFitStatesEqual,
  GARMENT_FIT_PRESETS,
  mergeExportFitIntoGarmentState,
  parseGarmentFitFromClosyJson,
} from "./garment-fit-state";
export { canUseCacheDirectoryForExport } from "./cache-availability";
export { clothingItemsToOutfitLike, colourStringToApproxRgb } from "./colour-heuristic";
export { getClosyRepoRoot } from "./repo-root";
export {
  buildNpmAvatarRequestCommand,
  buildNpmCliCommand,
  runAvatarExport,
  type RunAvatarExportOptions,
} from "./run-avatar-export";
export { saveAvatarExportRequest } from "./save-export-request";
export type {
  AvatarEngineOutfitFile,
  AvatarExportDebugFlags,
  AvatarExportFit,
  AvatarExportFitAdjust,
  AvatarExportRequest,
  AvatarEngineOutfitItem,
  AvatarOutfitLike,
  ExportResult,
  SaveAvatarRequestResult,
} from "./types";
