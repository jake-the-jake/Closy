import * as Clipboard from "expo-clipboard";
import { Image } from "expo-image";
import * as FileSystem from "expo-file-system/legacy";
import * as Linking from "expo-linking";
import { useRouter } from "expo-router";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  ActivityIndicator,
  Platform,
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  useWindowDimensions,
  View,
} from "react-native";

import { AppButton } from "@/components/ui/app-button";
import { ScreenContainer } from "@/components/ui/screen-container";

import {
  BODY_SHAPE_PRESET_LABELS,
  BODY_SHAPE_PRESETS,
  bodyShapesEqual,
  CLIPPING_HOTSPOT_DEFAULTS,
  DEFAULT_BODY_SHAPE,
  DEFAULT_GARMENT_FIT_STATE,
  FIT_ADJUST_PRESETS,
  FIT_DEBUG_MODE_LABELS,
  buildNpmAvatarRequestCommand,
  buildNpmCliCommand,
  canUseCacheDirectoryForExport,
  cloneFitState,
  fetchClippingStatsV1,
  fitStatesEqual,
  garmentFitFromLegacyFlat,
  getAvatarClippingStatsHttpUrl,
  getAvatarRenderHttpUrl,
  getClosyRepoRoot,
  getDevAvatarRenderBaseUrl,
  isFitDebugModeEngineWired,
  listFitDebugModes,
  probeAvatarRenderHttp,
  renderRelativePathForRenderId,
  requestRelativePathForRenderId,
  runAvatarExport,
  saveAvatarExportRequest,
  suggestionsFromChecklistTagIds,
  suggestionsFromClippingStats,
  type ClippingStatsV1,
  type FitDebugViewMode,
  type FitSuggestion,
  type GarmentFitState,
  type LegacyGarmentFitAdjustState,
  type SaveAvatarRequestResult,
  type BodyShapeParams,
  type BodyShapePresetId,
} from "@/features/avatar-export";
import {
  DEV_AVATAR_PRESETS as PRESETS,
  type DevAvatarPoseKey as PoseKey,
  type DevAvatarPresetKey as PresetKey,
} from "@/features/avatar-export/dev-avatar-shared";
import { runAvatarExportMock } from "@/features/avatar-export/runner/avatarExportRunner.mock";
import {
  analyzeRuntimeClipping,
  AvatarViewportLive,
  type AvatarViewportDevSceneInspect,
  buildExportRequestFromAvatarScene,
  getAvatarRuntimeAssetUrls,
  LIVE_VIEWPORT_SHADING_LABELS,
  listLiveViewportShadingModes,
  runPoseStressTest,
  stabilizeFitAcrossPoses,
  stressReportToSnapshotMeta,
  suggestionsFromLiveHeuristics,
  suggestionsFromRuntimeClipping,
  useAvatarSceneStore,
  type AvatarViewportNavSettings,
  type AvatarSourcePreference,
  type GarmentFitRegionKey,
  type GarmentAttachmentSnapshot,
  type LiveViewportPoseFitDebug,
  type LiveViewportShadingMode,
} from "@/features/avatar-viewport";
import { theme } from "@/theme";

export type DevAvatarPreviewPhase =
  | "idle"
  | "request_built"
  | "host_handoff_needed"
  | "waiting_for_export"
  | "waiting_for_render"
  | "render_loaded"
  | "render_not_found"
  | "stale_render"
  | "unsupported_debug_mode"
  | "render_failed";

type SessionRenderEntry = {
  saved: SaveAvatarRequestResult;
  pose: PoseKey;
  preset: PresetKey;
  fitDebugMode: FitDebugViewMode;
  garmentFit?: GarmentFitState;
  /** Pre–region-aware history entries. */
  fitAdjust?: LegacyGarmentFitAdjustState;
  checklistTags?: string[];
  createdAt: number;
  thumbnailUri: string | null;
};

type LoadSnapshot = {
  renderId: string;
  pose: PoseKey;
  preset: PresetKey;
  fitDebugMode: FitDebugViewMode;
  garmentFit: GarmentFitState;
};

const FIT_REGION_LABELS: Record<GarmentFitRegionKey, string> = {
  global: "Global",
  torso: "Torso",
  sleeves: "Sleeves",
  waist: "Waist",
  hem: "Hem",
};

function fmtVec3(t: [number, number, number]): string {
  return t.map((n) => n.toFixed(3)).join(", ");
}

const ATTACH_DEBUG_LINE = {
  fontSize: 10,
  fontFamily: "monospace" as const,
  color: theme.colors.text,
  lineHeight: 14,
};

function AttachmentDebugReadout({ snap }: { snap: GarmentAttachmentSnapshot }) {
  return (
    <>
      <Text style={ATTACH_DEBUG_LINE} selectable>
        attach source: {snap.source}
      </Text>
      <Text style={ATTACH_DEBUG_LINE} selectable>
        shL [{fmtVec3(snap.shoulderL)}] · shR [{fmtVec3(snap.shoulderR)}]
      </Text>
      <Text style={ATTACH_DEBUG_LINE} selectable>
        chest [{fmtVec3(snap.chest)}] · pelvis [{fmtVec3(snap.pelvisTop)}] · hipMid [{fmtVec3(snap.hipMid)}]
      </Text>
      <Text style={ATTACH_DEBUG_LINE} selectable>
        anchor top [{fmtVec3(snap.topAnchor)}] · bottom [{fmtVec3(snap.bottomAnchor)}]
      </Text>
      <Text style={ATTACH_DEBUG_LINE} selectable>
        sleeve pivot L [{fmtVec3(snap.leftSleevePivot)}] · R [{fmtVec3(snap.rightSleevePivot)}]
      </Text>
    </>
  );
}

/** Bounds aligned with `deriveBodyRigMetrics` clamps (multipliers ~1). */
const BODY_SHAPE_SLIDERS: {
  key: keyof BodyShapeParams;
  label: string;
  min: number;
  max: number;
  step: number;
}[] = [
  { key: "height", label: "Height", min: 0.88, max: 1.12, step: 0.02 },
  { key: "shoulderWidth", label: "Shoulder width", min: 0.82, max: 1.22, step: 0.02 },
  { key: "chest", label: "Chest", min: 0.82, max: 1.25, step: 0.02 },
  { key: "waist", label: "Waist", min: 0.82, max: 1.2, step: 0.02 },
  { key: "hips", label: "Hips", min: 0.82, max: 1.28, step: 0.02 },
  { key: "armThickness", label: "Arm thickness", min: 0.82, max: 1.25, step: 0.02 },
  { key: "legThickness", label: "Leg thickness", min: 0.82, max: 1.25, step: 0.02 },
  { key: "torsoLength", label: "Torso length", min: 0.88, max: 1.15, step: 0.02 },
  { key: "build", label: "Build / mass", min: 0.88, max: 1.15, step: 0.02 },
];

type CompareLayout = "off" | "toggle" | "side" | "onion";

type FitSliderRowProps = {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  disabled?: boolean;
};

function FitSliderRow({
  label,
  value,
  min,
  max,
  step,
  onChange,
  disabled,
}: FitSliderRowProps) {
  const clamp = (v: number) =>
    Math.min(max, Math.max(min, Math.round(v / step) * step));
  return (
    <View style={styles.fitRow}>
      <Text style={styles.fitRowLabel} numberOfLines={2}>
        {label}
      </Text>
      <Pressable
        disabled={disabled}
        onPress={() => onChange(clamp(value - step))}
        style={({ pressed }) => [
          styles.fitStepBtn,
          pressed && styles.fitStepBtnPressed,
        ]}
      >
        <Text style={styles.fitStepTxt}>−</Text>
      </Pressable>
      <Text style={styles.fitRowValue}>{value.toFixed(3)}</Text>
      <Pressable
        disabled={disabled}
        onPress={() => onChange(clamp(value + step))}
        style={({ pressed }) => [
          styles.fitStepBtn,
          pressed && styles.fitStepBtnPressed,
        ]}
      >
        <Text style={styles.fitStepTxt}>+</Text>
      </Pressable>
    </View>
  );
}

type RenderAnnotation = { notes: string; tags: string[] };

const FIT_ISSUE_DEFS = [
  { id: "torso_alignment", label: "Torso alignment", region: "upper" },
  { id: "chest_clipping", label: "Chest clipping", region: "upper" },
  { id: "back_clipping", label: "Back clipping", region: "upper" },
  { id: "shoulder_alignment", label: "Shoulder alignment", region: "upper" },
  { id: "torso_forward", label: "Torso too far forward", region: "upper" },
  { id: "clipping_back", label: "Clipping at back", region: "upper" },
  { id: "neckline_offset", label: "Neckline offset", region: "upper" },
  { id: "sleeve_fit", label: "Sleeve fit", region: "arms" },
  { id: "armpit_clipping", label: "Armpit clipping", region: "arms" },
  { id: "sleeves_ok", label: "Sleeves OK", region: "arms" },
  { id: "waist_fit", label: "Waist fit", region: "lower" },
  { id: "hem_alignment", label: "Hem alignment", region: "lower" },
  { id: "hem_high", label: "Hem too high", region: "lower" },
  { id: "hem_low", label: "Hem too low", region: "lower" },
  { id: "waist_mismatch", label: "Waist mismatch", region: "lower" },
  { id: "pose_specific", label: "Pose-specific failure", region: "both" },
] as const;

const LIVE_QUICK_TAGS = ["torso better", "sleeves fixed", "waist still off"] as const;

type LiveWorkbenchTabId =
  | "view"
  | "body"
  | "garments"
  | "fit"
  | "debug"
  | "stress"
  | "nav";

type LiveVisualPresetId =
  | "clean_mannequin"
  | "fit_debug"
  | "skeleton"
  | "debug";

const LIVE_WORKBENCH_TABS: { id: LiveWorkbenchTabId; label: string }[] = [
  { id: "view", label: "View" },
  { id: "body", label: "Body" },
  { id: "garments", label: "Garments" },
  { id: "fit", label: "Fit" },
  { id: "debug", label: "Debug" },
  { id: "stress", label: "Stress" },
  { id: "nav", label: "Nav" },
];

const LIVE_VISUAL_PRESETS: { id: LiveVisualPresetId; label: string }[] = [
  { id: "clean_mannequin", label: "Clean" },
  { id: "fit_debug", label: "Fit" },
  { id: "skeleton", label: "Skeleton" },
  { id: "debug", label: "Debug" },
];

const LIVE_AVATAR_SOURCE_OPTIONS: { id: AvatarSourcePreference; label: string }[] = [
  { id: "auto", label: "Auto" },
  { id: "realistic_glb", label: "Realistic GLB" },
  { id: "stylised_glb", label: "Stylised GLB" },
  { id: "procedural_fallback", label: "Procedural fallback" },
];

const MAX_RENDER_HISTORY = 10;
const AUTO_POLL_INTERVAL_MS = 1800;

const DEFAULT_PREVIEW_GARMENT_FIT: GarmentFitState = cloneFitState({
  ...DEFAULT_GARMENT_FIT_STATE,
  global: {
    offset: [0, -0.012, 0],
    scale: [1, 1, 1],
    inflate: 0,
  },
  regions: {
    torso: { offsetZ: 0, inflate: 0.006, scaleY: 1.01 },
    sleeves: { offset: [0, -0.01, 0], inflate: 0 },
    waist: { offsetZ: -0.01, tighten: 0.024 },
    hem: { offsetY: -0.012 },
  },
  legacy: {
    ...DEFAULT_GARMENT_FIT_STATE.legacy,
    sleeveOffsetY: -0.01,
    waistAdjustY: -0.024,
  },
});

const PHASE_COPY: Record<DevAvatarPreviewPhase, string> = {
  idle: "Idle — choose pose / preset / fit debug mode, then build a request.",
  request_built: "Request built — run host CLI or refresh render (HTTP).",
  host_handoff_needed:
    "Host handoff — copy JSON/commands on PC, export PNG, keep static server running.",
  waiting_for_export:
    "Waiting for export — host has not placed PNG at HTTP URL yet (404 / server).",
  waiting_for_render:
    "Waiting for render — HTTP poll in progress (manual refresh or auto-poll).",
  render_loaded: "Render loaded — use annotations, compare, and zoom to inspect fit.",
  render_not_found:
    "Render not found — timeout or bad URL; fix export/serve, retry refresh.",
  stale_render:
    "Stale — pose, preset, debug mode, or fit controls changed since this image loaded. Rebuild or refresh.",
  unsupported_debug_mode:
    "Debug view not wired in engine — JSON still includes closy.debug; exporter may ignore.",
  render_failed: "Failed — see error below.",
};

function isWindowsHostDriveRepoPath(root: string): boolean {
  const n = root.replace(/\\/g, "/").trim();
  return /^[a-zA-Z]:\//.test(n);
}

function pushSessionHistory(
  prev: SessionRenderEntry[],
  entry: SessionRenderEntry,
): SessionRenderEntry[] {
  const deduped = prev.filter(
    (s) => s.saved.renderId !== entry.saved.renderId,
  );
  return [entry, ...deduped].slice(0, MAX_RENDER_HISTORY);
}

function patchSessionThumbnail(
  prev: SessionRenderEntry[],
  renderId: string,
  thumbnailUri: string,
): SessionRenderEntry[] {
  return prev.map((e) =>
    e.saved.renderId === renderId ? { ...e, thumbnailUri } : e,
  );
}

function rehydrateFromHistory(entry: SaveAvatarRequestResult): {
  saved: SaveAvatarRequestResult;
  cliRequest: string | null;
  cliExport: string;
} {
  return {
    saved: entry,
    cliExport: buildNpmCliCommand(entry.renderId),
    cliRequest: entry.hostRepoWriteSkipped
      ? buildNpmAvatarRequestCommand(entry.renderId)
      : null,
  };
}

function garmentFitForSessionEntry(
  entry: SessionRenderEntry,
): GarmentFitState | null {
  if (entry.garmentFit) return entry.garmentFit;
  if (entry.fitAdjust) return garmentFitFromLegacyFlat(entry.fitAdjust);
  return null;
}

