import { useFrame, useLoader, useThree } from "@react-three/fiber/native";
import {
  Component,
  type ErrorInfo,
  type ReactNode,
  use,
  useLayoutEffect,
  useMemo,
  useRef,
} from "react";
import * as THREE from "three";
import type { GLTF } from "three/examples/jsm/loaders/GLTFLoader.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

import {
  DEFAULT_BODY_SHAPE,
  bodyShapeParamsKey,
  deriveBodyRigMetrics,
  type BodyRigMetrics,
  type BodyShapeParams,
  type GarmentFitState,
} from "@/features/avatar-export";
import type { DevAvatarPoseKey } from "@/features/avatar-export/dev-avatar-shared";

import { applySkinnedBodyFallbackMaterials } from "./gltf-body-fallback-materials";
import { loadBundledGltfModule } from "./gltf-bundled-load";
import { poseAngles } from "./avatar-pose-angles";
import {
  deformGarmentObject3D,
  type GarmentDeformProfile,
  type GarmentPoseSkinningParams,
} from "./garment-deformation";
import type { LiveViewportShadingMode } from "./live-viewport-shading";
import { alignSkinnedRootToPelvisMetric } from "./skinned-body-placement";
import type { SkinnedRigPoseReport } from "./live-viewport-debug-types";
import {
  applySkinnedPoseToBones,
  applySkinnedShapeScales,
  captureSkeletonRestQuats,
  captureSkeletonRestScales,
  classifySkinnedBoneMap,
  countCriticalMappedBones,
  countMappedSkinnedBones,
  findFirstSkinnedMesh,
  resolveSkinnedBodyBones,
  SKINNED_POSE_CRITICAL_SLOT_COUNT,
  type ResolvedSkinnedBones,
  type SkinnedPoseBias,
} from "./skinned-body-pose";

type MatBaseline = {
  color: THREE.Color;
  emissive: THREE.Color;
  transparent: boolean;
  opacity: number;
};

export function poseRootEulerApprox(pose: DevAvatarPoseKey): [number, number, number] {
  switch (pose) {
    case "tpose":
      return [0, 0, 0];
    case "relaxed":
      return [0.07, 0, 0];
    case "walk":
      return [0.11, 0.14, 0];
    case "apose":
      return [0.05, 0, 0];
    default:
      return [0, 0, 0];
  }
}

function collectStandardMaterials(root: THREE.Object3D): THREE.MeshStandardMaterial[] {
  const out: THREE.MeshStandardMaterial[] = [];
  root.traverse((o) => {
    if (!(o instanceof THREE.Mesh)) return;
    if (Array.isArray(o.material)) {
      for (const m of o.material) {
        if (m instanceof THREE.MeshStandardMaterial) out.push(m);
      }
    } else if (o.material instanceof THREE.MeshStandardMaterial) {
      out.push(o.material);
    }
  });
  return out;
}

function buildMaterialBaseline(
  root: THREE.Object3D,
): Map<THREE.MeshStandardMaterial, MatBaseline> {
  const map = new Map<THREE.MeshStandardMaterial, MatBaseline>();
  for (const m of collectStandardMaterials(root)) {
    map.set(m, {
      color: m.color.clone(),
      emissive: m.emissive.clone(),
      transparent: m.transparent,
      opacity: m.opacity,
    });
  }
  return map;
}

/** Restore then apply live debug shading. `body` = skin / base mesh; `garment` = clothing GLTF. */
export function applyLiveShadingToGltfMaterials(
  root: THREE.Object3D,
  mode: LiveViewportShadingMode,
  scope: "body" | "garment",
  baseline: Map<THREE.MeshStandardMaterial, MatBaseline>,
  /** Added on top of baseline emissive for garment clipping overlay (live proxy). */
  clipEmissiveAdd?: THREE.Color,
) {
  for (const m of collectStandardMaterials(root)) {
    const b = baseline.get(m);
    if (!b) continue;
    m.color.copy(b.color);
    m.emissive.copy(b.emissive);
    m.opacity = b.opacity;
    m.transparent = b.transparent;
    switch (mode) {
      case "normal":
        break;
      case "body_focus":
        if (scope === "garment") {
          m.transparent = true;
          m.opacity = 0.32;
        }
        break;
      case "garment_focus":
        if (scope === "body") {
          m.transparent = true;
          m.opacity = 0.32;
        }
        break;
      case "overlay_style":
        m.transparent = true;
        m.opacity = 0.92;
        if (scope === "body") {
          m.color.set(0.22, 0.42, 0.9);
          m.emissive.set(0.04, 0.06, 0.16);
        } else {
          m.color.set(0.95, 0.45, 0.12);
          m.emissive.set(0.06, 0.02, 0);
        }
        break;
      default:
        break;
    }
    if (clipEmissiveAdd && scope === "garment") {
      m.emissive.r += clipEmissiveAdd.r;
      m.emissive.g += clipEmissiveAdd.g;
      m.emissive.b += clipEmissiveAdd.b;
    }
  }
}

