import { Canvas } from "@react-three/fiber/native";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import {
  Gesture,
  GestureDetector,
  GestureHandlerRootView,
} from "react-native-gesture-handler";
import { runOnJS } from "react-native-reanimated";

import {
  DEFAULT_BODY_SHAPE,
  DEFAULT_GARMENT_FIT_STATE,
  fitStatesEqual,
  type BodyShapeParams,
  type GarmentFitState,
} from "@/features/avatar-export";
import type {
  DevAvatarPoseKey,
  DevAvatarPresetKey,
} from "@/features/avatar-export/dev-avatar-shared";
import { AppButton } from "@/components/ui/app-button";
import { theme } from "@/theme";

import { BUNDLED_SKINNED_BODY_GLTF } from "./bundled-body-asset";
import {
  AvatarProceduralScene,
  CameraRig,
  type OrbitSpherical,
} from "./avatar-procedural-scene";
import {
  mergeAvatarViewportNav,
  type AvatarViewportNavSettings,
} from "./avatar-viewport-nav-settings";
import { deformationSummary } from "./garment-deformation";
import type {
  GarmentAttachmentSnapshot,
  LiveViewportPoseFitDebug,
} from "./live-viewport-debug-types";
import {
  analyzeRuntimeClipping,
  clipSeverityToEmissive,
  worstGarmentClipSeverity,
} from "./runtime-clipping-approx";
import {
  LIVE_VIEWPORT_SHADING_LABELS,
  type LiveViewportShadingMode,
} from "./live-viewport-shading";
import {
  getAvatarRuntimeAssetUrls,
  runtimeAssetSummary,
  type AvatarRuntimeAssetUrls,
} from "./runtime-asset-sources";

export type AvatarViewportLiveProps = {
  pose: DevAvatarPoseKey;
  preset: DevAvatarPresetKey;
  garmentFit: GarmentFitState;
  liveShading: LiveViewportShadingMode;
  height?: number;
  /** Override env-based runtime GLBs (merged onto `getAvatarRuntimeAssetUrls()`). */
  runtimeAssets?: Partial<AvatarRuntimeAssetUrls>;
  /** Dev: viewport is showing saved baseline fit for before/after compare. */
  compareActive?: boolean;
  /** Dev: tint garments by runtime clipping proxy (sphere overlap). */
  clipOverlayEnabled?: boolean;
  /** Shared parametric body (viewport mesh + clip proxies). */
  bodyShape?: BodyShapeParams;
  /**
   * Dev: use procedural capsule/box body instead of bundled skinned GLB (or env body URL).
   * Does not override `EXPO_PUBLIC_AVATAR_USE_PROCEDURAL_BODY=1` (both force procedural).
   */
  useProceduralBody?: boolean;
  /** Dev: hide garment proxies/GLBs so the body mesh is visible alone. */
  bodyOnlyGarments?: boolean;
  /** Dev: hide body mesh; show garments only (isolates garment vs body alignment). */
  garmentOnlyViewport?: boolean;
  /** Dev: pose / skinned rig / garment anchor snapshot for preview panel. */
  onLiveViewportPoseFitDebug?: (d: LiveViewportPoseFitDebug) => void;
  /** Dev: show bone attachment markers (spheres) in the canvas. */
  garmentAttachmentDebug?: boolean;
  /** Merged with defaults; drives damped orbit + zoom (dev workstation). */
  navSettings?: Partial<AvatarViewportNavSettings>;
  /** `workbench`: compact chrome; parent supplies reset/zoom in tabs. */
  layout?: "standalone" | "workbench";
  /** Increment from parent to snap camera to defaults without remounting. */
  cameraResetNonce?: number;
};

const DEFAULT_ORBIT: OrbitSpherical = { theta: 0.48, phi: 1.02, radius: 3.55 };
const TARGET: [number, number, number] = [0, 1.12, 0];

const SHOW_RIG_DEBUG =
  typeof process.env.EXPO_PUBLIC_AVATAR_VIEWPORT_RIG_DEBUG === "string" &&
  process.env.EXPO_PUBLIC_AVATAR_VIEWPORT_RIG_DEBUG === "1";

