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
import { AvatarProceduralScene, CameraRig } from "./avatar-procedural-scene";
import { deformationSummary } from "./garment-deformation";
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
};

type Orbit = { theta: number; phi: number; radius: number };

const DEFAULT_ORBIT: Orbit = { theta: 0.48, phi: 1.02, radius: 3.55 };
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

const PHI_MIN = 0.15;
const PHI_MAX = 1.55;
const R_MIN = 1.5;
const R_MAX = 8;

const LOG_THROTTLE_MS = 280;

function sanitizeOrbit(o: Orbit, prev: Orbit): Orbit {
  let { theta, phi, radius } = o;
  if (!Number.isFinite(theta)) theta = prev.theta;
  if (!Number.isFinite(phi)) phi = prev.phi;
  if (!Number.isFinite(radius)) radius = prev.radius;
  phi = Math.min(PHI_MAX, Math.max(PHI_MIN, phi));
  radius = Math.min(R_MAX, Math.max(R_MIN, radius));
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
}: AvatarViewportLiveProps) {
  const [cam, setCam] = useState<Orbit>(() => ({ ...DEFAULT_ORBIT }));
  const camRef = useRef(cam);
  camRef.current = cam;

  const panBaseRef = useRef<Orbit>({ ...DEFAULT_ORBIT });
  const pinchRadius0Ref = useRef(DEFAULT_ORBIT.radius);
  const mountedRef = useRef(true);
  const lastGestureLog = useRef(0);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const safeSetCam = useCallback((updater: Orbit | ((prev: Orbit) => Orbit)) => {
    if (!mountedRef.current) return;
    setCam((prev) => {
      const next = typeof updater === "function" ? updater(prev) : updater;
      return sanitizeOrbit(next, prev);
    });
  }, []);

  const logThrottle = useCallback((tag: string) => {
    if (!__DEV__) return;
    const now = Date.now();
    if (now - lastGestureLog.current < LOG_THROTTLE_MS) return;
    lastGestureLog.current = now;
    console.log(tag, { path: "runOnJS", cam: { ...camRef.current } });
  }, []);

  const panBeginJS = useCallback(() => {
    panBaseRef.current = { ...camRef.current };
    if (__DEV__) {
      console.log("[AvatarViewport] pan begin", { base: { ...panBaseRef.current } });
    }
  }, []);

  const panUpdateJS = useCallback((translationX: number, translationY: number) => {
    if (!Number.isFinite(translationX) || !Number.isFinite(translationY)) return;
    if (Math.abs(translationX) > 500 || Math.abs(translationY) > 500) return;
    const b = panBaseRef.current;
    safeSetCam({
      theta: b.theta - translationX * 0.0075,
      phi: Math.min(PHI_MAX, Math.max(PHI_MIN, b.phi + translationY * 0.0075)),
      radius: b.radius,
    });
    logThrottle("[AvatarViewport] pan update");
  }, [safeSetCam, logThrottle]);

  const panEndJS = useCallback(() => {
    if (__DEV__) console.log("[AvatarViewport] pan end");
  }, []);

  const pinchBeginJS = useCallback(() => {
    pinchRadius0Ref.current = camRef.current.radius;
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
    const raw = r0 / scale;
    safeSetCam((c) => ({
      ...c,
      radius: Math.min(R_MAX, Math.max(R_MIN, raw)),
    }));
    logThrottle("[AvatarViewport] pinch update");
  }, [safeSetCam, logThrottle]);

  const pinchEndJS = useCallback(() => {
    if (__DEV__) console.log("[AvatarViewport] pinch end");
  }, []);

  const orbitGesture = useMemo(() => {
    const pan = Gesture.Pan()
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

    return Gesture.Simultaneous(pan, pinch);
  }, [
    panBeginJS,
    panUpdateJS,
    panEndJS,
    pinchBeginJS,
    pinchUpdateJS,
    pinchEndJS,
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
    safeSetCam({ ...DEFAULT_ORBIT });
    if (__DEV__) console.log("[AvatarViewport] reset cam (press)");
  };
  const zoomIn = () => {
    safeSetCam((c) => ({
      ...c,
      radius: Math.max(R_MIN, c.radius - 0.42),
    }));
    if (__DEV__) console.log("[AvatarViewport] zoom + (press)", camRef.current);
  };
  const zoomOut = () => {
    safeSetCam((c) => ({
      ...c,
      radius: Math.min(R_MAX, c.radius + 0.42),
    }));
    if (__DEV__) console.log("[AvatarViewport] zoom − (press)", camRef.current);
  };

  const fitIsNonDefault = !fitStatesEqual(garmentFit, DEFAULT_GARMENT_FIT_STATE);

  const [skinnedBodyLoadStatus, setSkinnedBodyLoadStatus] = useState<
    "idle" | "pending" | "loaded" | "failed"
  >("idle");
  const skinnedBodyLoadErrLogged = useRef<string | null>(null);

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

  return (
    <GestureHandlerRootView style={styles.wrap}>
      <Text style={styles.hint}>
        Drag to orbit · pinch to zoom (both use runOnJS from the gesture worklet). Zoom ± stays
        the most reliable path on emulators.
      </Text>
      <View style={[styles.frame, { height }]}>
        <Canvas
          pointerEvents="none"
          frameloop="always"
          camera={{ position: [0, 1.8, 4.2], fov: 42, near: 0.1, far: 80 }}
          gl={{ preserveDrawingBuffer: true }}
          style={StyleSheet.absoluteFill}
        >
          <Suspense fallback={null}>
            <CameraRig orbit={cam} target={TARGET} />
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
              onRuntimeBodyLoadError={onRuntimeBodyLoadError}
              onRuntimeBodyLoaded={onRuntimeBodyLoaded}
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

      {__DEV__ ? (
        <View style={styles.debugBox}>
          <Text style={styles.debugLine} selectable>
            cam r={cam.radius.toFixed(2)} θ={cam.theta.toFixed(2)} φ={cam.phi.toFixed(2)}
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
            pan/pinch: RNGH worklet → runOnJS(setState) · no direct worklet → JS refs
          </Text>
        </View>
      ) : null}

      <View style={styles.camRow}>
        <AppButton label="Reset cam" variant="secondary" onPress={resetCamera} />
        <AppButton label="Zoom +" variant="secondary" onPress={zoomIn} />
        <AppButton label="Zoom −" variant="secondary" onPress={zoomOut} />
      </View>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: theme.spacing.xs },
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