function normalizeRootToHeight(r: THREE.Object3D, targetY: number) {
  const box = new THREE.Box3().setFromObject(r);
  const size = box.getSize(new THREE.Vector3());
  if (size.y > 1e-5) {
    const sc = targetY / size.y;
    r.scale.setScalar(sc);
    box.setFromObject(r);
    r.position.set(0, -box.min.y, 0);
  }
}

type PreparedGltf = {
  scene: THREE.Object3D;
  baseline: Map<THREE.MeshStandardMaterial, MatBaseline>;
};

function usePreparedGltf(
  cacheKey: string,
  gltf: GLTF,
  normalizeY: number,
  metrics: BodyRigMetrics,
  applyPelvisAlign: boolean,
  /** Bundled / Expo: replace GLB materials so no GPU texture sampling from embedded maps. */
  applyUntexturedFallbackMaterials: boolean,
): PreparedGltf {
  return useMemo(() => {
    const root = gltf.scene.clone(true);
    normalizeRootToHeight(root, normalizeY);
    if (applyPelvisAlign) alignSkinnedRootToPelvisMetric(root, metrics);
    if (applyUntexturedFallbackMaterials) applySkinnedBodyFallbackMaterials(root);
    const baseline = buildMaterialBaseline(root);
    return { scene: root, baseline };
  }, [gltf, cacheKey, normalizeY, metrics, applyPelvisAlign, applyUntexturedFallbackMaterials]);
}

type SkinnedBindCache = {
  sceneId: string;
  shapeKey: string;
  restQuat: Map<string, THREE.Quaternion>;
  restScale: Map<string, THREE.Vector3>;
  bones: ResolvedSkinnedBones;
};

function resetSkeletonToRest(
  skeleton: THREE.Skeleton,
  restQuat: Map<string, THREE.Quaternion>,
  restScale: Map<string, THREE.Vector3>,
) {
  for (const bone of skeleton.bones) {
    const rq = restQuat.get(bone.name);
    if (rq) bone.quaternion.copy(rq);
    const rs = restScale.get(bone.name);
    if (rs) bone.scale.copy(rs);
  }
}

/** expo-gl / RN: ensure boneTexture / boneMatrices refresh every frame after CPU pose. */
function SkinnedSkeletonFrameUpdater({
  scene,
  enabled,
}: {
  scene: THREE.Object3D;
  enabled: boolean;
}) {
  const skinnedRef = useRef<THREE.SkinnedMesh | null>(null);
  useLayoutEffect(() => {
    skinnedRef.current = findFirstSkinnedMesh(scene);
  }, [scene]);
  useFrame(() => {
    if (!enabled) return;
    const sm = skinnedRef.current;
    if (sm?.skeleton) sm.skeleton.update();
  });
  return null;
}

function ensureBodyMeshesDrawable(root: THREE.Object3D) {
  root.traverse((o) => {
    o.visible = true;
    o.matrixAutoUpdate = true;
    if (o instanceof THREE.Mesh || o instanceof THREE.SkinnedMesh) {
      o.visible = true;
      o.frustumCulled = false;
      const s = o.scale;
      if (
        !Number.isFinite(s.x) ||
        !Number.isFinite(s.y) ||
        !Number.isFinite(s.z) ||
        s.x * s.x + s.y * s.y + s.z * s.z < 1e-24
      ) {
        o.scale.set(1, 1, 1);
      }
      if (Array.isArray(o.material)) {
        for (const m of o.material) {
          m.needsUpdate = true;
        }
      } else if (o.material) {
        o.material.needsUpdate = true;
      }
    }
  });
}