const SHOW_DEFORM_DEBUG =
  __DEV__ &&
  typeof process.env.EXPO_PUBLIC_AVATAR_DEFORM_DEBUG === "string" &&
  process.env.EXPO_PUBLIC_AVATAR_DEFORM_DEBUG === "1";

const SHOW_GARMENT_RIG_DEBUG =
  __DEV__ &&
  typeof process.env.EXPO_PUBLIC_AVATAR_GARMENT_RIG_DEBUG === "string" &&
  process.env.EXPO_PUBLIC_AVATAR_GARMENT_RIG_DEBUG === "1";

/** Set to `1` to force the procedural capsule/box body; default uses bundled skinned GLB. */
const FORCE_PROCEDURAL_BODY =
  typeof process.env.EXPO_PUBLIC_AVATAR_USE_PROCEDURAL_BODY === "string" &&
  process.env.EXPO_PUBLIC_AVATAR_USE_PROCEDURAL_BODY === "1";

const LOG_THROTTLE_MS = 280;

function sanitizeOrbit(o: OrbitSpherical, prev: OrbitSpherical, nav: AvatarViewportNavSettings): OrbitSpherical {
  let { theta, phi, radius } = o;
  if (!Number.isFinite(theta)) theta = prev.theta;
  if (!Number.isFinite(phi)) phi = prev.phi;
  if (!Number.isFinite(radius)) radius = prev.radius;
  phi = Math.min(nav.polarMax, Math.max(nav.polarMin, phi));
  radius = Math.min(nav.maxRadius, Math.max(nav.minRadius, radius));
  return { theta, phi, radius };
}

/**
 * RNGH Gesture *onUpdate* / *onBegin* run on the UI worklet thread with Reanimated.
 * Calling setState, touching refs from the wrong thread, or console.log from worklets crashes.
 * All such work is forwarded with runOnJS(...)(primitives only).
 */
