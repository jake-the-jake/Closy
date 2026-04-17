import type {
  BodyShapeParams,
  FitDebugViewMode,
  GarmentFitState,
} from "@/features/avatar-export";
import type { AvatarOutfitLike } from "@/features/avatar-export/types";

import type {
  DevAvatarPoseKey,
  DevAvatarPresetKey,
} from "@/features/avatar-export/dev-avatar-shared";

import type { LiveFitStressSnapshotMeta } from "./pose-stress-test";
import type { LiveViewportShadingMode } from "./live-viewport-shading";
import type { AvatarViewportNavSettings } from "./avatar-viewport-nav-settings";

/**
 * Single source of truth for avatar presentation: live viewport + offline export JSON.
 * Offline-only concerns (`FitDebugViewMode` / clipping hotspot) stay separate from live shading.
 */
export type AvatarSceneState = {
  /** Engine / export pose id. */
  pose: DevAvatarPoseKey;
  /** Named wardrobe preset (maps to `DEV_AVATAR_PRESETS` until custom outfit UX exists). */
  presetKey: DevAvatarPresetKey;
  /**
   * Optional outfit override (future: wardrobe item picks). When null, `resolveAvatarOutfit` uses
   * `presetKey` only.
   */
  outfitOverride: AvatarOutfitLike | null;
  /** Region-aware fit; same object serializes to `closy.fit` for export. */
  garmentFit: GarmentFitState;
  /** Parametric body (live + clipping + stress test + optional export `closy.bodyShape`). */
  bodyShape: BodyShapeParams;
  /** Live WebGL debug look (not written to PNG JSON unless we mirror later). */
  liveViewportShading: LiveViewportShadingMode;
  /** Host `avatar_export` debug flags (`closy.debug`). */
  offlineFitDebugMode: FitDebugViewMode;
  /** Live WebGL orbit / zoom tuning (dev workstation). */
  viewportNav: AvatarViewportNavSettings;
};

/** Serializable snapshot for session history / compare (offline render metadata). */
export type AvatarSceneSnapshot = Pick<
  AvatarSceneState,
  | "pose"
  | "presetKey"
  | "garmentFit"
  | "bodyShape"
  | "liveViewportShading"
  | "offlineFitDebugMode"
  | "outfitOverride"
>;

/** In-memory live fitting snapshot (dev workstation); not sent to exporter JSON. */
export type LiveFitSessionSnapshot = {
  id: string;
  createdAt: number;
  label?: string;
  pose: DevAvatarPoseKey;
  presetKey: DevAvatarPresetKey;
  garmentFit: GarmentFitState;
  /** Present on new snapshots; older in-memory entries may omit. */
  bodyShape?: BodyShapeParams;
  liveViewportShading: LiveViewportShadingMode;
  liveFitActiveRegion: GarmentFitRegionKey;
  /** When saved from stress-test / stabilize flow (optional). */
  stressTest?: LiveFitStressSnapshotMeta;
};

export type GarmentFitRegionKey =
  | "global"
  | "torso"
  | "sleeves"
  | "waist"
  | "hem";