function applyDebugBrightBodyMaterials(root: THREE.Object3D) {
  for (const m of collectStandardMaterials(root)) {
    m.color.set(0xff0a8c);
    m.emissive.set(0.38, 0.06, 0.2);
    m.transparent = false;
    m.opacity = 1;
    m.metalness = 0;
    m.roughness = 1;
    m.side = THREE.DoubleSide;
    m.depthWrite = true;
    m.needsUpdate = true;
  }
  root.traverse((o) => {
    if (o instanceof THREE.SkinnedMesh || o instanceof THREE.Mesh) {
      o.frustumCulled = false;
    }
  });
}

function useSkinnedBodyLayout(
  scene: THREE.Object3D,
  baseline: Map<THREE.MeshStandardMaterial, MatBaseline>,
  pose: DevAvatarPoseKey,
  liveShading: LiveViewportShadingMode,
  m: BodyRigMetrics,
  bodyShapeKeyStr: string,
  enableSkinnedRig: boolean,
  poseBias: SkinnedPoseBias | undefined,
  onSceneReady: (() => void) | undefined,
  onRigPoseReport: ((r: SkinnedRigPoseReport) => void) | undefined,
  debugForceBrightMaterial?: boolean,
) {
  const invalidate = useThree((st) => st.invalidate);
  const ang = useMemo(() => poseAngles(pose), [pose]);
  const skinnedCacheRef = useRef<SkinnedBindCache | null>(null);
  const sk = bodyShapeKeyStr;
  const onSceneReadyRef = useRef(onSceneReady);
  const onRigPoseReportRef = useRef(onRigPoseReport);
  const lastRigReportJson = useRef("");
  onSceneReadyRef.current = onSceneReady;
  onRigPoseReportRef.current = onRigPoseReport;

  useLayoutEffect(() => {
    try {
      const skinned = findFirstSkinnedMesh(scene);
      const euler = poseRootEulerApprox(pose);

      if (!enableSkinnedRig || !skinned?.skeleton) {
        scene.rotation.set(euler[0], euler[1], euler[2]);
        applyLiveShadingToGltfMaterials(scene, liveShading, "body", baseline);
        ensureBodyMeshesDrawable(scene);
        if (debugForceBrightMaterial) applyDebugBrightBodyMaterials(scene);
        scene.updateMatrixWorld(true);
        const report: SkinnedRigPoseReport = {
          activePose: pose,
          bodyPoseApplied: false,
          boneMapStatus: "fallback",
          mappedBoneSlots: 0,
          criticalMapped: 0,
          criticalTotal: SKINNED_POSE_CRITICAL_SLOT_COUNT,
        };
        const rj = JSON.stringify(report);
        if (rj !== lastRigReportJson.current) {
          lastRigReportJson.current = rj;
          onRigPoseReportRef.current?.(report);
        }
        onSceneReadyRef.current?.();
        return;
      }

      const skeleton = skinned.skeleton;
      const sid = `${scene.uuid}:${skinned.uuid}`;
      let cache = skinnedCacheRef.current;
      if (!cache || cache.sceneId !== sid || cache.shapeKey !== sk) {
        cache = {
          sceneId: sid,
          shapeKey: sk,
          restQuat: captureSkeletonRestQuats(skeleton),
          restScale: captureSkeletonRestScales(skeleton),
          bones: resolveSkinnedBodyBones(skeleton),
        };
        skinnedCacheRef.current = cache;
      }

      resetSkeletonToRest(skeleton, cache.restQuat, cache.restScale);
      applySkinnedShapeScales(cache.bones, cache.restScale, m);
      applySkinnedPoseToBones(cache.bones, cache.restQuat, ang, poseBias);

      scene.rotation.set(euler[0], euler[1], euler[2]);
      applyLiveShadingToGltfMaterials(scene, liveShading, "body", baseline);
      ensureBodyMeshesDrawable(scene);
      if (debugForceBrightMaterial) applyDebugBrightBodyMaterials(scene);
      scene.updateMatrixWorld(true);

      const boneMapStatus = classifySkinnedBoneMap(cache.bones);
      const criticalMapped = countCriticalMappedBones(cache.bones);
      const bodyPoseApplied =
        enableSkinnedRig && boneMapStatus !== "fallback" && criticalMapped >= 5;
      const report: SkinnedRigPoseReport = {
        activePose: pose,
        bodyPoseApplied,
        boneMapStatus,
        mappedBoneSlots: countMappedSkinnedBones(cache.bones),
        criticalMapped,
        criticalTotal: SKINNED_POSE_CRITICAL_SLOT_COUNT,
      };
      const rj = JSON.stringify(report);
      if (rj !== lastRigReportJson.current) {
        lastRigReportJson.current = rj;
        onRigPoseReportRef.current?.(report);
      }
      onSceneReadyRef.current?.();
    } finally {
      invalidate();
    }
  }, [
    scene,
    pose,
    liveShading,
    baseline,
    ang,
    m,
    enableSkinnedRig,
    poseBias,
    sk,
    debugForceBrightMaterial,
    invalidate,
  ]);
}

