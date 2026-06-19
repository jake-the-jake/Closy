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
import { THREE } from "./three";
import { GLTFLoader, SkeletonUtils, type GLTF } from "./three";

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
import { type AvatarNormalizeReport } from "./avatar-normalize";
import { type AvatarRigInspection } from "./avatar-rig-inspector";
import { auditAvatarObject3D, type AvatarAssetAudit } from "./avatar-loader/avatarAssetAudit";
import { normalizeAvatarScene } from "./avatar-loader/normalizeAvatarScene";
import { normalizeAvatarPbrMaterials } from "./avatar-loader/avatarMaterialNormalizer";
import { mapAvatarSkeleton } from "./avatar-loader/avatarSkeletonMapper";
import {
  deformGarmentObject3D,
  type GarmentDeformProfile,
  type GarmentPoseSkinningParams,
} from "./garment-deformation";
import type { LiveViewportShadingMode } from "./live-viewport-shading";
import { alignSkinnedRootToPelvisMetric } from "./skinned-body-placement";
import type {
  AvatarSkinCloneAudit,
  AvatarRenderableReport,
  SkinnedRigPoseReport,
} from "./live-viewport-debug-types";
import {
  createAvatarRenderProbe,
  projectObjectBounds,
  type AvatarProjectionSnapshot,
  type AvatarRenderProbeSnapshot,
} from "./avatar-source/avatarRenderProbe";
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

type AvatarGltfStats = {
  normalizeReport: AvatarNormalizeReport;
  rigInspection: AvatarRigInspection;
  audit: AvatarAssetAudit;
  meshCount: number;
  visibleMeshCount: number;
  skinnedMeshCount: number;
  materialCount: number;
  textureCount: number;
  materialNames: string[];
  transparentMaterialCount: number;
  triangleEstimate: number;
  sceneChildCount: number;
  worldScale: [number, number, number];
  animationCount: number;
  materialSafetyStatus?: "mobile_safe" | "mobile_sanitized";
  assetFailureReason: string | null;
  skinCloneAudit: AvatarSkinCloneAudit;
};

function isMeshLike(o: THREE.Object3D): o is THREE.Mesh | THREE.SkinnedMesh {
  const flags = o as { isMesh?: boolean; isSkinnedMesh?: boolean };
  return flags.isMesh === true || flags.isSkinnedMesh === true;
}

function isStandardMaterialLike(m: THREE.Material): m is THREE.MeshStandardMaterial {
  return m instanceof THREE.MeshStandardMaterial || (m as { isMeshStandardMaterial?: boolean }).isMeshStandardMaterial === true;
}

function countSkinnedMeshes(root: THREE.Object3D): number {
  let count = 0;
  root.traverse((o) => {
    if ((o as THREE.SkinnedMesh).isSkinnedMesh) count += 1;
  });
  return count;
}

function v3tuple(v: THREE.Vector3): [number, number, number] {
  return [v.x, v.y, v.z];
}

function finiteTuple(value: [number, number, number] | null | undefined): boolean {
  return !!value && value.every((n) => Number.isFinite(n));
}

function finiteNonZeroTuple(value: [number, number, number] | null | undefined): boolean {
  return finiteTuple(value) && value!.some((n) => Math.abs(n) > 1e-6);
}

function materialList(mesh: THREE.Mesh | THREE.SkinnedMesh): THREE.Material[] {
  if (Array.isArray(mesh.material)) return mesh.material.filter(Boolean);
  return mesh.material ? [mesh.material] : [];
}

function firstMaterialSnapshot(mesh: THREE.Mesh | THREE.SkinnedMesh): {
  opacity: number | null;
  transparent: boolean | null;
} {
  const mat = materialList(mesh)[0] as
    | (THREE.Material & { opacity?: number; transparent?: boolean })
    | undefined;
  return {
    opacity: typeof mat?.opacity === "number" && Number.isFinite(mat.opacity) ? mat.opacity : null,
    transparent: typeof mat?.transparent === "boolean" ? mat.transparent : null,
  };
}

function findFirstMesh(root: THREE.Object3D): THREE.Mesh | THREE.SkinnedMesh | null {
  let first: THREE.Mesh | THREE.SkinnedMesh | null = null;
  root.traverse((o) => {
    if (first || !isMeshLike(o)) return;
    first = o;
  });
  return first;
}

