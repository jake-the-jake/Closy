import * as Clipboard from "expo-clipboard";
import { Image } from "expo-image";
import * as FileSystem from "expo-file-system/legacy";
import * as Linking from "expo-linking";
import { useRouter } from "expo-router";
import {
  useCallback,
  useEffect,
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
  View,
} from "react-native";

import { AppButton } from "@/components/ui/app-button";
import { ScreenContainer } from "@/components/ui/screen-container";

import {
  FIT_DEBUG_MODE_LABELS,
  buildAvatarExportRequest,
  buildNpmAvatarRequestCommand,
  buildNpmCliCommand,
  canUseCacheDirectoryForExport,
  fitDebugModeToExportFlags,
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
  type AvatarOutfitLike,
  type FitDebugViewMode,
  type SaveAvatarRequestResult,
} from "@/features/avatar-export";
import { runAvatarExportMock } from "@/features/avatar-export/runner/avatarExportRunner.mock";
import { theme } from "@/theme";

type PoseKey = "relaxed" | "walk" | "tpose" | "apose";

type PresetKey = "default" | "navy" | "casual";

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
  createdAt: number;
  thumbnailUri: string | null;
};

type LoadSnapshot = {
  renderId: string;
  pose: PoseKey;
  preset: PresetKey;
  fitDebugMode: FitDebugViewMode;
};

type CompareLayout = "off" | "toggle" | "side" | "onion";

type RenderAnnotation = { notes: string; tags: string[] };

const FIT_ISSUE_DEFS = [
  { id: "torso_forward", label: "Torso too far forward", region: "tops" },
  { id: "clipping_back", label: "Clipping at back", region: "tops" },
  { id: "sleeves_ok", label: "Sleeves OK", region: "tops" },
  { id: "neckline_offset", label: "Neckline offset", region: "tops" },
  { id: "hem_high", label: "Hem too high", region: "bottoms" },
  { id: "hem_low", label: "Hem too low", region: "bottoms" },
  { id: "waist_mismatch", label: "Waist mismatch", region: "bottoms" },
  { id: "pose_specific", label: "Pose-specific failure", region: "both" },
] as const;

const PRESETS: Record<PresetKey, AvatarOutfitLike> = {
  default: {
    top: { kind: "jumper" },
    bottom: { kind: "trousers" },
  },
  navy: {
    top: { kind: "jumper", color: [0.12, 0.18, 0.42] },
    bottom: { kind: "trousers", color: [0.15, 0.16, 0.2] },
  },
  casual: {
    top: { kind: "shirt", color: [0.85, 0.35, 0.32] },
    bottom: { kind: "trousers", color: [0.28, 0.32, 0.38] },
    shoes: { kind: "shoes", color: [0.65, 0.64, 0.62] },
  },
};

const MAX_RENDER_HISTORY = 10;
const AUTO_POLL_INTERVAL_MS = 1800;

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
    "Stale — pose, preset, or debug mode changed since this image loaded. Rebuild or refresh.",
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