export function AvatarViewportLive({
  pose,
  preset,
  garmentFit,
  liveShading,
  height = 320,
  runtimeAssets,
  compareActive = false,
  clipOverlayEnabled = false,
  bodyShape = DEFAULT_BODY_SHAPE,
  useProceduralBody = false,
  bodyOnlyGarments = false,
  garmentOnlyViewport = false,
  onLiveViewportPoseFitDebug,
  garmentAttachmentDebug = false,
  navSettings,
  layout = "standalone",
  cameraResetNonce = 0,
}: AvatarViewportLiveProps) {
  const navMerged = useMemo(() => mergeAvatarViewportNav(navSettings ?? undefined), [navSettings]);
  const navRef = useRef(navMerged);
  navRef.current = navMerged;

  const desiredRef = useRef<OrbitSpherical>({ ...DEFAULT_ORBIT });
  const smoothRef = useRef<OrbitSpherical>({ ...DEFAULT_ORBIT });
  const targetPanRef = useRef({ x: 0, z: 0 });

  const panBaseRef = useRef<OrbitSpherical>({ ...DEFAULT_ORBIT });
  const panBasePanRef = useRef({ x: 0, z: 0 });
  const pinchRadius0Ref = useRef(DEFAULT_ORBIT.radius);
  const mountedRef = useRef(true);
  const lastGestureLog = useRef(0);
  const lastResetNonce = useRef(cameraResetNonce);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (cameraResetNonce === lastResetNonce.current) return;
    lastResetNonce.current = cameraResetNonce;
    const o = { ...DEFAULT_ORBIT };
    desiredRef.current = sanitizeOrbit(o, o, navRef.current);
    smoothRef.current = { ...desiredRef.current };
    targetPanRef.current = { x: 0, z: 0 };
  }, [cameraResetNonce]);

  const applyDesired = useCallback((updater: (d: OrbitSpherical) => OrbitSpherical) => {
    const prev = desiredRef.current;
    desiredRef.current = sanitizeOrbit(updater(prev), prev, navRef.current);
  }, []);

  const logThrottle = useCallback((tag: string) => {
    if (!__DEV__) return;
    const now = Date.now();
    if (now - lastGestureLog.current < LOG_THROTTLE_MS) return;
    lastGestureLog.current = now;
    console.log(tag, { path: "runOnJS", cam: { ...desiredRef.current } });
  }, []);

  const panBeginJS = useCallback(() => {
    panBaseRef.current = { ...desiredRef.current };
    if (__DEV__) {
      console.log("[AvatarViewport] pan begin", { base: { ...panBaseRef.current } });
    }
  }, []);

  const panUpdateJS = useCallback((translationX: number, translationY: number) => {
    if (!Number.isFinite(translationX) || !Number.isFinite(translationY)) return;
    if (Math.abs(translationX) > 520 || Math.abs(translationY) > 520) return;
    const nav = navRef.current;
    const b = panBaseRef.current;
    const ix = nav.invertOrbitX ? -1 : 1;
    const iy = nav.invertOrbitY ? -1 : 1;
    const dYaw =
      -translationX *
      nav.orbitYawRadPerPx *
      nav.orbitSensitivity *
      nav.yawSpeedMultiplier *
      ix;
    const dPitch =
      translationY * nav.orbitPitchRadPerPx * nav.orbitSensitivity * iy;
    applyDesired((cur) => ({
      theta: cur.theta + dYaw,
      phi: cur.phi + dPitch,
      radius: b.radius,
    }));
    logThrottle("[AvatarViewport] pan update");
  }, [applyDesired, logThrottle]);

  const panEndJS = useCallback(() => {
    if (__DEV__) console.log("[AvatarViewport] pan end");
  }, []);

  const pan2BeginJS = useCallback(() => {
    panBasePanRef.current = { ...targetPanRef.current };
  }, []);

  const pan2UpdateJS = useCallback((translationX: number, translationY: number) => {
    if (!navRef.current.enablePan) return;
    if (!Number.isFinite(translationX) || !Number.isFinite(translationY)) return;
    const b = panBasePanRef.current;
    const k = 0.00045;
    targetPanRef.current = {
      x: Math.min(0.35, Math.max(-0.35, b.x - translationX * k)),
      z: Math.min(0.35, Math.max(-0.35, b.z + translationY * k)),
    };
  }, []);

  const pan2EndJS = useCallback(() => {}, []);

  const pinchBeginJS = useCallback(() => {
    pinchRadius0Ref.current = desiredRef.current.radius;
    if (__DEV__) {
      console.log("[AvatarViewport] pinch begin", {
        radius0: pinchRadius0Ref.current,
      });
    }
  }, []);

  const pinchUpdateJS = useCallback((scale: number) => {
    if (typeof scale !== "number" || !Number.isFinite(scale) || scale <= 0) return;
    const r0 = pinchRadius0Ref.current;
    if (!Number.isFinite(r0)) return;
    const nav = navRef.current;
    const exp = 0.82 * nav.zoomSensitivity;
    const raw = r0 * Math.pow(1 / scale, exp);
    applyDesired((c) => ({
      ...c,
      radius: raw,
    }));
    logThrottle("[AvatarViewport] pinch update");
  }, [applyDesired, logThrottle]);

  const pinchEndJS = useCallback(() => {
    if (__DEV__) console.log("[AvatarViewport] pinch end");
  }, []);

  const orbitGesture = useMemo(() => {
    const pan1 = Gesture.Pan()
      .maxPointers(1)
      .onBegin(() => {
        "worklet";
        runOnJS(panBeginJS)();
      })
      .onUpdate((e) => {
        "worklet";
        runOnJS(panUpdateJS)(e.translationX, e.translationY);
      })
      .onEnd(() => {
        "worklet";
        runOnJS(panEndJS)();
      })
      .onFinalize(() => {
        "worklet";
        runOnJS(panEndJS)();
      });

    const pan2 = Gesture.Pan()
      .minPointers(2)
      .maxPointers(2)
      .enabled(navMerged.enablePan)
      .onBegin(() => {
        "worklet";
        runOnJS(pan2BeginJS)();
      })
      .onUpdate((e) => {
        "worklet";
        runOnJS(pan2UpdateJS)(e.translationX, e.translationY);
      })
      .onEnd(() => {
        "worklet";
        runOnJS(pan2EndJS)();
      })
      .onFinalize(() => {
        "worklet";
        runOnJS(pan2EndJS)();
      });

    const pinch = Gesture.Pinch()
      .onBegin(() => {
        "worklet";
        runOnJS(pinchBeginJS)();
      })
      .onUpdate((e) => {
        "worklet";
        const s = e.scale;
        if (typeof s === "number" && Number.isFinite(s) && s > 0) {
          runOnJS(pinchUpdateJS)(s);
        }
      })
      .onEnd(() => {
        "worklet";
        runOnJS(pinchEndJS)();
      })
      .onFinalize(() => {
        "worklet";
        runOnJS(pinchEndJS)();
      });

    return Gesture.Simultaneous(pan1, pan2, pinch);
  }, [
    panBeginJS,
    panUpdateJS,
    panEndJS,
    pan2BeginJS,
    pan2UpdateJS,
    pan2EndJS,
    pinchBeginJS,
    pinchUpdateJS,
    pinchEndJS,
    navMerged.enablePan,
  ]);

  useEffect(() => {
    if (!__DEV__) return;
    console.log("[AvatarViewport] props", {
      pose,
      preset,
      liveShading,
      fitIsDefault: fitStatesEqual(garmentFit, DEFAULT_GARMENT_FIT_STATE),
    });
  }, [pose, preset, garmentFit, liveShading]);

  const resetCamera = () => {
    const o = { ...DEFAULT_ORBIT };
    desiredRef.current = sanitizeOrbit(o, o, navRef.current);
    smoothRef.current = { ...desiredRef.current };
    targetPanRef.current = { x: 0, z: 0 };
    if (__DEV__) console.log("[AvatarViewport] reset cam (press)");
  };
  const zoomIn = () => {
    applyDesired((c) => ({
      ...c,
      radius: Math.max(navRef.current.minRadius, c.radius - 0.38),
    }));
  };
  const zoomOut = () => {
    applyDesired((c) => ({
      ...c,
      radius: Math.min(navRef.current.maxRadius, c.radius + 0.38),
    }));
  };

  const fitIsNonDefault = !fitStatesEqual(garmentFit, DEFAULT_GARMENT_FIT_STATE);

  const [skinnedBodyLoadStatus, setSkinnedBodyLoadStatus] = useState<
    "idle" | "pending" | "loaded" | "failed"
  >("idle");
  const skinnedBodyLoadErrLogged = useRef<string | null>(null);
  const [skinnedPoseReport, setSkinnedPoseReport] =
    useState<LiveViewportPoseFitDebug["skinned"]>(null);
  const [garmentAnchorsDbg, setGarmentAnchorsDbg] =
    useState<LiveViewportPoseFitDebug["anchors"]>(null);
  const [attachmentSnapshot, setAttachmentSnapshot] = useState<GarmentAttachmentSnapshot | null>(
    null,
  );
  const lastSkinnedReportJson = useRef("");
  const lastAnchorsJson = useRef("");
  const lastAttachmentJson = useRef("");
  const lastLivePoseFitJson = useRef("");

  const envRuntimeUrls = useMemo(() => getAvatarRuntimeAssetUrls(), []);

  const runtimeBodyBundledModule = useMemo(() => {
    if (FORCE_PROCEDURAL_BODY || useProceduralBody) return null;
    if (runtimeAssets?.bodyGltfUrl != null) return null;
    if (envRuntimeUrls.bodyGltfUrl != null) return null;
    return BUNDLED_SKINNED_BODY_GLTF;
  }, [useProceduralBody, runtimeAssets?.bodyGltfUrl, envRuntimeUrls.bodyGltfUrl]);

  const resolvedRuntime = useMemo(() => {
    const env = getAvatarRuntimeAssetUrls();
    let bodyGltfUrl: string | null = null;
    const procedural = FORCE_PROCEDURAL_BODY || useProceduralBody;
    if (!procedural && runtimeBodyBundledModule == null) {
      bodyGltfUrl = runtimeAssets?.bodyGltfUrl ?? env.bodyGltfUrl ?? null;
    }
    return {
      bodyGltfUrl,
      topGltfUrl: runtimeAssets?.topGltfUrl ?? env.topGltfUrl,
      bottomGltfUrl: runtimeAssets?.bottomGltfUrl ?? env.bottomGltfUrl,
    } satisfies AvatarRuntimeAssetUrls;
  }, [runtimeAssets, useProceduralBody, runtimeBodyBundledModule]);

  const onRuntimeBodyLoaded = useCallback(() => {
    setSkinnedBodyLoadStatus("loaded");
  }, []);

  const onSkinnedRigPoseReport = useCallback(
    (r: NonNullable<LiveViewportPoseFitDebug["skinned"]>) => {
      const j = JSON.stringify(r);
      if (j === lastSkinnedReportJson.current) return;
      lastSkinnedReportJson.current = j;
      setSkinnedPoseReport(r);
    },
    [],
  );

  const onGarmentAnchorsDebug = useCallback(
    (d: NonNullable<LiveViewportPoseFitDebug["anchors"]>) => {
      const j = JSON.stringify(d);
      if (j === lastAnchorsJson.current) return;
      lastAnchorsJson.current = j;
      setGarmentAnchorsDbg(d);
    },
    [],
  );

  const onGarmentAttachmentSnapshot = useCallback((s: GarmentAttachmentSnapshot) => {
    const j = JSON.stringify(s);
    if (j === lastAttachmentJson.current) return;
    lastAttachmentJson.current = j;
    setAttachmentSnapshot(s);
  }, []);

  useEffect(() => {
    const noSkinnedRuntime =
      FORCE_PROCEDURAL_BODY ||
      useProceduralBody ||
      (runtimeBodyBundledModule == null && !resolvedRuntime.bodyGltfUrl);
    if (noSkinnedRuntime || garmentOnlyViewport) {
      lastSkinnedReportJson.current = "";
      lastAttachmentJson.current = "";
      setSkinnedPoseReport(null);
      setAttachmentSnapshot(null);
    }
  }, [
    useProceduralBody,
    runtimeBodyBundledModule,
    resolvedRuntime.bodyGltfUrl,
    garmentOnlyViewport,
  ]);

  useEffect(() => {
    if (garmentOnlyViewport || bodyOnlyGarments) {
      lastAttachmentJson.current = "";
      setAttachmentSnapshot(null);
    }
  }, [garmentOnlyViewport, bodyOnlyGarments]);

  useEffect(() => {
    if (!onLiveViewportPoseFitDebug) return;
    const payload: LiveViewportPoseFitDebug = {
      pose,
      preset,
      garmentPoseMatchesBody: true,
      skinned: skinnedPoseReport,
      anchors: garmentAnchorsDbg,
      attachment: attachmentSnapshot,
    };
    const j = JSON.stringify(payload);
    if (j === lastLivePoseFitJson.current) return;
    lastLivePoseFitJson.current = j;
    onLiveViewportPoseFitDebug(payload);
  }, [
    pose,
    preset,
    skinnedPoseReport,
    garmentAnchorsDbg,
    attachmentSnapshot,
    onLiveViewportPoseFitDebug,
  ]);

  const onRuntimeBodyLoadError = useCallback((message: string) => {
    setSkinnedBodyLoadStatus("failed");
    if (__DEV__) {
      const key = message.slice(0, 240);
      if (skinnedBodyLoadErrLogged.current !== key) {
        skinnedBodyLoadErrLogged.current = key;
        console.warn("[AvatarViewportLive] skinned body load failed:", message);
      }
    }
  }, []);

  useEffect(() => {
    skinnedBodyLoadErrLogged.current = null;
    if (runtimeBodyBundledModule != null) {
      setSkinnedBodyLoadStatus("pending");
    } else if (resolvedRuntime.bodyGltfUrl) {
      setSkinnedBodyLoadStatus("pending");
    } else {
      setSkinnedBodyLoadStatus("idle");
    }
  }, [runtimeBodyBundledModule, resolvedRuntime.bodyGltfUrl]);

  const skinnedBodyPathActive =
    runtimeBodyBundledModule != null || resolvedRuntime.bodyGltfUrl != null;
  /** First paint is `idle` before `useEffect` sets `pending`; show pending in diagnostics. */
  const bodyLoadForUi =
    skinnedBodyPathActive && skinnedBodyLoadStatus === "idle"
      ? "pending"
      : skinnedBodyLoadStatus;

  const runtimeSummary = useMemo(() => {
    const base = runtimeAssetSummary(resolvedRuntime);
    const loadTag = skinnedBodyPathActive ? ` · body load: ${bodyLoadForUi}` : "";
    if (FORCE_PROCEDURAL_BODY || useProceduralBody) {
      return `${base} · body=procedural(forced)${loadTag}`;
    }
    if (runtimeBodyBundledModule != null) {
      if (skinnedBodyLoadStatus === "failed") {
        return `${base} · body=procedural(fallback)${loadTag} · skinned mesh unavailable`;
      }
      return `${base} · body=skinned(bundled, fallback-material)${loadTag}`;
    }
    if (resolvedRuntime.bodyGltfUrl != null) {
      const envB = getAvatarRuntimeAssetUrls().bodyGltfUrl;
      const src =
        runtimeAssets?.bodyGltfUrl != null
          ? "external(runtimeAssets)"
          : resolvedRuntime.bodyGltfUrl === envB
            ? "external(env)"
            : "external(url)";
      return `${base} · body=skinned(${src}, textured)${loadTag}`;
    }
    return `${base} · body=procedural(default)${loadTag}`;
  }, [
    resolvedRuntime,
    runtimeBodyBundledModule,
    useProceduralBody,
    skinnedBodyLoadStatus,
    bodyLoadForUi,
    skinnedBodyPathActive,
    runtimeAssets?.bodyGltfUrl,
  ]);

  useEffect(() => {
    if (!__DEV__) return;
    const parts: string[] = [];
    if (FORCE_PROCEDURAL_BODY) parts.push("EXPO_PUBLIC_AVATAR_USE_PROCEDURAL_BODY=1");
    if (useProceduralBody) parts.push("useProceduralBody");
    if (runtimeBodyBundledModule != null) {
      parts.push("bundled=strip-embedded-textures+parse+fallback-material");
    }
    if (resolvedRuntime.bodyGltfUrl) {
      const u = resolvedRuntime.bodyGltfUrl;
      parts.push(u.length > 88 ? `bodyUrl=${u.slice(0, 88)}…` : `bodyUrl=${u}`);
    } else if (!runtimeBodyBundledModule) {
      parts.push("bodyUrl=(none)");
    }
    parts.push(`loadStatus=${bodyLoadForUi}`);
    console.log("[AvatarViewportLive] body source:", parts.join(" | "));
  }, [
    resolvedRuntime.bodyGltfUrl,
    runtimeBodyBundledModule,
    useProceduralBody,
    skinnedBodyLoadStatus,
    bodyLoadForUi,
  ]);

  const runtimeClipReport = useMemo(
    () =>
      analyzeRuntimeClipping({
        garmentFit,
        pose,
        hasRuntimeBodyGltf:
          !!resolvedRuntime.bodyGltfUrl || runtimeBodyBundledModule != null,
        hasRuntimeTopGltf: !!resolvedRuntime.topGltfUrl,
        hasRuntimeBottomGltf: !!resolvedRuntime.bottomGltfUrl,
        bodyShape,
      }),
    [
      garmentFit,
      pose,
      resolvedRuntime.bodyGltfUrl,
      resolvedRuntime.topGltfUrl,
      resolvedRuntime.bottomGltfUrl,
      runtimeBodyBundledModule,
      bodyShape,
    ],
  );

  const clipEmissiveTop = useMemo(() => {
    if (!clipOverlayEnabled) return null;
    return clipSeverityToEmissive(
      worstGarmentClipSeverity(
        runtimeClipReport.torso.severity,
        runtimeClipReport.sleeves.severity,
      ),
    );
  }, [
    clipOverlayEnabled,
    runtimeClipReport.torso.severity,
    runtimeClipReport.sleeves.severity,
  ]);

  const clipEmissiveBottom = useMemo(() => {
    if (!clipOverlayEnabled) return null;
    return clipSeverityToEmissive(
      worstGarmentClipSeverity(
        runtimeClipReport.waist.severity,
        runtimeClipReport.hem.severity,
      ),
    );
  }, [
    clipOverlayEnabled,
    runtimeClipReport.waist.severity,
    runtimeClipReport.hem.severity,
  ]);

  const clipEmissiveSleeve = useMemo(() => {
    if (!clipOverlayEnabled) return null;
    return clipSeverityToEmissive(runtimeClipReport.sleeves.severity);
  }, [clipOverlayEnabled, runtimeClipReport.sleeves.severity]);

  const deformDebugLines = useMemo(() => {
    if (!SHOW_DEFORM_DEBUG) return null as string[] | null;
    const lines: string[] = ["deform (live): vertex masks, rest-cached"];
    if (resolvedRuntime.topGltfUrl) {
      lines.push(`top GLB: ${deformationSummary("top")}`);
    } else {
      lines.push(`top proxy: ${deformationSummary("top")}`);
    }
    if (resolvedRuntime.bottomGltfUrl) {
      lines.push(`bottom GLB: ${deformationSummary("bottom")}`);
    } else {
      lines.push(`bottom proxy: ${deformationSummary("bottom")}`);
    }
    lines.push(`sleeves: ${deformationSummary("sleeve")} (capsules)`);
    lines.push(
      `garment rig: CPU LBS-style pose (bind=relaxed) + regional fit · rig dbg ${SHOW_GARMENT_RIG_DEBUG ? "on" : "off"}`,
    );
    return lines;
  }, [resolvedRuntime.bottomGltfUrl, resolvedRuntime.topGltfUrl]);

  const isWorkbench = layout === "workbench";
  const [camUiTick, setCamUiTick] = useState(0);
  useEffect(() => {
    if (!__DEV__ || isWorkbench) return;
    const id = setInterval(() => setCamUiTick((n) => n + 1), 220);
    return () => clearInterval(id);
  }, [isWorkbench]);
  const smooth = smoothRef.current;
  void camUiTick;

  return (
    <GestureHandlerRootView style={[styles.wrap, isWorkbench && styles.wrapWorkbench]}>
      {isWorkbench ? (
        <Text style={styles.hintCompact} numberOfLines={1}>
          Drag orbit · pinch zoom
        </Text>
      ) : (
        <Text style={styles.hint}>
          Drag to orbit · pinch to zoom. Damped target-orbit camera; zoom ± buttons below.
        </Text>
      )}
      <View style={[styles.frame, { height }]}>
        <Canvas
          pointerEvents="none"
          frameloop="always"
          camera={{ position: [0, 1.8, 4.2], fov: 42, near: 0.1, far: 80 }}
          gl={{ preserveDrawingBuffer: true }}
          style={StyleSheet.absoluteFill}
        >
          <Suspense fallback={null}>
            <CameraRig
              desiredRef={desiredRef}
              smoothRef={smoothRef}
              navRef={navRef}
              targetBase={TARGET}
              targetPanRef={targetPanRef}
            />
            <AvatarProceduralScene
              pose={pose}
              preset={preset}
              garmentFit={garmentFit}
              liveShading={liveShading}
              bodyShape={bodyShape}
              runtimeBodyGltfUrl={resolvedRuntime.bodyGltfUrl}
              runtimeBodyBundledModule={runtimeBodyBundledModule}
              runtimeTopGltfUrl={resolvedRuntime.topGltfUrl}
              runtimeBottomGltfUrl={resolvedRuntime.bottomGltfUrl}
              showRigDebug={SHOW_RIG_DEBUG}
              showGarmentRigDebug={SHOW_GARMENT_RIG_DEBUG}
              clipEmissiveTop={clipEmissiveTop}
              clipEmissiveBottom={clipEmissiveBottom}
              clipEmissiveSleeve={clipEmissiveSleeve}
              bodyOnlyGarments={bodyOnlyGarments}
              garmentOnlyViewport={garmentOnlyViewport}
              onRuntimeBodyLoadError={onRuntimeBodyLoadError}
              onRuntimeBodyLoaded={onRuntimeBodyLoaded}
              onSkinnedRigPoseReport={onSkinnedRigPoseReport}
              onGarmentAnchorsDebug={onGarmentAnchorsDebug}
              garmentAttachmentDebug={garmentAttachmentDebug}
              onGarmentAttachmentSnapshot={onGarmentAttachmentSnapshot}
            />
          </Suspense>
        </Canvas>
        <GestureDetector gesture={orbitGesture}>
          <View
            style={[StyleSheet.absoluteFill, styles.touchOverlay]}
            accessibilityLabel="Orbit and pinch the avatar preview"
            collapsable={false}
          />
        </GestureDetector>
      </View>

      {__DEV__ && !isWorkbench ? (
        <View style={styles.debugBox}>
          <Text style={styles.debugLine} selectable>
            cam r={smooth.radius.toFixed(2)} θ={smooth.theta.toFixed(2)} φ={smooth.phi.toFixed(2)}
          </Text>
          <Text style={styles.debugLine} selectable>
            pose={pose} preset={preset} shade={LIVE_VIEWPORT_SHADING_LABELS[liveShading]}
          </Text>
          <Text style={styles.debugLine} selectable>
            fit≠default: {fitIsNonDefault ? "yes" : "no"}
          </Text>
          <Text style={styles.debugLine} selectable>
            runtime: {runtimeSummary}
          </Text>
          <Text style={styles.debugLine} selectable>
            body pose:{" "}
            {skinnedPoseReport
              ? skinnedPoseReport.bodyPoseApplied
                ? "applied (skinned bones)"
                : "not applied (root euler / no skeleton)"
              : "n/a (no skinned body)"}{" "}
            · pose={pose} · bone map:{" "}
            {skinnedPoseReport?.boneMapStatus ?? "—"} (
            {skinnedPoseReport?.criticalMapped ?? "?"}/{skinnedPoseReport?.criticalTotal ?? "?"})
          </Text>
          {pose === "walk" ? (
            <Text style={styles.debugSub} selectable>
              walk stress: use clip overlay + proxy severities above for shoulder / torso / hem drift
            </Text>
          ) : null}
          {attachmentSnapshot ? (
            <Text style={styles.debugLine} selectable>
              garment attach: {attachmentSnapshot.source} · top Y {attachmentSnapshot.topAnchor[1].toFixed(3)} ·
              sleeves L/R Y {attachmentSnapshot.leftSleevePivot[1].toFixed(2)} /{" "}
              {attachmentSnapshot.rightSleevePivot[1].toFixed(2)}
            </Text>
          ) : null}
          {deformDebugLines
            ? deformDebugLines.map((line, i) => (
                <Text key={`def:${i}:${line}`} style={styles.debugLine} selectable>
                  {line}
                </Text>
              ))
            : null}
          {compareActive ? (
            <Text style={styles.debugLineCompare} selectable>
              compare: baseline fit (before)
            </Text>
          ) : null}
          {__DEV__ ? (
            <Text style={styles.debugLine} selectable>
              clip overlay: {clipOverlayEnabled ? "on" : "off"} · torso{" "}
              {runtimeClipReport.torso.severity} · sleeves {runtimeClipReport.sleeves.severity} · waist{" "}
              {runtimeClipReport.waist.severity} · hem {runtimeClipReport.hem.severity}
            </Text>
          ) : null}
          <Text style={styles.debugSub} selectable>
            pan/pinch: RNGH worklet → runOnJS updates desired orbit refs · damped in GL frame
          </Text>
        </View>
      ) : null}

      {!isWorkbench ? (
        <View style={styles.camRow}>
          <AppButton label="Reset cam" variant="secondary" onPress={resetCamera} />
          <AppButton label="Zoom +" variant="secondary" onPress={zoomIn} />
          <AppButton label="Zoom −" variant="secondary" onPress={zoomOut} />
        </View>
      ) : null}
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: theme.spacing.xs },
  wrapWorkbench: { gap: 2 },
  hintCompact: {
    fontSize: 10,
    color: theme.colors.textMuted,
    fontFamily: "monospace",
  },
  hint: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    lineHeight: 18,
  },
  frame: {
    borderRadius: theme.radii.md,
    overflow: "hidden",
    backgroundColor: theme.colors.border,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  touchOverlay: {
    zIndex: 1,
    backgroundColor: "transparent",
  },
  debugBox: {
    padding: theme.spacing.xs,
    borderRadius: theme.radii.sm,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
    gap: 4,
  },
  debugLine: {
    fontSize: 11,
    fontFamily: "monospace",
    color: theme.colors.text,
  },
  debugLineCompare: {
    fontSize: 11,
    fontFamily: "monospace",
    color: theme.colors.primary,
    fontWeight: "600",
  },
  debugSub: {
    fontSize: 10,
    color: theme.colors.textMuted,
    fontFamily: "monospace",
  },
  camRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: theme.spacing.sm,
  },
});