function updateWorldFromSceneRoot(object: THREE.Object3D) {
  let root = object;
  while (root.parent) root = root.parent;
  root.updateMatrixWorld(true);
}

function collectBones(root: THREE.Object3D): Set<THREE.Bone> {
  const bones = new Set<THREE.Bone>();
  root.traverse((o) => {
    if (o instanceof THREE.Bone || (o as { isBone?: boolean }).isBone === true) {
      bones.add(o as THREE.Bone);
    }
  });
  return bones;
}

function finiteMatrix(matrix: THREE.Matrix4): boolean {
  return matrix.elements.every((n) => Number.isFinite(n));
}

function skinAttributesValid(mesh: THREE.SkinnedMesh): boolean {
  const geometry = mesh.geometry;
  const skinIndex = geometry?.getAttribute("skinIndex");
  const skinWeight = geometry?.getAttribute("skinWeight");
  if (!skinIndex || !skinWeight || skinIndex.count !== skinWeight.count) return false;
  for (let i = 0; i < Math.min(skinWeight.count, 64); i += 1) {
    for (let c = 0; c < skinWeight.itemSize; c += 1) {
      const weight = skinWeight.getComponent(i, c);
      if (!Number.isFinite(weight)) return false;
    }
  }
  return true;
}

function auditSkinClone(sourceScene: THREE.Object3D, cloneScene: THREE.Object3D): AvatarSkinCloneAudit {
  const sourceBones = collectBones(sourceScene);
  const clonedBones = collectBones(cloneScene);
  let skinnedMeshCount = 0;
  let sharedSourceBoneReferences = 0;
  let clonedBonesBelongToClone = true;
  let bindMatricesFinite = true;
  let skinAttrsValid = true;

  cloneScene.traverse((o) => {
    const mesh = o as THREE.SkinnedMesh;
    if (!mesh.isSkinnedMesh) return;
    skinnedMeshCount += 1;
    if (!mesh.skeleton || mesh.skeleton.bones.length <= 0) {
      clonedBonesBelongToClone = false;
      skinAttrsValid = false;
      return;
    }
    if (mesh.skeleton.boneInverses.length !== mesh.skeleton.bones.length) {
      bindMatricesFinite = false;
    }
    if (!finiteMatrix(mesh.bindMatrix) || !finiteMatrix(mesh.bindMatrixInverse)) {
      bindMatricesFinite = false;
    }
    for (const inverse of mesh.skeleton.boneInverses) {
      if (!finiteMatrix(inverse)) bindMatricesFinite = false;
    }
    for (const bone of mesh.skeleton.bones) {
      if (!clonedBones.has(bone)) clonedBonesBelongToClone = false;
      if (sourceBones.has(bone)) sharedSourceBoneReferences += 1;
    }
    if (!skinAttributesValid(mesh)) skinAttrsValid = false;
    try {
      mesh.skeleton.update();
    } catch {
      bindMatricesFinite = false;
    }
  });

  const valid =
    skinnedMeshCount <= 0 ||
    (clonedBones.size > 0 &&
      clonedBonesBelongToClone &&
      sharedSourceBoneReferences === 0 &&
      bindMatricesFinite &&
      skinAttrsValid);
  const reason = valid
    ? skinnedMeshCount > 0
      ? "skinned_clone_valid"
      : "no_skinned_meshes"
    : sharedSourceBoneReferences > 0
      ? "clone_references_source_bones"
      : !clonedBonesBelongToClone
        ? "cloned_bones_not_in_clone_hierarchy"
        : !bindMatricesFinite
          ? "bind_matrices_invalid"
          : "skin_attributes_invalid";

  return {
    sourceSceneUuid: sourceScene.uuid,
    cloneSceneUuid: cloneScene.uuid,
    skinnedMeshCount,
    sourceBoneCount: sourceBones.size,
    clonedBoneCount: clonedBones.size,
    clonedBonesBelongToClone,
    sharedSourceBoneReferences,
    bindMatricesFinite,
    skinAttributesValid: skinAttrsValid,
    valid,
    reason,
  };
}

