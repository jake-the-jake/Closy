import { create } from "zustand";

import type { FitDebugViewMode } from "@/features/avatar-export";
import {
  cloneFitState,
  DEFAULT_GARMENT_FIT_STATE,
  type GarmentFitState,
} from "@/features/avatar-export";
import type { AvatarOutfitLike } from "@/features/avatar-export/types";

import type {
  DevAvatarPoseKey,
  DevAvatarPresetKey,
} from "@/features/avatar-export/dev-avatar-shared";

import type {
  LiveFitStressSnapshotMeta,
  PoseStressTestReport,
} from "./pose-stress-test";

import type {
  AvatarSceneState,
  GarmentFitRegionKey,
  LiveFitSessionSnapshot,
} from "./avatar-scene-types";
import { resetGarmentFitRegion } from "./garment-fit-region-reset";
import type { LiveViewportShadingMode } from "./live-viewport-shading";

const MAX_LIVE_FIT_SNAPSHOTS = 14;

export const DEFAULT_AVATAR_SCENE_STATE: AvatarSceneState = {
  pose: "relaxed",
  presetKey: "default",
  outfitOverride: null,
  garmentFit: cloneFitState(DEFAULT_GARMENT_FIT_STATE),
  liveViewportShading: "normal",
  offlineFitDebugMode: "normal",
};

type AvatarSceneActions = {
  setPose: (pose: DevAvatarPoseKey) => void;
  setPresetKey: (presetKey: DevAvatarPresetKey) => void;
  setOutfitOverride: (outfit: AvatarOutfitLike | null) => void;
  setGarmentFit: (garmentFit: GarmentFitState) => void;
  patchGarmentFit: (fn: (prev: GarmentFitState) => GarmentFitState) => void;
  setLiveViewportShading: (mode: LiveViewportShadingMode) => void;
  setOfflineFitDebugMode: (mode: FitDebugViewMode) => void;
  hydrateScene: (partial: Partial<AvatarSceneState>) => void;
  resetGarmentFit: () => void;

  liveFitActiveRegion: GarmentFitRegionKey;
  setLiveFitActiveRegion: (region: GarmentFitRegionKey) => void;
  liveFitBaseline: GarmentFitState | null;
  liveFitShowBaseline: boolean;
  captureLiveFitBaseline: () => void;
  clearLiveFitBaseline: () => void;
  setLiveFitShowBaseline: (show: boolean) => void;
  toggleLiveFitBaselineCompare: () => void;
  liveFitSnapshots: LiveFitSessionSnapshot[];
  pushLiveFitSnapshot: (label?: string, stressTest?: LiveFitStressSnapshotMeta) => void;
  /** Last multi-pose stress test (dev fitting workstation). */
  lastPoseStressReport: PoseStressTestReport | null;
  setLastPoseStressReport: (r: PoseStressTestReport | null) => void;
  /** Highlight worst pose from last stress test (optional UI). */
  stressTestHighlightPose: DevAvatarPoseKey | null;
  setStressTestHighlightPose: (p: DevAvatarPoseKey | null) => void;
  restoreLiveFitSnapshot: (id: string) => void;
  removeLiveFitSnapshot: (id: string) => void;
  clearLiveFitSnapshots: () => void;
  liveFitQuickTags: string[];
  addLiveFitQuickTag: (tag: string) => void;
  clearLiveFitQuickTags: () => void;
  liveFitLastSuggestionId: string | null;
  setLiveFitLastSuggestionId: (id: string | null) => void;
  liveFitLastSuggestionSource: string | null;
  setLiveFitLastSuggestionSource: (source: string | null) => void;
  /** Live viewport: tint garments by runtime clipping proxy (dev fitting). */
  liveClipOverlay: boolean;
  setLiveClipOverlay: (on: boolean) => void;
  resetLiveFitRegionToDefault: (region: GarmentFitRegionKey) => void;
};

export type AvatarSceneStore = AvatarSceneState & AvatarSceneActions;

