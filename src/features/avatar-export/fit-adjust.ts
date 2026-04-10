/**
 * Backward-compatible re-exports. Prefer `garment-fit-state` and `fit-suggestions` directly.
 */

export type { GarmentFitState, LegacyGarmentFitAdjustState } from "./garment-fit-state";
export {
  cloneGarmentFitState as cloneFitState,
  DEFAULT_GARMENT_FIT_STATE,
  garmentFitFromLegacyFlat,
  garmentFitStateToExportPatch as fitStateToExportPatch,
  garmentFitStatesEqual as fitStatesEqual,
  GARMENT_FIT_PRESETS as FIT_ADJUST_PRESETS,
  mergeExportFitIntoGarmentState as mergeExportFitIntoState,
  parseGarmentFitFromClosyJson as parseFitFromClosyJson,
} from "./garment-fit-state";