function cloneGltfScene(gltf: GLTF): { root: THREE.Object3D; skinCloneAudit: AvatarSkinCloneAudit } {
  const sourceScene = gltf.scene;
  const root =
    countSkinnedMeshes(sourceScene) > 0
      ? (SkeletonUtils.clone(sourceScene) as THREE.Object3D)
      : sourceScene.clone(true);
  return {
    root,
    skinCloneAudit: auditSkinClone(sourceScene, root),
  };
}

function boundsAreFiniteNonZero(bounds: AvatarRenderableReport["bounds"]): boolean {
  if (!bounds) return false;
  return (
    finiteTuple(bounds.min) &&
    finiteTuple(bounds.max) &&
    finiteTuple(bounds.center) &&
    finiteNonZeroTuple(bounds.size)
  );
}

function buildRenderableReport(
  sourceKey: string,
  assetId: string,
  scene: THREE.Object3D,
  stats: AvatarGltfStats,
  probe: AvatarRenderProbeSnapshot,
  projection: AvatarProjectionSnapshot,
): AvatarRenderableReport {
  updateWorldFromSceneRoot(scene);
  const firstMesh = findFirstMesh(scene);
  const firstWorld = new THREE.Vector3();
  const firstScale = new THREE.Vector3();
  let firstMeshWorldPosition: [number, number, number] | null = null;
  let firstMeshWorldScale: [number, number, number] | null = null;
  let firstMaterialOpacity: number | null = null;
  let firstMaterialTransparent: boolean | null = null;
  if (firstMesh) {
    firstMesh.getWorldPosition(firstWorld);
    firstMesh.getWorldScale(firstScale);
    firstMeshWorldPosition = v3tuple(firstWorld);
    firstMeshWorldScale = v3tuple(firstScale);
    const material = firstMaterialSnapshot(firstMesh);
    firstMaterialOpacity = material.opacity;
    firstMaterialTransparent = material.transparent;
  }

  const bounds = stats.audit.bounds ?? null;
  const reportBase = {
    sourceKey,
    assetId,
    sceneUuid: scene.uuid,
    mounted: scene.parent != null,
    meshCount: stats.meshCount,
    visibleMeshCount: stats.visibleMeshCount,
    skinnedMeshCount: stats.skinnedMeshCount,
    materialCount: stats.materialCount,
    textureCount: stats.textureCount,
    boneCount: stats.rigInspection.boneCount,
    animationCount: stats.animationCount,
    triangleEstimate: stats.triangleEstimate,
    bounds,
    firstMeshName: firstMesh?.name || null,
    firstMeshWorldPosition,
    firstMeshWorldScale,
    firstMaterialOpacity,
    firstMaterialTransparent,
  };

  const hierarchyValid =
    !stats.assetFailureReason &&
    stats.meshCount > 0 &&
    stats.visibleMeshCount > 0 &&
    boundsAreFiniteNonZero(bounds) &&
    !(firstMaterialTransparent === true && (firstMaterialOpacity ?? 0) <= 0.01) &&
    finiteTuple(firstMeshWorldPosition) &&
    finiteNonZeroTuple(firstMeshWorldScale) &&
    stats.skinCloneAudit.valid;
  const mounted = reportBase.mounted;
  const renderConfirmed = probe.drawConfirmationCount >= 2 && projection.projectedBoundsVisible;
  const preflightValid = hierarchyValid;
  const mountValid = mounted;
  const renderValid = renderConfirmed;
  const promotionValid = preflightValid && mountValid && renderValid;

  let hierarchyReason = "hierarchy_valid";
  if (stats.assetFailureReason) hierarchyReason = stats.assetFailureReason;
  else if (stats.meshCount <= 0) hierarchyReason = "asset_has_no_meshes";
  else if (stats.visibleMeshCount <= 0) hierarchyReason = "asset_has_no_visible_meshes";
  else if (!boundsAreFiniteNonZero(bounds)) hierarchyReason = "asset_bounds_invalid";
  else if (firstMaterialTransparent === true && (firstMaterialOpacity ?? 0) <= 0.01) {
    hierarchyReason = "first_mesh_material_fully_transparent";
  } else if (!finiteTuple(firstMeshWorldPosition)) {
    hierarchyReason = "first_mesh_world_position_invalid";
  } else if (!finiteNonZeroTuple(firstMeshWorldScale)) {
    hierarchyReason = "first_mesh_world_scale_invalid";
  } else if (!stats.skinCloneAudit.valid) {
    hierarchyReason = stats.skinCloneAudit.reason;
  }

  const renderConfirmationReason = !hierarchyValid
    ? hierarchyReason
    : !mounted
      ? "scene_not_mounted"
      : probe.drawConfirmationCount <= 0
        ? "draw_pending"
        : probe.drawConfirmationCount < 2
          ? "draw_needs_second_frame"
          : !projection.projectedBoundsVisible
            ? projection.reason
            : "render_confirmed";
  const reason = promotionValid ? "promotion_valid" : renderConfirmationReason;

  return {
    ...reportBase,
    mounted,
    hierarchyValid,
    drawSubmitted: probe.drawSubmitted,
    drawConfirmationCount: probe.drawConfirmationCount,
    firstDrawTimestamp: probe.firstDrawTimestamp,
    lastDrawTimestamp: probe.lastDrawTimestamp,
    firstDrawFrame: probe.firstDrawFrame,
    lastDrawFrame: probe.lastDrawFrame,
    projectedBoundsVisible: projection.projectedBoundsVisible,
    cameraFrustumValid: projection.cameraFrustumValid,
    rendererCallCountAtConfirmation: probe.rendererCallCountAtConfirmation,
    rendererTriangleCountAtConfirmation: probe.rendererTriangleCountAtConfirmation,
    renderConfirmed,
    renderConfirmationReason,
    ndcMin: projection.ndcMin,
    ndcMax: projection.ndcMax,
    cameraDistance: projection.cameraDistance,
    cameraNear: projection.cameraNear,
    cameraFar: projection.cameraFar,
    preflightValid,
    mountValid,
    renderValid,
    promotionValid,
    skinCloneAudit: stats.skinCloneAudit,
    valid: promotionValid,
    reason,
  };
}