type GltfRuntimeBodyShared = {
  pose: DevAvatarPoseKey;
  liveShading: LiveViewportShadingMode;
  bodyShape?: BodyShapeParams;
  enableSkinnedRig?: boolean;
  /** Extra pose deltas for skinned bind vs procedural rig. */
  poseBias?: SkinnedPoseBias;
  onSceneReady?: () => void;
  /** Dev: skinned bone pose / map status for live diagnostics. */
  onRigPoseReport?: (r: SkinnedRigPoseReport) => void;
  /** Dev: loud unlit-ish standard material + no frustum cull — visibility proof only. */
  debugForceBrightMaterial?: boolean;
};

/** Bundled module: Android-safe parse path (no `file://` in GLTFLoader). */
export function GltfRuntimeBodyFromBundledModule({
  bundledAssetModule,
  pose,
  liveShading,
  bodyShape = DEFAULT_BODY_SHAPE,
  enableSkinnedRig = true,
  poseBias,
  onSceneReady,
  onRigPoseReport,
  debugForceBrightMaterial,
}: GltfRuntimeBodyShared & { bundledAssetModule: number }) {
  const gltf = use(useMemo(() => loadBundledGltfModule(bundledAssetModule), [bundledAssetModule]));
  const bodyShapeKeyStr = bodyShapeParamsKey(bodyShape);
  const m = useMemo(() => deriveBodyRigMetrics(bodyShape), [bodyShapeKeyStr]);
  const { scene, baseline } = usePreparedGltf(
    `bundled:${bundledAssetModule}`,
    gltf,
    m.gltfNormalizeY,
    m,
    true,
    true,
  );
  const [sx, sy, sz] = m.gltfBodyScale;
  useSkinnedBodyLayout(
    scene,
    baseline,
    pose,
    liveShading,
    m,
    bodyShapeKeyStr,
    enableSkinnedRig ?? true,
    poseBias,
    onSceneReady,
    onRigPoseReport,
    debugForceBrightMaterial,
  );

  return (
    <>
      <SkinnedSkeletonFrameUpdater scene={scene} enabled={enableSkinnedRig ?? true} />
      <group scale={[sx, sy, sz]}>
        <primitive object={scene} />
      </group>
    </>
  );
}

/** Remote / https body URL — `useLoader` is fine for http(s). */
export function GltfRuntimeBodyFromUrl({
  url,
  pose,
  liveShading,
  bodyShape = DEFAULT_BODY_SHAPE,
  enableSkinnedRig = true,
  poseBias,
  onSceneReady,
  onRigPoseReport,
  debugForceBrightMaterial,
}: GltfRuntimeBodyShared & { url: string }) {
  const gltf = useLoader(GLTFLoader, url);
  const bodyShapeKeyStr = bodyShapeParamsKey(bodyShape);
  const m = useMemo(() => deriveBodyRigMetrics(bodyShape), [bodyShapeKeyStr]);
  const { scene, baseline } = usePreparedGltf(
    url,
    gltf,
    m.gltfNormalizeY,
    m,
    true,
    false,
  );
  const [sx, sy, sz] = m.gltfBodyScale;
  useSkinnedBodyLayout(
    scene,
    baseline,
    pose,
    liveShading,
    m,
    bodyShapeKeyStr,
    enableSkinnedRig ?? true,
    poseBias,
    onSceneReady,
    onRigPoseReport,
    debugForceBrightMaterial,
  );

  return (
    <>
      <SkinnedSkeletonFrameUpdater scene={scene} enabled={enableSkinnedRig ?? true} />
      <group scale={[sx, sy, sz]}>
        <primitive object={scene} />
      </group>
    </>
  );
}

export type GltfRuntimeBodyProps = GltfRuntimeBodyShared & {
  /** Remote GLB URL (https / reachable). Ignored when `bundledAssetModule` is set. */
  url?: string | null;
  /** Metro `require()` module id — load via `parse` (Android-safe; no `file://` in loader). */
  bundledAssetModule?: number | null;
};

