import { Canvas } from "@react-three/fiber/native";
import { Component, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { Platform, StyleSheet, Text, View } from "react-native";
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

import { DEFAULT_STYLISED_AVATAR } from "./avatar-assets";
import {
  AvatarProceduralScene,
  CameraRig,
  type OrbitSpherical,
} from "./avatar-procedural-scene";
import {
  PROCEDURAL_AVATAR_MODEL_ID,
  PROCEDURAL_GARMENT_FOLLOW_MODE,
  PROCEDURAL_HUMANOID_BODY_PART_COUNT,
  PROCEDURAL_HUMANOID_GARMENT_PART_COUNT,
  PROCEDURAL_HUMANOID_JOINT_COUNT,
  PROCEDURAL_PROPORTIONS_VERSION,
} from "./procedural-humanoid-v2";
import {
  mergeAvatarViewportNav,
  type AvatarViewportNavSettings,
} from "./avatar-viewport-nav-settings";
import { deformationSummary } from "./garment-deformation";
import type {
  AvatarRenderAudit,
  GarmentAttachmentSnapshot,
  LiveViewportBodySourceDebug,
  LiveViewportPoseFitDebug,
  LiveViewportSceneDiagnostics,
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
import {
  avatarSourceLoadStateLabel,
  resolveAvatarSource,
  type AvatarSourceLoadState,
  type AvatarSourcePreference,
  type AvatarSourceType,
} from "./avatar-source-manager";

export type AvatarViewportDevSceneInspect = {
  enabled: boolean;
  showMarkers: boolean;
  debugBrightBody: boolean;
  /** Increment (e.g. button) to snap camera to measured body bounds. */
  manualFrameBoundsNonce: number;
};

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
  /** Source manager preference. `auto` tries realistic GLB, then stylised GLB, then fallback. */
  avatarSourcePreference?: AvatarSourcePreference;
  /** Legacy escape hatch: forces procedural fallback when true. Prefer `avatarSourcePreference`. */
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
  /** Dev workbench: scene-space markers, bounds framing, bright-body visibility proof. */
  devSceneInspect?: AvatarViewportDevSceneInspect;
  /** Dev: skeleton / joint overlay for the procedural mannequin. */
  showSkeletonOverlay?: boolean;
  /** Dev: garment anchor / fit overlay. */
  showFitDebugOverlay?: boolean;
  /** Baseline / camera-reset generation from preview (diagnostics). */
  viewportBaselineNonce?: number;
  /** Current control tab label for diagnostics. */
  activeTab?: string;
  /** True when the clean presentation preset is active. */
  cleanMode?: boolean;
  /** Dev: show the in-viewport diagnostics overlay even outside the Debug tab. */
  debugOverlay?: boolean;
};

const DEFAULT_ORBIT: OrbitSpherical = { theta: 0.64, phi: 1.08, radius: 3.78 };
const TARGET: [number, number, number] = [0, 1.06, 0];

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

/** Set to `1` to force the procedural mannequin; dev startup already defaults procedural. */
const FORCE_PROCEDURAL_BODY =
  typeof process.env.EXPO_PUBLIC_AVATAR_USE_PROCEDURAL_BODY === "string" &&
  process.env.EXPO_PUBLIC_AVATAR_USE_PROCEDURAL_BODY === "1";

const LOG_THROTTLE_MS = 280;

function AvatarSceneCrashFallback() {
  return (
    <group name="avatar_scene_crash_fallback">
      <ambientLight intensity={0.55} />
      <directionalLight position={[3, 5, 4]} intensity={0.8} />
      <mesh position={[0, 1.18, 0]}>
        <capsuleGeometry args={[0.18, 0.62, 10, 18]} />
        <meshStandardMaterial color="#d8b28c" roughness={0.86} />
      </mesh>
      <mesh position={[0, 1.66, 0]}>
        <sphereGeometry args={[0.12, 16, 16]} />
        <meshStandardMaterial color="#d8b28c" roughness={0.82} />
      </mesh>
      <mesh position={[0, 0.58, 0]}>
        <capsuleGeometry args={[0.16, 0.78, 10, 18]} />
        <meshStandardMaterial color="#7f8fa6" roughness={0.84} />
      </mesh>
    </group>
  );
}

class AvatarSceneErrorBoundary extends Component<
  { children: ReactNode; onError?: (message: string) => void },
  { crashed: boolean }
> {
  state = { crashed: false };

  static getDerivedStateFromError() {
    return { crashed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    const detail = `${error.name || "Error"}: ${error.message || "scene render failed"}`;
    this.props.onError?.(info.componentStack ? `${detail}` : detail);
  }

  render() {
    if (this.state.crashed) return <AvatarSceneCrashFallback />;
    return this.props.children;
  }
}

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
  avatarSourcePreference = "auto",
  useProceduralBody = false,
  bodyOnlyGarments = false,
  garmentOnlyViewport = false,
  onLiveViewportPoseFitDebug,
  garmentAttachmentDebug = false,
  navSettings,
  layout = "standalone",
  cameraResetNonce = 0,
  devSceneInspect,
  showSkeletonOverlay = false,
  showFitDebugOverlay = false,
  viewportBaselineNonce = 0,
  activeTab = "view",
  cleanMode = true,
  debugOverlay = false,
}: AvatarViewportLiveProps) {
  const navMerged = useMemo(() => mergeAvatarViewportNav(navSettings ?? undefined), [navSettings]);
  const navRef = useRef(navMerged);
  navRef.current = navMerged;

  const desiredRef = useRef<OrbitSpherical>({ ...DEFAULT_ORBIT });
  const smoothRef = useRef<OrbitSpherical>({ ...DEFAULT_ORBIT });
  const targetPanRef = useRef({ x: 0, z: 0 });
  const targetBaseRef = useRef<[number, number, number]>([...TARGET]);
  /** Workbench: true while pan/pinch gesture is active — CameraRig snaps smooth→desired for responsiveness. */
  const orbitGestureActiveRef = useRef(false);

  const panBaseRef = useRef<OrbitSpherical>({ ...DEFAULT_ORBIT });
  const panBasePanRef = useRef({ x: 0, z: 0 });
  const pinchRadius0Ref = useRef(DEFAULT_ORBIT.radius);
  const mountedRef = useRef(true);
  const lastGestureLog = useRef(0);
  const lastResetNonce = useRef(cameraResetNonce);
  const [safeDefaultActive, setSafeDefaultActive] = useState(false);
  const [cameraTargetValid, setCameraTargetValid] = useState(true);
  const [zoomInputMode, setZoomInputMode] = useState<
    "idle" | "native_pinch" | "wheel_fallback" | "emulator_fallback"
  >("idle");
  const visibilityGuardedRef = useRef(false);
  const [sceneReady, setSceneReady] = useState(false);
  const [visibleMeshCount, setVisibleMeshCount] = useState(0);
  const [bodyGroupVisible, setBodyGroupVisible] = useState(false);
  const [garmentGroupVisible, setGarmentGroupVisible] = useState(false);
  const [startupReason, setStartupReason] = useState("initializing");
  const [renderAudit, setRenderAudit] = useState<AvatarRenderAudit | null>(null);
  const renderAuditRef = useRef<AvatarRenderAudit | null>(null);
  const [renderSafe, setRenderSafe] = useState(true);
  const [lastSceneError, setLastSceneError] = useState<string | null>(null);

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
    targetBaseRef.current = [...TARGET];
    setSafeDefaultActive(false);
    setCameraTargetValid(true);
  }, [cameraResetNonce]);

  useEffect(() => {
    const nav = navRef.current;
    const prev = desiredRef.current;
    const next = sanitizeOrbit(prev, prev, nav);
    const corrected =
      Math.abs(next.phi - prev.phi) > 1e-4 ||
      Math.abs(next.radius - prev.radius) > 1e-4;
    const targetOk = Number.isFinite(nav.targetYOffset) && Math.abs(nav.targetYOffset) <= 0.6;
    setCameraTargetValid(targetOk);
    if (corrected || !targetOk) {
      desiredRef.current = next;
      smoothRef.current = sanitizeOrbit(smoothRef.current, next, nav);
      if (!targetOk) {
        targetBaseRef.current = [...TARGET];
      }
      if (__DEV__) {
        console.log("[AvatarViewport] nav clamp / target check", {
          corrected,
          targetOk,
          resetLookTarget: !targetOk,
        });
      }
      setSafeDefaultActive(!targetOk);
    }
  }, [navMerged]);

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
    orbitGestureActiveRef.current = true;
    if (__DEV__) {
      console.log("[AvatarViewport] pan begin", { base: { ...panBaseRef.current } });
    }
  }, []);

  const panUpdateJS = useCallback((translationX: number, translationY: number) => {
    if (!Number.isFinite(translationX) || !Number.isFinite(translationY)) return;
    if (Math.abs(translationX) > 520 || Math.abs(translationY) > 520) return;
    const nav = navRef.current;
    const b = panBaseRef.current;
    const clampedX = Math.max(-340, Math.min(340, translationX));
    const clampedY = Math.max(-300, Math.min(300, translationY));
    const ix = nav.invertOrbitX ? -1 : 1;
    const iy = nav.invertOrbitY ? -1 : 1;
    const dYaw =
      -clampedX *
      nav.orbitYawRadPerPx *
      nav.orbitSensitivity *
      nav.yawSpeedMultiplier *
      ix;
    const dPitch =
      clampedY * nav.orbitPitchRadPerPx * nav.orbitSensitivity * iy;
    applyDesired(() => ({
      theta: b.theta + dYaw,
      phi: b.phi + dPitch,
      radius: b.radius,
    }));
    if (layout !== "workbench") {
      logThrottle("[AvatarViewport] pan update");
    }
  }, [applyDesired, logThrottle, layout]);

  const panEndJS = useCallback(() => {
    orbitGestureActiveRef.current = false;
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
    orbitGestureActiveRef.current = true;
    setZoomInputMode(Platform.OS === "android" ? "emulator_fallback" : "native_pinch");
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
    const exp = 1.08 * nav.zoomSensitivity;
    const raw = r0 * Math.pow(1 / scale, exp);
    const nextRadius = Math.min(nav.maxRadius, Math.max(nav.minRadius, raw));
    applyDesired((c) => ({
      ...c,
      radius: nextRadius,
    }));
    smoothRef.current.radius += (nextRadius - smoothRef.current.radius) * 0.34;
    if (layout !== "workbench") {
      logThrottle("[AvatarViewport] pinch update");
    }
  }, [applyDesired, logThrottle, layout]);

  const wheelZoomJS = useCallback((deltaY: number) => {
    if (!Number.isFinite(deltaY) || deltaY === 0) return;
    setZoomInputMode("wheel_fallback");
    const nav = navRef.current;
    const clamped = Math.max(-180, Math.min(180, deltaY));
    const factor = Math.exp(clamped * 0.0024 * nav.zoomSensitivity);
    applyDesired((c) => ({
      ...c,
      radius: Math.min(nav.maxRadius, Math.max(nav.minRadius, c.radius * factor)),
    }));
    smoothRef.current.radius += (desiredRef.current.radius - smoothRef.current.radius) * 0.42;
    if (layout !== "workbench") {
      logThrottle("[AvatarViewport] wheel zoom");
    }
  }, [applyDesired, logThrottle, layout]);

  const pinchEndJS = useCallback(() => {
    orbitGestureActiveRef.current = false;
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

  useEffect(() => {
    const bodyVisible = !garmentOnlyViewport;
    const garmentsVisible = !bodyOnlyGarments;
    if (bodyVisible || garmentsVisible) {
      visibilityGuardedRef.current = false;
      return;
    }
    if (visibilityGuardedRef.current) return;
    visibilityGuardedRef.current = true;
    setSafeDefaultActive(true);
    if (__DEV__) {
      console.log("[AvatarViewport] visibility reset -> safe default framing");
    }
  }, [bodyOnlyGarments, garmentOnlyViewport]);

  const resetCamera = () => {
    const o = { ...DEFAULT_ORBIT };
    desiredRef.current = sanitizeOrbit(o, o, navRef.current);
    smoothRef.current = { ...desiredRef.current };
    targetPanRef.current = { x: 0, z: 0 };
    targetBaseRef.current = [...TARGET];
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
  const [failedAvatarSourceType, setFailedAvatarSourceType] =
    useState<AvatarSourceType | null>(null);
  const [bodyLoadGeneration, setBodyLoadGeneration] = useState(0);
  const bodyReadyEmittedRef = useRef(false);
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

  const requestedAvatarSource: AvatarSourcePreference = useProceduralBody
    ? "procedural_fallback"
    : avatarSourcePreference;
  const avatarSourceLoadState: AvatarSourceLoadState =
    skinnedBodyLoadStatus === "pending" ? "loading" : skinnedBodyLoadStatus;

  useEffect(() => {
    skinnedBodyLoadErrLogged.current = null;
    setFailedAvatarSourceType(null);
  }, [requestedAvatarSource, runtimeAssets?.bodyGltfUrl, envRuntimeUrls.bodyGltfUrl]);

  const resolvedAvatarSource = useMemo(
    () =>
      resolveAvatarSource({
        preference: requestedAvatarSource,
        runtimeAssets,
        envRuntimeUrls,
        stylisedBundledAssetModule: DEFAULT_STYLISED_AVATAR.bundledAssetModule,
        forceProcedural: FORCE_PROCEDURAL_BODY,
        failedSourceType: failedAvatarSourceType,
        loadState: avatarSourceLoadState,
        errorReason: skinnedBodyLoadErrLogged.current,
      }),
    [
      requestedAvatarSource,
      runtimeAssets,
      envRuntimeUrls,
      failedAvatarSourceType,
      avatarSourceLoadState,
    ],
  );

  const runtimeBodyBundledModule =
    resolvedAvatarSource.sourceType === "stylised_glb"
      ? resolvedAvatarSource.bundledAssetModule
      : null;

  const resolvedRuntime = useMemo(() => {
    const env = getAvatarRuntimeAssetUrls();
    return {
      bodyGltfUrl:
        resolvedAvatarSource.sourceType === "realistic_glb"
          ? resolvedAvatarSource.resolvedUri
          : null,
      topGltfUrl: runtimeAssets?.topGltfUrl ?? env.topGltfUrl,
      bottomGltfUrl: runtimeAssets?.bottomGltfUrl ?? env.bottomGltfUrl,
    } satisfies AvatarRuntimeAssetUrls;
  }, [runtimeAssets, resolvedAvatarSource.sourceType, resolvedAvatarSource.resolvedUri]);

  const bodyAssetKey = useMemo(
    () =>
      `${resolvedAvatarSource.sourceType}|${runtimeBodyBundledModule ?? ""}|${
        resolvedRuntime.bodyGltfUrl ?? ""
      }|${resolvedAvatarSource.fallbackReason}`,
    [
      resolvedAvatarSource.sourceType,
      resolvedAvatarSource.fallbackReason,
      runtimeBodyBundledModule,
      resolvedRuntime.bodyGltfUrl,
    ],
  );

  useEffect(() => {
    bodyReadyEmittedRef.current = false;
    setBodyLoadGeneration(0);
    setSceneReady(false);
    setVisibleMeshCount(0);
    setBodyGroupVisible(false);
    setGarmentGroupVisible(false);
    setStartupReason("body_asset_changed");
    renderAuditRef.current = null;
    setRenderAudit(null);
    setRenderSafe(true);
    setLastSceneError(null);
  }, [bodyAssetKey]);

  const [sceneDiagnostics, setSceneDiagnostics] = useState<LiveViewportSceneDiagnostics | null>(
    null,
  );
  const lastSceneDiagJson = useRef("");
  const handleSceneDiagnostics = useCallback((d: LiveViewportSceneDiagnostics) => {
    const j = JSON.stringify(d);
    if (j === lastSceneDiagJson.current) return;
    lastSceneDiagJson.current = j;
    setSceneDiagnostics(d);
  }, []);

  const sceneSpaceDebug = useMemo(() => {
    if (!__DEV__ || layout !== "workbench") return null;
    return {
      enabled: true,
      showMarkers: !!devSceneInspect?.enabled && !!devSceneInspect.showMarkers,
      debugBrightBody: !!devSceneInspect?.enabled && !!devSceneInspect.debugBrightBody,
      bodyLoadGeneration,
      manualFrameBoundsNonce: devSceneInspect?.manualFrameBoundsNonce ?? 0,
      onSceneDiagnostics: handleSceneDiagnostics,
      orbit: {
        desiredRef,
        smoothRef,
        navRef,
        targetBaseRef,
        targetPanRef,
      },
    };
  }, [
    devSceneInspect?.showMarkers,
    devSceneInspect?.debugBrightBody,
    devSceneInspect?.manualFrameBoundsNonce,
    layout,
    bodyLoadGeneration,
    handleSceneDiagnostics,
  ]);

  const onRuntimeBodyLoaded = useCallback(() => {
    setSkinnedBodyLoadStatus("loaded");
    if (!bodyReadyEmittedRef.current) {
      bodyReadyEmittedRef.current = true;
      setBodyLoadGeneration((g) => g + 1);
    }
    setStartupReason("body_loaded");
  }, []);

  const onSceneRenderError = useCallback((message: string) => {
    setRenderSafe(false);
    setLastSceneError(message);
    setSceneReady(true);
    setVisibleMeshCount((count) => Math.max(count, 3));
    setBodyGroupVisible(true);
    setGarmentGroupVisible(false);
    setStartupReason("scene_error_fallback");
    if (__DEV__) {
      console.error("[AvatarViewport] scene render fallback", message);
    }
  }, []);

  const onStartupVisibilityReport = useCallback(
    (report: {
      sceneReady: boolean;
      visibleMeshCount: number;
      bodyGroupVisible: boolean;
      garmentGroupVisible: boolean;
      startupReason: string;
      renderAudit?: AvatarRenderAudit | null;
    }) => {
      setSceneReady(report.sceneReady);
      setVisibleMeshCount(report.visibleMeshCount);
      setBodyGroupVisible(report.bodyGroupVisible);
      setGarmentGroupVisible(report.garmentGroupVisible);
      setStartupReason(report.startupReason);
      renderAuditRef.current = report.renderAudit ?? null;
      setRenderAudit(report.renderAudit ?? null);
    },
    [],
  );

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

  const skinnedBodyPathActive =
    runtimeBodyBundledModule != null || resolvedRuntime.bodyGltfUrl != null;
  const bodyLoadForUi =
    skinnedBodyPathActive && skinnedBodyLoadStatus === "idle"
      ? "pending"
      : skinnedBodyLoadStatus;

  useEffect(() => {
    if (resolvedAvatarSource.sourceType !== "stylised_glb" || bodyLoadForUi !== "loaded") {
      return;
    }
    const id = setTimeout(() => {
      if (!mountedRef.current || resolvedAvatarSource.sourceType !== "stylised_glb") return;
      const audit = renderAuditRef.current;
      if (audit && audit.gltfVisibleMeshCount > 0) return;
      const reason = "stylised_glb_loaded_but_no_visible_meshes";
      skinnedBodyLoadErrLogged.current = reason;
      setFailedAvatarSourceType("stylised_glb");
      setSkinnedBodyLoadStatus("failed");
      setStartupReason(reason);
      if (__DEV__) {
        console.warn("[AvatarViewportLive] falling back to procedural:", {
          reason,
          audit,
        });
      }
    }, 1000);
    return () => clearTimeout(id);
  }, [resolvedAvatarSource.sourceType, bodyLoadForUi, bodyAssetKey]);

  const bodySourceDebug = useMemo((): LiveViewportBodySourceDebug | null => {
    if (!__DEV__) return null;
    let reason: LiveViewportBodySourceDebug["reason"] = "avatar_source_manager";
    let active: LiveViewportBodySourceDebug["active"];
    if (FORCE_PROCEDURAL_BODY) {
      active = "procedural_env_forced";
      reason = "env_force_procedural";
    } else if (
      resolvedAvatarSource.usingProceduralFallback &&
      resolvedAvatarSource.fallbackReason === "explicit_procedural"
    ) {
      active = "procedural_user";
      reason = "user_procedural_toggle";
    } else if (
      resolvedAvatarSource.usingProceduralFallback &&
      resolvedAvatarSource.fallbackReason === "glb_load_failed"
    ) {
      active = "procedural_fallback_error";
      reason = "skinned_load_failed_fallback";
    } else if (resolvedAvatarSource.sourceType === "realistic_glb") {
      active = "realistic_glb";
      reason = "runtime_url_override";
    } else if (resolvedAvatarSource.sourceType === "stylised_glb") {
      active = "stylised_glb";
    } else {
      active = "procedural_scene_default";
    }

    const sourceReason: LiveViewportBodySourceDebug["sourceReason"] =
      reason === "skinned_load_failed_fallback" ? "hard_fallback" : "startup";

    return {
      active,
      userIntent:
        requestedAvatarSource === "procedural_fallback"
          ? "procedural"
          : requestedAvatarSource,
      sourceReason,
      loadStatus: bodyLoadForUi,
      reason,
      debugLabel: resolvedAvatarSource.debugLabel,
      fallbackReason: resolvedAvatarSource.fallbackReason,
      errorReason: resolvedAvatarSource.errorReason,
    };
  }, [
    requestedAvatarSource,
    resolvedAvatarSource,
    bodyLoadForUi,
  ]);

  useEffect(() => {
    const noSkinnedRuntime =
      FORCE_PROCEDURAL_BODY ||
      resolvedAvatarSource.usingProceduralFallback ||
      (runtimeBodyBundledModule == null && !resolvedRuntime.bodyGltfUrl);
    if (noSkinnedRuntime || garmentOnlyViewport) {
      lastSkinnedReportJson.current = "";
      lastAttachmentJson.current = "";
      setSkinnedPoseReport(null);
      setAttachmentSnapshot(null);
    }
  }, [
    resolvedAvatarSource.usingProceduralFallback,
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
    const bodyVisible = !garmentOnlyViewport;
    const garmentsVisible = !bodyOnlyGarments;
    const bundledBodyMounted =
      bodyVisible &&
      !resolvedAvatarSource.usingProceduralFallback &&
      !FORCE_PROCEDURAL_BODY &&
      (runtimeBodyBundledModule != null || resolvedRuntime.bodyGltfUrl != null) &&
      bodyLoadForUi === "loaded";
    const bundledBodyVisible =
      bundledBodyMounted &&
      (bodySourceDebug?.active === "stylised_glb" ||
        bodySourceDebug?.active === "realistic_glb" ||
        bodySourceDebug?.active === "bundled_skinned" ||
        bodySourceDebug?.active === "external_skinned_url") &&
      (renderAudit?.gltfVisibleMeshCount ?? 0) > 0;
    const visibleBranch: "bundled" | "procedural" | "none" =
      !bodyVisible
        ? "none"
        : bundledBodyVisible
          ? "bundled"
          : bodySourceDebug?.active === "procedural_user" ||
              bodySourceDebug?.active === "procedural_env_forced" ||
              bodySourceDebug?.active === "procedural_fallback_error" ||
              bodySourceDebug?.active === "procedural_scene_default"
            ? "procedural"
            : "procedural";
    const poseTargetBranch = visibleBranch;
    const startupVisibleBody = visibleBranch !== "none";
    const combinedVisible = bodyVisible && garmentsVisible;
    const visiblePartsCount =
      (bodyVisible ? PROCEDURAL_HUMANOID_BODY_PART_COUNT : 0) +
      (garmentsVisible ? PROCEDURAL_HUMANOID_GARMENT_PART_COUNT : 0);
    const anchorsCount = PROCEDURAL_HUMANOID_JOINT_COUNT;
    const visualAvatarSource: "GLB" | "proceduralFallback" =
      visibleBranch === "bundled" ? "GLB" : "proceduralFallback";
    const rigDetected =
      !!skinnedPoseReport &&
      (skinnedPoseReport.bodyPoseApplied || skinnedPoseReport.criticalMapped > 0);
    const poseDriver: "skinnedBones" | "proceduralFallback" =
      visualAvatarSource === "GLB" && rigDetected ? "skinnedBones" : "proceduralFallback";
    const exactBaselineOk =
      sceneReady &&
      combinedVisible &&
      visibleMeshCount > 0 &&
      bodyGroupVisible &&
      garmentGroupVisible &&
      (!resolvedAvatarSource.usingProceduralFallback &&
      !FORCE_PROCEDURAL_BODY
        ? bundledBodyVisible || visibleBranch === "procedural"
        : visibleBranch === "procedural") &&
      !showSkeletonOverlay &&
      !showFitDebugOverlay &&
      !garmentAttachmentDebug &&
      !clipOverlayEnabled &&
      !devSceneInspect?.enabled &&
      liveShading === "normal" &&
      pose === "relaxed" &&
      preset === "default";
    const startupWarning = exactBaselineOk
      ? null
      : "startup deviated from deterministic clean preview";
    const mode =
      bodyVisible && garmentsVisible
        ? "combined"
        : bodyVisible
          ? "body_only"
          : garmentsVisible
            ? "garment_only"
            : "invalid";
    const cameraTarget: [number, number, number] = [
      targetBaseRef.current[0] + targetPanRef.current.x,
      targetBaseRef.current[1] + navRef.current.targetYOffset,
      targetBaseRef.current[2] + targetPanRef.current.z,
    ];
    const orbit = smoothRef.current;
    const cameraPosition: [number, number, number] = [
      cameraTarget[0] + orbit.radius * Math.sin(orbit.phi) * Math.cos(orbit.theta),
      cameraTarget[1] + orbit.radius * Math.cos(orbit.phi),
      cameraTarget[2] + orbit.radius * Math.sin(orbit.phi) * Math.sin(orbit.theta),
    ];
    const renderAuditWithCamera: AvatarRenderAudit | null = renderAudit
      ? {
          ...renderAudit,
          cameraPosition,
          cameraTarget,
          cameraRadius: orbit.radius,
        }
      : null;
    const payload: LiveViewportPoseFitDebug = {
      pose,
      preset,
      avatar: {
        activeAvatarModel: PROCEDURAL_AVATAR_MODEL_ID,
        visualAvatarSource,
        rigDetected,
        garmentFollowMode: PROCEDURAL_GARMENT_FOLLOW_MODE,
        garmentMode: mode,
        jointCount: PROCEDURAL_HUMANOID_JOINT_COUNT,
        anchorsCount,
        visiblePartsCount,
        garmentAnchors: garmentAnchorsDbg ? "ok" : "missing",
        currentQualityPreset: cleanMode ? "Clean mannequin" : activeTab,
        poseDriver,
        startupVisible: startupVisibleBody,
        proportionsVersion: PROCEDURAL_PROPORTIONS_VERSION,
        loadStatus: bodyLoadForUi,
        avatarSource: resolvedAvatarSource.sourceType,
        fallbackReason: resolvedAvatarSource.fallbackReason,
        meshCount: skinnedPoseReport?.meshCount,
        materialCount: skinnedPoseReport?.materialCount,
        boneCount: skinnedPoseReport?.boneCount,
        boundsHeight: skinnedPoseReport?.boundsHeight,
      },
      garmentPoseMatchesBody: true,
      skinned: skinnedPoseReport,
      anchors: garmentAnchorsDbg,
      attachment: attachmentSnapshot,
      bodySource: layout === "workbench" ? bodySourceDebug : null,
      startup:
        layout === "workbench"
          ? {
              sceneReady,
              combinedViewOk: mode === "combined",
              cameraFramedHint: sceneDiagnostics?.framedHeuristic ?? false,
              exactBaselineOk,
              startupVisibleBody,
              combinedVisible,
              visibleMeshCount,
              bodyGroupVisible,
              garmentGroupVisible,
              activeTab,
              cleanMode,
              renderSafe,
              lastSceneError,
              startupReason,
              warning: startupWarning,
            }
          : null,
      visibility: {
        mode,
        bodyVisible,
        garmentsVisible,
        safeDefaultActive,
        cameraTargetValid,
        visibleBranch,
        poseTargetBranch,
        bundledBodyMounted,
        bundledBodyVisible,
      },
      interaction: {
        zoomInputMode,
      },
      renderAudit: layout === "workbench" ? renderAuditWithCamera : null,
      scene: devSceneInspect?.enabled ? sceneDiagnostics : null,
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
    bodyOnlyGarments,
    garmentOnlyViewport,
    safeDefaultActive,
    cameraTargetValid,
    devSceneInspect?.enabled,
    sceneDiagnostics,
    layout,
    bodySourceDebug,
    resolvedAvatarSource,
    runtimeBodyBundledModule,
    resolvedRuntime.bodyGltfUrl,
    bodyLoadForUi,
    showSkeletonOverlay,
    showFitDebugOverlay,
    garmentAttachmentDebug,
    clipOverlayEnabled,
    devSceneInspect?.enabled,
    liveShading,
    zoomInputMode,
    sceneReady,
    visibleMeshCount,
    bodyGroupVisible,
    garmentGroupVisible,
    renderAudit,
    activeTab,
    cleanMode,
    startupReason,
    renderSafe,
    lastSceneError,
    onLiveViewportPoseFitDebug,
  ]);

  const onRuntimeBodyLoadError = useCallback((message: string) => {
    const key = message.slice(0, 240);
    const previousKey = skinnedBodyLoadErrLogged.current;
    skinnedBodyLoadErrLogged.current = key;
    setSkinnedBodyLoadStatus("failed");
    setFailedAvatarSourceType(
      resolvedAvatarSource.sourceType === "procedural_fallback"
        ? null
        : resolvedAvatarSource.sourceType,
    );
    if (__DEV__) {
      if (previousKey !== key) {
        console.warn("[AvatarViewportLive] skinned body load failed:", message);
      }
    }
  }, [resolvedAvatarSource.sourceType]);

  useEffect(() => {
    if (!resolvedAvatarSource.usingProceduralFallback) {
      skinnedBodyLoadErrLogged.current = null;
    }
    if (resolvedAvatarSource.usingProceduralFallback) {
      setSkinnedBodyLoadStatus("idle");
    } else if (runtimeBodyBundledModule != null) {
      setSkinnedBodyLoadStatus("pending");
    } else if (resolvedRuntime.bodyGltfUrl) {
      setSkinnedBodyLoadStatus("pending");
    } else {
      setSkinnedBodyLoadStatus("idle");
    }
  }, [
    resolvedAvatarSource.usingProceduralFallback,
    runtimeBodyBundledModule,
    resolvedRuntime.bodyGltfUrl,
  ]);

  const runtimeSummary = useMemo(() => {
    const base = runtimeAssetSummary(resolvedRuntime);
    const loadTag = skinnedBodyPathActive ? ` · body load: ${bodyLoadForUi}` : "";
    if (resolvedAvatarSource.usingProceduralFallback) {
      const mode = resolvedAvatarSource.fallbackReason;
      return `${base} · body=procedural(${mode})${loadTag}`;
    }
    if (runtimeBodyBundledModule != null) {
      if (skinnedBodyLoadStatus === "failed") {
        return `${base} · body=procedural(fallback)${loadTag} · skinned mesh unavailable`;
      }
      return `${base} · body=skinned(stylised bundled, original materials)${loadTag}`;
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
    resolvedAvatarSource,
    skinnedBodyLoadStatus,
    bodyLoadForUi,
    skinnedBodyPathActive,
    runtimeAssets?.bodyGltfUrl,
  ]);

  useEffect(() => {
    if (!__DEV__) return;
    const parts: string[] = [];
    parts.push(`source=${avatarSourceLoadStateLabel(resolvedAvatarSource)}`);
    if (FORCE_PROCEDURAL_BODY) parts.push("EXPO_PUBLIC_AVATAR_USE_PROCEDURAL_BODY=1");
    if (runtimeBodyBundledModule != null) {
      parts.push("bundled=parse+preserve-materials");
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
    resolvedAvatarSource,
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
  const overlayVisiblePartsCount =
    (!garmentOnlyViewport ? PROCEDURAL_HUMANOID_BODY_PART_COUNT : 0) +
    (!bodyOnlyGarments ? PROCEDURAL_HUMANOID_GARMENT_PART_COUNT : 0);
  const showStartupOverlay =
    __DEV__ &&
    (activeTab === "debug" || liveShading === "overlay_debug" || debugOverlay);
  void camUiTick;

  return (
    <GestureHandlerRootView style={[styles.wrap, isWorkbench && styles.wrapWorkbench]}>
      {isWorkbench ? (
        <Text style={styles.hintCompact} numberOfLines={1}>
          Drag orbit · pinch zoom · wheel/two-finger scroll fallback
        </Text>
      ) : (
        <Text style={styles.hint}>
          Drag to orbit · pinch to zoom · wheel/two-finger scroll also zooms in dev. Damped target-orbit camera; zoom +/- buttons below.
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
              targetBaseRef={targetBaseRef}
              targetPanRef={targetPanRef}
              orbitGestureActiveRef={layout === "workbench" ? orbitGestureActiveRef : undefined}
            />
            <AvatarSceneErrorBoundary
              key={`scene-boundary:${bodyAssetKey}`}
              onError={onSceneRenderError}
            >
              <AvatarProceduralScene
                key={`scene:${bodyAssetKey}`}
                pose={pose}
                preset={preset}
                garmentFit={garmentFit}
                liveShading={liveShading}
                bodyShape={bodyShape}
                runtimeBodyGltfUrl={resolvedRuntime.bodyGltfUrl}
                runtimeBodyBundledModule={runtimeBodyBundledModule}
                runtimeTopGltfUrl={resolvedRuntime.topGltfUrl}
                runtimeBottomGltfUrl={resolvedRuntime.bottomGltfUrl}
                showRigDebug={SHOW_RIG_DEBUG || showSkeletonOverlay}
                showGarmentRigDebug={SHOW_GARMENT_RIG_DEBUG || showFitDebugOverlay}
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
                onStartupVisibilityReport={onStartupVisibilityReport}
                startupLoadGeneration={bodyLoadGeneration}
                sceneSpaceDebug={sceneSpaceDebug}
                showVisualSanityMarker={!!sceneSpaceDebug?.showMarkers}
              />
            </AvatarSceneErrorBoundary>
          </Suspense>
        </Canvas>
        <GestureDetector gesture={orbitGesture}>
          <View
            style={[StyleSheet.absoluteFill, styles.touchOverlay]}
            accessibilityLabel="Orbit and pinch the avatar preview"
            collapsable={false}
            {...(Platform.OS === "web"
              ? ({
                  onWheel: (event: {
                    preventDefault?: () => void;
                    nativeEvent?: { deltaY?: number };
                  }) => {
                    event.preventDefault?.();
                    wheelZoomJS(event.nativeEvent?.deltaY ?? 0);
                  },
                } as object)
              : ({} as object))}
          />
        </GestureDetector>
        {bodyLoadForUi === "pending" ? (
          <View style={styles.loadingOverlay}>
            <Text style={styles.loadingText}>loading body...</Text>
          </View>
        ) : null}
        {showStartupOverlay ? (
          <View style={styles.startupOverlay}>
            <Text style={styles.startupOverlayText}>
              avatarModel={PROCEDURAL_AVATAR_MODEL_ID} pose={pose} quality={cleanMode ? "Clean mannequin" : activeTab}
            </Text>
            <Text style={styles.startupOverlayText}>
              renderSafe={renderSafe ? "true" : "false"} bodySource={bodySourceDebug?.active ?? "n/a"} loadStatus={bodyLoadForUi}
            </Text>
            <Text style={styles.startupOverlayText} numberOfLines={1}>
              lastSceneError={lastSceneError ?? "none"}
            </Text>
            <Text style={styles.startupOverlayText}>
              anchors={PROCEDURAL_HUMANOID_JOINT_COUNT} garmentAnchors={garmentAnchorsDbg ? "ok" : "missing"} parts={overlayVisiblePartsCount}
            </Text>
            <Text style={styles.startupOverlayText}>
              load={bodyLoadForUi} ready={sceneReady ? "yes" : "no"} meshes={visibleMeshCount}
            </Text>
            {renderAudit ? (
              <Text style={styles.startupOverlayText}>
                branch={renderAudit.activeRenderBranchName} mounted={renderAudit.mountedAvatarRoot ? "yes" : "no"} gltf={renderAudit.gltfVisibleMeshCount}/{renderAudit.gltfTotalMeshCount}
              </Text>
            ) : null}
            <Text style={styles.startupOverlayText}>
              body={bodyGroupVisible ? "yes" : "no"} garments={garmentGroupVisible ? "yes" : "no"} tab={activeTab}
            </Text>
            <Text style={styles.startupOverlayText}>
              clean={cleanMode ? "yes" : "no"} r={smooth.radius.toFixed(2)} reason={startupReason}
            </Text>
            <Text style={styles.startupOverlayText}>
              target=[{(targetBaseRef.current[0] + targetPanRef.current.x).toFixed(2)},{" "}
              {(targetBaseRef.current[1] + navRef.current.targetYOffset).toFixed(2)},{" "}
              {(targetBaseRef.current[2] + targetPanRef.current.z).toFixed(2)}]
            </Text>
          </View>
        ) : null}
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
  loadingOverlay: {
    position: "absolute",
    left: 8,
    top: 8,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: theme.radii.sm,
    backgroundColor: "rgba(20,20,20,0.55)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.12)",
  },
  loadingText: {
    color: "#f5f5f5",
    fontSize: 10,
    fontFamily: "monospace",
  },
  startupOverlay: {
    position: "absolute",
    right: 8,
    top: 8,
    paddingHorizontal: 8,
    paddingVertical: 6,
    borderRadius: theme.radii.sm,
    backgroundColor: "rgba(8,8,8,0.66)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.12)",
    gap: 2,
  },
  startupOverlayText: {
    color: "#f5f5f5",
    fontSize: 10,
    fontFamily: "monospace",
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