function useRenderableReport(
  sourceKey: string,
  assetId: string,
  scene: THREE.Object3D,
  stats: AvatarGltfStats,
  onRenderableReport: ((report: AvatarRenderableReport) => void) | undefined,
) {
  const camera = useThree((st) => st.camera);
  const lastReportJson = useRef("");
  const emittedPromotionRef = useRef(false);
  const probeRef = useRef<ReturnType<typeof createAvatarRenderProbe> | null>(null);
  const emit = () => {
    if (!onRenderableReport) return;
    const probe = probeRef.current?.snapshot() ?? {
      drawSubmitted: false,
      drawConfirmationCount: 0,
      firstDrawTimestamp: null,
      lastDrawTimestamp: null,
      firstDrawFrame: null,
      lastDrawFrame: null,
      rendererCallCountAtConfirmation: null,
      rendererTriangleCountAtConfirmation: null,
    };
    const projection = projectObjectBounds(scene, camera);
    const report = buildRenderableReport(sourceKey, assetId, scene, stats, probe, projection);
    const json = JSON.stringify(report);
    if (json !== lastReportJson.current) {
      lastReportJson.current = json;
      onRenderableReport(report);
    }
    if (report.promotionValid) emittedPromotionRef.current = true;
  };

  useLayoutEffect(() => {
    emittedPromotionRef.current = false;
    probeRef.current?.dispose();
    probeRef.current = createAvatarRenderProbe({
      root: scene,
      sourceKey,
      sceneUuid: scene.uuid,
    });
    emit();
    return () => {
      probeRef.current?.dispose();
      probeRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceKey, assetId, scene, stats, onRenderableReport]);

  useFrame(() => {
    probeRef.current?.tickFrame();
    if (emittedPromotionRef.current) return;
    emit();
  });
}

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
    if (!isMeshLike(o)) return;
    if (Array.isArray(o.material)) {
      for (const m of o.material) {
        if (m && isStandardMaterialLike(m)) out.push(m);
      }
    } else if (o.material && isStandardMaterialLike(o.material)) {
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
      case "overlay_debug":
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

type PreparedGltf = {
  scene: THREE.Object3D;
  baseline: Map<THREE.MeshStandardMaterial, MatBaseline>;
  stats: AvatarGltfStats;
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
    const { root, skinCloneAudit } = cloneGltfScene(gltf);
    const normalizeReport = normalizeAvatarScene(root, {
      expectedHeightMeters: normalizeY,
    });
    if (applyPelvisAlign) alignSkinnedRootToPelvisMetric(root, metrics);
    if (applyUntexturedFallbackMaterials) applySkinnedBodyFallbackMaterials(root);
    ensureBodyMeshesDrawable(root);
    const materialReport = normalizeAvatarPbrMaterials(root);
    const baseline = buildMaterialBaseline(root);
    const rigInspection = mapAvatarSkeleton(root).inspection;
    const audit = auditAvatarObject3D(root, {
      gltf,
      normalizeReport,
      materialTextureCount: materialReport.textureCount,
      materialSafetyStatus: materialReport.materialSafetyStatus,
    });
    return {
      scene: root,
      baseline,
      stats: {
        normalizeReport,
        rigInspection,
        audit,
        meshCount: audit.meshCount,
        visibleMeshCount: audit.visibleMeshCount,
        skinnedMeshCount: audit.skinnedMeshCount,
        materialCount: materialReport.materialCount || audit.materialCount,
        textureCount: audit.textureCount,
        materialNames: audit.materialNames,
        transparentMaterialCount: audit.transparentMaterialCount,
        triangleEstimate: audit.triangleEstimate,
        sceneChildCount: audit.sceneChildCount,
        worldScale: audit.worldScale,
        animationCount: audit.animationCount,
        materialSafetyStatus: audit.materialSafetyStatus,
        assetFailureReason: audit.failureReason,
        skinCloneAudit,
      },
    };
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
    if (isMeshLike(o)) {
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
      if (!o.material) {
        o.material = new THREE.MeshStandardMaterial({
          color: 0xdcc2a8,
          roughness: 0.88,
          metalness: 0,
        });
      }
      if (Array.isArray(o.material)) {
        for (const m of o.material) {
          m.depthWrite = true;
          m.depthTest = true;
          m.opacity = 1;
          m.transparent = false;
          m.side = THREE.DoubleSide;
          m.needsUpdate = true;
        }
      } else if (o.material) {
        o.material.depthWrite = true;
        o.material.depthTest = true;
        o.material.opacity = 1;
        o.material.transparent = false;
        o.material.side = THREE.DoubleSide;
        o.material.needsUpdate = true;
      }
    }
  });
  root.updateMatrixWorld(true);
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
    if (isMeshLike(o)) {
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
  stats: AvatarGltfStats,
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
          meshCount: stats.meshCount,
          visibleMeshCount: stats.visibleMeshCount,
          skinnedMeshCount: stats.skinnedMeshCount,
          materialCount: stats.materialCount,
          textureCount: stats.textureCount,
          materialNames: stats.materialNames,
          transparentMaterialCount: stats.transparentMaterialCount,
          triangleEstimate: stats.triangleEstimate,
          sceneChildCount: stats.sceneChildCount,
          worldScale: stats.worldScale,
          animationCount: stats.animationCount,
          materialSafetyStatus: stats.materialSafetyStatus,
          boneCount: stats.rigInspection.boneCount,
          boundsHeight: stats.normalizeReport.height,
          rigTypeGuess: stats.rigInspection.rigTypeGuess,
          rigConfidence: stats.rigInspection.confidence,
          assetFailureReason: stats.assetFailureReason,
          skinCloneAudit: stats.skinCloneAudit,
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
        meshCount: stats.meshCount,
        visibleMeshCount: stats.visibleMeshCount,
        skinnedMeshCount: stats.skinnedMeshCount,
        materialCount: stats.materialCount,
        textureCount: stats.textureCount,
        materialNames: stats.materialNames,
        transparentMaterialCount: stats.transparentMaterialCount,
        triangleEstimate: stats.triangleEstimate,
        sceneChildCount: stats.sceneChildCount,
        worldScale: stats.worldScale,
        animationCount: stats.animationCount,
        materialSafetyStatus: stats.materialSafetyStatus,
        boneCount: stats.rigInspection.boneCount,
        boundsHeight: stats.normalizeReport.height,
        rigTypeGuess: stats.rigInspection.rigTypeGuess,
        rigConfidence: stats.rigInspection.confidence,
        assetFailureReason: stats.assetFailureReason,
        skinCloneAudit: stats.skinCloneAudit,
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
    stats,
    invalidate,
  ]);
}