/**
 * Prefer `bundledAssetModule` when set so Android never uses `file://` URIs with GLTFLoader.
 * Otherwise loads `url`.
 */
export function GltfRuntimeBody(props: GltfRuntimeBodyProps) {
  if (props.bundledAssetModule != null) {
    return (
      <GltfRuntimeBodyFromBundledModule
        bundledAssetModule={props.bundledAssetModule}
        pose={props.pose}
        liveShading={props.liveShading}
        bodyShape={props.bodyShape}
        enableSkinnedRig={props.enableSkinnedRig}
        poseBias={props.poseBias}
        onSceneReady={props.onSceneReady}
        onRigPoseReport={props.onRigPoseReport}
        debugForceBrightMaterial={props.debugForceBrightMaterial}
      />
    );
  }
  if (props.url) {
    return (
      <GltfRuntimeBodyFromUrl
        url={props.url}
        pose={props.pose}
        liveShading={props.liveShading}
        bodyShape={props.bodyShape}
        enableSkinnedRig={props.enableSkinnedRig}
        poseBias={props.poseBias}
        onSceneReady={props.onSceneReady}
        onRigPoseReport={props.onRigPoseReport}
        debugForceBrightMaterial={props.debugForceBrightMaterial}
      />
    );
  }
  return null;
}

type GltfRuntimeGarmentProps = {
  url: string;
  liveShading: LiveViewportShadingMode;
  /** Target height in scene units after normalization (shirt ~0.42, pants ~0.52). */
  normalizeHeight?: number;
  /** Shared live fit; drives regional vertex deformation (see `garment-deformation.ts`). */
  garmentFit: GarmentFitState;
  deformProfile: GarmentDeformProfile;
  /** CPU pose follow (weighted arm/thigh deltas) before regional fit. */
  garmentPoseSkin?: GarmentPoseSkinningParams | null;
  /** Runtime clipping overlay emissive add (garment materials only). */
  clipEmissiveAdd?: THREE.Color;
};

/**
 * Static garment GLB under a parent group that already applies fit offsets.
 * Pipeline: base placement + parent transforms → pose skinning → regional fit → live shading.
 */
export function GltfRuntimeGarment({
  url,
  liveShading,
  normalizeHeight = 0.48,
  garmentFit,
  deformProfile,
  garmentPoseSkin = null,
  clipEmissiveAdd,
}: GltfRuntimeGarmentProps) {
  const gltf = useLoader(GLTFLoader, url);
  const { scene, baseline } = useMemo(() => {
    const root = gltf.scene.clone(true);
    normalizeRootToHeight(root, normalizeHeight);
    const bl = buildMaterialBaseline(root);
    return { scene: root, baseline: bl };
  }, [gltf, url, normalizeHeight]);

  useLayoutEffect(() => {
    deformGarmentObject3D(scene, garmentFit, deformProfile, garmentPoseSkin ?? undefined);
    applyLiveShadingToGltfMaterials(
      scene,
      liveShading,
      "garment",
      baseline,
      clipEmissiveAdd,
    );
    scene.traverse((o) => {
      if (o instanceof THREE.Mesh) o.updateMatrixWorld(true);
    });
  }, [
    scene,
    liveShading,
    baseline,
    garmentFit,
    deformProfile,
    garmentPoseSkin,
    clipEmissiveAdd,
  ]);

  return <primitive object={scene} />;
}

type EBProps = {
  children: ReactNode;
  fallback: ReactNode;
  /** Dev / diagnostics: runtime GLB load or parse failed. */
  onLoadError?: (message: string) => void;
};

type EBState = { hasError: boolean };

/** Dedupe console noise when the same GLTF error re-triggers (e.g. strict mode / remounts). */
const gltfErrorBoundaryLogged = new Set<string>();

export class GltfErrorBoundary extends Component<EBProps, EBState> {
  constructor(props: EBProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  override componentDidCatch(error: Error, info: ErrorInfo) {
    if (__DEV__) {
      const key = error.message.slice(0, 240);
      if (!gltfErrorBoundaryLogged.has(key)) {
        gltfErrorBoundaryLogged.add(key);
        console.warn("[AvatarViewport] GLTF fallback:", error.message, info.componentStack);
      }
    }
    this.props.onLoadError?.(error.message);
  }

  override render() {
    if (this.state.hasError) return this.props.fallback;
    return this.props.children;
  }
}