export function AvatarPreviewDevScreen() {
  const router = useRouter();
  const [pose, setPose] = useState<PoseKey>("relaxed");
  const [preset, setPreset] = useState<PresetKey>("default");
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
  const [fitDebugMode, setFitDebugMode] =
    useState<FitDebugViewMode>("normal");
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
    () => isFitDebugModeEngineWired(fitDebugMode),
    [fitDebugMode],
  );

  const mayBeStale = useMemo(() => {
    if (!imageUri || !lastSaved || !loadSnapshot) return false;
    if (loadSnapshot.renderId !== lastSaved.renderId) return false;
    return (
      loadSnapshot.pose !== pose ||
      loadSnapshot.preset !== preset ||
      loadSnapshot.fitDebugMode !== fitDebugMode
    );
  }, [imageUri, lastSaved, loadSnapshot, pose, preset, fitDebugMode]);

  const currentAnnotation: RenderAnnotation = useMemo(() => {
    if (!lastSaved) return { notes: "", tags: [] };
    return annotations[lastSaved.renderId] ?? { notes: "", tags: [] };
  }, [annotations, lastSaved]);

  useEffect(() => {
    const wired =
      fitDebugMode === "normal" || isFitDebugModeEngineWired(fitDebugMode);
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
  }, [fitDebugMode]);

  useEffect(() => {
    if (!imageUri || !lastSaved || !loadSnapshot) return;
    if (loadSnapshot.renderId !== lastSaved.renderId) return;
    const changed =
      loadSnapshot.pose !== pose ||
      loadSnapshot.preset !== preset ||
      loadSnapshot.fitDebugMode !== fitDebugMode;
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
    preset,
    fitDebugMode,
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
        "pose" | "preset" | "fitDebugMode"
      >,
    ) => {
      const base = uri.split("?")[0];
      setImageUri(base);
      setImageCacheBust(Date.now());
      setLastSuccessAt(new Date().toLocaleString());
      setLoadSnapshot({
        renderId: saved.renderId,
        pose: snapshotOverride?.pose ?? pose,
        preset: snapshotOverride?.preset ?? preset,
        fitDebugMode: snapshotOverride?.fitDebugMode ?? fitDebugMode,
      });
      setSessionHistory((h) => patchSessionThumbnail(h, saved.renderId, base));
    },
    [pose, preset, fitDebugMode],
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
      const outfit = PRESETS[preset];
      const debug = fitDebugModeToExportFlags(fitDebugMode);
      const request = buildAvatarExportRequest(outfit, {
        pose,
        width: 1024,
        height: 1024,
        camera: "three_quarter",
        renderId: `dev_${preset}_${pose}_${Date.now()}`,
        debug,
      });
      const saved = await saveAvatarExportRequest(request);
      setLastSaved(saved);
      const entry: SessionRenderEntry = {
        saved,
        pose,
        preset,
        fitDebugMode,
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
  }, [applyPersistedExportResult, fitDebugMode, pose, preset, repoRoot]);

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
    setPose(entry.pose);
    setPreset(entry.preset);
    setFitDebugMode(entry.fitDebugMode);
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
  }, [afterRenderReady]);

  const onMock = useCallback(async () => {
    setBusy(true);
    setError(null);
    setWarnings([]);
    setImageUri(null);
    setImageCacheBust(null);
    try {
      const request = buildAvatarExportRequest(PRESETS.casual, {
        pose: "relaxed",
        renderId: `mock_${Date.now()}`,
        debug: fitDebugModeToExportFlags(fitDebugMode),
      });
      const saved = await saveAvatarExportRequest(request);
      setLastSaved(saved);
      const entry: SessionRenderEntry = {
        saved,
        pose: "relaxed",
        preset: "casual",
        fitDebugMode,
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
        afterRenderReady(result.imageUri, saved);
        setDevPhase("render_loaded");
        setStatus("Mock image (no native binary).");
      }
    } catch (e) {
      setDevPhase("render_failed");
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setBusy(false);
    }
  }, [afterRenderReady, fitDebugMode]);

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
      <ScrollView
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={styles.title}>Avatar preview (dev)</Text>
        <Text style={styles.devBadge}>Dev / debug only — not shown in production flows.</Text>

        <View style={styles.phaseBox}>
          <Text style={styles.phaseTitle}>State</Text>
          <Text style={[styles.phasePill, styles.mono]}>{devPhase}</Text>
          <Text style={styles.phaseText}>{PHASE_COPY[devPhase]}</Text>
        </View>

        <Text style={styles.section}>Fit debug view mode</Text>
        <Text style={styles.debugNote}>
          Modes map to optional <Text style={styles.mono}>closy.debug</Text> in export JSON.
          Only <Text style={styles.mono}>normal</Text> is wired in the engine today; others are staged.
        </Text>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.modeChipsRow}
        >
          {listFitDebugModes().map((m) => {
            const wired = isFitDebugModeEngineWired(m);
            const selected = fitDebugMode === m;
            return (
              <Pressable
                key={m}
                onPress={() => setFitDebugMode(m)}
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
          Engine support: {debugWired ? "current mode" : "off for this mode — PNG may match normal until exporter reads flags"}
        </Text>

        <Text style={styles.section}>Render metadata</Text>
        <View style={styles.diagnostics}>
          <Text style={styles.diagnosticsLine}>
            debug mode: {fitDebugMode} {debugWired ? "(wired)" : "(staged)"}
          </Text>
          <Text style={styles.diagnosticsLine}>
            pose: {pose} · preset: {preset}
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
                  <Text style={styles.historyMeta} numberOfLines={2}>
                    {h.pose} · {h.preset}
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
          In-memory only per renderId. Use for consistent fit reviews (tops / bottoms).
        </Text>
        {(["tops", "bottoms", "both"] as const).map((region) => (
          <View key={region} style={styles.checklistRegion}>
            <Text style={styles.checklistRegionTitle}>
              {region === "tops"
                ? "Tops / upper"
                : region === "bottoms"
                  ? "Bottoms"
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

        <Text style={styles.section}>Pose</Text>
        <View style={styles.row}>
          {(["relaxed", "walk", "tpose", "apose"] as const).map((p) => (
            <AppButton
              key={p}
              label={p}
              variant={pose === p ? "primary" : "secondary"}
              onPress={() => setPose(p)}
              disabled={busy || busyPoll || autoPollLoopOn}
            />
          ))}
        </View>

        <Text style={styles.section}>Outfit preset</Text>
        <View style={styles.row}>
          {(["default", "navy", "casual"] as const).map((p) => (
            <AppButton
              key={p}
              label={p}
              variant={preset === p ? "primary" : "secondary"}
              onPress={() => setPreset(p)}
              disabled={busy || busyPoll || autoPollLoopOn}
            />
          ))}
        </View>

        <Text style={styles.debugNote}>
          Change pose or preset, then build again for a new renderId (same outfit preset + fit debug). Run host export, then Refresh render.
        </Text>
        <AppButton
          label={
            Platform.OS === "web"
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
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
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