type GltfRuntimeBodyShared = {
  sourceKey: string;
  assetId: string;
  pose: DevAvatarPoseKey;
  liveShading: LiveViewportShadingMode;
  bodyShape?: BodyShapeParams;
  enableSkinnedRig?: boolean;
  /** Extra pose deltas for skinned bind vs procedural rig. */
  poseBias?: SkinnedPoseBias;
  onSceneReady?: () => void;
  /** Dev: skinned bone pose / map status for live diagnostics. */
  onRigPoseReport?: (r: SkinnedRigPoseReport) => void;
  onRenderableReport?: (report: AvatarRenderableReport) => void;
  /** Dev: loud unlit-ish standard material + no frustum cull — visibility proof only. */
  debugForceBrightMaterial?: boolean;
};

/** Bundled module: Android-safe parse path (no `file://` in GLTFLoader). */
export function GltfRuntimeBodyFromBundledModule({
  bundledAssetModule,
  sourceKey,
  assetId,
  pose,
  liveShading,
  bodyShape = DEFAULT_BODY_SHAPE,
  enableSkinnedRig = true,
  poseBias,
  onSceneReady,
  onRigPoseReport,
  onRenderableReport,
  debugForceBrightMaterial,
}: GltfRuntimeBodyShared & { bundledAssetModule: number }) {
  const gltf = use(useMemo(() => loadBundledGltfModule(bundledAssetModule), [bundledAssetModule]));
  const bodyShapeKeyStr = bodyShapeParamsKey(bodyShape);
  const m = useMemo(() => deriveBodyRigMetrics(bodyShape), [bodyShapeKeyStr]);
  const { scene, baseline, stats } = usePreparedGltf(
    `bundled:${bundledAssetModule}`,
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
    stats,
    debugForceBrightMaterial,
  );
  useRenderableReport(sourceKey, assetId, scene, stats, onRenderableReport);

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
  sourceKey,
  assetId,
  pose,
  liveShading,
  bodyShape = DEFAULT_BODY_SHAPE,
  enableSkinnedRig = true,
  poseBias,
  onSceneReady,
  onRigPoseReport,
  onRenderableReport,
  debugForceBrightMaterial,
}: GltfRuntimeBodyShared & { url: string }) {
  const gltf = useLoader(GLTFLoader, url);
  const bodyShapeKeyStr = bodyShapeParamsKey(bodyShape);
  const m = useMemo(() => deriveBodyRigMetrics(bodyShape), [bodyShapeKeyStr]);
  const { scene, baseline, stats } = usePreparedGltf(
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
    stats,
    debugForceBrightMaterial,
  );
  useRenderableReport(sourceKey, assetId, scene, stats, onRenderableReport);

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
        sourceKey={props.sourceKey}
        assetId={props.assetId}
        pose={props.pose}
        liveShading={props.liveShading}
        bodyShape={props.bodyShape}
        enableSkinnedRig={props.enableSkinnedRig}
        poseBias={props.poseBias}
        onSceneReady={props.onSceneReady}
        onRigPoseReport={props.onRigPoseReport}
        onRenderableReport={props.onRenderableReport}
        debugForceBrightMaterial={props.debugForceBrightMaterial}
      />
    );
  }
  if (props.url) {
    return (
      <GltfRuntimeBodyFromUrl
        url={props.url}
        sourceKey={props.sourceKey}
        assetId={props.assetId}
        pose={props.pose}
        liveShading={props.liveShading}
        bodyShape={props.bodyShape}
        enableSkinnedRig={props.enableSkinnedRig}
        poseBias={props.poseBias}
        onSceneReady={props.onSceneReady}
        onRigPoseReport={props.onRigPoseReport}
        onRenderableReport={props.onRenderableReport}
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
    const root = SkeletonUtils.clone(gltf.scene) as THREE.Object3D;
    normalizeAvatarScene(root, { expectedHeightMeters: normalizeHeight });
    normalizeAvatarPbrMaterials(root);
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
      if (isMeshLike(o)) o.updateMatrixWorld(true);
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