export function AvatarPreviewDevScreen() {
  const router = useRouter();
  const pose = useAvatarSceneStore((s) => s.pose);
  const setPose = useAvatarSceneStore((s) => s.setPose);
  const presetKey = useAvatarSceneStore((s) => s.presetKey);
  const setPresetKey = useAvatarSceneStore((s) => s.setPresetKey);
  const garmentFit = useAvatarSceneStore((s) => s.garmentFit);
  const setGarmentFit = useAvatarSceneStore((s) => s.setGarmentFit);
  const patchGarmentFit = useAvatarSceneStore((s) => s.patchGarmentFit);
  const resetGarmentFit = useAvatarSceneStore((s) => s.resetGarmentFit);
  const liveViewportShading = useAvatarSceneStore((s) => s.liveViewportShading);
  const setLiveViewportShading = useAvatarSceneStore((s) => s.setLiveViewportShading);
  const offlineFitDebugMode = useAvatarSceneStore((s) => s.offlineFitDebugMode);
  const setOfflineFitDebugMode = useAvatarSceneStore((s) => s.setOfflineFitDebugMode);
  const hydrateScene = useAvatarSceneStore((s) => s.hydrateScene);
  const liveFitActiveRegion = useAvatarSceneStore((s) => s.liveFitActiveRegion);
  const setLiveFitActiveRegion = useAvatarSceneStore(
    (s) => s.setLiveFitActiveRegion,
  );
  const liveFitBaseline = useAvatarSceneStore((s) => s.liveFitBaseline);
  const liveFitShowBaseline = useAvatarSceneStore((s) => s.liveFitShowBaseline);
  const captureLiveFitBaseline = useAvatarSceneStore(
    (s) => s.captureLiveFitBaseline,
  );
  const clearLiveFitBaseline = useAvatarSceneStore((s) => s.clearLiveFitBaseline);
  const toggleLiveFitBaselineCompare = useAvatarSceneStore(
    (s) => s.toggleLiveFitBaselineCompare,
  );
  const pushLiveFitSnapshot = useAvatarSceneStore((s) => s.pushLiveFitSnapshot);
  const restoreLiveFitSnapshot = useAvatarSceneStore(
    (s) => s.restoreLiveFitSnapshot,
  );
  const removeLiveFitSnapshot = useAvatarSceneStore(
    (s) => s.removeLiveFitSnapshot,
  );
  const clearLiveFitSnapshots = useAvatarSceneStore(
    (s) => s.clearLiveFitSnapshots,
  );
  const liveFitSnapshots = useAvatarSceneStore((s) => s.liveFitSnapshots);
  const liveFitQuickTags = useAvatarSceneStore((s) => s.liveFitQuickTags);
  const addLiveFitQuickTag = useAvatarSceneStore((s) => s.addLiveFitQuickTag);
  const clearLiveFitQuickTags = useAvatarSceneStore(
    (s) => s.clearLiveFitQuickTags,
  );
  const liveFitLastSuggestionId = useAvatarSceneStore(
    (s) => s.liveFitLastSuggestionId,
  );
  const setLiveFitLastSuggestionId = useAvatarSceneStore(
    (s) => s.setLiveFitLastSuggestionId,
  );
  const liveFitLastSuggestionSource = useAvatarSceneStore(
    (s) => s.liveFitLastSuggestionSource,
  );
  const setLiveFitLastSuggestionSource = useAvatarSceneStore(
    (s) => s.setLiveFitLastSuggestionSource,
  );
  const liveClipOverlay = useAvatarSceneStore((s) => s.liveClipOverlay);
  const setLiveClipOverlay = useAvatarSceneStore((s) => s.setLiveClipOverlay);
  const lastPoseStressReport = useAvatarSceneStore((s) => s.lastPoseStressReport);
  const setLastPoseStressReport = useAvatarSceneStore(
    (s) => s.setLastPoseStressReport,
  );
  const stressTestHighlightPose = useAvatarSceneStore(
    (s) => s.stressTestHighlightPose,
  );
  const setStressTestHighlightPose = useAvatarSceneStore(
    (s) => s.setStressTestHighlightPose,
  );
  const resetLiveFitRegionToDefault = useAvatarSceneStore(
    (s) => s.resetLiveFitRegionToDefault,
  );
  const bodyShape = useAvatarSceneStore((s) => s.bodyShape);
  const patchBodyShape = useAvatarSceneStore((s) => s.patchBodyShape);
  const resetBodyShape = useAvatarSceneStore((s) => s.resetBodyShape);

  const [stressTestBusy, setStressTestBusy] = useState(false);
  const [stabilizeBusy, setStabilizeBusy] = useState(false);
  const [liveAvatarSourcePreference, setLiveAvatarSourcePreference] =
    useState<AvatarSourcePreference>("auto");
  const [liveBodyOnlyGarments, setLiveBodyOnlyGarments] = useState(false);
  const [liveGarmentOnlyViewport, setLiveGarmentOnlyViewport] = useState(false);
  const [liveSkeletonOverlay, setLiveSkeletonOverlay] = useState(false);
  const [liveFitDebugOverlay, setLiveFitDebugOverlay] = useState(false);
  const [liveVisualPreset, setLiveVisualPreset] =
    useState<LiveVisualPresetId>("clean_mannequin");
  const [livePoseFitDebug, setLivePoseFitDebug] = useState<LiveViewportPoseFitDebug | null>(
    null,
  );
  const [liveGarmentAttachDebug, setLiveGarmentAttachDebug] = useState(false);
  const [liveSceneInspectEnabled, setLiveSceneInspectEnabled] = useState(false);
  const [liveSceneMarkers, setLiveSceneMarkers] = useState(false);
  const [liveSceneBrightBody, setLiveSceneBrightBody] = useState(false);
  const [manualFrameBoundsNonce, setManualFrameBoundsNonce] = useState(0);
  const [viewportBaselineNonce, setViewportBaselineNonce] = useState(0);

  const devSceneInspect = useMemo<AvatarViewportDevSceneInspect>(
    () => ({
      enabled: liveSceneInspectEnabled,
      showMarkers: liveSceneMarkers,
      debugBrightBody: liveSceneBrightBody,
      manualFrameBoundsNonce,
    }),
    [
      liveSceneInspectEnabled,
      liveSceneMarkers,
      liveSceneBrightBody,
      manualFrameBoundsNonce,
    ],
  );

  const setLiveBodyOnlyGarmentsSafe = useCallback((v: boolean) => {
    setLiveBodyOnlyGarments(v);
    if (v) setLiveGarmentOnlyViewport(false);
  }, []);

  const setLiveGarmentOnlyViewportSafe = useCallback((v: boolean) => {
    setLiveGarmentOnlyViewport(v);
    if (v) setLiveBodyOnlyGarments(false);
  }, []);

  const applyLiveVisualPreset = useCallback(
    (presetId: LiveVisualPresetId) => {
      setLiveVisualPreset(presetId);
      switch (presetId) {
        case "clean_mannequin":
          setLiveViewportShading("normal");
          setLiveBodyOnlyGarments(false);
          setLiveGarmentOnlyViewport(false);
          setLiveSkeletonOverlay(false);
          setLiveFitDebugOverlay(false);
          setLiveGarmentAttachDebug(false);
          setLiveClipOverlay(false);
          setLiveSceneInspectEnabled(false);
          setLiveSceneMarkers(false);
          setLiveSceneBrightBody(false);
          break;
        case "fit_debug":
          setLiveViewportShading("garment_focus");
          setLiveBodyOnlyGarments(false);
          setLiveGarmentOnlyViewport(false);
          setLiveSkeletonOverlay(false);
          setLiveFitDebugOverlay(true);
          setLiveGarmentAttachDebug(true);
          setLiveClipOverlay(true);
          setLiveSceneInspectEnabled(false);
          setLiveSceneMarkers(false);
          break;
        case "skeleton":
          setLiveViewportShading("garment_focus");
          setLiveBodyOnlyGarments(false);
          setLiveGarmentOnlyViewport(false);
          setLiveSkeletonOverlay(true);
          setLiveFitDebugOverlay(false);
          setLiveGarmentAttachDebug(false);
          setLiveClipOverlay(false);
          break;
        case "debug":
          setLiveViewportShading("overlay_debug");
          setLiveBodyOnlyGarments(false);
          setLiveGarmentOnlyViewport(false);
          setLiveSkeletonOverlay(true);
          setLiveFitDebugOverlay(true);
          setLiveGarmentAttachDebug(true);
          setLiveClipOverlay(true);
          setLiveSceneInspectEnabled(true);
          setLiveSceneMarkers(true);
          break;
        default:
          break;
      }
    },
    [
      setLiveViewportShading,
      setLiveClipOverlay,
      setLiveSceneInspectEnabled,
      setLiveSceneMarkers,
      setLiveSceneBrightBody,
    ],
  );

  const [busy, setBusy] = useState(false);
  const [busyPoll, setBusyPoll] = useState(false);
  const [autoPoll, setAutoPoll] = useState(false);
  const [autoPollLoopOn, setAutoPollLoopOn] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [cliExportHint, setCliExportHint] = useState<string | null>(null);
  const [cliRequestHint, setCliRequestHint] = useState<string | null>(null);
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [imageCacheBust, setImageCacheBust] = useState<number | null>(null);
  const [lastJsonPreview, setLastJsonPreview] = useState<string | null>(null);
  const [lastSaved, setLastSaved] = useState<SaveAvatarRequestResult | null>(
    null,
  );
  const [sessionHistory, setSessionHistory] = useState<SessionRenderEntry[]>(
    [],
  );
  const [lastFetchSummary, setLastFetchSummary] = useState<string | null>(null);
  const [lastSuccessAt, setLastSuccessAt] = useState<string | null>(null);
  const [devPhase, setDevPhase] = useState<DevAvatarPreviewPhase>("idle");
  const [lastClippingStats, setLastClippingStats] =
    useState<ClippingStatsV1 | null>(null);
  const [devMainTab, setDevMainTab] = useState<"live" | "offline">("live");
  const [liveWorkbenchTab, setLiveWorkbenchTab] = useState<LiveWorkbenchTabId>("view");
  const [camResetNonce, setCamResetNonce] = useState(0);
  const { height: windowHeight } = useWindowDimensions();
  const liveViewportH = Math.round(Math.min(420, Math.max(256, windowHeight * 0.34)));
  const viewportNav = useAvatarSceneStore((s) => s.viewportNav);
  const patchViewportNav = useAvatarSceneStore((s) => s.patchViewportNav);
  const resetViewportNav = useAvatarSceneStore((s) => s.resetViewportNav);
  const resetVisibleBaseline = useCallback(
    (reason: "first_open" | "manual" | "guard") => {
      setPose("relaxed");
      setPresetKey("default");
      setLiveVisualPreset("clean_mannequin");
      setLiveViewportShading("normal");
      setOfflineFitDebugMode("normal");
      setLiveAvatarSourcePreference("auto");
      setLiveBodyOnlyGarments(false);
      setLiveGarmentOnlyViewport(false);
      setLiveSkeletonOverlay(false);
      setLiveFitDebugOverlay(false);
      setLiveGarmentAttachDebug(false);
      setLiveClipOverlay(false);
      setLiveSceneInspectEnabled(false);
      setLiveSceneMarkers(false);
      setLiveSceneBrightBody(false);
      setManualFrameBoundsNonce(0);
      setLiveFitActiveRegion("global");
      clearLiveFitBaseline();
      resetBodyShape();
      setGarmentFit(cloneFitState(DEFAULT_PREVIEW_GARMENT_FIT));
      resetViewportNav();
      setViewportBaselineNonce((n) => n + 1);
      setCamResetNonce((n) => n + 1);
      if (reason !== "first_open") {
      setStatus(
          reason === "guard"
            ? "Viewport visibility reset -> sane default preview."
            : "Startup preview baseline restored.",
        );
      }
    },
    [
      resetViewportNav,
      setGarmentFit,
      clearLiveFitBaseline,
      setLiveFitActiveRegion,
      resetBodyShape,
      setLiveClipOverlay,
      setLiveViewportShading,
      setOfflineFitDebugMode,
      setPose,
      setPresetKey,
    ],
  );
  useLayoutEffect(() => {
    resetVisibleBaseline("first_open");
  }, [resetVisibleBaseline]);
  const [reuseRenderId, setReuseRenderId] = useState(false);
  const [loadSnapshot, setLoadSnapshot] = useState<LoadSnapshot | null>(null);
  const [annotations, setAnnotations] = useState<
    Record<string, RenderAnnotation>
  >({});
  const [compareLayout, setCompareLayout] = useState<CompareLayout>("off");
  const [compareBaselineUri, setCompareBaselineUri] = useState<string | null>(
    null,
  );
  const [compareShowBaseline, setCompareShowBaseline] = useState(false);
  const [onionOpacity, setOnionOpacity] = useState(0.45);
  const [previewZoom, setPreviewZoom] = useState(1);

  const phaseRef = useRef<DevAvatarPreviewPhase>("idle");
  const autoPollRef = useRef(false);
  const lastSavedRef = useRef<SaveAvatarRequestResult | null>(null);

  useEffect(() => {
    phaseRef.current = devPhase;
  }, [devPhase]);

  useEffect(() => {
    autoPollRef.current = autoPoll;
  }, [autoPoll]);

  useEffect(() => {
    lastSavedRef.current = lastSaved;
  }, [lastSaved]);

  useEffect(() => {
    if (!lastSaved) return;
    const id = lastSaved.renderId;
    const ann = annotations[id];
    if (!ann) return;
    setSessionHistory((h) =>
      h.map((e) =>
        e.saved.renderId === id
          ? { ...e, checklistTags: [...ann.tags] }
          : e,
      ),
    );
  }, [annotations, lastSaved?.renderId]);

  const repoRoot = useMemo(() => getClosyRepoRoot(), []);
  const renderBaseUrl = useMemo(() => getDevAvatarRenderBaseUrl(), []);

  const expectedRequestRel = useMemo(
    () =>
      lastSaved ? requestRelativePathForRenderId(lastSaved.renderId) : null,
    [lastSaved],
  );
  const expectedRenderRel = useMemo(
    () =>
      lastSaved ? renderRelativePathForRenderId(lastSaved.renderId) : null,
    [lastSaved],
  );
  const resolvedRenderUrl = useMemo(
    () => (lastSaved ? getAvatarRenderHttpUrl(lastSaved.renderId) : null),
    [lastSaved],
  );

  const displayImageUri = useMemo(() => {
    if (imageUri == null) return null;
    const base = imageUri.split("?")[0];
    return imageCacheBust != null ? `${base}?cb=${imageCacheBust}` : imageUri;
  }, [imageUri, imageCacheBust]);

  const mockOn = process.env.EXPO_PUBLIC_AVATAR_EXPORT_MOCK === "1";
  const repoIsWindowsHostPath =
    repoRoot != null && isWindowsHostDriveRepoPath(repoRoot);
  const canUseCache = canUseCacheDirectoryForExport();
  const envRawLen =
    typeof process.env.EXPO_PUBLIC_CLOSY_REPO_ROOT === "string"
      ? process.env.EXPO_PUBLIC_CLOSY_REPO_ROOT.length
      : 0;
  const hostFileRenderOnAndroidDisabled =
    Platform.OS === "android" && repoIsWindowsHostPath;

  const debugWired = useMemo(
    () => isFitDebugModeEngineWired(offlineFitDebugMode),
    [offlineFitDebugMode],
  );

  const mayBeStale = useMemo(() => {
    if (!imageUri || !lastSaved || !loadSnapshot) return false;
    if (loadSnapshot.renderId !== lastSaved.renderId) return false;
    return (
      loadSnapshot.pose !== pose ||
      loadSnapshot.preset !== presetKey ||
      loadSnapshot.fitDebugMode !== offlineFitDebugMode ||
      !fitStatesEqual(loadSnapshot.garmentFit, garmentFit)
    );
  }, [imageUri, lastSaved, loadSnapshot, pose, presetKey, offlineFitDebugMode, garmentFit]);

  const currentAnnotation: RenderAnnotation = useMemo(() => {
    if (!lastSaved) return { notes: "", tags: [] };
    return annotations[lastSaved.renderId] ?? { notes: "", tags: [] };
  }, [annotations, lastSaved]);

  const garmentFitForViewport =
    liveFitShowBaseline && liveFitBaseline != null
      ? liveFitBaseline
      : garmentFit;

  const runtimeAssetUrls = useMemo(() => getAvatarRuntimeAssetUrls(), []);

  const runtimeClipReport = useMemo(
    () =>
      analyzeRuntimeClipping({
        garmentFit: garmentFitForViewport,
        pose,
        hasRuntimeBodyGltf: !!runtimeAssetUrls.bodyGltfUrl,
        hasRuntimeTopGltf: !!runtimeAssetUrls.topGltfUrl,
        hasRuntimeBottomGltf: !!runtimeAssetUrls.bottomGltfUrl,
        bodyShape,
      }),
    [
      garmentFitForViewport,
      pose,
      runtimeAssetUrls.bodyGltfUrl,
      runtimeAssetUrls.topGltfUrl,
      runtimeAssetUrls.bottomGltfUrl,
      bodyShape,
    ],
  );

  const runtimeClipFlags = useMemo(
    () => ({
      hasRuntimeBodyGltf: !!runtimeAssetUrls.bodyGltfUrl,
      hasRuntimeTopGltf: !!runtimeAssetUrls.topGltfUrl,
      hasRuntimeBottomGltf: !!runtimeAssetUrls.bottomGltfUrl,
      bodyShape,
    }),
    [
      runtimeAssetUrls.bodyGltfUrl,
      runtimeAssetUrls.topGltfUrl,
      runtimeAssetUrls.bottomGltfUrl,
      bodyShape,
    ],
  );

  const fitSuggestions = useMemo(() => {
    const fromLive = suggestionsFromLiveHeuristics(
      garmentFit,
      liveViewportShading,
    );
    const fromRuntime = suggestionsFromRuntimeClipping(runtimeClipReport);
    const fromStats = suggestionsFromClippingStats(lastClippingStats);
    const fromChk = suggestionsFromChecklistTagIds(currentAnnotation.tags);
    const seen = new Set<string>();
    const out: FitSuggestion[] = [];
    for (const s of [...fromLive, ...fromRuntime, ...fromStats, ...fromChk]) {
      if (seen.has(s.id)) continue;
      seen.add(s.id);
      out.push(s);
    }
    return out;
  }, [
    garmentFit,
    liveViewportShading,
    runtimeClipReport,
    lastClippingStats,
    currentAnnotation.tags,
  ]);

  useEffect(() => {
    const wired =
      offlineFitDebugMode === "normal" ||
      isFitDebugModeEngineWired(offlineFitDebugMode);
    if (wired) {
      setDevPhase((ph) =>
        ph === "unsupported_debug_mode" ? "idle" : ph,
      );
      return;
    }
    setDevPhase((ph) => {
      const allow = [
        "idle",
        "request_built",
        "render_loaded",
        "stale_render",
        "unsupported_debug_mode",
      ];
      return allow.includes(ph) ? "unsupported_debug_mode" : ph;
    });
  }, [offlineFitDebugMode]);

  useEffect(() => {
    if (!imageUri || !lastSaved || !loadSnapshot) return;
    if (loadSnapshot.renderId !== lastSaved.renderId) return;
    const changed =
      loadSnapshot.pose !== pose ||
      loadSnapshot.preset !== presetKey ||
      loadSnapshot.fitDebugMode !== offlineFitDebugMode ||
      !fitStatesEqual(loadSnapshot.garmentFit, garmentFit);
    if (changed) {
      setDevPhase((ph) =>
        ph === "render_loaded" || ph === "stale_render"
          ? "stale_render"
          : ph,
      );
    } else if (devPhase === "stale_render") {
      setDevPhase("render_loaded");
    }
  }, [
    pose,
    presetKey,
    offlineFitDebugMode,
    garmentFit,
    imageUri,
    lastSaved?.renderId,
    loadSnapshot,
    devPhase,
  ]);

  const flashCopied = useCallback(() => {
    setStatus("Copied to clipboard.");
  }, []);

  const onShareCommand = useCallback(async (cmd: string) => {
    try {
      await Share.share({ message: cmd, title: "Closy avatar export" });
      setStatus((s) => s ?? "Share sheet dismissed.");
    } catch {
      /* user cancelled */
    }
  }, []);

  const onShareJson = useCallback(async (json: string) => {
    try {
      await Share.share({ message: json, title: "Closy outfit JSON" });
    } catch {
      /* user cancelled */
    }
  }, []);

  const onCopy = useCallback(
    async (text: string) => {
      await Clipboard.setStringAsync(text);
      flashCopied();
    },
    [flashCopied],
  );

  const openRenderUrl = useCallback(async () => {
    if (resolvedRenderUrl == null) return;
    try {
      const can = await Linking.canOpenURL(resolvedRenderUrl);
      if (can) await Linking.openURL(resolvedRenderUrl);
      else setStatus("Cannot open URL on this device.");
    } catch {
      setStatus("Failed to open URL.");
    }
  }, [resolvedRenderUrl]);

  const recordProbeForUrl = useCallback(
    async (url: string | null) => {
      if (url == null) {
        setLastFetchSummary(
          "No resolved HTTP render URL (set EXPO_PUBLIC_AVATAR_RENDER_BASE_URL or check Metro host).",
        );
        return;
      }
      const p = await probeAvatarRenderHttp(url);
      setLastFetchSummary(
        p.ok
          ? `OK — HTTP ${p.status}`
          : `HTTP ${p.status}${p.detail ? ` — ${p.detail}` : ""}`,
      );
      if (
        !p.ok &&
        p.status === 404 &&
        (phaseRef.current === "host_handoff_needed" ||
          phaseRef.current === "waiting_for_render")
      ) {
        setDevPhase("waiting_for_export");
      }
    },
    [],
  );

  const afterRenderReady = useCallback(
    (
      uri: string,
      saved: SaveAvatarRequestResult,
      snapshotOverride?: Pick<
        LoadSnapshot,
        "pose" | "preset" | "fitDebugMode" | "garmentFit"
      >,
    ) => {
      const base = uri.split("?")[0];
      setImageUri(base);
      setImageCacheBust(Date.now());
      setLastSuccessAt(new Date().toLocaleString());
      const mode = snapshotOverride?.fitDebugMode ?? offlineFitDebugMode;
      setLoadSnapshot({
        renderId: saved.renderId,
        pose: snapshotOverride?.pose ?? pose,
        preset: snapshotOverride?.preset ?? presetKey,
        fitDebugMode: mode,
        garmentFit: cloneFitState(snapshotOverride?.garmentFit ?? garmentFit),
      });
      setSessionHistory((h) => patchSessionThumbnail(h, saved.renderId, base));
      if (mode === "clipping_hotspot") {
        void fetchClippingStatsV1(saved.renderId, getAvatarClippingStatsHttpUrl).then(
          setLastClippingStats,
        );
      } else {
        setLastClippingStats(null);
      }
    },
    [pose, presetKey, offlineFitDebugMode, garmentFit],
  );

  /* Auto-poll HTTP when enabled; stops when render loads or toggle off. */
  useEffect(() => {
    if (!autoPoll || !lastSaved) {
      setAutoPollLoopOn(false);
      return;
    }
    const url = getAvatarRenderHttpUrl(lastSaved.renderId);
    if (!url) {
      setAutoPollLoopOn(false);
      return;
    }

    let stopped = false;
    setAutoPollLoopOn(true);

    const loop = async () => {
      while (!stopped && autoPollRef.current) {
        if (phaseRef.current === "render_loaded") break;

        setDevPhase((ph) => {
          if (ph === "idle" || ph === "render_failed") {
            return ph;
          }
          /* Include render_not_found so auto-poll can recover after a timeout. */
          return "waiting_for_render";
        });

        const p = await probeAvatarRenderHttp(url);
        if (stopped || !autoPollRef.current) break;

        setLastFetchSummary(
          p.ok
            ? `OK — HTTP ${p.status} (auto-poll)`
            : `HTTP ${p.status} (auto-poll)${p.detail ? ` — ${p.detail}` : ""}`,
        );

        if (p.ok) {
          const s = lastSavedRef.current;
          if (s) afterRenderReady(url, s);
          setDevPhase("render_loaded");
          setError(null);
          break;
        }

        setDevPhase((ph) =>
          ph === "waiting_for_render" ? "waiting_for_export" : ph,
        );

        await new Promise((r) => setTimeout(r, AUTO_POLL_INTERVAL_MS));
      }
      if (!stopped) setAutoPollLoopOn(false);
    };

    void loop();

    return () => {
      stopped = true;
      setAutoPollLoopOn(false);
    };
  }, [afterRenderReady, autoPoll, lastSaved?.renderId]);

  const applyPersistedExportResult = useCallback(
    async (saved: SaveAvatarRequestResult) => {
      const exportResult = await runAvatarExport(saved, {});

      if (exportResult.ok && exportResult.variant === "manual_cli") {
        setDevPhase("request_built");
        const reqRel = requestRelativePathForRenderId(saved.renderId);
        const head = saved.repoWriteSucceeded
          ? `Request saved to ${reqRel}.`
          : "Request stored in app cache.";
        setStatus(
          `${head}\n\n${exportResult.message}\n\nOutput: ${exportResult.outputPathForDisplay}\nCLI: ${exportResult.cliCommand}`,
        );
      } else if (
        exportResult.ok &&
        exportResult.variant === "host_handoff_required"
      ) {
        setDevPhase("host_handoff_needed");
        const u = getAvatarRenderHttpUrl(saved.renderId);
        void recordProbeForUrl(u ?? null);
        const lines = [
          "Step 1 — Request built",
          saved.cacheWriteSucceeded
            ? "JSON in app cache (below)."
            : "",
          "",
          "Step 2 — PC: closy:avatar-request → closy:avatar-export. Serve repo: `npx serve .`",
          "",
          exportResult.cliRequestCommand,
          "",
          exportResult.cliExportCommand,
          "",
          `Files: ${exportResult.expectedRequestRelativePath} → ${exportResult.expectedRenderRelativePath}`,
          "",
          "Step 3 — Refresh render (or enable Auto-poll).",
        ].filter(Boolean);
        setStatus(lines.join("\n"));
      } else if (exportResult.ok && exportResult.variant === "image") {
        setDevPhase("render_loaded");
        afterRenderReady(exportResult.imageUri, saved);
        if (exportResult.mode === "http") {
          void recordProbeForUrl(exportResult.imageUri);
        }
        setStatus(`Loaded render (${exportResult.mode}).`);
      } else if (!exportResult.ok) {
        setDevPhase(
          exportResult.code === "POLL_TIMEOUT"
            ? "render_not_found"
            : "render_failed",
        );
        setError(
          `${exportResult.message}${exportResult.cliCommand ? `\n\n${exportResult.cliCommand}` : ""}`,
        );
      }
    },
    [afterRenderReady, recordProbeForUrl],
  );

  const onGenerate = useCallback(async () => {
    setBusy(true);
    setBusyPoll(false);
    setError(null);
    setStatus(null);
    setWarnings([]);
    setImageUri(null);
    setImageCacheBust(null);
    setLastSuccessAt(null);
    setLastJsonPreview(null);
    setLastSaved(null);
    setLastFetchSummary(null);
    setCliExportHint(null);
    setCliRequestHint(null);
    setLoadSnapshot(null);
    setDevPhase("idle");
    try {
      const renderIdToUse =
        reuseRenderId && lastSavedRef.current != null
          ? lastSavedRef.current.renderId
          : `dev_${presetKey}_${pose}_${Date.now()}`;
      const request = buildExportRequestFromAvatarScene(useAvatarSceneStore.getState(), {
        renderId: renderIdToUse,
      });
      const saved = await saveAvatarExportRequest(request);
      setLastSaved(saved);
      const entry: SessionRenderEntry = {
        saved,
        pose,
        preset: presetKey,
        fitDebugMode: offlineFitDebugMode,
        garmentFit: cloneFitState(garmentFit),
        createdAt: Date.now(),
        thumbnailUri: null,
      };
      setSessionHistory((h) => pushSessionHistory(h, entry));
      setLastJsonPreview(saved.jsonForEngine);
      setCliExportHint(buildNpmCliCommand(saved.renderId));
      if (saved.hostRepoWriteSkipped) {
        setCliRequestHint(buildNpmAvatarRequestCommand(saved.renderId));
      }

      const persisted = saved.repoWriteSucceeded || saved.cacheWriteSucceeded;
      setWarnings(saved.warnings);

      if (!persisted) {
        setDevPhase("render_failed");
        setError(
          saved.warnings.length > 0
            ? saved.warnings.join("\n\n")
            : "Could not save the request JSON to disk.",
        );
        if (repoRoot == null) {
          setStatus(
            "Set EXPO_PUBLIC_CLOSY_REPO_ROOT and restart Expo (`npx expo start --clear`) for path hints.",
          );
        }
        return;
      }

      setError(null);
      await applyPersistedExportResult(saved);
    } catch (e) {
      setDevPhase("render_failed");
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setBusy(false);
    }
  }, [
    applyPersistedExportResult,
    garmentFit,
    offlineFitDebugMode,
    pose,
    presetKey,
    repoRoot,
    reuseRenderId,
  ]);

  const onRefreshRenderHttp = useCallback(async () => {
    if (lastSaved == null) {
      setError("Build a request first.");
      setDevPhase("render_failed");
      return;
    }
    const url = getAvatarRenderHttpUrl(lastSaved.renderId);
    if (url == null) {
      setDevPhase("render_failed");
      setError(
        "No HTTP render base URL. Set EXPO_PUBLIC_AVATAR_RENDER_BASE_URL and restart Expo.",
      );
      return;
    }
    setBusyPoll(true);
    setError(null);
    setDevPhase("waiting_for_render");
    setLastFetchSummary("Polling…");
    try {
      const exportResult = await runAvatarExport(lastSaved, {
        poll: true,
        pollTimeoutMs: 120_000,
      });
      if (exportResult.ok && exportResult.variant === "image") {
        if (lastSaved) afterRenderReady(exportResult.imageUri, lastSaved);
        setDevPhase("render_loaded");
        void recordProbeForUrl(exportResult.imageUri);
        setStatus(`Render loaded (${exportResult.mode}).`);
      } else if (!exportResult.ok) {
        void recordProbeForUrl(url);
        if (exportResult.code === "POLL_TIMEOUT") {
          setDevPhase("render_not_found");
        } else {
          setDevPhase("render_failed");
        }
        setError(
          `${exportResult.message}${exportResult.cliCommand ? `\n\n${exportResult.cliCommand}` : ""}`,
        );
      } else if (
        exportResult.ok &&
        exportResult.variant === "host_handoff_required"
      ) {
        setDevPhase("host_handoff_needed");
        void recordProbeForUrl(url);
        setStatus(exportResult.message);
      }
    } catch (e) {
      setDevPhase("render_failed");
      setLastFetchSummary(e instanceof Error ? e.message : "Request failed");
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setBusyPoll(false);
    }
  }, [afterRenderReady, lastSaved, recordProbeForUrl]);

  const selectHistoryEntry = useCallback((entry: SessionRenderEntry) => {
    const { saved, cliRequest, cliExport } = rehydrateFromHistory(entry.saved);
    setLastSaved(saved);
    useAvatarSceneStore.getState().setLiveFitShowBaseline(false);
    const gf: GarmentFitState =
      entry.garmentFit
        ? cloneFitState(entry.garmentFit)
        : entry.fitAdjust
          ? garmentFitFromLegacyFlat(entry.fitAdjust)
          : cloneFitState(DEFAULT_GARMENT_FIT_STATE);
    hydrateScene({
      pose: entry.pose,
      presetKey: entry.preset,
      offlineFitDebugMode: entry.fitDebugMode,
      garmentFit: gf,
    });
    setAnnotations((a) => ({
      ...a,
      [saved.renderId]: {
        notes: a[saved.renderId]?.notes ?? "",
        tags: [...(entry.checklistTags ?? [])],
      },
    }));
    setLastJsonPreview(saved.jsonForEngine);
    setCliExportHint(cliExport);
    setCliRequestHint(cliRequest);
    setError(null);
    setStatus(`History: ${saved.renderId}`);
    setLastFetchSummary(null);
    if (entry.thumbnailUri) {
      afterRenderReady(entry.thumbnailUri, saved, {
        pose: entry.pose,
        preset: entry.preset,
        fitDebugMode: entry.fitDebugMode,
        garmentFit: entry.garmentFit
          ? cloneFitState(entry.garmentFit)
          : entry.fitAdjust
            ? garmentFitFromLegacyFlat(entry.fitAdjust)
            : DEFAULT_GARMENT_FIT_STATE,
      });
      setDevPhase("render_loaded");
    } else {
      setImageUri(null);
      setImageCacheBust(null);
      setLastSuccessAt(null);
      setLoadSnapshot(null);
      setDevPhase(
        saved.hostRepoWriteSkipped ? "host_handoff_needed" : "request_built",
      );
    }
  }, [afterRenderReady, hydrateScene]);

  const applyLastSuggestionAgain = useCallback(() => {
    const id = useAvatarSceneStore.getState().liveFitLastSuggestionId;
    if (id == null) return;
    const sug = fitSuggestions.find((x) => x.id === id);
    if (sug) {
      patchGarmentFit((prev) => sug.apply(cloneFitState(prev)));
      setLiveFitLastSuggestionSource(sug.suggestionSource ?? "unknown");
    }
  }, [fitSuggestions, patchGarmentFit, setLiveFitLastSuggestionSource]);

  const runStressTestFit = useCallback(() => {
    setStressTestBusy(true);
    try {
      const r = runPoseStressTest(garmentFit, runtimeClipFlags);
      setLastPoseStressReport(r);
      setStressTestHighlightPose(r.worstPose);
      setStatus(
        `Stress test: stability ${r.overallStabilityScore} · worst pose ${r.worstPose ?? "—"}`,
      );
    } finally {
      setStressTestBusy(false);
    }
  }, [
    garmentFit,
    runtimeClipFlags,
    setLastPoseStressReport,
    setStressTestHighlightPose,
  ]);

  const runStabilizeFit = useCallback(() => {
    setStabilizeBusy(true);
    try {
      const out = stabilizeFitAcrossPoses(garmentFit, runtimeClipFlags);
      setLastPoseStressReport(out.finalReport);
      setStressTestHighlightPose(out.finalReport.worstPose);
      if (out.iterations > 0) {
        patchGarmentFit(() => out.fit);
      }
      setStatus(
        out.iterations === 0
          ? `Already stable: score ${out.finalReport.overallStabilityScore}`
          : `Stabilized: ${out.iterations} step(s), stability ${out.finalReport.overallStabilityScore}`,
      );
    } finally {
      setStabilizeBusy(false);
    }
  }, [
    garmentFit,
    runtimeClipFlags,
    patchGarmentFit,
    setLastPoseStressReport,
    setStressTestHighlightPose,
  ]);

  const onMock = useCallback(async () => {
    setBusy(true);
    setError(null);
    setWarnings([]);
    setImageUri(null);
    setImageCacheBust(null);
    try {
      const request = buildExportRequestFromAvatarScene(
        {
          ...useAvatarSceneStore.getState(),
          pose: "relaxed",
          presetKey: "casual",
        },
        { renderId: `mock_${Date.now()}` },
      );
      const saved = await saveAvatarExportRequest(request);
      setLastSaved(saved);
      const entry: SessionRenderEntry = {
        saved,
        pose: "relaxed",
        preset: "casual",
        fitDebugMode: useAvatarSceneStore.getState().offlineFitDebugMode,
        garmentFit: cloneFitState(useAvatarSceneStore.getState().garmentFit),
        createdAt: Date.now(),
        thumbnailUri: null,
      };
      setSessionHistory((h) => pushSessionHistory(h, entry));
      if (!saved.repoWriteSucceeded && !saved.cacheWriteSucceeded) {
        setWarnings(saved.warnings);
        setDevPhase("render_failed");
        setError(
          saved.warnings.join("\n\n") ||
            "Save failed; mock preview can still run.",
        );
      } else {
        setWarnings(saved.warnings);
      }
      setCliExportHint(buildNpmCliCommand(saved.renderId));
      setCliRequestHint(
        saved.hostRepoWriteSkipped
          ? buildNpmAvatarRequestCommand(saved.renderId)
          : null,
      );
      const result = await runAvatarExportMock(saved);
      if (result.ok && result.variant === "image") {
        afterRenderReady(result.imageUri, saved, {
          pose: "relaxed",
          preset: "casual",
          fitDebugMode: useAvatarSceneStore.getState().offlineFitDebugMode,
          garmentFit: cloneFitState(useAvatarSceneStore.getState().garmentFit),
        });
        setDevPhase("render_loaded");
        setStatus("Mock image (no native binary).");
      }
    } catch (e) {
      setDevPhase("render_failed");
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setBusy(false);
    }
  }, [afterRenderReady]);

  const refreshBlocked =
    lastSaved == null || busy || busyPoll || autoPollLoopOn;

  const setNotesForCurrent = useCallback(
    (text: string) => {
      if (!lastSaved) return;
      const id = lastSaved.renderId;
      setAnnotations((a) => {
        const cur = a[id] ?? { notes: "", tags: [] };
        return { ...a, [id]: { ...cur, notes: text } };
      });
    },
    [lastSaved],
  );

  const toggleIssueTag = useCallback(
    (tagId: string) => {
      if (!lastSaved) return;
      const id = lastSaved.renderId;
      setAnnotations((a) => {
        const cur = a[id] ?? { notes: "", tags: [] };
        const tags = cur.tags.includes(tagId)
          ? cur.tags.filter((t) => t !== tagId)
          : [...cur.tags, tagId];
        return { ...a, [id]: { ...cur, tags } };
      });
    },
    [lastSaved],
  );

  const captureCompareBaseline = useCallback(() => {
    if (!displayImageUri) return;
    setCompareBaselineUri(displayImageUri.split("?")[0]);
    setCompareShowBaseline(false);
    if (compareLayout === "off") setCompareLayout("toggle");
  }, [compareLayout, displayImageUri]);

  const loadCompareFromPreviousHistory = useCallback(() => {
    const prev = sessionHistory.find(
      (e) => e.saved.renderId !== lastSaved?.renderId && e.thumbnailUri,
    );
    if (prev?.thumbnailUri) {
      setCompareBaselineUri(prev.thumbnailUri);
      setCompareLayout("toggle");
      setCompareShowBaseline(true);
      setStatus(`Compare baseline: ${prev.saved.renderId.slice(0, 24)}…`);
    } else {
      setStatus("No previous thumbnail in session history.");
    }
  }, [lastSaved?.renderId, sessionHistory]);

  const previewHelpText = useMemo(() => {
    if (busy && !imageUri) return "Building request…";
    if (autoPollLoopOn && !imageUri) return "Auto-polling HTTP render…";
    if (busyPoll && !imageUri) return "Refreshing render…";
    if (imageUri) return null;
    if (devPhase === "render_not_found") return "Render not found at HTTP URL.";
    if (devPhase === "render_failed" && error)
      return "Resolve error, then build or refresh.";
    if (devPhase === "waiting_for_export")
      return "Waiting for host PNG at HTTP URL.";
    if (lastSaved) return "Tap Refresh render or enable Auto-poll.";
    return "Build a request to see the preview frame.";
  }, [
    busy,
    imageUri,
    autoPollLoopOn,
    busyPoll,
    devPhase,
    error,
    lastSaved,
  ]);

  return (
    <ScreenContainer scroll={false} omitTopSafeArea style={styles.root}>
      <View style={styles.flexPage}>
        <View style={styles.headerBlock}>
        <Text style={styles.title}>Avatar preview (dev)</Text>
        <Text style={styles.devBadge}>Dev / debug only — not shown in production flows.</Text>

        <View style={styles.mainTabRow}>
          <AppButton
            label="Live 3D (mainline)"
            variant={devMainTab === "live" ? "primary" : "secondary"}
            onPress={() => {
              setDevMainTab("live");
              setLiveWorkbenchTab("view");
            }}
          />
          <AppButton
            label="Offline debug render"
            variant={devMainTab === "offline" ? "primary" : "secondary"}
            onPress={() => setDevMainTab("offline")}
          />
        </View>
        <Text style={styles.debugNote}>
          {devMainTab === "live"
            ? "Primary path: in-app WebGL. Body / top / bottom can load GLBs via EXPO_PUBLIC_AVATAR_RUNTIME_*_GLTF_URL (see .env.example); unset slots stay proxy geometry. Offline PNG stays the regression / clipping tool."
            : "Secondary path: host request JSON → CLI `avatar_export` → HTTP PNG. Use for clipping hotspot, high-res stills, and engine-identical review."}
        </Text>
        </View>

        {devMainTab === "live" ? (
          <View style={styles.liveWorkbenchColumn}>
            <View style={[styles.viewportPinned, { height: liveViewportH + 22 }]}>
              <AvatarViewportLive
                key={`live-viewport:${viewportBaselineNonce}`}
                pose={pose}
                preset={presetKey}
                garmentFit={garmentFitForViewport}
                liveShading={liveViewportShading}
                bodyShape={bodyShape}
                height={liveViewportH}
                compareActive={liveFitShowBaseline && liveFitBaseline != null}
                clipOverlayEnabled={liveClipOverlay}
                avatarSourcePreference={liveAvatarSourcePreference}
                bodyOnlyGarments={liveBodyOnlyGarments}
                garmentOnlyViewport={liveGarmentOnlyViewport}
                showSkeletonOverlay={liveSkeletonOverlay}
                showFitDebugOverlay={liveFitDebugOverlay}
                onLiveViewportPoseFitDebug={setLivePoseFitDebug}
                garmentAttachmentDebug={liveGarmentAttachDebug}
                layout="workbench"
                navSettings={viewportNav}
                cameraResetNonce={camResetNonce}
                devSceneInspect={__DEV__ ? devSceneInspect : undefined}
                viewportBaselineNonce={viewportBaselineNonce}
                activeTab={liveWorkbenchTab}
                cleanMode={liveVisualPreset === "clean_mannequin"}
              />
            </View>
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={styles.liveSubTabBar}
            >
              {LIVE_WORKBENCH_TABS.map((tab) => {
                const on = liveWorkbenchTab === tab.id;
                return (
                  <Pressable
                    key={tab.id}
                    onPress={() => setLiveWorkbenchTab(tab.id)}
                    style={({ pressed }) => [
                      styles.liveSubTabChip,
                      on && styles.liveSubTabChipActive,
                      pressed && styles.modeChipPressed,
                    ]}
                  >
                    <Text
                      style={[
                        styles.liveSubTabChipTxt,
                        on && styles.liveSubTabChipTxtActive,
                      ]}
                    >
                      {tab.label}
                    </Text>
                  </Pressable>
                );
              })}
            </ScrollView>
            <ScrollView
              style={[styles.liveWorkbenchPanel, { maxHeight: windowHeight * 0.38 }]}
              contentContainerStyle={styles.liveWorkbenchPanelInner}
              keyboardShouldPersistTaps="handled"
            >
              {liveWorkbenchTab === "view" ? (
                <>
                  <Text style={styles.section}>View</Text>
                  <Text style={styles.debugNote}>
                    Shading + pose + visibility. Camera uses damped target-orbit (see Nav tab).
                  </Text>
                  <Text style={styles.fitSubnote}>Visual quality preset</Text>
                  <ScrollView
                    horizontal
                    showsHorizontalScrollIndicator={false}
                    contentContainerStyle={styles.modeChipsRow}
                  >
                    {LIVE_VISUAL_PRESETS.map((presetOption) => {
                      const selected = liveVisualPreset === presetOption.id;
                      return (
                        <Pressable
                          key={presetOption.id}
                          onPress={() => applyLiveVisualPreset(presetOption.id)}
                          style={({ pressed }) => [
                            styles.modeChip,
                            selected && styles.modeChipSelected,
                            pressed && styles.modeChipPressed,
                          ]}
                        >
                          <Text
                            style={[
                              styles.modeChipLabel,
                              selected && styles.modeChipLabelSelected,
                            ]}
                            numberOfLines={2}
                          >
                            {presetOption.label}
                          </Text>
                        </Pressable>
                      );
                    })}
                  </ScrollView>
                  <Text style={styles.fitSubnote}>Live viewport shading</Text>
                  <ScrollView
                    horizontal
                    showsHorizontalScrollIndicator={false}
                    contentContainerStyle={styles.modeChipsRow}
                  >
                    {listLiveViewportShadingModes().map((m) => {
                      const selected = liveViewportShading === m;
                      return (
                        <Pressable
                          key={m}
                          onPress={() => setLiveViewportShading(m)}
                          style={({ pressed }) => [
                            styles.modeChip,
                            selected && styles.modeChipSelected,
                            pressed && styles.modeChipPressed,
                          ]}
                        >
                          <Text
                            style={[
                              styles.modeChipLabel,
                              selected && styles.modeChipLabelSelected,
                            ]}
                            numberOfLines={2}
                          >
                            {LIVE_VIEWPORT_SHADING_LABELS[m]}
                          </Text>
                        </Pressable>
                      );
                    })}
                  </ScrollView>
                  <Text style={styles.fitSubnote}>Pose</Text>
                  <View style={styles.row}>
                    {(["relaxed", "walk", "tpose", "apose"] as const).map((p) => (
                      <AppButton
                        key={p}
                        label={
                          stressTestHighlightPose === p ? `${p} · stress` : p
                        }
                        variant={pose === p ? "primary" : "secondary"}
                        onPress={() => {
                          setPose(p);
                          setStressTestHighlightPose(null);
                        }}
                        disabled={busy || busyPoll || autoPollLoopOn}
                      />
                    ))}
                  </View>
                  {liveVisualPreset === "debug" ? (
                    <>
                      <View style={[styles.row, styles.clipOverlayRow]}>
                        <Text style={styles.fitSubnote}>Body only</Text>
                        <Switch
                          value={liveBodyOnlyGarments}
                          onValueChange={setLiveBodyOnlyGarmentsSafe}
                          accessibilityLabel="Body only"
                        />
                      </View>
                      <View style={[styles.row, styles.clipOverlayRow]}>
                        <Text style={styles.fitSubnote}>Garment only</Text>
                        <Switch
                          value={liveGarmentOnlyViewport}
                          onValueChange={setLiveGarmentOnlyViewportSafe}
                          accessibilityLabel="Garment only"
                        />
                      </View>
                      <View style={[styles.row, styles.clipOverlayRow]}>
                        <Text style={styles.fitSubnote}>Skeleton overlay</Text>
                        <Switch
                          value={liveSkeletonOverlay}
                          onValueChange={setLiveSkeletonOverlay}
                          accessibilityLabel="Skeleton overlay"
                        />
                      </View>
                      <View style={[styles.row, styles.clipOverlayRow]}>
                        <Text style={styles.fitSubnote}>Fit debug overlay</Text>
                        <Switch
                          value={liveFitDebugOverlay}
                          onValueChange={setLiveFitDebugOverlay}
                          accessibilityLabel="Fit debug overlay"
                        />
                      </View>
                    </>
                  ) : null}
                  <View style={[styles.row, styles.fitPresetWrap]}>
                    <AppButton
                      label="Reset camera"
                      variant="secondary"
                      onPress={() => setCamResetNonce((n) => n + 1)}
                    />
                    <AppButton
                      label="Restore startup preview"
                      variant="secondary"
                      onPress={() => resetVisibleBaseline("manual")}
                    />
                  </View>
                </>
              ) : null}
              {liveWorkbenchTab === "body" ? (
                <>
                  <Text style={styles.section}>Body</Text>
                  <Text style={styles.debugNote}>
                    Deterministic avatar source selection. Auto tries a realistic GLB URL, then the bundled stylised GLB, then the procedural fallback without requiring a toggle.
                  </Text>
                  <Text style={styles.fitSubnote}>Avatar source</Text>
                  <ScrollView
                    horizontal
                    showsHorizontalScrollIndicator={false}
                    contentContainerStyle={styles.modeChipsRow}
                  >
                    {LIVE_AVATAR_SOURCE_OPTIONS.map((sourceOption) => {
                      const selected = liveAvatarSourcePreference === sourceOption.id;
                      return (
                        <Pressable
                          key={sourceOption.id}
                          onPress={() => {
                            setLiveAvatarSourcePreference(sourceOption.id);
                            setViewportBaselineNonce((n) => n + 1);
                          }}
                          style={({ pressed }) => [
                            styles.modeChip,
                            selected && styles.modeChipSelected,
                            pressed && styles.modeChipPressed,
                          ]}
                        >
                          <Text
                            style={[
                              styles.modeChipLabel,
                              selected && styles.modeChipLabelSelected,
                            ]}
                            numberOfLines={2}
                          >
                            {sourceOption.label}
                          </Text>
                        </Pressable>
                      );
                    })}
                  </ScrollView>
                  <Text style={styles.debugNote}>
                    GLB failures keep the fallback visible. Use Debug quality to inspect source status, bounds, mesh/material counts, and fallback reason.
                  </Text>
                  <View style={styles.bodyShapeActions}>
                    <AppButton
                      label="Reload avatar"
                      variant="secondary"
                      onPress={() => setViewportBaselineNonce((n) => n + 1)}
                    />
                    <AppButton
                      label="Reset camera"
                      variant="secondary"
                      onPress={() => setCamResetNonce((n) => n + 1)}
                    />
                  </View>
                  <Text style={styles.fitSubnote}>Body shape presets</Text>
                  <ScrollView
                    horizontal
                    showsHorizontalScrollIndicator={false}
                    contentContainerStyle={styles.modeChipsRow}
                  >
                    {(Object.keys(BODY_SHAPE_PRESETS) as BodyShapePresetId[]).map((id) => {
                      const preset = BODY_SHAPE_PRESETS[id];
                      const matches = bodyShapesEqual(bodyShape, preset);
                      return (
                        <Pressable
                          key={id}
                          onPress={() => patchBodyShape(() => ({ ...preset }))}
                          style={({ pressed }) => [
                            styles.modeChip,
                            matches && styles.modeChipSelected,
                            pressed && styles.modeChipPressed,
                          ]}
                        >
                          <Text
                            style={[
                              styles.modeChipLabel,
                              matches && styles.modeChipLabelSelected,
                            ]}
                            numberOfLines={2}
                          >
                            {BODY_SHAPE_PRESET_LABELS[id]}
                          </Text>
                        </Pressable>
                      );
                    })}
                  </ScrollView>
                  <View style={styles.bodyShapeActions}>
                    <AppButton label="Reset body" variant="secondary" onPress={resetBodyShape} />
                  </View>
                  <View style={[styles.fitPanel, styles.bodyShapeSliders]}>
                    {BODY_SHAPE_SLIDERS.map((row) => (
                      <FitSliderRow
                        key={row.key}
                        label={row.label}
                        value={bodyShape[row.key]}
                        min={row.min}
                        max={row.max}
                        step={row.step}
                        onChange={(v) =>
                          patchBodyShape((b) => ({
                            ...b,
                            [row.key]: v,
                          }))
                        }
                      />
                    ))}
                  </View>
                </>
              ) : null}
              {liveWorkbenchTab === "garments" ? (
                <>
                  <Text style={styles.section}>Garments</Text>
                  <Text style={styles.fitSubnote}>Outfit preset</Text>
                  <View style={styles.row}>
                    {(["default", "navy", "casual"] as const).map((p) => (
                      <AppButton
                        key={p}
                        label={p}
                        variant={presetKey === p ? "primary" : "secondary"}
                        onPress={() => setPresetKey(p)}
                        disabled={busy || busyPoll || autoPollLoopOn}
                      />
                    ))}
                  </View>
                  <View style={[styles.row, styles.clipOverlayRow]}>
                    <Text style={styles.fitSubnote}>Garment attach debug</Text>
                    <Switch
                      value={liveGarmentAttachDebug}
                      onValueChange={setLiveGarmentAttachDebug}
                      accessibilityLabel="Garment attach debug"
                    />
                  </View>
                </>
              ) : null}
              {liveWorkbenchTab === "fit" ? (
                <>
                  <Text style={styles.section}>Fit</Text>
                  <View style={[styles.fitPanel, styles.liveWorkstationBox]}>
                    <Text style={styles.workstationLoop}>
                      Region → baseline / compare → snapshots (see Stress tab for multi-pose).
                    </Text>
                    {liveFitShowBaseline && liveFitBaseline != null ? (
                      <Text style={styles.liveCompareBanner}>
                        Showing saved baseline (before).
                      </Text>
                    ) : null}
                    <Text style={styles.fitSubnote}>Editing region</Text>
                    <ScrollView
                      horizontal
                      showsHorizontalScrollIndicator={false}
                      contentContainerStyle={styles.modeChipsRow}
                    >
                      {(["global", "torso", "sleeves", "waist", "hem"] as const).map((r) => {
                        const on = liveFitActiveRegion === r;
                        return (
                          <Pressable
                            key={r}
                            onPress={() => {
                              setLiveFitActiveRegion(r);
                              useAvatarSceneStore.getState().setLiveFitShowBaseline(false);
                            }}
                            disabled={busy || busyPoll || autoPollLoopOn}
                            style={({ pressed }) => [
                              styles.liveRegionPill,
                              on && styles.liveRegionPillActive,
                              pressed && styles.modeChipPressed,
                            ]}
                          >
                            <Text
                              style={[
                                styles.liveRegionPillText,
                                on && styles.liveRegionPillTextActive,
                              ]}
                            >
                              {FIT_REGION_LABELS[r]}
                            </Text>
                          </Pressable>
                        );
                      })}
                    </ScrollView>
                    <View style={[styles.row, styles.fitPresetWrap]}>
                      <AppButton
                        label="Set baseline"
                        variant="secondary"
                        onPress={() => {
                          captureLiveFitBaseline();
                          setStatus("Baseline saved.");
                        }}
                        disabled={busy || busyPoll || autoPollLoopOn}
                      />
                      <AppButton
                        label={liveFitShowBaseline ? "Show current" : "Show baseline"}
                        variant="secondary"
                        onPress={() => toggleLiveFitBaselineCompare()}
                        disabled={liveFitBaseline == null || busy || busyPoll || autoPollLoopOn}
                      />
                      <AppButton
                        label="Clear baseline"
                        variant="secondary"
                        onPress={() => clearLiveFitBaseline()}
                        disabled={liveFitBaseline == null || busy || busyPoll || autoPollLoopOn}
                      />
                    </View>
                    <View style={[styles.row, styles.fitPresetWrap]}>
                      <AppButton
                        label="Save snapshot"
                        variant="secondary"
                        onPress={() => {
                          pushLiveFitSnapshot();
                          setStatus("Snapshot saved.");
                        }}
                        disabled={busy || busyPoll || autoPollLoopOn}
                      />
                      <AppButton
                        label="Clear snapshots"
                        variant="secondary"
                        onPress={() => clearLiveFitSnapshots()}
                        disabled={liveFitSnapshots.length === 0}
                      />
                    </View>
                    <Text style={styles.fitSubnote}>Quick tags</Text>
                    <View style={[styles.row, styles.fitPresetWrap]}>
                      {LIVE_QUICK_TAGS.map((tag) => (
                        <AppButton
                          key={tag}
                          label={tag}
                          variant={liveFitQuickTags.includes(tag) ? "primary" : "secondary"}
                          onPress={() => addLiveFitQuickTag(tag)}
                          disabled={busy || busyPoll || autoPollLoopOn}
                        />
                      ))}
                    </View>
                    <View style={[styles.row, styles.fitPresetWrap]}>
                      <AppButton
                        label={`Reset ${FIT_REGION_LABELS[liveFitActiveRegion]}`}
                        variant="secondary"
                        onPress={() => resetLiveFitRegionToDefault(liveFitActiveRegion)}
                        disabled={busy || busyPoll || autoPollLoopOn}
                      />
                      <AppButton
                        label="Apply last suggestion"
                        variant="secondary"
                        onPress={applyLastSuggestionAgain}
                        disabled={
                          liveFitLastSuggestionId == null || busy || busyPoll || autoPollLoopOn
                        }
                      />
                    </View>
                  </View>
                  <Text style={styles.debugNote}>
                    Garment region sliders & suggestions: use the{" "}
                    <Text style={styles.boldMuted}>Garment fit</Text> section in this scroll (below) —
                    it stays shared with Offline exports.
                  </Text>
                </>
              ) : null}
              {liveWorkbenchTab === "debug" ? (
                <>
                  <Text style={styles.section}>Debug</Text>
                  {livePoseFitDebug ? (
                    <View style={styles.poseFitDebugBox}>
                      {livePoseFitDebug.avatar ? (
                        <Text style={styles.poseFitDebugLine} selectable>
                          avatar model: {livePoseFitDebug.avatar.activeAvatarModel} · garment follow{" "}
                          {livePoseFitDebug.avatar.garmentFollowMode} · garment mode{" "}
                          {livePoseFitDebug.avatar.garmentMode} · proportions{" "}
                          {livePoseFitDebug.avatar.proportionsVersion} · joints{" "}
                          {livePoseFitDebug.avatar.jointCount} · visible parts{" "}
                          {livePoseFitDebug.avatar.visiblePartsCount} · startup visible{" "}
                          {livePoseFitDebug.avatar.startupVisible ? "yes" : "no"}
                        </Text>
                      ) : null}
                      {livePoseFitDebug.avatar ? (
                        <Text style={styles.poseFitDebugLine} selectable>
                          visual source: {livePoseFitDebug.avatar.visualAvatarSource} · rig detected{" "}
                          {livePoseFitDebug.avatar.rigDetected ? "true" : "false"} · pose driver{" "}
                          {livePoseFitDebug.avatar.poseDriver} · load{" "}
                          {livePoseFitDebug.avatar.loadStatus}
                        </Text>
                      ) : null}
                      {livePoseFitDebug.avatar ? (
                        <Text style={styles.poseFitDebugLine} selectable>
                          avatarSource: {livePoseFitDebug.avatar.avatarSource ?? "n/a"} · fallback{" "}
                          {livePoseFitDebug.avatar.fallbackReason ?? "none"} · meshes{" "}
                          {livePoseFitDebug.avatar.meshCount ?? "n/a"} · materials{" "}
                          {livePoseFitDebug.avatar.materialCount ?? "n/a"} · bones{" "}
                          {livePoseFitDebug.avatar.boneCount ?? "n/a"} · boundsH{" "}
                          {typeof livePoseFitDebug.avatar.boundsHeight === "number"
                            ? livePoseFitDebug.avatar.boundsHeight.toFixed(2)
                            : "n/a"}
                        </Text>
                      ) : null}
                      <Text style={styles.poseFitDebugLine} selectable>
                        body pose:{" "}
                        {livePoseFitDebug.skinned?.bodyPoseApplied === true
                          ? "bones"
                          : livePoseFitDebug.skinned
                            ? "no"
                            : "n/a"}{" "}
                        · map {livePoseFitDebug.skinned?.boneMapStatus ?? "—"}
                      </Text>
                      <Text style={styles.poseFitDebugLine} selectable>
                        visible mode: {livePoseFitDebug.visibility?.mode ?? "—"} · body{" "}
                        {livePoseFitDebug.visibility?.bodyVisible ? "yes" : "no"} · garments{" "}
                        {livePoseFitDebug.visibility?.garmentsVisible ? "yes" : "no"}
                      </Text>
                      <Text style={styles.poseFitDebugLine} selectable>
                        visible branch: {livePoseFitDebug.visibility?.visibleBranch ?? "—"} · pose target{" "}
                        {livePoseFitDebug.visibility?.poseTargetBranch ?? "—"}
                      </Text>
                      <Text style={styles.poseFitDebugLine} selectable>
                        bundled mounted:{" "}
                        {livePoseFitDebug.visibility?.bundledBodyMounted ? "yes" : "no"} · bundled visible{" "}
                        {livePoseFitDebug.visibility?.bundledBodyVisible ? "yes" : "no"}
                      </Text>
                      <Text style={styles.poseFitDebugLine} selectable>
                        safe default active:{" "}
                        {livePoseFitDebug.visibility?.safeDefaultActive ? "yes" : "no"} · camera target valid:{" "}
                        {livePoseFitDebug.visibility?.cameraTargetValid ? "yes" : "no"}
                      </Text>
                      {livePoseFitDebug.startup ? (
                        <>
                          <Text style={styles.poseFitDebugLine} selectable>
                            startup ready:{" "}
                            {livePoseFitDebug.startup.sceneReady ? "yes" : "no"} · combined{" "}
                            {livePoseFitDebug.startup.combinedViewOk ? "ok" : "no"} · cam framed hint{" "}
                            {livePoseFitDebug.startup.cameraFramedHint ? "yes" : "no"}
                          </Text>
                          <Text style={styles.poseFitDebugLine} selectable>
                            startup visible body:{" "}
                            {livePoseFitDebug.startup.startupVisibleBody ? "yes" : "no"} · combined visible{" "}
                            {livePoseFitDebug.startup.combinedVisible ? "yes" : "no"}
                          </Text>
                          <Text style={styles.poseFitDebugLine} selectable>
                            visible meshes: {livePoseFitDebug.startup.visibleMeshCount} · body group{" "}
                            {livePoseFitDebug.startup.bodyGroupVisible ? "yes" : "no"} · garment group{" "}
                            {livePoseFitDebug.startup.garmentGroupVisible ? "yes" : "no"}
                          </Text>
                          <Text style={styles.poseFitDebugLine} selectable>
                            active tab: {livePoseFitDebug.startup.activeTab} · clean mode{" "}
                            {livePoseFitDebug.startup.cleanMode ? "yes" : "no"} · reason{" "}
                            {livePoseFitDebug.startup.startupReason} · exact baseline{" "}
                            {livePoseFitDebug.startup.exactBaselineOk ? "yes" : "no"}
                          </Text>
                          <Text style={styles.poseFitDebugLine} selectable>
                            renderSafe: {livePoseFitDebug.startup.renderSafe ? "true" : "false"} | lastSceneError{" "}
                            {livePoseFitDebug.startup.lastSceneError ?? "none"}
                          </Text>
                          {livePoseFitDebug.startup.warning ? (
                            <Text style={styles.poseFitDebugLine} selectable>
                              warning: {livePoseFitDebug.startup.warning}
                            </Text>
                          ) : null}
                        </>
                      ) : null}
                      {livePoseFitDebug.renderAudit ? (
                        <>
                          <Text style={styles.poseFitDebugLine} selectable>
                            render branch: {livePoseFitDebug.renderAudit.activeRenderBranchName} · root mounted{" "}
                            {livePoseFitDebug.renderAudit.mountedAvatarRoot ? "yes" : "no"} · meshes{" "}
                            {livePoseFitDebug.renderAudit.visibleMeshCount}/
                            {livePoseFitDebug.renderAudit.totalMeshCount} · gltf{" "}
                            {livePoseFitDebug.renderAudit.gltfVisibleMeshCount}/
                            {livePoseFitDebug.renderAudit.gltfTotalMeshCount}
                          </Text>
                          {livePoseFitDebug.renderAudit.firstMeshWorldPosition ? (
                            <Text style={styles.poseFitDebugLine} selectable>
                              first mesh pos [{fmtVec3(livePoseFitDebug.renderAudit.firstMeshWorldPosition)}] · scale [
                              {fmtVec3(livePoseFitDebug.renderAudit.firstMeshScale ?? [0, 0, 0])}] · mat opacity{" "}
                              {livePoseFitDebug.renderAudit.firstMeshMaterialOpacity?.toFixed(2) ?? "n/a"} · transparent{" "}
                              {livePoseFitDebug.renderAudit.firstMeshMaterialTransparent == null
                                ? "n/a"
                                : livePoseFitDebug.renderAudit.firstMeshMaterialTransparent
                                  ? "yes"
                                  : "no"}
                            </Text>
                          ) : null}
                          {livePoseFitDebug.renderAudit.cameraPosition &&
                          livePoseFitDebug.renderAudit.cameraTarget ? (
                            <Text style={styles.poseFitDebugLine} selectable>
                              render cam pos [{fmtVec3(livePoseFitDebug.renderAudit.cameraPosition)}] · target [
                              {fmtVec3(livePoseFitDebug.renderAudit.cameraTarget)}] · radius{" "}
                              {livePoseFitDebug.renderAudit.cameraRadius?.toFixed(2) ?? "n/a"}
                            </Text>
                          ) : null}
                          {livePoseFitDebug.renderAudit.safetyFallbackReason ? (
                            <Text style={styles.poseFitDebugLine} selectable>
                              render fallback: {livePoseFitDebug.renderAudit.safetyFallbackReason}
                            </Text>
                          ) : null}
                        </>
                      ) : null}
                      {livePoseFitDebug.bodySource ? (
                        <Text style={styles.poseFitDebugLine} selectable>
                          body source: {livePoseFitDebug.bodySource.active} · intent{" "}
                          {livePoseFitDebug.bodySource.userIntent} · source reason{" "}
                          {livePoseFitDebug.bodySource.sourceReason} · detail{" "}
                          {livePoseFitDebug.bodySource.reason} · load {livePoseFitDebug.bodySource.loadStatus}
                          {livePoseFitDebug.bodySource.errorReason
                            ? ` · error ${livePoseFitDebug.bodySource.errorReason}`
                            : ""}
                        </Text>
                      ) : null}
                      {livePoseFitDebug.interaction ? (
                        <Text style={styles.poseFitDebugLine} selectable>
                          zoom input: {livePoseFitDebug.interaction.zoomInputMode}
                        </Text>
                      ) : null}
                      {livePoseFitDebug.scene ? (
                        <>
                          <Text style={styles.poseFitDebugLine} selectable>
                            scene body loaded: {livePoseFitDebug.scene.bodyLoaded ? "yes" : "no"} · framed
                            (heuristic): {livePoseFitDebug.scene.framedHeuristic ? "yes" : "no"}
                          </Text>
                          <Text style={styles.poseFitDebugLine} selectable>
                            body root [{fmtVec3(livePoseFitDebug.scene.bodyRootWorld)}] · bounds c [
                            {fmtVec3(livePoseFitDebug.scene.boundsCenter)}] · size [
                            {fmtVec3(livePoseFitDebug.scene.boundsSize)}]
                          </Text>
                          <Text style={styles.poseFitDebugLine} selectable>
                            cam pos [{fmtVec3(livePoseFitDebug.scene.cameraPosition)}] · target [
                            {fmtVec3(livePoseFitDebug.scene.cameraTarget)}] · dist target→body{" "}
                            {livePoseFitDebug.scene.distTargetToBodyCenter.toFixed(3)}
                          </Text>
                          {livePoseFitDebug.scene.skeletonRootWorld ? (
                            <Text style={styles.poseFitDebugLine} selectable>
                              skeleton root [{fmtVec3(livePoseFitDebug.scene.skeletonRootWorld)}]
                            </Text>
                          ) : null}
                        </>
                      ) : null}
                      {livePoseFitDebug.attachment ? (
                        <AttachmentDebugReadout snap={livePoseFitDebug.attachment} />
                      ) : (
                        <Text style={styles.poseFitDebugLine}>attachment: (none)</Text>
                      )}
                    </View>
                  ) : (
                    <Text style={styles.debugNote}>Waiting for first frame…</Text>
                  )}
                  <Text style={styles.fitSubnote}>Scene space inspect (viewport)</Text>
                  <View style={[styles.row, styles.clipOverlayRow]}>
                    <Text style={styles.poseFitDebugLine}>Enable</Text>
                    <Switch
                      value={liveSceneInspectEnabled}
                      onValueChange={setLiveSceneInspectEnabled}
                      accessibilityLabel="Scene space inspect"
                    />
                  </View>
                  <View style={[styles.row, styles.clipOverlayRow]}>
                    <Text style={styles.poseFitDebugLine}>In-canvas markers + grid</Text>
                    <Switch
                      value={liveSceneMarkers}
                      onValueChange={setLiveSceneMarkers}
                      disabled={!liveSceneInspectEnabled}
                      accessibilityLabel="Scene markers"
                    />
                  </View>
                  <View style={[styles.row, styles.clipOverlayRow]}>
                    <Text style={styles.poseFitDebugLine}>Debug bright body material</Text>
                    <Switch
                      value={liveSceneBrightBody}
                      onValueChange={setLiveSceneBrightBody}
                      disabled={!liveSceneInspectEnabled}
                      accessibilityLabel="Bright body material"
                    />
                  </View>
                  <AppButton
                    label="Frame avatar bounds"
                    variant="secondary"
                    onPress={() => setManualFrameBoundsNonce((n) => n + 1)}
                    disabled={!liveSceneInspectEnabled}
                  />
                  <View style={[styles.row, styles.clipOverlayRow]}>
                    <Text style={styles.fitSubnote}>Runtime clip overlay</Text>
                    <Switch
                      value={liveClipOverlay}
                      onValueChange={setLiveClipOverlay}
                      accessibilityLabel="Clip overlay"
                    />
                  </View>
                  <Text style={styles.clipSummary} selectable>
                    clip proxy — torso {runtimeClipReport.torso.severity} · sleeves{" "}
                    {runtimeClipReport.sleeves.severity} · waist {runtimeClipReport.waist.severity} · hem{" "}
                    {runtimeClipReport.hem.severity}
                  </Text>
                </>
              ) : null}
              {liveWorkbenchTab === "stress" ? (
                <>
                  <Text style={styles.section}>Stress / snapshots</Text>
                  {liveFitSnapshots.length > 0 ? (
                    <ScrollView
                      horizontal
                      showsHorizontalScrollIndicator={false}
                      contentContainerStyle={styles.snapshotStrip}
                    >
                      {liveFitSnapshots.map((sn) => (
                        <View key={sn.id} style={styles.snapshotCard}>
                          <Pressable
                            onPress={() => {
                              restoreLiveFitSnapshot(sn.id);
                              setStatus(`Restored ${sn.label ?? sn.id.slice(0, 10)}`);
                            }}
                            disabled={busy || busyPoll || autoPollLoopOn}
                            style={({ pressed }) => [
                              styles.snapshotTap,
                              pressed && styles.modeChipPressed,
                            ]}
                          >
                            <Text style={styles.snapshotMeta} numberOfLines={3}>
                              {sn.label ? `${sn.label}\n` : ""}
                              {sn.pose} · {sn.presetKey}
                            </Text>
                          </Pressable>
                          <AppButton
                            label="Del"
                            variant="ghost"
                            onPress={() => removeLiveFitSnapshot(sn.id)}
                            disabled={busy || busyPoll || autoPollLoopOn}
                          />
                        </View>
                      ))}
                    </ScrollView>
                  ) : null}
                  <Text style={styles.stressHint}>
                    Multi-pose stress + stabilize (same as previous workstation block).
                  </Text>
                  <View style={[styles.row, styles.fitPresetWrap]}>
                    <AppButton
                      label="Stress test fit"
                      variant="secondary"
                      onPress={runStressTestFit}
                      disabled={
                        busy || busyPoll || autoPollLoopOn || stressTestBusy || stabilizeBusy
                      }
                    />
                    <AppButton
                      label="Stabilize fit"
                      variant="secondary"
                      onPress={runStabilizeFit}
                      disabled={
                        busy || busyPoll || autoPollLoopOn || stressTestBusy || stabilizeBusy
                      }
                    />
                    <AppButton
                      label="Jump worst pose"
                      variant="secondary"
                      onPress={() => {
                        const w = lastPoseStressReport?.worstPose;
                        if (w) {
                          setPose(w);
                          setStressTestHighlightPose(w);
                          setStatus(`Pose → ${w}`);
                        }
                      }}
                      disabled={
                        lastPoseStressReport?.worstPose == null ||
                        busy ||
                        busyPoll ||
                        autoPollLoopOn
                      }
                    />
                    <AppButton
                      label="Save + stress meta"
                      variant="secondary"
                      onPress={() => {
                        if (!lastPoseStressReport) {
                          setStatus("Run stress test first.");
                          return;
                        }
                        pushLiveFitSnapshot(
                          "stress",
                          stressReportToSnapshotMeta(lastPoseStressReport),
                        );
                        setStatus("Snapshot with stress meta.");
                      }}
                      disabled={
                        lastPoseStressReport == null || busy || busyPoll || autoPollLoopOn
                      }
                    />
                  </View>
                  {lastPoseStressReport ? (
                    <View style={styles.stressResultBox}>
                      <Text style={styles.stressScoreLine}>
                        Stability {lastPoseStressReport.overallStabilityScore}
                        {lastPoseStressReport.allPosesPass ? " · all pass" : ""}
                      </Text>
                      {lastPoseStressReport.poses.map((pr) => (
                        <Text key={pr.pose} style={styles.stressPoseLine} selectable>
                          {pr.pose}: {pr.pass ? "pass" : "fail"} · {pr.stabilityScore}
                        </Text>
                      ))}
                    </View>
                  ) : null}
                </>
              ) : null}
              {liveWorkbenchTab === "nav" ? (
                <>
                  <Text style={styles.section}>Navigation</Text>
                  <Text style={styles.debugNote}>
                    Damped orbit around target. Defaults tuned for avatar inspection.
                  </Text>
                  <View style={[styles.row, styles.clipOverlayRow]}>
                    <Text style={styles.fitSubnote}>Invert orbit X</Text>
                    <Switch
                      value={viewportNav.invertOrbitX}
                      onValueChange={(v) =>
                        patchViewportNav((n) => ({ ...n, invertOrbitX: v }))
                      }
                    />
                  </View>
                  <View style={[styles.row, styles.clipOverlayRow]}>
                    <Text style={styles.fitSubnote}>Invert orbit Y</Text>
                    <Switch
                      value={viewportNav.invertOrbitY}
                      onValueChange={(v) =>
                        patchViewportNav((n) => ({ ...n, invertOrbitY: v }))
                      }
                    />
                  </View>
                  <View style={[styles.row, styles.clipOverlayRow]}>
                    <Text style={styles.fitSubnote}>Two-finger pan target</Text>
                    <Switch
                      value={viewportNav.enablePan}
                      onValueChange={(v) =>
                        patchViewportNav((n) => ({ ...n, enablePan: v }))
                      }
                    />
                  </View>
                  <FitSliderRow
                    label="Orbit sensitivity"
                    value={viewportNav.orbitSensitivity}
                    min={0.5}
                    max={2}
                    step={0.05}
                    onChange={(v) => patchViewportNav((n) => ({ ...n, orbitSensitivity: v }))}
                  />
                  <FitSliderRow
                    label="Zoom sensitivity"
                    value={viewportNav.zoomSensitivity}
                    min={0.55}
                    max={1.65}
                    step={0.05}
                    onChange={(v) => patchViewportNav((n) => ({ ...n, zoomSensitivity: v }))}
                  />
                  <FitSliderRow
                    label="Damping"
                    value={viewportNav.damping}
                    min={0.08}
                    max={0.42}
                    step={0.02}
                    onChange={(v) => patchViewportNav((n) => ({ ...n, damping: v }))}
                  />
                  <FitSliderRow
                    label="Min zoom (radius)"
                    value={viewportNav.minRadius}
                    min={0.9}
                    max={4}
                    step={0.05}
                    onChange={(v) =>
                      patchViewportNav((n) => ({
                        ...n,
                        minRadius: Math.min(v, n.maxRadius - 0.05),
                      }))
                    }
                  />
                  <FitSliderRow
                    label="Max zoom (radius)"
                    value={viewportNav.maxRadius}
                    min={2}
                    max={14}
                    step={0.1}
                    onChange={(v) =>
                      patchViewportNav((n) => ({
                        ...n,
                        maxRadius: Math.max(v, n.minRadius + 0.05),
                      }))
                    }
                  />
                  <FitSliderRow
                    label="Target Y offset"
                    value={viewportNav.targetYOffset}
                    min={-0.25}
                    max={0.35}
                    step={0.02}
                    onChange={(v) => patchViewportNav((n) => ({ ...n, targetYOffset: v }))}
                  />
                  <FitSliderRow
                    label="Polar min"
                    value={viewportNav.polarMin}
                    min={0.05}
                    max={1.2}
                    step={0.02}
                    onChange={(v) =>
                      patchViewportNav((n) => ({
                        ...n,
                        polarMin: Math.min(v, n.polarMax - 0.02),
                      }))
                    }
                  />
                  <FitSliderRow
                    label="Polar max"
                    value={viewportNav.polarMax}
                    min={0.35}
                    max={1.58}
                    step={0.02}
                    onChange={(v) =>
                      patchViewportNav((n) => ({
                        ...n,
                        polarMax: Math.max(v, n.polarMin + 0.02),
                      }))
                    }
                  />
                  <FitSliderRow
                    label="Yaw speed ×"
                    value={viewportNav.yawSpeedMultiplier}
                    min={0.6}
                    max={1.8}
                    step={0.05}
                    onChange={(v) =>
                      patchViewportNav((n) => ({ ...n, yawSpeedMultiplier: v }))
                    }
                  />
                  <FitSliderRow
                    label="Pitch rad/px"
                    value={viewportNav.orbitPitchRadPerPx}
                    min={0.003}
                    max={0.012}
                    step={0.0002}
                    onChange={(v) =>
                      patchViewportNav((n) => ({ ...n, orbitPitchRadPerPx: v }))
                    }
                  />
                  <FitSliderRow
                    label="Yaw rad/px"
                    value={viewportNav.orbitYawRadPerPx}
                    min={0.003}
                    max={0.012}
                    step={0.0002}
                    onChange={(v) =>
                      patchViewportNav((n) => ({ ...n, orbitYawRadPerPx: v }))
                    }
                  />
                  <AppButton
                    label="Reset nav defaults"
                    variant="secondary"
                    onPress={() => resetViewportNav()}
                  />
                </>
              ) : null}
            </ScrollView>
          </View>
        ) : null}

        <ScrollView
          style={styles.flexScroll}
          contentContainerStyle={styles.scroll}
          keyboardShouldPersistTaps="handled"
        >
        {devMainTab === "offline" ? (
          <>
            <View style={styles.phaseBox}>
              <Text style={styles.phaseTitle}>Offline pipeline state</Text>
              <Text style={[styles.phasePill, styles.mono]}>{devPhase}</Text>
              <Text style={styles.phaseText}>{PHASE_COPY[devPhase]}</Text>
            </View>

            <Text style={styles.section}>Offline — engine debug view mode</Text>
            <Text style={styles.debugNote}>
              Modes map to optional <Text style={styles.mono}>closy.debug</Text> in export JSON.
              Engine-wired today: <Text style={styles.mono}>normal</Text>,{" "}
              <Text style={styles.mono}>overlay</Text>, <Text style={styles.mono}>silhouette</Text>,{" "}
              <Text style={styles.mono}>clipping</Text> (hotspot composite). Live preview now supports
              body-only, garment-only, skeleton, and fit overlays directly in-canvas.
            </Text>
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={styles.modeChipsRow}
            >
              {listFitDebugModes().map((m) => {
                const wired = isFitDebugModeEngineWired(m);
                const selected = offlineFitDebugMode === m;
                return (
                  <Pressable
                    key={m}
                    onPress={() => setOfflineFitDebugMode(m)}
                    disabled={busy || busyPoll || autoPollLoopOn}
                    style={({ pressed }) => [
                      styles.modeChip,
                      selected && styles.modeChipSelected,
                      pressed && styles.modeChipPressed,
                    ]}
                  >
                    <Text
                      style={[
                        styles.modeChipLabel,
                        selected && styles.modeChipLabelSelected,
                      ]}
                      numberOfLines={2}
                    >
                      {FIT_DEBUG_MODE_LABELS[m]}
                      {!wired && m !== "normal" ? "\n(not wired)" : ""}
                    </Text>
                  </Pressable>
                );
              })}
            </ScrollView>
            <Text style={styles.diagnosticsLine}>
              Engine support:{" "}
              {debugWired
                ? "current mode"
                : "off for this mode — PNG may match normal until exporter reads flags"}
            </Text>
            {offlineFitDebugMode === "clipping_hotspot" ? (
              <Text style={styles.clippingHelp}>
                Clipping hotspot (approx.): <Text style={styles.boldMuted}>red</Text> = strong silhouette
                overlap (likely penetration or tangled projection in this view).{" "}
                <Text style={styles.boldMuted}>yellow</Text> = near-contact band at silhouette edge.
                Muted blues/greens = body-only vs garment-only. Not physically exact — compare poses and
                cameras to see pose-specific vs systematic issues.
              </Text>
            ) : null}

            <Text style={styles.section}>Offline — render metadata</Text>
            <View style={styles.diagnostics}>
              <Text style={styles.diagnosticsLine}>
                UI debug mode: {offlineFitDebugMode}{" "}
                {FIT_DEBUG_MODE_LABELS[offlineFitDebugMode]}
                {debugWired ? "" : " (staged — engine may ignore)"}
              </Text>
              <Text style={styles.diagnosticsLine}>
                JSON{" "}
                <Text style={styles.mono}>debugMode</Text>:{" "}
                {offlineFitDebugMode === "normal"
                  ? "—"
                  : offlineFitDebugMode === "overlay"
                    ? "overlay"
                    : offlineFitDebugMode === "silhouette"
                      ? "silhouette"
                      : offlineFitDebugMode === "clipping_hotspot"
                        ? "clipping"
                        : "(other flags only)"}
              </Text>
              <Text style={styles.diagnosticsLine}>
                exporter pipeline:{" "}
                {offlineFitDebugMode === "clipping_hotspot"
                  ? "clipping hotspot (multi-pass composite)"
                  : offlineFitDebugMode === "normal"
                    ? "standard"
                    : debugWired
                      ? `single contrast pass (${offlineFitDebugMode})`
                      : "normal (flags not wired)"}
              </Text>
              {offlineFitDebugMode === "overlay" ? (
                <Text style={styles.diagnosticsLine}>
                  overlay look: blue body + orange garment
                </Text>
              ) : null}
              {offlineFitDebugMode === "silhouette" ? (
                <Text style={styles.diagnosticsLine}>
                  silhouette look: dark body + yellow garment
                </Text>
              ) : null}
              {offlineFitDebugMode === "clipping_hotspot" ? (
                <>
                  <Text style={styles.diagnosticsLine}>
                    clipping visualization: {CLIPPING_HOTSPOT_DEFAULTS.clippingVisualization}{" "}
                    (change via JSON / future UI; <Text style={styles.mono}>binary</Text> = white overlap
                    only)
                  </Text>
                  <Text style={styles.diagnosticsLine}>
                    clipping threshold: {CLIPPING_HOTSPOT_DEFAULTS.clippingThreshold}
                  </Text>
                  <Text style={styles.diagnosticsLine}>
                    base underlay:{" "}
                    {CLIPPING_HOTSPOT_DEFAULTS.showBaseRenderUnderlay ? "on (overlay)" : "off"}
                  </Text>
                </>
              ) : null}
              <Text style={styles.diagnosticsLine}>
                pose: {pose} · preset: {presetKey}
              </Text>
              <Text style={styles.diagnosticsLine}>
                fit global — offset [{garmentFit.global.offset.map((n) => n.toFixed(3)).join(", ")}]
                scale [{garmentFit.global.scale.map((n) => n.toFixed(3)).join(", ")}] · inflate{" "}
                {garmentFit.global.inflate.toFixed(3)}
              </Text>
              <Text style={styles.diagnosticsLine}>
                regions — torso Z {garmentFit.regions.torso.offsetZ.toFixed(3)} · sleeves inflate{" "}
                {garmentFit.regions.sleeves.inflate.toFixed(3)} · waist tighten{" "}
                {garmentFit.regions.waist.tighten.toFixed(3)} · hem Y{" "}
                {garmentFit.regions.hem.offsetY.toFixed(3)}
              </Text>
              <Text style={styles.diagnosticsLine}>
                renderId: {lastSaved?.renderId ?? "—"}
              </Text>
              <Text style={styles.diagnosticsLine}>
                request path: {expectedRequestRel ?? "—"}
              </Text>
              <Text style={styles.diagnosticsLine}>
                expected render: {expectedRenderRel ?? "—"}
              </Text>
              <Text style={styles.diagnosticsLine}>
                HTTP render URL: {resolvedRenderUrl ?? "—"}
              </Text>
              <Text style={styles.diagnosticsLine}>
                last poll / probe: {lastFetchSummary ?? "—"}
              </Text>
              <Text style={styles.diagnosticsLine}>
                last success: {lastSuccessAt ?? "—"}
              </Text>
              <Text style={styles.diagnosticsLine}>
                image may be stale: {mayBeStale || devPhase === "stale_render" ? "yes — rebuild or refresh" : imageUri ? "low if controls unchanged" : "—"}
              </Text>
            </View>
          </>
        ) : null}

        {devMainTab !== "live" ? (
        <>
        <Text style={styles.section}>Pose</Text>
        <View style={styles.row}>
          {(["relaxed", "walk", "tpose", "apose"] as const).map((p) => (
            <AppButton
              key={p}
              label={
                stressTestHighlightPose === p
                  ? `${p} · stress`
                  : p
              }
              variant={pose === p ? "primary" : "secondary"}
              onPress={() => {
                setPose(p);
                setStressTestHighlightPose(null);
              }}
              disabled={busy || busyPoll || autoPollLoopOn}
            />
          ))}
        </View>
        </>
        ) : null}

        {devMainTab !== "live" ? (
        <>
        <Text style={styles.section}>Outfit preset</Text>
        <View style={styles.row}>
          {(["default", "navy", "casual"] as const).map((p) => (
            <AppButton
              key={p}
              label={p}
              variant={presetKey === p ? "primary" : "secondary"}
              onPress={() => setPresetKey(p)}
              disabled={busy || busyPoll || autoPollLoopOn}
            />
          ))}
        </View>
        </>
        ) : null}

        {devMainTab !== "live" ? (
          <>
            <Text style={styles.section}>Fit debug workflow</Text>
            <View style={styles.workflowBox}>
              {[
                "Tune in live 3D — or offline: build clipping / overlay export",
                "Check silhouette mismatch (body vs garment)",
                "Inspect offline clipping heatmap (red overlap) when needed",
                "Use fit suggestions + checklist, then region sliders",
                "Re-render offline and compare in session history",
              ].map((step, i) => (
                <Text key={step} style={styles.workflowStep}>
                  {i + 1}. {step}
                </Text>
              ))}
            </View>
          </>
        ) : null}

        {(devMainTab !== "live" || liveWorkbenchTab === "fit") ? (
        <>
        <Text style={styles.section}>Garment fit (dev)</Text>
        <Text style={styles.debugNote}>
          Optional <Text style={styles.mono}>closy.fit</Text> with{" "}
          <Text style={styles.mono}>global</Text> then <Text style={styles.mono}>regions</Text> (
          torso / sleeves / waist / hem). Live tab: region pills live in the workstation above.
          Live heuristics + (when available) clipping stats merge in suggestions below. Engine PNG
          uses the same shared store values.
        </Text>
        <View style={styles.fitPanel}>
          <View style={[styles.row, styles.fitPresetWrap]}>
            <AppButton
              label="Reset fit"
              variant="secondary"
              onPress={() => setGarmentFit(FIT_ADJUST_PRESETS.reset())}
              disabled={busy || busyPoll || autoPollLoopOn}
            />
            <AppButton
              label="Tight"
              variant="secondary"
              onPress={() => setGarmentFit(FIT_ADJUST_PRESETS.tight_fit())}
              disabled={busy || busyPoll || autoPollLoopOn}
            />
            <AppButton
              label="Loose"
              variant="secondary"
              onPress={() => setGarmentFit(FIT_ADJUST_PRESETS.loose_fit())}
              disabled={busy || busyPoll || autoPollLoopOn}
            />
            <AppButton
              label="Inflate test"
              variant="secondary"
              onPress={() => setGarmentFit(FIT_ADJUST_PRESETS.inflate_test())}
              disabled={busy || busyPoll || autoPollLoopOn}
            />
            <AppButton
              label="Back −Z"
              variant="secondary"
              onPress={() =>
                patchGarmentFit((prev) => FIT_ADJUST_PRESETS.offset_back(prev))
              }
              disabled={busy || busyPoll || autoPollLoopOn}
            />
            <AppButton
              label="Forward +Z"
              variant="secondary"
              onPress={() =>
                patchGarmentFit((prev) => FIT_ADJUST_PRESETS.offset_forward(prev))
              }
              disabled={busy || busyPoll || autoPollLoopOn}
            />
          </View>
          {devMainTab !== "live" ? (
            <>
              <Text style={styles.fitSubnote}>Adjust region</Text>
              <View style={[styles.row, styles.fitPresetWrap]}>
                {(
                  ["global", "torso", "sleeves", "waist", "hem"] as const
                ).map((r) => (
                  <AppButton
                    key={r}
                    label={FIT_REGION_LABELS[r]}
                    variant={liveFitActiveRegion === r ? "primary" : "secondary"}
                    onPress={() => {
                      setLiveFitActiveRegion(r);
                      useAvatarSceneStore.getState().setLiveFitShowBaseline(false);
                    }}
                    disabled={busy || busyPoll || autoPollLoopOn}
                  />
                ))}
              </View>
            </>
          ) : (
            <Text style={styles.fitSubnote}>
              Sliders for:{" "}
              <Text style={styles.boldMuted}>{FIT_REGION_LABELS[liveFitActiveRegion]}</Text> — switch
              region in the Live fitting workstation.
            </Text>
          )}
          {liveFitActiveRegion === "global" ? (
            <>
              <FitSliderRow
                label="Offset X"
                value={garmentFit.global.offset[0]}
                min={-0.15}
                max={0.15}
                step={0.01}
                disabled={busy || busyPoll || autoPollLoopOn}
                onChange={(v) =>
                  patchGarmentFit((s) => {
                    const c = cloneFitState(s);
                    c.global.offset[0] = v;
                    return c;
                  })
                }
              />
              <FitSliderRow
                label="Offset Y"
                value={garmentFit.global.offset[1]}
                min={-0.15}
                max={0.15}
                step={0.01}
                disabled={busy || busyPoll || autoPollLoopOn}
                onChange={(v) =>
                  patchGarmentFit((s) => {
                    const c = cloneFitState(s);
                    c.global.offset[1] = v;
                    return c;
                  })
                }
              />
              <FitSliderRow
                label="Offset Z (back / forward)"
                value={garmentFit.global.offset[2]}
                min={-0.15}
                max={0.15}
                step={0.01}
                disabled={busy || busyPoll || autoPollLoopOn}
                onChange={(v) =>
                  patchGarmentFit((s) => {
                    const c = cloneFitState(s);
                    c.global.offset[2] = v;
                    return c;
                  })
                }
              />
              <FitSliderRow
                label="Scale X"
                value={garmentFit.global.scale[0]}
                min={0.85}
                max={1.2}
                step={0.01}
                disabled={busy || busyPoll || autoPollLoopOn}
                onChange={(v) =>
                  patchGarmentFit((s) => {
                    const c = cloneFitState(s);
                    c.global.scale[0] = v;
                    return c;
                  })
                }
              />
              <FitSliderRow
                label="Scale Y"
                value={garmentFit.global.scale[1]}
                min={0.85}
                max={1.2}
                step={0.01}
                disabled={busy || busyPoll || autoPollLoopOn}
                onChange={(v) =>
                  patchGarmentFit((s) => {
                    const c = cloneFitState(s);
                    c.global.scale[1] = v;
                    return c;
                  })
                }
              />
              <FitSliderRow
                label="Scale Z"
                value={garmentFit.global.scale[2]}
                min={0.85}
                max={1.2}
                step={0.01}
                disabled={busy || busyPoll || autoPollLoopOn}
                onChange={(v) =>
                  patchGarmentFit((s) => {
                    const c = cloneFitState(s);
                    c.global.scale[2] = v;
                    return c;
                  })
                }
              />
              <FitSliderRow
                label="Inflate (uniform scale bump)"
                value={garmentFit.global.inflate}
                min={-0.08}
                max={0.15}
                step={0.005}
                disabled={busy || busyPoll || autoPollLoopOn}
                onChange={(v) =>
                  patchGarmentFit((s) => {
                    const c = cloneFitState(s);
                    c.global.inflate = v;
                    return c;
                  })
                }
              />
              <FitSliderRow
                label="Body bias Z (legacy flat)"
                value={garmentFit.legacy.bodyOffsetBias}
                min={-0.08}
                max={0.08}
                step={0.01}
                disabled={busy || busyPoll || autoPollLoopOn}
                onChange={(v) =>
                  patchGarmentFit((s) => {
                    const c = cloneFitState(s);
                    c.legacy.bodyOffsetBias = v;
                    return c;
                  })
                }
              />
              <FitSliderRow
                label="Shrinkwrap strength"
                value={garmentFit.legacy.shrinkwrapStrength}
                min={0}
                max={1}
                step={0.05}
                disabled={busy || busyPoll || autoPollLoopOn}
                onChange={(v) =>
                  patchGarmentFit((s) => {
                    const c = cloneFitState(s);
                    c.legacy.shrinkwrapStrength = v;
                    return c;
                  })
                }
              />
            </>
          ) : null}
          {liveFitActiveRegion === "torso" ? (
            <>
              <FitSliderRow
                label="Torso offset Z"
                value={garmentFit.regions.torso.offsetZ}
                min={-0.08}
                max={0.08}
                step={0.01}
                disabled={busy || busyPoll || autoPollLoopOn}
                onChange={(v) =>
                  patchGarmentFit((s) => {
                    const c = cloneFitState(s);
                    c.regions.torso.offsetZ = v;
                    return c;
                  })
                }
              />
              <FitSliderRow
                label="Torso inflate"
                value={garmentFit.regions.torso.inflate}
                min={-0.06}
                max={0.12}
                step={0.005}
                disabled={busy || busyPoll || autoPollLoopOn}
                onChange={(v) =>
                  patchGarmentFit((s) => {
                    const c = cloneFitState(s);
                    c.regions.torso.inflate = v;
                    return c;
                  })
                }
              />
              <FitSliderRow
                label="Torso scale Y"
                value={garmentFit.regions.torso.scaleY}
                min={0.92}
                max={1.08}
                step={0.01}
                disabled={busy || busyPoll || autoPollLoopOn}
                onChange={(v) =>
                  patchGarmentFit((s) => {
                    const c = cloneFitState(s);
                    c.regions.torso.scaleY = v;
                    return c;
                  })
                }
              />
            </>
          ) : null}
          {liveFitActiveRegion === "sleeves" ? (
            <>
              <FitSliderRow
                label="Sleeves offset X"
                value={garmentFit.regions.sleeves.offset[0]}
                min={-0.08}
                max={0.08}
                step={0.01}
                disabled={busy || busyPoll || autoPollLoopOn}
                onChange={(v) =>
                  patchGarmentFit((s) => {
                    const c = cloneFitState(s);
                    c.regions.sleeves.offset[0] = v;
                    return c;
                  })
                }
              />
              <FitSliderRow
                label="Sleeves offset Y"
                value={garmentFit.regions.sleeves.offset[1]}
                min={-0.08}
                max={0.08}
                step={0.01}
                disabled={busy || busyPoll || autoPollLoopOn}
                onChange={(v) =>
                  patchGarmentFit((s) => {
                    const c = cloneFitState(s);
                    c.regions.sleeves.offset[1] = v;
                    return c;
                  })
                }
              />
              <FitSliderRow
                label="Sleeves offset Z"
                value={garmentFit.regions.sleeves.offset[2]}
                min={-0.08}
                max={0.08}
                step={0.01}
                disabled={busy || busyPoll || autoPollLoopOn}
                onChange={(v) =>
                  patchGarmentFit((s) => {
                    const c = cloneFitState(s);
                    c.regions.sleeves.offset[2] = v;
                    return c;
                  })
                }
              />
              <FitSliderRow
                label="Sleeves inflate"
                value={garmentFit.regions.sleeves.inflate}
                min={-0.06}
                max={0.12}
                step={0.005}
                disabled={busy || busyPoll || autoPollLoopOn}
                onChange={(v) =>
                  patchGarmentFit((s) => {
                    const c = cloneFitState(s);
                    c.regions.sleeves.inflate = v;
                    return c;
                  })
                }
              />
              <FitSliderRow
                label="Legacy sleeve Y (flat export)"
                value={garmentFit.legacy.sleeveOffsetY}
                min={-0.08}
                max={0.08}
                step={0.01}
                disabled={busy || busyPoll || autoPollLoopOn}
                onChange={(v) =>
                  patchGarmentFit((s) => {
                    const c = cloneFitState(s);
                    c.legacy.sleeveOffsetY = v;
                    return c;
                  })
                }
              />
            </>
          ) : null}
          {liveFitActiveRegion === "waist" ? (
            <>
              <FitSliderRow
                label="Waist offset Z"
                value={garmentFit.regions.waist.offsetZ}
                min={-0.08}
                max={0.08}
                step={0.01}
                disabled={busy || busyPoll || autoPollLoopOn}
                onChange={(v) =>
                  patchGarmentFit((s) => {
                    const c = cloneFitState(s);
                    c.regions.waist.offsetZ = v;
                    return c;
                  })
                }
              />
              <FitSliderRow
                label="Waist tighten"
                value={garmentFit.regions.waist.tighten}
                min={0}
                max={0.35}
                step={0.01}
                disabled={busy || busyPoll || autoPollLoopOn}
                onChange={(v) =>
                  patchGarmentFit((s) => {
                    const c = cloneFitState(s);
                    c.regions.waist.tighten = v;
                    return c;
                  })
                }
              />
              <FitSliderRow
                label="Legacy waist / hip Y"
                value={garmentFit.legacy.waistAdjustY}
                min={-0.08}
                max={0.08}
                step={0.01}
                disabled={busy || busyPoll || autoPollLoopOn}
                onChange={(v) =>
                  patchGarmentFit((s) => {
                    const c = cloneFitState(s);
                    c.legacy.waistAdjustY = v;
                    return c;
                  })
                }
              />
            </>
          ) : null}
          {liveFitActiveRegion === "hem" ? (
            <FitSliderRow
              label="Hem offset Y"
              value={garmentFit.regions.hem.offsetY}
              min={-0.08}
              max={0.08}
              step={0.01}
              disabled={busy || busyPoll || autoPollLoopOn}
              onChange={(v) =>
                patchGarmentFit((s) => {
                  const c = cloneFitState(s);
                  c.regions.hem.offsetY = v;
                  return c;
                })
              }
            />
          ) : null}
        </View>

        <Text style={styles.section}>Fit suggestions</Text>
        <Text style={styles.debugNote}>
          Rule-based hints: <Text style={styles.boldMuted}>live heuristics</Text>,{" "}
          <Text style={styles.boldMuted}>runtime clip proxy</Text> (sphere overlap in the rig — see Live
          tab toggle), <Text style={styles.boldMuted}>offline clipping stats</Text> after a hotspot PNG,
          and checklist tags. Apply updates the shared garment fit immediately.
        </Text>
        <View style={styles.fitPanel}>
          <AppButton
            label="Apply all suggestions"
            variant="secondary"
            disabled={
              busy ||
              busyPoll ||
              autoPollLoopOn ||
              fitSuggestions.length === 0
            }
            onPress={() => {
              patchGarmentFit((prev) => {
                let c = cloneFitState(prev);
                for (const s of fitSuggestions) c = s.apply(c);
                return c;
              });
              const last = fitSuggestions[fitSuggestions.length - 1];
              setLiveFitLastSuggestionId(last?.id ?? null);
              setLiveFitLastSuggestionSource(last?.suggestionSource ?? "mixed");
              useAvatarSceneStore.getState().setLiveFitShowBaseline(false);
            }}
          />
          {fitSuggestions.length === 0 ? (
            <Text style={styles.fitSubnote}>
              No suggestions — nudge sliders into extreme ranges for live hints, or run a clipping
              hotspot export (Offline) and refresh stats.
            </Text>
          ) : (
            fitSuggestions.map((s: FitSuggestion) => (
              <View key={s.id} style={styles.suggestionRow}>
                <Text style={styles.suggestionMessage}>{s.message}</Text>
                <Text style={styles.suggestionDetail}>{s.detail}</Text>
                {s.suggestionSource ? (
                  <Text style={styles.suggestionSource}>{s.suggestionSource}</Text>
                ) : null}
                <AppButton
                  label="Apply"
                  variant="secondary"
                  disabled={busy || busyPoll || autoPollLoopOn}
                  onPress={() => {
                    patchGarmentFit((prev) => s.apply(cloneFitState(prev)));
                    setLiveFitLastSuggestionId(s.id);
                    setLiveFitLastSuggestionSource(s.suggestionSource ?? "unknown");
                    useAvatarSceneStore.getState().setLiveFitShowBaseline(false);
                  }}
                />
              </View>
            ))
          )}
          {liveFitLastSuggestionId ? (
            <Text style={styles.fitSubnote} selectable>
              Last applied suggestion: {liveFitLastSuggestionId}
              {liveFitLastSuggestionSource
                ? ` · source ${liveFitLastSuggestionSource}`
                : ""}
            </Text>
          ) : null}
        </View>
        </>
        ) : null}

        {devMainTab === "live" ? (
          <Text style={styles.debugNote}>
            PNG preview, session thumbnails, host CLI commands, and the per-render checklist live in
            the <Text style={styles.boldMuted}>Offline debug render</Text> tab.
          </Text>
        ) : null}

        {devMainTab === "offline" ? (
          <>
        <Text style={styles.section}>Quick copy</Text>
        <View style={styles.copyGrid}>
          <AppButton
            label="Copy JSON"
            variant="secondary"
            onPress={() =>
              lastJsonPreview ? void onCopy(lastJsonPreview) : undefined
            }
            disabled={busy || !lastJsonPreview}
          />
          <AppButton
            label="Copy request CLI"
            variant="secondary"
            onPress={() =>
              cliRequestHint ? void onCopy(cliRequestHint) : undefined
            }
            disabled={busy || !cliRequestHint}
          />
          <AppButton
            label="Copy export CLI"
            variant="secondary"
            onPress={() =>
              cliExportHint ? void onCopy(cliExportHint) : undefined
            }
            disabled={busy || !cliExportHint}
          />
          <AppButton
            label="Copy render URL"
            variant="secondary"
            onPress={() =>
              resolvedRenderUrl
                ? void onCopy(resolvedRenderUrl)
                : undefined
            }
            disabled={busy || !resolvedRenderUrl}
          />
        </View>

        {sessionHistory.length > 0 ? (
          <>
            <Text style={styles.section}>Session render history</Text>
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={styles.historyScroll}
            >
              {sessionHistory.map((h) => (
                <Pressable
                  key={h.saved.renderId}
                  onPress={() => selectHistoryEntry(h)}
                  disabled={busy || busyPoll || autoPollLoopOn}
                  style={({ pressed }) => [
                    styles.historyCard,
                    lastSaved?.renderId === h.saved.renderId &&
                      styles.historyCardSelected,
                    pressed && styles.historyCardPressed,
                  ]}
                >
                  <View style={styles.historyThumbWrap}>
                    {h.thumbnailUri ? (
                      <Image
                        source={{ uri: h.thumbnailUri }}
                        style={styles.historyThumb}
                        contentFit="cover"
                      />
                    ) : (
                      <Text style={styles.historyThumbEmpty}>—</Text>
                    )}
                  </View>
                  <Text style={styles.historyMeta} numberOfLines={4}>
                    {h.pose} · {h.preset}
                    {"\n"}
                    {FIT_DEBUG_MODE_LABELS[h.fitDebugMode]}
                    {"\n"}
                    {(() => {
                      const gf = garmentFitForSessionEntry(h);
                      if (!gf) return "fit —";
                      return `gz ${gf.global.offset[2].toFixed(2)} · torsoZ ${gf.regions.torso.offsetZ.toFixed(2)} · inf ${gf.global.inflate.toFixed(2)}`;
                    })()}
                  </Text>
                  <Text style={styles.historyId} numberOfLines={1}>
                    {h.saved.renderId.length > 20
                      ? `${h.saved.renderId.slice(0, 10)}…`
                      : h.saved.renderId}
                  </Text>
                  <Text style={styles.historyTime}>
                    {new Date(h.createdAt).toLocaleTimeString()}
                  </Text>
                </Pressable>
              ))}
            </ScrollView>
          </>
        ) : null}

        <Text style={styles.section}>Fit issue checklist (session notes)</Text>
        <Text style={styles.debugNote}>
          In-memory only per renderId. Grouped for systematic reviews; tags also feed fit
          suggestions above.
        </Text>
        {(["upper", "arms", "lower", "both"] as const).map((region) => (
          <View key={region} style={styles.checklistRegion}>
            <Text style={styles.checklistRegionTitle}>
              {region === "upper"
                ? "Upper body"
                : region === "arms"
                  ? "Arms"
                  : region === "lower"
                    ? "Lower body"
                    : "General"}
            </Text>
            <View style={styles.row}>
              {FIT_ISSUE_DEFS.filter((d) => d.region === region).map((d) => {
                const on = currentAnnotation.tags.includes(d.id);
                return (
                  <AppButton
                    key={d.id}
                    label={d.label}
                    variant={on ? "primary" : "secondary"}
                    onPress={() => toggleIssueTag(d.id)}
                    disabled={!lastSaved || busy || busyPoll}
                  />
                );
              })}
            </View>
          </View>
        ))}
        <Text style={styles.section}>Dev notes (this render)</Text>
        <TextInput
          style={styles.notesInput}
          placeholder="Torso vs sleeves, clipping zones, pose notes…"
          placeholderTextColor={theme.colors.textMuted}
          multiline
          value={currentAnnotation.notes}
          onChangeText={setNotesForCurrent}
          editable={!!lastSaved && !busy}
        />

        <View style={styles.previewShell}>
          <Text style={styles.section}>Preview & compare</Text>
          <View style={styles.cliRow}>
            <AppButton
              label="Compare off"
              variant={compareLayout === "off" ? "primary" : "secondary"}
              onPress={() => setCompareLayout("off")}
              disabled={busyPoll}
            />
            <AppButton
              label="Toggle A/B"
              variant={compareLayout === "toggle" ? "primary" : "secondary"}
              onPress={() => setCompareLayout("toggle")}
              disabled={busyPoll}
            />
            <AppButton
              label="Side-by-side"
              variant={compareLayout === "side" ? "primary" : "secondary"}
              onPress={() => setCompareLayout("side")}
              disabled={busyPoll}
            />
            <AppButton
              label="Onion skin"
              variant={compareLayout === "onion" ? "primary" : "secondary"}
              onPress={() => setCompareLayout("onion")}
              disabled={busyPoll}
            />
          </View>
          <View style={styles.cliRow}>
            <AppButton
              label="Baseline: current image"
              variant="secondary"
              onPress={captureCompareBaseline}
              disabled={!displayImageUri || busyPoll}
            />
            <AppButton
              label="Baseline: prev history"
              variant="secondary"
              onPress={loadCompareFromPreviousHistory}
              disabled={busyPoll || sessionHistory.length < 2}
            />
            {compareLayout === "toggle" && compareBaselineUri ? (
              <AppButton
                label={compareShowBaseline ? "Show current" : "Show baseline"}
                variant="secondary"
                onPress={() => setCompareShowBaseline((v) => !v)}
                disabled={busyPoll}
              />
            ) : null}
          </View>
          {compareLayout === "onion" && compareBaselineUri && displayImageUri ? (
            <View style={styles.cliRow}>
              <Text style={styles.autoPollLabel}>Overlay alpha</Text>
              <AppButton
                label="−"
                variant="ghost"
                onPress={() => setOnionOpacity((o) => Math.max(0.1, o - 0.1))}
              />
              <Text style={styles.mono}>{onionOpacity.toFixed(2)}</Text>
              <AppButton
                label="+"
                variant="ghost"
                onPress={() => setOnionOpacity((o) => Math.min(1, o + 0.1))}
              />
            </View>
          ) : null}
          <View style={styles.cliRow}>
            <Text style={styles.autoPollLabel}>Zoom</Text>
            <AppButton
              label="−"
              variant="ghost"
              onPress={() =>
                setPreviewZoom((z) => Math.max(1, Math.round((z - 0.25) * 100) / 100))
              }
            />
            <Text style={styles.mono}>{previewZoom.toFixed(2)}×</Text>
            <AppButton
              label="+"
              variant="ghost"
              onPress={() =>
                setPreviewZoom((z) => Math.min(2.25, Math.round((z + 0.25) * 100) / 100))
              }
            />
            <AppButton
              label="Reset"
              variant="ghost"
              onPress={() => setPreviewZoom(1)}
            />
          </View>

          <View style={[styles.previewFrame, { overflow: "hidden" }]}>
            <View
              style={[
                styles.previewZoomInner,
                {
                  transform: [{ scale: previewZoom }],
                },
              ]}
            >
              {(() => {
                const currentUri = displayImageUri;
                const baselineRaw = compareBaselineUri?.split("?")[0];
                const baselineUri = baselineRaw
                  ? `${baselineRaw}?cb=cmp`
                  : null;

                if (
                  compareLayout === "side" &&
                  baselineUri &&
                  currentUri
                ) {
                  return (
                    <View style={styles.sideBySide}>
                      <Image
                        source={{ uri: baselineUri }}
                        style={styles.sideImage}
                        contentFit="contain"
                      />
                      <Image
                        source={{ uri: currentUri }}
                        style={styles.sideImage}
                        contentFit="contain"
                      />
                    </View>
                  );
                }

                if (
                  compareLayout === "onion" &&
                  baselineUri &&
                  currentUri
                ) {
                  return (
                    <View style={styles.onionWrap}>
                      <Image
                        source={{ uri: baselineUri }}
                        style={StyleSheet.absoluteFillObject}
                        contentFit="contain"
                      />
                      <Image
                        source={{ uri: currentUri }}
                        style={[
                          StyleSheet.absoluteFillObject,
                          { opacity: onionOpacity },
                        ]}
                        contentFit="contain"
                      />
                    </View>
                  );
                }

                const toggleUri =
                  compareLayout === "toggle" &&
                  compareShowBaseline &&
                  baselineUri
                    ? baselineUri
                    : currentUri;

                if (toggleUri) {
                  return (
                    <Image
                      source={{ uri: toggleUri }}
                      style={styles.previewImage}
                      contentFit="contain"
                      accessibilityLabel="Avatar render preview"
                    />
                  );
                }

                if (currentUri) {
                  return (
                    <Image
                      source={{ uri: currentUri }}
                      style={styles.previewImage}
                      contentFit="contain"
                      accessibilityLabel="Avatar render preview"
                    />
                  );
                }

                return (
                  <View style={styles.previewPlaceholder}>
                    {(busy && !imageUri) || busyPoll || autoPollLoopOn ? (
                      <ActivityIndicator color={theme.colors.primary} />
                    ) : null}
                    {previewHelpText ? (
                      <Text style={styles.previewPlaceholderText}>
                        {previewHelpText}
                      </Text>
                    ) : null}
                  </View>
                );
              })()}
            </View>
          </View>
          {imageUri ? (
            <>
              <Text style={styles.staleNote}>
                Re-export on host with same renderId can be cached. Refresh applies a cache-bust query.
                {(mayBeStale || devPhase === "stale_render") &&
                  " Controls changed since load — treat as stale until you rebuild or refresh."}
              </Text>
              <View style={styles.cliRow}>
                {resolvedRenderUrl ? (
                  <AppButton
                    label="Open render URL"
                    variant="secondary"
                    onPress={() => void openRenderUrl()}
                    disabled={busy}
                  />
                ) : null}
                <AppButton
                  label="Refresh render"
                  variant="secondary"
                  onPress={() => void onRefreshRenderHttp()}
                  loading={busyPoll}
                  disabled={refreshBlocked}
                />
              </View>
            </>
          ) : (
            <AppButton
              label="Refresh render"
              variant="secondary"
              onPress={() => void onRefreshRenderHttp()}
              loading={busyPoll}
              disabled={refreshBlocked}
              fullWidth
            />
          )}
        </View>

        <Text style={styles.hint}>
          <Text style={styles.hintStrong}>Workflow: </Text>
          build request → host JSON + export → serve repo (
          <Text style={styles.mono}>npx serve .</Text>
          ) → refresh or auto-poll HTTP. Android does not read{" "}
          <Text style={styles.mono}>E:/…</Text> directly.
        </Text>

        <View style={styles.diagnostics}>
          <Text style={styles.diagnosticsTitle}>Environment</Text>
          <Text style={styles.diagnosticsLine}>Platform: {Platform.OS}</Text>
          <Text style={styles.diagnosticsLine}>
            Repo root: {repoRoot ?? "—"}
          </Text>
          <Text style={styles.diagnosticsLine}>
            CLOSY_REPO_ROOT env length: {envRawLen}
          </Text>
          <Text style={styles.diagnosticsLine}>
            Host render base URL: {renderBaseUrl ?? "—"}
          </Text>
          <Text style={styles.diagnosticsLine}>
            Direct file render on Android (Windows repo):{" "}
            {hostFileRenderOnAndroidDisabled ? "off — use HTTP" : "n/a"}
          </Text>
          <Text style={styles.diagnosticsLine}>
            Mock: {mockOn ? "on" : "off"}
          </Text>
          <Text style={styles.diagnosticsLine}>
            Windows-style repo path:{" "}
            {repoRoot != null ? (repoIsWindowsHostPath ? "yes" : "no") : "—"}
          </Text>
          <Text style={styles.diagnosticsLine}>
            FileSystem cache: {canUseCache ? "yes" : "no"}
            {Platform.OS === "web" ? " (n/a web)" : ""}
          </Text>
        </View>

        <Text style={styles.debugNote}>
          Adjust fit sliders, pick offline debug mode (e.g. clipping), then build. Run host export →
          Refresh render. Enable reuse when you want the same renderId/path for faster PNG overwrite
          iteration.
        </Text>
        <View style={styles.autoPollRow}>
          <Text style={styles.autoPollLabel}>Reuse renderId (same PNG path)</Text>
          <Switch
            value={reuseRenderId}
            onValueChange={setReuseRenderId}
            disabled={busy || busyPoll || autoPollLoopOn || lastSaved == null}
          />
        </View>
        {lastSaved == null ? (
          <Text style={styles.debugNote}>
            After the first successful build, you can enable reuse to overwrite the same request JSON
            and export path.
          </Text>
        ) : null}
        <AppButton
          label={
            reuseRenderId
              ? "Build / rebuild request (reuse renderId)"
              : Platform.OS === "web"
                ? "Build request (new renderId)"
                : "Build / rebuild request (new renderId)"
          }
          onPress={() => void onGenerate()}
          loading={busy}
          disabled={busy || busyPoll || autoPollLoopOn}
          fullWidth
        />

        <View style={styles.autoPollRow}>
          <Text style={styles.autoPollLabel}>Auto-poll HTTP</Text>
          <Switch
            value={autoPoll}
            onValueChange={setAutoPoll}
            disabled={lastSaved == null || busy}
          />
        </View>
        {autoPoll && lastSaved == null ? (
          <Text style={styles.debugNote}>Build a request to enable polling.</Text>
        ) : null}

        <AppButton
          label="Mock image"
          variant="secondary"
          onPress={() => void onMock()}
          disabled={busy || busyPoll || autoPollLoopOn}
          fullWidth
        />

        {lastJsonPreview ? (
          <View style={styles.jsonBox}>
            <Text style={styles.section}>Request JSON</Text>
            <Text style={styles.jsonPreview} selectable numberOfLines={6}>
              {lastJsonPreview}
            </Text>
            <View style={styles.cliRow}>
              <AppButton
                label="Copy"
                variant="secondary"
                onPress={() => void onCopy(lastJsonPreview)}
                disabled={busy || busyPoll}
              />
              <AppButton
                label="Share"
                variant="secondary"
                onPress={() => void onShareJson(lastJsonPreview)}
                disabled={busy || busyPoll}
              />
            </View>
          </View>
        ) : null}

        {cliRequestHint ? (
          <View style={styles.cliBox}>
            <Text style={styles.cliLabel}>Host — request JSON</Text>
            <Text style={styles.cliText} selectable>
              {cliRequestHint}
            </Text>
            <View style={styles.cliRow}>
              <AppButton
                label="Copy"
                variant="secondary"
                onPress={() => void onCopy(cliRequestHint)}
                disabled={busy || busyPoll}
              />
              <AppButton
                label="Share"
                variant="secondary"
                onPress={() => void onShareCommand(cliRequestHint)}
                disabled={busy || busyPoll}
              />
            </View>
          </View>
        ) : null}

        {cliExportHint ? (
          <View style={styles.cliBox}>
            <Text style={styles.cliLabel}>Host — export PNG</Text>
            <Text style={styles.cliText} selectable>
              {cliExportHint}
            </Text>
            <View style={styles.cliRow}>
              <AppButton
                label="Copy"
                variant="secondary"
                onPress={() => void onCopy(cliExportHint)}
                disabled={busy || busyPoll}
              />
              <AppButton
                label="Share"
                variant="secondary"
                onPress={() => void onShareCommand(cliExportHint)}
                disabled={busy || busyPoll}
              />
            </View>
          </View>
        ) : null}
          </>
        ) : null}

        {warnings.length > 0 ? (
          <View style={styles.warningsBox}>
            {warnings.map((w) => (
              <Text key={w} style={styles.warningText}>
                {w}
              </Text>
            ))}
          </View>
        ) : null}

        {status ? <Text style={styles.status}>{status}</Text> : null}
        {error ? <Text style={styles.error}>{error}</Text> : null}

        <AppButton
          label="Back"
          variant="secondary"
          onPress={() => router.back()}
          fullWidth
        />
      </ScrollView>
      </View>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  flexPage: {
    flex: 1,
    maxWidth: 560,
    width: "100%",
    alignSelf: "center",
  },
  headerBlock: {
    paddingHorizontal: theme.spacing.md,
    paddingTop: theme.spacing.sm,
    gap: theme.spacing.sm,
  },
  flexScroll: {
    flex: 1,
    minHeight: 0,
  },
  liveWorkbenchColumn: {
    paddingHorizontal: theme.spacing.md,
    gap: theme.spacing.xs,
    marginBottom: theme.spacing.sm,
  },
  viewportPinned: {
    borderRadius: theme.radii.md,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.border,
  },
  liveSubTabBar: {
    flexDirection: "row",
    flexWrap: "nowrap",
    gap: 6,
    paddingVertical: 4,
  },
  liveSubTabChip: {
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: 6,
    borderRadius: theme.radii.sm,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
  },
  liveSubTabChipActive: {
    borderColor: theme.colors.primary,
    backgroundColor: theme.colors.surface,
  },
  liveSubTabChipTxt: {
    fontSize: 11,
    fontWeight: "600",
    color: theme.colors.textMuted,
  },
  liveSubTabChipTxtActive: {
    color: theme.colors.primary,
  },
  liveWorkbenchPanel: {
    minHeight: 80,
  },
  liveWorkbenchPanelInner: {
    paddingBottom: theme.spacing.md,
    gap: theme.spacing.sm,
  },
  scroll: {
    padding: theme.spacing.md,
    paddingBottom: theme.spacing.xl,
    gap: theme.spacing.md,
    maxWidth: 560,
    alignSelf: "center",
    width: "100%",
  },
  title: {
    fontSize: theme.typography.fontSize.lg,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  devBadge: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    fontStyle: "italic",
  },
  mainTabRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: theme.spacing.sm,
  },
  phaseBox: {
    padding: theme.spacing.sm,
    borderRadius: theme.radii.sm,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
    gap: 6,
  },
  phaseTitle: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
    textTransform: "uppercase",
  },
  phasePill: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.primary,
  },
  phaseText: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.text,
    lineHeight: 20,
  },
  section: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
    textTransform: "uppercase",
  },
  row: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: theme.spacing.sm,
  },
  historyRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: theme.spacing.xs,
  },
  debugNote: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    lineHeight: 18,
  },
  clippingHelp: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.text,
    lineHeight: 20,
    paddingVertical: theme.spacing.xs,
  },
  boldMuted: {
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  fitPanel: {
    padding: theme.spacing.sm,
    borderRadius: theme.radii.sm,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
    gap: 8,
  },
  liveWorkstationBox: {
    borderColor: theme.colors.primary,
    borderWidth: 1,
    backgroundColor: theme.colors.surface,
  },
  bodyShapeActions: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    gap: theme.spacing.sm,
    marginBottom: theme.spacing.xs,
  },
  bodyShapeDefaultHint: {
    fontSize: 11,
    fontFamily: "monospace",
    color: theme.colors.textMuted,
  },
  bodyShapeSliders: {
    marginBottom: theme.spacing.sm,
    marginTop: theme.spacing.xs,
  },
  clipOverlayRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    gap: theme.spacing.sm,
    marginTop: theme.spacing.xs,
  },
  clipOverlayHint: {
    flex: 1,
    minWidth: 120,
    fontSize: 11,
    color: theme.colors.textMuted,
    lineHeight: 15,
  },
  clipSummary: {
    fontSize: 11,
    fontFamily: "monospace",
    color: theme.colors.text,
    lineHeight: 16,
    marginTop: 4,
  },
  poseFitDebugBox: {
    marginTop: theme.spacing.xs,
    marginBottom: theme.spacing.sm,
    padding: theme.spacing.xs,
    borderRadius: theme.radii.sm,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
    gap: 4,
  },
  poseFitDebugLine: {
    fontSize: 10,
    fontFamily: "monospace",
    color: theme.colors.text,
    lineHeight: 14,
  },
  stressHint: {
    fontSize: 11,
    color: theme.colors.textMuted,
    lineHeight: 16,
    marginBottom: theme.spacing.xs,
  },
  stressResultBox: {
    marginTop: theme.spacing.xs,
    padding: theme.spacing.xs,
    borderRadius: theme.radii.sm,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
    gap: 4,
  },
  stressScoreLine: {
    fontSize: 12,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  stressWorstLine: {
    fontSize: 11,
    color: theme.colors.primary,
    lineHeight: 16,
  },
  stressPoseLine: {
    fontSize: 10,
    fontFamily: "monospace",
    color: theme.colors.textMuted,
    lineHeight: 15,
  },
  stressPoseWorst: {
    color: theme.colors.primary,
    fontWeight: theme.typography.fontWeight.semibold,
  },
  workstationLoop: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.text,
    lineHeight: 20,
  },
  liveCompareBanner: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.primary,
    fontWeight: theme.typography.fontWeight.semibold,
    lineHeight: 18,
  },
  liveRegionPill: {
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
    borderRadius: theme.radii.sm,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
    marginRight: theme.spacing.xs,
  },
  liveRegionPillActive: {
    borderColor: theme.colors.primary,
    borderWidth: 2,
    backgroundColor: theme.colors.surface,
  },
  liveRegionPillText: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    fontWeight: theme.typography.fontWeight.medium,
  },
  liveRegionPillTextActive: {
    color: theme.colors.primary,
    fontWeight: theme.typography.fontWeight.semibold,
  },
  snapshotStrip: {
    flexDirection: "row",
    gap: theme.spacing.xs,
    paddingVertical: theme.spacing.xs,
  },
  snapshotCard: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    maxWidth: 200,
    padding: 6,
    borderRadius: theme.radii.sm,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
  },
  snapshotTap: { flex: 1, minWidth: 0 },
  snapshotMeta: {
    fontSize: 10,
    color: theme.colors.textMuted,
    fontFamily: Platform.select({ web: "monospace", default: "monospace" }),
  },
  fitPresetWrap: {
    flexWrap: "wrap",
    marginBottom: theme.spacing.xs,
  },
  fitRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.xs,
  },
  fitRowLabel: {
    flex: 1,
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.text,
  },
  fitRowValue: {
    minWidth: 52,
    fontSize: theme.typography.fontSize.sm,
    fontVariant: ["tabular-nums"],
    color: theme.colors.primary,
    textAlign: "center",
  },
  fitStepBtn: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: theme.radii.sm,
    backgroundColor: theme.colors.border,
  },
  fitStepBtnPressed: { opacity: 0.75 },
  fitStepTxt: {
    fontSize: theme.typography.fontSize.md,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  fitSubnote: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    marginTop: theme.spacing.xs,
  },
  workflowBox: {
    padding: theme.spacing.sm,
    borderRadius: theme.radii.sm,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
    gap: 6,
  },
  workflowStep: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.text,
    lineHeight: 18,
  },
  suggestionRow: {
    gap: 6,
    paddingVertical: theme.spacing.xs,
    borderTopWidth: 1,
    borderTopColor: theme.colors.border,
  },
  suggestionMessage: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.text,
  },
  suggestionDetail: {
    fontSize: theme.typography.fontSize.caption,
    fontFamily: Platform.select({ web: "monospace", default: "monospace" }),
    color: theme.colors.textMuted,
  },
  suggestionSource: {
    fontSize: 10,
    color: theme.colors.primary,
    fontFamily: Platform.select({ web: "monospace", default: "monospace" }),
  },
  diagnostics: {
    padding: theme.spacing.sm,
    borderRadius: theme.radii.sm,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
    gap: 6,
  },
  diagnosticsTitle: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
    textTransform: "uppercase",
  },
  diagnosticsLine: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.text,
    fontFamily: Platform.select({ web: "monospace", default: "monospace" }),
  },
  copyGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: theme.spacing.sm,
  },
  previewShell: { gap: theme.spacing.sm },
  previewFrame: {
    width: "100%",
    aspectRatio: 1,
    backgroundColor: theme.colors.border,
    borderRadius: theme.radii.md,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  previewImage: {
    width: "100%",
    height: "100%",
  },
  previewPlaceholder: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    padding: theme.spacing.md,
    gap: theme.spacing.sm,
    minHeight: 200,
  },
  previewPlaceholderText: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
    textAlign: "center",
    lineHeight: 20,
  },
  staleNote: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    lineHeight: 18,
  },
  hint: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
    lineHeight: 20,
  },
  hintStrong: {
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  mono: {
    fontFamily: Platform.select({ web: "monospace", default: "monospace" }),
    fontSize: theme.typography.fontSize.caption,
  },
  cliBox: {
    gap: theme.spacing.sm,
    padding: theme.spacing.sm,
    borderRadius: theme.radii.sm,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  cliLabel: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
  },
  cliText: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.text,
    fontFamily: Platform.select({ web: "monospace", default: "monospace" }),
  },
  cliRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: theme.spacing.sm,
  },
  jsonBox: { gap: theme.spacing.sm },
  jsonPreview: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    fontFamily: Platform.select({ web: "monospace", default: "monospace" }),
  },
  warningsBox: {
    gap: 8,
    padding: theme.spacing.sm,
    borderRadius: theme.radii.sm,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  warningText: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
    lineHeight: 20,
  },
  status: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.text,
    lineHeight: 20,
  },
  error: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.danger,
    lineHeight: 20,
  },
  autoPollRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: theme.spacing.xs,
  },
  autoPollLabel: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.text,
  },
  modeChipsRow: {
    flexDirection: "row",
    gap: theme.spacing.xs,
    paddingVertical: theme.spacing.xs,
  },
  modeChip: {
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
    borderRadius: theme.radii.sm,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
    maxWidth: 120,
  },
  modeChipSelected: {
    borderColor: theme.colors.primary,
    backgroundColor: theme.colors.surface,
  },
  modeChipPressed: { opacity: 0.85 },
  modeChipLabel: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    textAlign: "center",
  },
  modeChipLabelSelected: {
    color: theme.colors.primary,
    fontWeight: theme.typography.fontWeight.semibold,
  },
  historyScroll: {
    flexDirection: "row",
    gap: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
  },
  historyCard: {
    width: 88,
    padding: 6,
    borderRadius: theme.radii.sm,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
  },
  historyCardSelected: {
    borderColor: theme.colors.primary,
  },
  historyCardPressed: { opacity: 0.9 },
  historyThumbWrap: {
    width: "100%",
    aspectRatio: 1,
    borderRadius: 4,
    overflow: "hidden",
    backgroundColor: theme.colors.border,
    marginBottom: 4,
  },
  historyThumb: { width: "100%", height: "100%" },
  historyThumbEmpty: {
    textAlign: "center",
    lineHeight: 72,
    color: theme.colors.textMuted,
    fontSize: theme.typography.fontSize.xs,
  },
  historyMeta: {
    fontSize: 10,
    color: theme.colors.textMuted,
  },
  historyId: {
    fontSize: 9,
    fontFamily: Platform.select({ web: "monospace", default: "monospace" }),
    color: theme.colors.text,
  },
  historyTime: {
    fontSize: 9,
    color: theme.colors.textMuted,
  },
  checklistRegion: { gap: theme.spacing.xs },
  checklistRegionTitle: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
  },
  notesInput: {
    minHeight: 72,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radii.sm,
    padding: theme.spacing.sm,
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.text,
    textAlignVertical: "top",
  },
  previewZoomInner: {
    width: "100%",
    height: "100%",
    justifyContent: "center",
    alignItems: "center",
  },
  sideBySide: {
    flexDirection: "row",
    width: "100%",
    height: "100%",
  },
  sideImage: { flex: 1, minWidth: 0 },
  onionWrap: {
    width: "100%",
    height: "100%",
    position: "relative",
  },
});