export const useAvatarSceneStore = create<AvatarSceneStore>((set, get) => ({
  ...DEFAULT_AVATAR_SCENE_STATE,

  liveFitActiveRegion: "global",
  liveFitBaseline: null,
  liveFitShowBaseline: false,
  liveFitSnapshots: [],
  liveFitQuickTags: [],
  liveFitLastSuggestionId: null,
  liveFitLastSuggestionSource: null,
  liveClipOverlay: false,
  lastPoseStressReport: null,
  stressTestHighlightPose: null,

  setPose: (pose) => set({ pose }),

  setPresetKey: (presetKey) =>
    set({ presetKey, outfitOverride: null }),

  setOutfitOverride: (outfitOverride) => set({ outfitOverride }),

  setGarmentFit: (garmentFit) =>
    set({ garmentFit, liveFitShowBaseline: false }),

  patchGarmentFit: (fn) =>
    set((s) => ({
      garmentFit: fn(s.garmentFit),
      liveFitShowBaseline: false,
    })),

  setLiveViewportShading: (liveViewportShading) => set({ liveViewportShading }),

  setOfflineFitDebugMode: (offlineFitDebugMode) => set({ offlineFitDebugMode }),

  hydrateScene: (partial) => set((s) => ({ ...s, ...partial })),

  resetGarmentFit: () =>
    set({
      garmentFit: cloneFitState(DEFAULT_GARMENT_FIT_STATE),
      liveFitShowBaseline: false,
    }),

  setLiveFitActiveRegion: (liveFitActiveRegion) => set({ liveFitActiveRegion }),

  captureLiveFitBaseline: () =>
    set({
      liveFitBaseline: cloneFitState(get().garmentFit),
      liveFitShowBaseline: false,
    }),

  clearLiveFitBaseline: () =>
    set({ liveFitBaseline: null, liveFitShowBaseline: false }),

  setLiveFitShowBaseline: (liveFitShowBaseline) => set({ liveFitShowBaseline }),

  toggleLiveFitBaselineCompare: () => {
    const s = get();
    if (s.liveFitBaseline == null) return;
    set({ liveFitShowBaseline: !s.liveFitShowBaseline });
  },

  pushLiveFitSnapshot: (label, stressTest) => {
    const s = get();
    const id = `fit_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const entry: LiveFitSessionSnapshot = {
      id,
      createdAt: Date.now(),
      label,
      pose: s.pose,
      presetKey: s.presetKey,
      garmentFit: cloneFitState(s.garmentFit),
      liveViewportShading: s.liveViewportShading,
      liveFitActiveRegion: s.liveFitActiveRegion,
      ...(stressTest ? { stressTest } : {}),
    };
    set({
      liveFitSnapshots: [entry, ...s.liveFitSnapshots].slice(0, MAX_LIVE_FIT_SNAPSHOTS),
    });
  },

  setLastPoseStressReport: (lastPoseStressReport) => set({ lastPoseStressReport }),

  setStressTestHighlightPose: (stressTestHighlightPose) =>
    set({ stressTestHighlightPose }),

  restoreLiveFitSnapshot: (id) => {
    const e = get().liveFitSnapshots.find((x) => x.id === id);
    if (!e) return;
    set({
      pose: e.pose,
      presetKey: e.presetKey,
      garmentFit: cloneFitState(e.garmentFit),
      liveViewportShading: e.liveViewportShading,
      liveFitActiveRegion: e.liveFitActiveRegion,
      liveFitShowBaseline: false,
    });
  },

  removeLiveFitSnapshot: (id) =>
    set((s) => ({
      liveFitSnapshots: s.liveFitSnapshots.filter((x) => x.id !== id),
    })),

  clearLiveFitSnapshots: () => set({ liveFitSnapshots: [] }),

  addLiveFitQuickTag: (tag) =>
    set((s) =>
      s.liveFitQuickTags.includes(tag)
        ? s
        : { liveFitQuickTags: [...s.liveFitQuickTags, tag] },
    ),

  clearLiveFitQuickTags: () => set({ liveFitQuickTags: [] }),

  setLiveFitLastSuggestionId: (liveFitLastSuggestionId) =>
    set({ liveFitLastSuggestionId }),

  setLiveFitLastSuggestionSource: (liveFitLastSuggestionSource) =>
    set({ liveFitLastSuggestionSource }),

  setLiveClipOverlay: (liveClipOverlay) => set({ liveClipOverlay }),

  resetLiveFitRegionToDefault: (region) =>
    set((s) => ({
      garmentFit: resetGarmentFitRegion(s.garmentFit, region),
      liveFitShowBaseline: false,
    })),
}));
