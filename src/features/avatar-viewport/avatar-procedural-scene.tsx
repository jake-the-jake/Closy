import { useFrame, useThree } from "@react-three/fiber/native";
import { Suspense, useCallback, useLayoutEffect, useMemo, useRef } from "react";
import type { RefObject } from "react";
import * as THREE from "three";

import type { GarmentFitState } from "@/features/avatar-export";
import {
  bodySceneAnchorsFromShape,
  bodyShapeParamsKey,
  DEFAULT_BODY_SHAPE,
  type BodySceneAnchors,
  type BodyShapeParams,
} from "@/features/avatar-export";
import {
  DEV_AVATAR_PRESETS,
  type DevAvatarPoseKey,
  type DevAvatarPresetKey,
  presetGarmentColors,
} from "@/features/avatar-export/dev-avatar-shared";

import { poseAngles, type PoseAngleSet } from "./avatar-pose-angles";
import {
  applySleeveGarmentDeformation,
  applyTopGarmentDeformation,
  deformGarmentObject3D,
  type GarmentPoseSkinningParams,
} from "./garment-deformation";
import { GARMENT_POSE_BIND_POSE } from "./garment-rig-pose";
import {
  GltfErrorBoundary,
  GltfRuntimeBody,
  GltfRuntimeGarment,
} from "./gltf-runtime-body";
import type {
  AvatarRenderAudit,
  GarmentAnchorFitDebug,
  GarmentAttachmentSnapshot,
  LiveViewportSceneDiagnostics,
  SkinnedRigPoseReport,
} from "./live-viewport-debug-types";
import {
  ViewportSceneSpaceDebug,
  type SceneSpaceDebugOrbitBindings,
} from "./avatar-viewport-scene-debug";
import {
  PROCEDURAL_HUMANOID_JOINTS,
  HUMANOID_PROPORTIONS,
  averageJoints,
  buildProceduralGarmentFollowPoints,
  buildProceduralHumanoidJointMap,
  jointVector,
  type ProceduralHumanoidJointMap,
  type ProceduralHumanoidJointName,
} from "./procedural-humanoid-v2";
import { buildFitProxiesFromAnchors, type AvatarAnchorMap } from "./avatar-anchors";
import { SkinnedGarmentAttachmentDriver } from "./skinned-garment-attachment-driver";
import type { LiveViewportShadingMode } from "./live-viewport-shading";
import type { AvatarViewportNavSettings } from "./avatar-viewport-nav-settings";

const SKIN = new THREE.Color(0xdcc2a8);
const SKIN_DIM = new THREE.Color(0xb39073);

/**
 * Scene-space anchors (meters-ish, ~1.78m footprint). Ground y=0; rig built upward.
 * Synced with `bodySceneAnchorsFromShape(DEFAULT_BODY_SHAPE)` — do not hand-edit.
 */
const _DEFAULT_SCENE_RIG = bodySceneAnchorsFromShape(DEFAULT_BODY_SHAPE);
export const AVATAR_RIG_ANCHORS = {
  pelvisY: _DEFAULT_SCENE_RIG.pelvisY,
  chestY: _DEFAULT_SCENE_RIG.chestY,
  shoulderY: _DEFAULT_SCENE_RIG.shoulderY,
  shoulderHalf: _DEFAULT_SCENE_RIG.shoulderHalf,
  headY: _DEFAULT_SCENE_RIG.headY,
  pantsProxyHemY: _DEFAULT_SCENE_RIG.pantsProxyHemY,
  gltfTopMountY: _DEFAULT_SCENE_RIG.gltfTopMountY,
  gltfBottomMountY: _DEFAULT_SCENE_RIG.gltfBottomMountY,
} as const;

/** Live fit UX: amplify region sliders so changes read clearly in-viewport. */
const FIT_VIS = {
  torsoOffsetZ: 3.4,
  torsoOffsetY: 0.42,
  torsoInflateMul: 3.2,
  torsoInflateYMul: 1.35,
  waistOffsetZ: 2.6,
  sleevePosMul: 1.75,
  globalGarmentInflate: 1.85,
} as const;

function v3tuple(v: THREE.Vector3): [number, number, number] {
  return [v.x, v.y, v.z];
}

function toVec3Array(
  value: THREE.Vector3 | readonly number[] | null | undefined,
  fallback: [number, number, number] = [0, 0, 0],
): [number, number, number] {
  if (value instanceof THREE.Vector3) {
    return [
      Number.isFinite(value.x) ? value.x : fallback[0],
      Number.isFinite(value.y) ? value.y : fallback[1],
      Number.isFinite(value.z) ? value.z : fallback[2],
    ];
  }
  const x = value?.[0];
  const y = value?.[1];
  const z = value?.[2];
  return [
    typeof x === "number" && Number.isFinite(x) ? x : fallback[0],
    typeof y === "number" && Number.isFinite(y) ? y : fallback[1],
    typeof z === "number" && Number.isFinite(z) ? z : fallback[2],
  ];
}

function toScaleArray(
  value: THREE.Vector3 | readonly number[] | null | undefined,
  fallback: [number, number, number] = [1, 1, 1],
): [number, number, number] {
  const s = toVec3Array(value, fallback);
  return [
    Math.abs(s[0]) > 1e-6 ? s[0] : fallback[0],
    Math.abs(s[1]) > 1e-6 ? s[1] : fallback[1],
    Math.abs(s[2]) > 1e-6 ? s[2] : fallback[2],
  ];
}

function toEulerArray(
  value: THREE.Euler | readonly number[] | null | undefined,
  fallback: [number, number, number] = [0, 0, 0],
): [number, number, number] {
  if (value instanceof THREE.Euler) {
    return [
      Number.isFinite(value.x) ? value.x : fallback[0],
      Number.isFinite(value.y) ? value.y : fallback[1],
      Number.isFinite(value.z) ? value.z : fallback[2],
    ];
  }
  return toVec3Array(value, fallback);
}

function toQuaternionArray(
  value: THREE.Quaternion | readonly number[] | null | undefined,
): [number, number, number, number] {
  if (value instanceof THREE.Quaternion) {
    return [
      Number.isFinite(value.x) ? value.x : 0,
      Number.isFinite(value.y) ? value.y : 0,
      Number.isFinite(value.z) ? value.z : 0,
      Number.isFinite(value.w) ? value.w : 1,
    ];
  }
  const x = value?.[0];
  const y = value?.[1];
  const z = value?.[2];
  const w = value?.[3];
  return [
    typeof x === "number" && Number.isFinite(x) ? x : 0,
    typeof y === "number" && Number.isFinite(y) ? y : 0,
    typeof z === "number" && Number.isFinite(z) ? z : 0,
    typeof w === "number" && Number.isFinite(w) ? w : 1,
  ];
}

function segmentFrame(from: THREE.Vector3, to: THREE.Vector3) {
  const delta = to.clone().sub(from);
  const length = Math.max(0.001, delta.length());
  const center = from.clone().addScaledVector(delta, 0.5);
  const quat = new THREE.Quaternion().setFromUnitVectors(
    new THREE.Vector3(0, 1, 0),
    delta.normalize(),
  );
  return {
    center: v3tuple(center),
    quaternion: [quat.x, quat.y, quat.z, quat.w] as [number, number, number, number],
    shaftLength: Math.max(0.001, length),
  };
}

function blendColor(base: THREE.Color, scalar: number) {
  return base.clone().multiplyScalar(scalar);
}


/** Spherical orbit: theta = yaw around world +Y, phi = polar from +Y, radius = distance to target. */
export type OrbitSpherical = { theta: number; phi: number; radius: number };

function lerpAngleShortest(from: number, to: number, t: number): number {
  let d = to - from;
  while (d > Math.PI) d -= 2 * Math.PI;
  while (d < -Math.PI) d += 2 * Math.PI;
  return from + d * t;
}

/**
 * Target-orbit camera with exponential smoothing toward `desiredRef` (mutated by gesture layer).
 * Y-up, no roll: `camera.up` stays world Y.
 */
export function CameraRig({
  desiredRef,
  smoothRef,
  navRef,
  targetBaseRef,
  targetPanRef,
  orbitGestureActiveRef,
}: {
  desiredRef: RefObject<OrbitSpherical>;
  smoothRef: RefObject<OrbitSpherical>;
  navRef: RefObject<AvatarViewportNavSettings>;
  /** Mutable look-at base (world); framing tools rewrite this while pan adds delta on top. */
  targetBaseRef: RefObject<[number, number, number]>;
  targetPanRef: RefObject<{ x: number; z: number }>;
  /** When true (during pan/pinch), snap smoothed orbit to desired for low-latency interaction. */
  orbitGestureActiveRef?: RefObject<boolean>;
}) {
  const { camera, clock } = useThree();
  const target = useMemo(() => new THREE.Vector3(), []);

  useFrame(() => {
    const nav = navRef.current;
    const d = desiredRef.current;
    const s = smoothRef.current;
    const dt = Math.min(clock.getDelta(), 0.08);
    const gesture = orbitGestureActiveRef?.current === true;
    const k = gesture ? 0.28 : 1 - Math.exp(-nav.damping * 14 * dt);

    s.theta = lerpAngleShortest(s.theta, d.theta, k);
    s.phi = THREE.MathUtils.lerp(s.phi, d.phi, k);
    s.radius = THREE.MathUtils.lerp(s.radius, d.radius, k);

    s.phi = Math.min(nav.polarMax, Math.max(nav.polarMin, s.phi));
    s.radius = Math.min(nav.maxRadius, Math.max(nav.minRadius, s.radius));

    const pan = targetPanRef.current;
    const tb = targetBaseRef.current ?? [0, 1.12, 0];
    target.set(tb[0] + pan.x, tb[1] + nav.targetYOffset, tb[2] + pan.z);

    const { theta, phi, radius } = s;
    const x = target.x + radius * Math.sin(phi) * Math.cos(theta);
    const y = target.y + radius * Math.cos(phi);
    const z = target.z + radius * Math.sin(phi) * Math.sin(theta);
    camera.position.set(x, y, z);
    camera.up.set(0, 1, 0);
    camera.lookAt(target);
    if (nav.enableRoll) {
      // Rare dev toggle: keep default identity roll.
    }
    camera.updateProjectionMatrix();
  });
  return null;
}

export { poseAngles } from "./avatar-pose-angles";

type RigMaterialProps = {
  rig: BodySceneAnchors;
  ang: PoseAngleSet;
  jointMap: ProceduralHumanoidJointMap;
  garmentPoseSkin: GarmentPoseSkinningParams;
  bodyColor: THREE.Color;
  bodyOpacity: number;
  bodyEmissive: THREE.Color;
  liveShading: LiveViewportShadingMode;
  shirtOpacity: number;
  topColor: THREE.Color;
  topEmissive: THREE.Color;
  clipEmissiveSleeve?: THREE.Color | null;
  sleeveS: number;
  sleevePos: [number, number, number];
  garmentFit: GarmentFitState;
};

type StartupVisibilityReport = {
  sceneReady: boolean;
  visibleMeshCount: number;
  bodyGroupVisible: boolean;
  garmentGroupVisible: boolean;
  startupReason: string;
  renderAudit?: AvatarRenderAudit | null;
};

function isDrawableMesh(o: THREE.Object3D): o is THREE.Mesh | THREE.SkinnedMesh {
  const flags = o as { isMesh?: boolean; isSkinnedMesh?: boolean };
  return flags.isMesh === true || flags.isSkinnedMesh === true;
}

function materialList(o: THREE.Mesh | THREE.SkinnedMesh): THREE.Material[] {
  const material = o.material;
  if (Array.isArray(material)) return material.filter(Boolean);
  return material ? [material] : [];
}

function firstMaterialSnapshot(o: THREE.Mesh | THREE.SkinnedMesh): {
  opacity: number | null;
  transparent: boolean | null;
} {
  const mat = materialList(o)[0] as
    | (THREE.Material & { opacity?: number; transparent?: boolean })
    | undefined;
  return {
    opacity: typeof mat?.opacity === "number" && Number.isFinite(mat.opacity) ? mat.opacity : null,
    transparent: typeof mat?.transparent === "boolean" ? mat.transparent : null,
  };
}

function repairDrawableHierarchy(
  root: THREE.Object3D | null | undefined,
  countRoot: THREE.Object3D | null | undefined = root,
): number {
  if (!root) return 0;
  let visibleMeshCount = 0;
  root.visible = true;
  root.matrixAutoUpdate = true;
  root.scale.set(
    Number.isFinite(root.scale.x) && Math.abs(root.scale.x) > 1e-6 ? root.scale.x : 1,
    Number.isFinite(root.scale.y) && Math.abs(root.scale.y) > 1e-6 ? root.scale.y : 1,
    Number.isFinite(root.scale.z) && Math.abs(root.scale.z) > 1e-6 ? root.scale.z : 1,
  );
  root.traverse((o) => {
    o.visible = true;
    o.matrixAutoUpdate = true;
    if (!Number.isFinite(o.scale.x) || Math.abs(o.scale.x) <= 1e-6) o.scale.x = 1;
    if (!Number.isFinite(o.scale.y) || Math.abs(o.scale.y) <= 1e-6) o.scale.y = 1;
    if (!Number.isFinite(o.scale.z) || Math.abs(o.scale.z) <= 1e-6) o.scale.z = 1;
    if (isDrawableMesh(o)) {
      if (!countRoot || o === countRoot || isDescendantOf(o, countRoot)) visibleMeshCount += 1;
      o.visible = true;
      o.frustumCulled = false;
      if (!o.material) {
        o.material = new THREE.MeshStandardMaterial({
          color: 0xdcc2a8,
          roughness: 0.88,
          metalness: 0,
        });
      }
      for (const mat of materialList(o)) {
        if (!mat) continue;
        if ("transparent" in mat && "opacity" in mat) {
          mat.transparent = false;
          mat.opacity = 1;
        }
        if ("depthWrite" in mat) mat.depthWrite = true;
        if ("depthTest" in mat) mat.depthTest = true;
        if ("side" in mat) mat.side = THREE.DoubleSide;
        if ("needsUpdate" in mat) mat.needsUpdate = true;
      }
    }
  });
  root.updateMatrixWorld(true);
  return visibleMeshCount;
}

function isDescendantOf(o: THREE.Object3D, root: THREE.Object3D): boolean {
  let p: THREE.Object3D | null = o;
  while (p) {
    if (p === root) return true;
    p = p.parent;
  }
  return false;
}

function countDrawableMeshes(root: THREE.Object3D | null | undefined): {
  total: number;
  visible: number;
  first: THREE.Mesh | THREE.SkinnedMesh | null;
} {
  if (!root) return { total: 0, visible: 0, first: null };
  let total = 0;
  let visible = 0;
  let first: THREE.Mesh | THREE.SkinnedMesh | null = null;
  root.traverse((o) => {
    if (!isDrawableMesh(o)) return;
    total += 1;
    if (o.visible) visible += 1;
    first ??= o;
  });
  return { total, visible, first };
}

function auditDrawableHierarchy({
  root,
  gltfRoot,
  activeRenderBranchName,
  safetyFallbackReason,
}: {
  root: THREE.Object3D | null | undefined;
  gltfRoot: THREE.Object3D | null | undefined;
  activeRenderBranchName: string;
  safetyFallbackReason: string | null;
}): AvatarRenderAudit {
  repairDrawableHierarchy(root);
  const total = countDrawableMeshes(root);
  const gltf = countDrawableMeshes(gltfRoot);
  const firstWorld = new THREE.Vector3();
  const firstScale = new THREE.Vector3();
  let firstMeshWorldPosition: [number, number, number] | null = null;
  let firstMeshScale: [number, number, number] | null = null;
  let firstMeshMaterialOpacity: number | null = null;
  let firstMeshMaterialTransparent: boolean | null = null;

  if (total.first) {
    total.first.getWorldPosition(firstWorld);
    total.first.getWorldScale(firstScale);
    firstMeshWorldPosition = v3tuple(firstWorld);
    firstMeshScale = v3tuple(firstScale);
    const mat = firstMaterialSnapshot(total.first);
    firstMeshMaterialOpacity = mat.opacity;
    firstMeshMaterialTransparent = mat.transparent;
  }

  return {
    activeRenderBranchName,
    mountedAvatarRoot: !!root,
    totalMeshCount: total.total,
    visibleMeshCount: total.visible,
    gltfTotalMeshCount: gltf.total,
    gltfVisibleMeshCount: gltf.visible,
    firstMeshWorldPosition,
    firstMeshScale,
    firstMeshMaterialOpacity,
    firstMeshMaterialTransparent,
    safetyFallbackReason,
  };
}

function CapsuleBetween({
  name,
  start,
  end,
  radius,
  color,
  opacity = 1,
  emissive,
  roughness = 0.62,
  transparent = true,
}: {
  name: string;
  start: THREE.Vector3;
  end: THREE.Vector3;
  radius: number;
  color: THREE.Color;
  opacity?: number;
  emissive?: THREE.Color;
  roughness?: number;
  transparent?: boolean;
}) {
  const frame = useMemo(() => segmentFrame(start, end), [start, end]);
  return (
    <mesh
      name={name}
      position={toVec3Array(frame.center)}
      quaternion={toQuaternionArray(frame.quaternion)}
      castShadow
    >
      <capsuleGeometry args={[radius, Math.max(0.001, frame.shaftLength - radius * 2), 12, 22]} />
      <meshStandardMaterial
        color={color}
        transparent={transparent}
        opacity={opacity}
        emissive={emissive}
        roughness={roughness}
      />
    </mesh>
  );
}

function EllipsoidMesh({
  name,
  position,
  scale,
  rotation,
  color,
  opacity = 1,
  emissive,
  roughness = 0.62,
  transparent = true,
}: {
  name: string;
  position: [number, number, number];
  scale: [number, number, number];
  rotation?: [number, number, number];
  color: THREE.Color;
  opacity?: number;
  emissive?: THREE.Color;
  roughness?: number;
  transparent?: boolean;
}) {
  return (
    <mesh
      name={name}
      position={toVec3Array(position)}
      rotation={toEulerArray(rotation)}
      scale={toScaleArray(scale)}
      castShadow
    >
      <sphereGeometry args={[1, 22, 18]} />
      <meshStandardMaterial
        color={color}
        transparent={transparent}
        opacity={opacity}
        emissive={emissive}
        roughness={roughness}
      />
    </mesh>
  );
}

function TaperedSectionMesh({
  name,
  center,
  height,
  topWidth,
  bottomWidth,
  depth,
  color,
  opacity = 1,
  emissive,
  roughness = 0.72,
  transparent = true,
}: {
  name: string;
  center: THREE.Vector3;
  height: number;
  topWidth: number;
  bottomWidth: number;
  depth: number;
  color: THREE.Color;
  opacity?: number;
  emissive?: THREE.Color;
  roughness?: number;
  transparent?: boolean;
}) {
  return (
    <mesh
      name={name}
      position={toVec3Array(center)}
      scale={toScaleArray([1, 1, depth / Math.max(0.001, (topWidth + bottomWidth) * 0.5)])}
      castShadow
    >
      <cylinderGeometry
        args={[
          Math.max(0.001, topWidth * 0.5),
          Math.max(0.001, bottomWidth * 0.5),
          Math.max(0.001, height),
          32,
          3,
        ]}
      />
      <meshStandardMaterial
        color={color}
        transparent={transparent}
        opacity={opacity}
        emissive={emissive}
        roughness={roughness}
      />
    </mesh>
  );
}

function GarmentSleeveProxyMesh({
  garmentFit,
  start,
  end,
  shirtOpacity,
  topColor,
  topEmissive,
  clipEmissiveAdd,
  sleeveRadius,
}: {
  garmentFit: GarmentFitState;
  start: THREE.Vector3;
  end: THREE.Vector3;
  shirtOpacity: number;
  topColor: THREE.Color;
  topEmissive: THREE.Color;
  clipEmissiveAdd?: THREE.Color | null;
  sleeveRadius: number;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const frame = useMemo(() => segmentFrame(start, end), [start, end]);
  useLayoutEffect(() => {
    const m = meshRef.current;
    if (!m?.geometry) return;
    /** Pose is already applied by parent arm groups; only regional fit here. */
    applySleeveGarmentDeformation(m.geometry, garmentFit);
  }, [garmentFit]);
  const sleeveEmissive = useMemo(() => {
    const e = topEmissive.clone();
    if (clipEmissiveAdd) e.add(clipEmissiveAdd);
    return e;
  }, [topEmissive, clipEmissiveAdd]);
  return (
    <mesh
      ref={meshRef}
      position={toVec3Array(frame.center)}
      quaternion={toQuaternionArray(frame.quaternion)}
      castShadow
    >
      <capsuleGeometry
        args={[
          sleeveRadius,
          Math.max(0.001, frame.shaftLength - sleeveRadius * 2),
          10,
          20,
        ]}
      />
      <meshStandardMaterial
        color={topColor}
        transparent
        opacity={shirtOpacity}
        emissive={sleeveEmissive}
        roughness={0.75}
      />
    </mesh>
  );
}

/** Shirt torso only (sleeves follow arms inside `ProceduralRigBody`). */
function ShirtTorsoProxy({
  rig,
  jointMap,
  garmentPoseSkin,
  topColor,
  shirtOpacity,
  topEmissive,
  clipEmissiveAdd,
  garmentFit,
  inflateK,
  torsoMountMode = "rig_chest",
}: {
  rig: BodySceneAnchors;
  jointMap: ProceduralHumanoidJointMap;
  garmentPoseSkin: GarmentPoseSkinningParams;
  topColor: THREE.Color;
  shirtOpacity: number;
  topEmissive: THREE.Color;
  clipEmissiveAdd?: THREE.Color | null;
  garmentFit: GarmentFitState;
  inflateK: number;
  /** `skinned_chest`: anchor group is already at bone chest — use small offset only. */
  torsoMountMode?: "rig_chest" | "skinned_chest";
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  useLayoutEffect(() => {
    const m = meshRef.current;
    if (!m?.geometry) return;
    applyTopGarmentDeformation(m.geometry, garmentFit, garmentPoseSkin);
  }, [garmentFit, garmentPoseSkin]);
  const shirtEmissive = useMemo(() => {
    const e = topEmissive.clone();
    if (clipEmissiveAdd) e.add(clipEmissiveAdd);
    return e;
  }, [topEmissive, clipEmissiveAdd]);
  const P = HUMANOID_PROPORTIONS;
  const follow = useMemo(() => buildProceduralGarmentFollowPoints(jointMap), [jointMap]);
  const topCenter = torsoMountMode === "skinned_chest"
    ? new THREE.Vector3(0, P.chestY - rig.chestY - 0.045, 0.01)
    : follow.topCenter.clone().add(new THREE.Vector3(0, -0.036, 0.012));
  const shirtHeight = P.topShellScale[1] * 1.28 * inflateK;
  const shoulderWidth = P.chestWidth * 1.08 * inflateK;
  const hemWidth = P.waistWidth * 1.18 * inflateK;
  const shirtDepth = P.chestDepth * 1.18 * inflateK;
  const collarY = topCenter.y + shirtHeight * 0.45;
  const shoulderSeamY = topCenter.y + shirtHeight * 0.35;
  const seamL = follow.topLeftShoulder.clone().lerp(new THREE.Vector3(-0.028, shoulderSeamY, 0.03), 0.18);
  const seamR = follow.topRightShoulder.clone().lerp(new THREE.Vector3(0.028, shoulderSeamY, 0.03), 0.18);
  return (
    <group name="shirt_torso_proxy">
      <mesh
        ref={meshRef}
        name="shirt_torso_shell"
        position={toVec3Array(topCenter)}
        scale={toScaleArray([1, 1, shirtDepth / Math.max(0.001, (shoulderWidth + hemWidth) * 0.5)])}
        castShadow
      >
        <cylinderGeometry args={[shoulderWidth * 0.5, hemWidth * 0.5, shirtHeight, 32, 3]} />
        <meshStandardMaterial
          color={topColor}
          transparent
          opacity={shirtOpacity}
          emissive={shirtEmissive}
          roughness={0.82}
        />
      </mesh>
      <mesh
        name="shirt_neck_opening"
        position={toVec3Array([0, collarY, 0.035])}
        rotation={toEulerArray([Math.PI / 2, 0, 0])}
        scale={toScaleArray([1.04, 0.58, 1])}
      >
        <torusGeometry args={[0.058, 0.006, 10, 32]} />
        <meshStandardMaterial
          color={topColor}
          transparent
          opacity={shirtOpacity}
          emissive={shirtEmissive}
          roughness={0.86}
        />
      </mesh>
      <CapsuleBetween
        name="shirt_shoulder_line"
        start={seamL}
        end={seamR}
        radius={0.012}
        color={topColor}
        opacity={shirtOpacity}
        emissive={shirtEmissive}
        roughness={0.86}
      />
    </group>
  );
}

function PantsGarmentProxies({
  rig,
  jointMap,
  garmentPoseSkin,
  bottomColor,
  pantOpacity,
  bottomEmissive,
  clipEmissiveAdd,
  hemYOffset,
  garmentFit,
  bottomMountMode = "rig",
}: {
  rig: BodySceneAnchors;
  jointMap: ProceduralHumanoidJointMap;
  garmentPoseSkin: GarmentPoseSkinningParams;
  bottomColor: THREE.Color;
  pantOpacity: number;
  bottomEmissive: THREE.Color;
  clipEmissiveAdd?: THREE.Color | null;
  hemYOffset: number;
  garmentFit: GarmentFitState;
  /** When parent anchor sits on skinned pelvis, use shorter proxy stack. */
  bottomMountMode?: "rig" | "skinned_pelvis";
}) {
  const follow = useMemo(() => buildProceduralGarmentFollowPoints(jointMap), [jointMap]);
  const groupRef = useRef<THREE.Group>(null);
  useLayoutEffect(() => {
    const root = groupRef.current;
    if (!root) return;
    deformGarmentObject3D(root, garmentFit, "bottom", garmentPoseSkin);
  }, [garmentFit, garmentPoseSkin]);
  const pantsEmissive = useMemo(() => {
    const e = bottomEmissive.clone();
    if (clipEmissiveAdd) e.add(clipEmissiveAdd);
    return e;
  }, [bottomEmissive, clipEmissiveAdd]);
  const P = HUMANOID_PROPORTIONS;
  const bottomCenter =
    bottomMountMode === "skinned_pelvis"
      ? new THREE.Vector3(0, P.pelvisY - rig.pelvisY - 0.03 + hemYOffset * 0.2, 0.002)
      : follow.bottomCenter.clone().add(new THREE.Vector3(0, -0.044 + hemYOffset * 0.2, 0.002));
  const waistWidth = P.waistWidth * 1.18;
  const hipWidth = P.pelvisWidth * 1.03;
  const pantsDepth = P.pelvisDepth * 1.1;
  const pantsRise = P.bottomShellScale[1] * 1.02;
  const thighUpperL = jointVector(jointMap, "hipL")
    .clone()
    .lerp(jointVector(jointMap, "ankleL"), 0.9)
    .add(new THREE.Vector3(0.006, hemYOffset * 0.5, 0));
  const thighUpperR = jointVector(jointMap, "hipR")
    .clone()
    .lerp(jointVector(jointMap, "ankleR"), 0.9)
    .add(new THREE.Vector3(-0.006, hemYOffset * 0.5, 0));
  return (
    <group ref={groupRef}>
      <mesh
        name="pants_waist_hip_shell"
        position={toVec3Array(bottomCenter)}
        scale={toScaleArray([1, 1, pantsDepth / Math.max(0.001, (waistWidth + hipWidth) * 0.5)])}
        castShadow
      >
        <cylinderGeometry args={[waistWidth * 0.5, hipWidth * 0.5, pantsRise, 32, 3]} />
        <meshStandardMaterial
          color={bottomColor}
          transparent
          opacity={pantOpacity}
          emissive={pantsEmissive}
          roughness={0.82}
        />
      </mesh>
      <CapsuleBetween
        name="pants_leg_l"
        start={jointVector(jointMap, "hipL")}
        end={thighUpperL}
        radius={P.thighRadius * 0.98}
        color={bottomColor}
        opacity={pantOpacity}
        emissive={pantsEmissive}
        roughness={0.68}
      />
      <CapsuleBetween
        name="pants_leg_r"
        start={jointVector(jointMap, "hipR")}
        end={thighUpperR}
        radius={P.thighRadius * 0.98}
        color={bottomColor}
        opacity={pantOpacity}
        emissive={pantsEmissive}
        roughness={0.68}
      />
    </group>
  );
}

function RigDebugAnchors({ jointMap }: { jointMap: ProceduralHumanoidJointMap }) {
  const radius = 0.018;
  const chainColor = new THREE.Color("#67e8f9");
  const edges: [ProceduralHumanoidJointName, ProceduralHumanoidJointName][] = [
    ["pelvis", "spine"],
    ["spine", "waist"],
    ["spine", "chest"],
    ["chest", "neck"],
    ["neck", "head"],
    ["chest", "shoulderL"],
    ["shoulderL", "elbowL"],
    ["elbowL", "wristL"],
    ["chest", "shoulderR"],
    ["shoulderR", "elbowR"],
    ["elbowR", "wristR"],
    ["pelvis", "hips"],
    ["hips", "hipL"],
    ["hipL", "kneeL"],
    ["kneeL", "ankleL"],
    ["ankleL", "footL"],
    ["hips", "hipR"],
    ["hipR", "kneeR"],
    ["kneeR", "ankleR"],
    ["ankleR", "footR"],
  ];
  return (
    <group name="skeleton_overlay">
      {edges.map(([from, to]) => (
        <CapsuleBetween
          key={`${from}-${to}`}
          name={`skeleton_${from}_${to}`}
          start={jointVector(jointMap, from)}
          end={jointVector(jointMap, to)}
          radius={0.009}
          color={chainColor}
          roughness={0.2}
          emissive={chainColor.clone().multiplyScalar(0.25)}
        />
      ))}
      {PROCEDURAL_HUMANOID_JOINTS.map((joint) => (
        <mesh key={joint} position={toVec3Array(jointMap[joint])}>
          <sphereGeometry args={[radius, 8, 8]} />
          <meshBasicMaterial color="#f59e0b" depthTest={false} />
        </mesh>
      ))}
    </group>
  );
}

/** Dev: garment anchor pivots from the shared mannequin map. */
function GarmentRigDebugOverlay({ jointMap }: { jointMap: ProceduralHumanoidJointMap }) {
  const pts: [string, [number, number, number]][] = [
    ["g_chest", jointMap.chest],
    ["g_waist", jointMap.waist],
    ["g_hips", jointMap.hips],
    ["g_l_shoulder", jointMap.shoulderL],
    ["g_r_shoulder", jointMap.shoulderR],
    ["g_l_hip", jointMap.hipL],
    ["g_r_hip", jointMap.hipR],
  ];
  return (
    <group name="garment_rig_debug">
      {pts.map(([id, pos]) => (
        <mesh key={id} position={toVec3Array(pos)}>
          <sphereGeometry args={[0.024, 7, 7]} />
          <meshBasicMaterial color="#db2777" depthTest={false} />
        </mesh>
      ))}
    </group>
  );
}

function anchorMapFromProceduralJoints(
  jointMap: ProceduralHumanoidJointMap,
): AvatarAnchorMap {
  return {
    head: jointMap.head,
    neck: jointMap.neck,
    chest: jointMap.chest,
    waist: jointMap.waist,
    hips: jointMap.hips,
    shoulderL: jointMap.shoulderL,
    elbowL: jointMap.elbowL,
    wristL: jointMap.wristL,
    shoulderR: jointMap.shoulderR,
    elbowR: jointMap.elbowR,
    wristR: jointMap.wristR,
    thighL: jointMap.hipL,
    kneeL: jointMap.kneeL,
    ankleL: jointMap.ankleL,
    footL: jointMap.footL,
    thighR: jointMap.hipR,
    kneeR: jointMap.kneeR,
    ankleR: jointMap.ankleR,
    footR: jointMap.footR,
  };
}

function FitProxyDebugOverlay({ jointMap }: { jointMap: ProceduralHumanoidJointMap }) {
  const proxies = useMemo(
    () => buildFitProxiesFromAnchors(anchorMapFromProceduralJoints(jointMap)),
    [jointMap],
  );
  const color = new THREE.Color("#38bdf8");
  const emissive = new THREE.Color("#075985");
  return (
    <group name="fit_proxy_debug_overlay">
      {proxies.map((proxy) =>
        proxy.kind === "ellipsoid" ? (
          <EllipsoidMesh
            key={proxy.name}
            name={proxy.name}
            position={toVec3Array(proxy.center)}
            scale={toScaleArray(proxy.radius)}
            color={color}
            opacity={0.18}
            emissive={emissive}
            roughness={0.9}
            transparent
          />
        ) : (
          <CapsuleBetween
            key={proxy.name}
            name={proxy.name}
            start={new THREE.Vector3(...proxy.start)}
            end={new THREE.Vector3(...proxy.end)}
            radius={proxy.radius}
            color={color}
            opacity={0.22}
            emissive={emissive}
            roughness={0.9}
            transparent
          />
        ),
      )}
    </group>
  );
}

/** Sleeve proxies matching arm pose when the skin body is GLTF (no procedural arms). */
function SleeveGarmentPair({
  rig,
  sleeveRadius,
  ang,
  shirtOpacity,
  topColor,
  topEmissive,
  clipEmissiveSleeve,
  sleeveS,
  sleevePos,
  garmentFit,
  skinnedBoneFollow = false,
  leftSleevePivotRef,
  rightSleevePivotRef,
  leftSleeveBoneFollowRef,
  rightSleeveBoneFollowRef,
}: Pick<
  RigMaterialProps,
  | "rig"
  | "ang"
  | "shirtOpacity"
  | "topColor"
  | "topEmissive"
  | "clipEmissiveSleeve"
  | "sleeveS"
  | "sleevePos"
  | "garmentFit"
> & {
  sleeveRadius: number;
  /** Outer pivots positioned each frame from skinned shoulder bones. */
  skinnedBoneFollow?: boolean;
  leftSleevePivotRef?: RefObject<THREE.Group | null>;
  rightSleevePivotRef?: RefObject<THREE.Group | null>;
  /** Inner groups: additive rotation from shoulder bone world pose (weighted follow). */
  leftSleeveBoneFollowRef?: RefObject<THREE.Group | null>;
  rightSleeveBoneFollowRef?: RefObject<THREE.Group | null>;
}) {
  const { shoulderY, shoulderHalf } = rig;
  const spx = sleevePos[0] * FIT_VIS.sleevePosMul;
  const spy = sleevePos[1] * FIT_VIS.sleevePosMul;
  const spz = sleevePos[2] * FIT_VIS.sleevePosMul;

  const leftPos = skinnedBoneFollow
    ? ([0, 0, 0] as [number, number, number])
    : ([shoulderHalf, shoulderY, 0] as [number, number, number]);
  const rightPos = skinnedBoneFollow
    ? ([0, 0, 0] as [number, number, number])
    : ([-shoulderHalf, shoulderY, 0] as [number, number, number]);
  const upperStart = useMemo(() => new THREE.Vector3(0, 0, 0), []);
  const upperEnd = useMemo(() => new THREE.Vector3(0, -0.26, 0.01), []);

  return (
    <group name="sleeve_garment_pair_gltf_body">
      <group
        ref={skinnedBoneFollow ? leftSleevePivotRef : undefined}
        position={toVec3Array(leftPos)}
        rotation={toEulerArray([ang.laxz, 0, ang.laz])}
      >
        <group ref={skinnedBoneFollow ? leftSleeveBoneFollowRef : undefined}>
        <group rotation={toEulerArray([0, 0, ang.lax])}>
          <group position={toVec3Array([spx, spy, spz])} scale={toScaleArray([sleeveS, sleeveS, sleeveS])}>
            <GarmentSleeveProxyMesh
              garmentFit={garmentFit}
              start={upperStart}
              end={upperEnd}
              shirtOpacity={shirtOpacity}
              topColor={topColor}
              topEmissive={topEmissive}
              clipEmissiveAdd={clipEmissiveSleeve}
              sleeveRadius={sleeveRadius}
            />
          </group>
        </group>
        </group>
      </group>
      <group
        ref={skinnedBoneFollow ? rightSleevePivotRef : undefined}
        position={toVec3Array(rightPos)}
        rotation={toEulerArray([-ang.laxz, 0, ang.raz])}
      >
        <group ref={skinnedBoneFollow ? rightSleeveBoneFollowRef : undefined}>
        <group rotation={toEulerArray([0, 0, -ang.rax])}>
          <group position={toVec3Array([-spx, spy, spz])} scale={toScaleArray([sleeveS, sleeveS, sleeveS])}>
            <GarmentSleeveProxyMesh
              garmentFit={garmentFit}
              start={upperStart}
              end={upperEnd}
              shirtOpacity={shirtOpacity}
              topColor={topColor}
              topEmissive={topEmissive}
              clipEmissiveAdd={clipEmissiveSleeve}
              sleeveRadius={sleeveRadius}
            />
          </group>
        </group>
        </group>
      </group>
    </group>
  );
}

/**
 * avatarRoot (world fit)
 * └─ bodyAnchor (torso region: slide + scaleY)
 *    ├─ pelvis + legs
 *    ├─ torso + neck + head
 *    ├─ arms (+ sleeve proxies parented to shoulders)
 */
function ProceduralRigBody({
  rig,
  jointMap,
  bodyColor,
  bodyOpacity,
  bodyEmissive,
  liveShading,
  shirtOpacity,
  topColor,
  topEmissive,
  clipEmissiveSleeve,
  sleeveS,
  sleevePos,
  garmentFit,
}: RigMaterialProps) {
  const P = HUMANOID_PROPORTIONS;
  const overlayDebug = liveShading === "overlay_style" || liveShading === "overlay_debug";
  const matProps = (opacity: number, roughness = 0.62) => ({
    color: bodyColor,
    transparent: !overlayDebug,
    opacity,
    emissive: bodyEmissive,
    roughness,
  });

  const pelvis = jointVector(jointMap, "pelvis");
  const spine = jointVector(jointMap, "spine");
  const waist = jointVector(jointMap, "waist");
  const chest = jointVector(jointMap, "chest");
  const neck = jointVector(jointMap, "neck");
  const head = jointVector(jointMap, "head");
  const shoulderL = jointVector(jointMap, "shoulderL");
  const shoulderR = jointVector(jointMap, "shoulderR");
  const elbowL = jointVector(jointMap, "elbowL");
  const elbowR = jointVector(jointMap, "elbowR");
  const wristL = jointVector(jointMap, "wristL");
  const wristR = jointVector(jointMap, "wristR");
  const hips = jointVector(jointMap, "hips");
  const hipL = jointVector(jointMap, "hipL");
  const hipR = jointVector(jointMap, "hipR");
  const kneeL = jointVector(jointMap, "kneeL");
  const kneeR = jointVector(jointMap, "kneeR");
  const ankleL = jointVector(jointMap, "ankleL");
  const ankleR = jointVector(jointMap, "ankleR");
  const footL = jointVector(jointMap, "footL");
  const footR = jointVector(jointMap, "footR");

  const shoulderCapsuleColor = blendColor(bodyColor, 0.96);
  const jointBlendColor = blendColor(bodyColor, 0.985);
  const pelvisShellCenter = averageJoints(jointMap, "pelvis", "hipL", "hipR");
  const torsoCenter = averageJoints(jointMap, "spine", "chest");
  const abdomenCenter = averageJoints(jointMap, "waist", "spine", "pelvis");
  const neckBase = chest.clone().lerp(neck, 0.48);
  const sleeveFollow = useMemo(() => buildProceduralGarmentFollowPoints(jointMap), [jointMap]);
  const sleeveOffset = new THREE.Vector3(
    sleevePos[0] * FIT_VIS.sleevePosMul * 0.18,
    sleevePos[1] * FIT_VIS.sleevePosMul * 0.12,
    sleevePos[2] * FIT_VIS.sleevePosMul * 0.18,
  );
  const sleeveUpperL = sleeveFollow.topLeftShoulder.clone().add(sleeveOffset);
  const sleeveUpperLEnd = sleeveFollow.sleeveUpperL
    .clone()
    .add(sleeveOffset)
    .lerp(sleeveFollow.sleeveLowerL, 0.22);
  const sleeveLowerL = sleeveFollow.sleeveUpperL.clone().add(sleeveOffset);
  const sleeveLowerLEnd = sleeveFollow.sleeveLowerL.clone().add(sleeveOffset);
  const sleeveUpperR = sleeveFollow.topRightShoulder.clone().add(sleeveOffset);
  const sleeveUpperREnd = sleeveFollow.sleeveUpperR
    .clone()
    .add(sleeveOffset)
    .lerp(sleeveFollow.sleeveLowerR, 0.22);
  const sleeveLowerR = sleeveFollow.sleeveUpperR.clone().add(sleeveOffset);
  const sleeveLowerREnd = sleeveFollow.sleeveLowerR.clone().add(sleeveOffset);

  return (
    <group name="avatar_procedural_rig">
      <EllipsoidMesh
        name="pelvis_shell"
        position={toVec3Array(pelvisShellCenter)}
        scale={toScaleArray([P.pelvisWidth * 0.5, P.pelvisHeight * 0.42, P.pelvisDepth * 0.5])}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.78}
        transparent={!overlayDebug}
      />
      <TaperedSectionMesh
        name="abdomen_shell"
        center={abdomenCenter}
        height={Math.max(0.001, spine.y - pelvis.y)}
        topWidth={P.waistWidth}
        bottomWidth={P.pelvisWidth * 0.86}
        depth={P.waistDepth * 1.03}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.78}
        transparent={!overlayDebug}
      />
      <TaperedSectionMesh
        name="torso_shell"
        center={torsoCenter}
        height={Math.max(0.001, chest.y - waist.y)}
        topWidth={P.chestWidth}
        bottomWidth={P.waistWidth}
        depth={P.chestDepth}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.76}
        transparent={!overlayDebug}
      />
      <CapsuleBetween
        name="shoulder_bridge"
        start={shoulderL.clone().lerp(chest, 0.12)}
        end={shoulderR.clone().lerp(chest, 0.12)}
        radius={0.024}
        color={shoulderCapsuleColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.76}
        transparent={!overlayDebug}
      />
      <EllipsoidMesh
        name="waist_blend"
        position={toVec3Array(waist)}
        scale={toScaleArray([P.waistWidth * 0.46, P.waistHeight * 0.18, P.waistDepth * 0.5])}
        color={jointBlendColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.8}
        transparent={!overlayDebug}
      />
      <CapsuleBetween
        name="hip_bridge"
        start={hipL.clone().lerp(hips, 0.1)}
        end={hipR.clone().lerp(hips, 0.1)}
        radius={0.032}
        color={jointBlendColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.78}
        transparent={!overlayDebug}
      />
      <CapsuleBetween
        name="neck_segment"
        start={neckBase}
        end={neck}
        radius={P.neckRadius}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.56}
        transparent={!overlayDebug}
      />
      <EllipsoidMesh
        name="head_shell"
        position={toVec3Array(head)}
        scale={toScaleArray([
          P.headRadius * P.headScale[0],
          P.headRadius * P.headScale[1],
          P.headRadius * P.headScale[2],
        ])}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.5}
        transparent={!overlayDebug}
      />
      <EllipsoidMesh
        name="shoulder_cap_l"
        position={toVec3Array(jointMap.shoulderL)}
        scale={toScaleArray(P.shoulderCapScale)}
        color={shoulderCapsuleColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.6}
        transparent={!overlayDebug}
      />
      <EllipsoidMesh
        name="shoulder_cap_r"
        position={toVec3Array(jointMap.shoulderR)}
        scale={toScaleArray(P.shoulderCapScale)}
        color={shoulderCapsuleColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.6}
        transparent={!overlayDebug}
      />
      <CapsuleBetween
        name="upper_arm_l"
        start={shoulderL}
        end={elbowL}
        radius={P.upperArmRadius}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        transparent={!overlayDebug}
      />
      <CapsuleBetween
        name="forearm_l"
        start={elbowL}
        end={wristL}
        radius={P.forearmRadius}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        transparent={!overlayDebug}
      />
      <EllipsoidMesh
        name="elbow_blend_l"
        position={toVec3Array(jointMap.elbowL)}
        scale={toScaleArray([P.upperArmRadius * 1.08, P.upperArmRadius * 0.88, P.upperArmRadius * 1.02])}
        color={jointBlendColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.74}
        transparent={!overlayDebug}
      />
      <EllipsoidMesh
        name="hand_l"
        position={toVec3Array(jointMap.wristL)}
        scale={toScaleArray(P.handScale)}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.58}
        transparent={!overlayDebug}
      />
      <CapsuleBetween
        name="upper_arm_r"
        start={shoulderR}
        end={elbowR}
        radius={P.upperArmRadius}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        transparent={!overlayDebug}
      />
      <CapsuleBetween
        name="forearm_r"
        start={elbowR}
        end={wristR}
        radius={P.forearmRadius}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        transparent={!overlayDebug}
      />
      <EllipsoidMesh
        name="elbow_blend_r"
        position={toVec3Array(jointMap.elbowR)}
        scale={toScaleArray([P.upperArmRadius * 1.08, P.upperArmRadius * 0.88, P.upperArmRadius * 1.02])}
        color={jointBlendColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.74}
        transparent={!overlayDebug}
      />
      <EllipsoidMesh
        name="hand_r"
        position={toVec3Array(jointMap.wristR)}
        scale={toScaleArray(P.handScale)}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.58}
        transparent={!overlayDebug}
      />
      <CapsuleBetween
        name="thigh_l"
        start={hipL}
        end={kneeL}
        radius={P.thighRadius}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        transparent={!overlayDebug}
      />
      <CapsuleBetween
        name="calf_l"
        start={kneeL}
        end={ankleL}
        radius={P.calfRadius}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        transparent={!overlayDebug}
      />
      <EllipsoidMesh
        name="hip_blend_l"
        position={toVec3Array(jointMap.hipL)}
        scale={toScaleArray([P.thighRadius * 1.22, P.thighRadius * 0.88, P.thighRadius * 1.04])}
        color={jointBlendColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.76}
        transparent={!overlayDebug}
      />
      <EllipsoidMesh
        name="knee_blend_l"
        position={toVec3Array(jointMap.kneeL)}
        scale={toScaleArray([P.thighRadius * 0.92, P.thighRadius * 0.72, P.thighRadius * 0.84])}
        color={jointBlendColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.78}
        transparent={!overlayDebug}
      />
      <EllipsoidMesh
        name="ankle_blend_l"
        position={toVec3Array(jointMap.ankleL)}
        scale={toScaleArray([P.calfRadius * 0.82, P.calfRadius * 0.62, P.calfRadius * 0.72])}
        color={jointBlendColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.78}
        transparent={!overlayDebug}
      />
      <EllipsoidMesh
        name="foot_l"
        position={toVec3Array(footL)}
        rotation={toEulerArray([0, -0.08, 0.045])}
        scale={toScaleArray(P.footScale)}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.6}
        transparent={!overlayDebug}
      />
      <CapsuleBetween
        name="thigh_r"
        start={hipR}
        end={kneeR}
        radius={P.thighRadius}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        transparent={!overlayDebug}
      />
      <CapsuleBetween
        name="calf_r"
        start={kneeR}
        end={ankleR}
        radius={P.calfRadius}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        transparent={!overlayDebug}
      />
      <EllipsoidMesh
        name="hip_blend_r"
        position={toVec3Array(jointMap.hipR)}
        scale={toScaleArray([P.thighRadius * 1.22, P.thighRadius * 0.88, P.thighRadius * 1.04])}
        color={jointBlendColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.76}
        transparent={!overlayDebug}
      />
      <EllipsoidMesh
        name="knee_blend_r"
        position={toVec3Array(jointMap.kneeR)}
        scale={toScaleArray([P.thighRadius * 0.92, P.thighRadius * 0.72, P.thighRadius * 0.84])}
        color={jointBlendColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.78}
        transparent={!overlayDebug}
      />
      <EllipsoidMesh
        name="ankle_blend_r"
        position={toVec3Array(jointMap.ankleR)}
        scale={toScaleArray([P.calfRadius * 0.82, P.calfRadius * 0.62, P.calfRadius * 0.72])}
        color={jointBlendColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.78}
        transparent={!overlayDebug}
      />
      <EllipsoidMesh
        name="foot_r"
        position={toVec3Array(footR)}
        rotation={toEulerArray([0, 0.08, -0.045])}
        scale={toScaleArray(P.footScale)}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.6}
        transparent={!overlayDebug}
      />

      <GarmentSleeveProxyMesh
        garmentFit={garmentFit}
        start={sleeveUpperL}
        end={sleeveUpperLEnd}
        shirtOpacity={shirtOpacity}
        topColor={topColor}
        topEmissive={topEmissive}
        clipEmissiveAdd={clipEmissiveSleeve}
        sleeveRadius={P.upperArmRadius * 1.12 * sleeveS}
      />
      <GarmentSleeveProxyMesh
        garmentFit={garmentFit}
        start={sleeveLowerL}
        end={sleeveLowerLEnd}
        shirtOpacity={shirtOpacity}
        topColor={topColor}
        topEmissive={topEmissive}
        clipEmissiveAdd={clipEmissiveSleeve}
        sleeveRadius={P.forearmRadius * 1.12 * sleeveS}
      />
      <GarmentSleeveProxyMesh
        garmentFit={garmentFit}
        start={sleeveUpperR}
        end={sleeveUpperREnd}
        shirtOpacity={shirtOpacity}
        topColor={topColor}
        topEmissive={topEmissive}
        clipEmissiveAdd={clipEmissiveSleeve}
        sleeveRadius={P.upperArmRadius * 1.12 * sleeveS}
      />
      <GarmentSleeveProxyMesh
        garmentFit={garmentFit}
        start={sleeveLowerR}
        end={sleeveLowerREnd}
        shirtOpacity={shirtOpacity}
        topColor={topColor}
        topEmissive={topEmissive}
        clipEmissiveAdd={clipEmissiveSleeve}
        sleeveRadius={P.forearmRadius * 1.12 * sleeveS}
      />
    </group>
  );
}

export function AvatarProceduralScene({
  pose,
  preset,
  garmentFit,
  liveShading,
  bodyShape = DEFAULT_BODY_SHAPE,
  runtimeBodyGltfUrl = null,
  runtimeBodyBundledModule = null,
  runtimeTopGltfUrl = null,
  runtimeBottomGltfUrl = null,
  includeSceneLights = true,
  showRigDebug = false,
  clipEmissiveTop = null,
  clipEmissiveBottom = null,
  clipEmissiveSleeve = null,
  showGarmentRigDebug = false,
  bodyOnlyGarments = false,
  /** Dev: hide body mesh entirely (inspect floating garments / GLB garments). */
  garmentOnlyViewport = false,
  onRuntimeBodyLoadError,
  onRuntimeBodyLoaded,
  onSkinnedRigPoseReport,
  onGarmentAnchorsDebug,
  garmentAttachmentDebug = false,
  onGarmentAttachmentSnapshot,
  onStartupVisibilityReport,
  startupLoadGeneration = 0,
  showVisualSanityMarker = false,
  sceneSpaceDebug = null,
}: {
  pose: DevAvatarPoseKey;
  preset: DevAvatarPresetKey;
  garmentFit: GarmentFitState;
  liveShading: LiveViewportShadingMode;
  /** Parametric body drives procedural mesh, clipping proxies, and approximate GLB body scale. */
  bodyShape?: BodyShapeParams;
  runtimeBodyGltfUrl?: string | null;
  /** Bundled body: Metro module id; loaded via `GLTFLoader.parse` (no `file://`). */
  runtimeBodyBundledModule?: number | null;
  runtimeTopGltfUrl?: string | null;
  runtimeBottomGltfUrl?: string | null;
  includeSceneLights?: boolean;
  /** Dev: small spheres at pelvis, chest, shoulders, head (depthTest off). */
  showRigDebug?: boolean;
  /** Dev: magenta spheres at garment pose / skinning pivots (shoulders, hips). */
  showGarmentRigDebug?: boolean;
  /** Runtime clipping overlay: emissive add for shirt / GLB top. */
  clipEmissiveTop?: THREE.Color | null;
  clipEmissiveBottom?: THREE.Color | null;
  clipEmissiveSleeve?: THREE.Color | null;
  /** Dev: hide garment proxies + GLB garments for body inspection. */
  bodyOnlyGarments?: boolean;
  garmentOnlyViewport?: boolean;
  onRuntimeBodyLoadError?: (message: string) => void;
  onRuntimeBodyLoaded?: () => void;
  onSkinnedRigPoseReport?: (r: SkinnedRigPoseReport) => void;
  onGarmentAnchorsDebug?: (d: GarmentAnchorFitDebug) => void;
  /** Dev: show spheres at bone-derived attachment points (requires skinned body + garments). */
  garmentAttachmentDebug?: boolean;
  onGarmentAttachmentSnapshot?: (s: GarmentAttachmentSnapshot) => void;
  onStartupVisibilityReport?: (r: StartupVisibilityReport) => void;
  startupLoadGeneration?: number;
  /** Dev: chest-height proof-of-render marker under the same Canvas scene root. */
  showVisualSanityMarker?: boolean;
  /** Dev (workbench): in-canvas bounds/markers, framing, throttled scene diagnostics. */
  sceneSpaceDebug?: {
    enabled: boolean;
    showMarkers: boolean;
    debugBrightBody: boolean;
    bodyLoadGeneration: number;
    manualFrameBoundsNonce: number;
    onSceneDiagnostics?: (d: LiveViewportSceneDiagnostics) => void;
    orbit: SceneSpaceDebugOrbitBindings;
  } | null;
}) {
  const torsoRegionFitRef = useRef<THREE.Group>(null);
  const avatarWorldFitRef = useRef<THREE.Group>(null);
  const bodyRootRef = useRef<THREE.Group>(null);
  const gltfBodyRootRef = useRef<THREE.Group>(null);
  const leftSleevePivotRef = useRef<THREE.Group>(null);
  const rightSleevePivotRef = useRef<THREE.Group>(null);
  const leftSleeveBoneFollowRef = useRef<THREE.Group>(null);
  const rightSleeveBoneFollowRef = useRef<THREE.Group>(null);
  const topAnchorRef = useRef<THREE.Group>(null);
  const bottomAnchorRef = useRef<THREE.Group>(null);
  const attachmentMarkersRef = useRef<THREE.Group>(null);
  const garmentRootRef = useRef<THREE.Group>(null);
  const lastAnchorDebugJson = useRef("");
  const lastStartupReportJson = useRef("");

  const bodyShapeKey = bodyShapeParamsKey(bodyShape);
  const rig = useMemo(() => bodySceneAnchorsFromShape(bodyShape), [bodyShapeKey]);
  const garmentPoseSkin = useMemo<GarmentPoseSkinningParams>(
    () => ({
      rig,
      angBind: poseAngles(GARMENT_POSE_BIND_POSE),
      angPose: poseAngles(pose),
    }),
    [rig, pose],
  );
  const sleeveRadius = rig.metrics.upperArmCapsule[0];
  const ang = poseAngles(pose);
  const jointMap = useMemo(() => buildProceduralHumanoidJointMap(rig, ang), [rig, ang]);
  const colors = presetGarmentColors(preset);
  const showShoes = DEV_AVATAR_PRESETS[preset].shoes != null;

  const g = garmentFit.global;
  const inf = g.inflate;
  const inflVis = inf * FIT_VIS.globalGarmentInflate;
  const gsx = g.scale[0] + inflVis;
  const gsy = g.scale[1] + inflVis;
  const gsz = g.scale[2] + inflVis;
  const r = garmentFit.regions;
  const sleeveS = 1 + r.sleeves.inflate * 2.8;
  const sleevePos = [
    r.sleeves.offset[0],
    r.sleeves.offset[1] + garmentFit.legacy.sleeveOffsetY,
    r.sleeves.offset[2],
  ] as [number, number, number];

  let shirtOpacity = 1;
  let pantOpacity = 1;
  let shoeOpacity = 1;
  let bodyOpacity = 1;
  let bodyColor = SKIN.clone();
  const topColor = new THREE.Color(colors.top[0], colors.top[1], colors.top[2]);
  const bottomColor = new THREE.Color(
    colors.bottom[0],
    colors.bottom[1],
    colors.bottom[2],
  );
  const shoeColor = new THREE.Color(colors.shoes[0], colors.shoes[1], colors.shoes[2]);
  let topEmissive = new THREE.Color(0, 0, 0);
  let bottomEmissive = new THREE.Color(0, 0, 0);
  let bodyEmissive = new THREE.Color(0, 0, 0);

  if (bodyOnlyGarments) {
    shirtOpacity = 0;
    pantOpacity = 0;
    shoeOpacity = 0;
    bodyOpacity = 1;
  } else if (liveShading === "body_focus") {
    shirtOpacity = 0.32;
    pantOpacity = 0.32;
    shoeOpacity = 0.4;
  } else if (liveShading === "garment_focus") {
    bodyOpacity = 0.28;
    bodyColor = SKIN_DIM.clone();
  } else if (liveShading === "overlay_style" || liveShading === "overlay_debug") {
    bodyColor = new THREE.Color(0.2, 0.35, 0.85);
    topColor.set(0.95, 0.45, 0.12);
    bottomColor.set(0.85, 0.42, 0.1);
    topEmissive.set(0.06, 0.02, 0);
    bottomEmissive.set(0.04, 0.02, 0);
    bodyEmissive.set(0.02, 0.04, 0.12);
  }

  const worldOff = [
    g.offset[0],
    g.offset[1] + garmentFit.legacy.bodyOffsetBias,
    g.offset[2],
  ] as [number, number, number];

  const tz = r.torso.offsetZ;
  const bodyAnchorPos = useMemo(
    () => [0, tz * FIT_VIS.torsoOffsetY, tz * FIT_VIS.torsoOffsetZ] as [number, number, number],
    [tz],
  );
  const bodyAnchorScale = useMemo(
    () =>
      [
        1 + r.torso.inflate * FIT_VIS.torsoInflateMul,
        r.torso.scaleY * (1 + r.torso.inflate * FIT_VIS.torsoInflateYMul),
        1 + r.torso.inflate * FIT_VIS.torsoInflateMul,
      ] as [number, number, number],
    [r.torso.inflate, r.torso.scaleY],
  );

  const shirtInfl = 1 + r.torso.inflate * 2.2;

  const skinnedAnchorsActive =
    !garmentOnlyViewport &&
    (runtimeBodyBundledModule != null || runtimeBodyGltfUrl != null);
  const showBodyMesh = !garmentOnlyViewport;
  const hideGarments = bodyOnlyGarments;

  const attachmentDriverEnabled =
    skinnedAnchorsActive &&
    !hideGarments &&
    showBodyMesh &&
    (runtimeBodyBundledModule != null || runtimeBodyGltfUrl != null);

  const rigTopYFallback = tz * 0.18;
  const rigTopZFallback = tz * 0.35;
  const rigBottomYFallback = garmentFit.legacy.waistAdjustY;
  const bottomAnchorZ = r.waist.offsetZ * FIT_VIS.waistOffsetZ;

  const topAnchorY = attachmentDriverEnabled ? 0 : rigTopYFallback;
  const topAnchorZ = attachmentDriverEnabled ? 0 : rigTopZFallback;
  const bottomAnchorY = attachmentDriverEnabled ? 0 : rigBottomYFallback;

  const shirtTorsoMount = attachmentDriverEnabled ? "skinned_chest" : "rig_chest";
  const pantsBottomMount = attachmentDriverEnabled ? "skinned_pelvis" : "rig";

  const emitGarmentAnchorsDebug = useCallback(() => {
    if (!onGarmentAnchorsDebug) return;
    const payload = {
      bodyAnchorPos: [...bodyAnchorPos] as [number, number, number],
      bodyAnchorScale: [...bodyAnchorScale] as [number, number, number],
      topAnchorLocal: [0, topAnchorY, topAnchorZ] as [number, number, number],
      bottomAnchorLocal: [0, bottomAnchorY, bottomAnchorZ] as [number, number, number],
      waistTighten: r.waist.tighten,
      hemOffsetY: r.hem.offsetY,
      legacyWaistAdjustY: garmentFit.legacy.waistAdjustY,
      torsoOffsetZ: tz,
      skinnedBodyActive: skinnedAnchorsActive,
    };
    const j = JSON.stringify(payload);
    if (j === lastAnchorDebugJson.current) return;
    lastAnchorDebugJson.current = j;
    onGarmentAnchorsDebug(payload);
  }, [
    onGarmentAnchorsDebug,
    bodyAnchorPos,
    bodyAnchorScale,
    topAnchorY,
    topAnchorZ,
    bottomAnchorY,
    bottomAnchorZ,
    r.waist.tighten,
    r.hem.offsetY,
    garmentFit.legacy.waistAdjustY,
    tz,
    skinnedAnchorsActive,
  ]);

  useLayoutEffect(() => {
    emitGarmentAnchorsDebug();
  }, [emitGarmentAnchorsDebug, attachmentDriverEnabled]);

  useLayoutEffect(() => {
    if (!onStartupVisibilityReport) return;
    const bodyGroup = bodyRootRef.current;
    const gltfGroup = gltfBodyRootRef.current;
    const garmentGroup = garmentRootRef.current;
    const runtimeBodyActive = runtimeBodyBundledModule != null || runtimeBodyGltfUrl != null;
    const activeRenderBranchName =
      runtimeBodyBundledModule != null
        ? "stylised_glb"
        : runtimeBodyGltfUrl != null
          ? "realistic_glb"
          : "procedural_fallback";
    const initialRenderAudit = showBodyMesh
      ? auditDrawableHierarchy({
          root: bodyGroup,
          gltfRoot: gltfGroup,
          activeRenderBranchName,
          safetyFallbackReason: null,
        })
      : null;
    const safetyFallbackReason =
      runtimeBodyActive &&
      startupLoadGeneration > 0 &&
      (initialRenderAudit?.gltfVisibleMeshCount ?? 0) <= 0
        ? runtimeBodyBundledModule != null
          ? "stylised_glb_loaded_but_no_visible_meshes"
          : "realistic_glb_loaded_but_no_visible_meshes"
        : null;
    const renderAudit =
      initialRenderAudit && safetyFallbackReason
        ? { ...initialRenderAudit, safetyFallbackReason }
        : initialRenderAudit;
    const bodyMeshCount = renderAudit?.visibleMeshCount ?? 0;
    const garmentMeshCount = !hideGarments ? repairDrawableHierarchy(garmentGroup) : 0;
    if (__DEV__ && showVisualSanityMarker && bodyMeshCount <= 0) {
      const bounds = new THREE.Box3();
      if (bodyGroup) bounds.setFromObject(bodyGroup);
      console.log("[AvatarViewport] sanity marker active but avatar body has no visible meshes", {
        showBodyMesh,
        hideGarments,
        bodyBoundsMin: bounds.min.toArray(),
        bodyBoundsMax: bounds.max.toArray(),
      });
    }
    const payload: StartupVisibilityReport = {
      sceneReady: (showBodyMesh ? bodyMeshCount > 0 : true) && (!hideGarments ? garmentMeshCount > 0 : true),
      visibleMeshCount: bodyMeshCount + garmentMeshCount,
      bodyGroupVisible: showBodyMesh ? !!bodyGroup?.visible : false,
      garmentGroupVisible: !hideGarments ? !!garmentGroup?.visible : false,
      startupReason: safetyFallbackReason
        ? safetyFallbackReason
        : runtimeBodyActive
          ? startupLoadGeneration > 0
            ? "skinned_attached"
            : "skinned_waiting_attach"
          : "procedural_fallback_attached",
      renderAudit,
    };
    const json = JSON.stringify(payload);
    if (json === lastStartupReportJson.current) return;
    lastStartupReportJson.current = json;
    onStartupVisibilityReport(payload);
  }, [
    onStartupVisibilityReport,
    showBodyMesh,
    hideGarments,
    startupLoadGeneration,
    runtimeBodyBundledModule,
    runtimeBodyGltfUrl,
    pose,
    liveShading,
    garmentFit,
    showVisualSanityMarker,
  ]);

  const rigMat: RigMaterialProps = {
    rig,
    ang,
    jointMap,
    garmentPoseSkin,
    bodyColor,
    bodyOpacity,
    bodyEmissive,
    liveShading,
    shirtOpacity,
    topColor,
    topEmissive,
    clipEmissiveSleeve,
    sleeveS,
    sleevePos,
    garmentFit,
  };

  return (
    <>
      {includeSceneLights ? (
        <>
          <ambientLight intensity={0.42} />
          <hemisphereLight args={[0xfff4e6, 0xd5c4b0, 0.55]} />
          <directionalLight position={[3.8, 7.5, 4.8]} intensity={0.95} castShadow />
          <directionalLight position={[-3, 3.5, -3.5]} intensity={0.28} />
          <directionalLight position={[0, 2.4, -4]} intensity={0.18} />
        </>
      ) : null}

      {showVisualSanityMarker ? (
        <mesh position={toVec3Array([0, 1.22, 0.18])} name="viewport_sanity_marker">
          <boxGeometry args={[0.08, 0.08, 0.08]} />
          <meshStandardMaterial color="#22c55e" emissive="#14532d" />
        </mesh>
      ) : null}

      {sceneSpaceDebug?.enabled ? (
        <ViewportSceneSpaceDebug
          enabled
          showMarkers={sceneSpaceDebug.showMarkers}
          bodyRootRef={bodyRootRef}
          avatarWorldFitRef={avatarWorldFitRef}
          torsoRegionFitRef={torsoRegionFitRef}
          orbit={sceneSpaceDebug.orbit}
          bodyLoadGeneration={sceneSpaceDebug.bodyLoadGeneration}
          manualFrameBoundsNonce={sceneSpaceDebug.manualFrameBoundsNonce}
          onDiagnostics={sceneSpaceDebug.onSceneDiagnostics}
        />
      ) : null}

      <group
        ref={avatarWorldFitRef}
        position={toVec3Array(worldOff)}
        scale={toScaleArray([gsx, gsy, gsz])}
        name="avatar_world_fit"
      >
        <group
          ref={torsoRegionFitRef}
          position={toVec3Array(bodyAnchorPos)}
          scale={toScaleArray(bodyAnchorScale)}
          name="avatar_torso_region_fit"
        >
          {showRigDebug ? <RigDebugAnchors jointMap={jointMap} /> : null}
          {showGarmentRigDebug ? <GarmentRigDebugOverlay jointMap={jointMap} /> : null}
          {showGarmentRigDebug ? <FitProxyDebugOverlay jointMap={jointMap} /> : null}

          {showBodyMesh ? (
            <group ref={bodyRootRef} name="avatar_body_root">
              <group name="procedural_body_root">
                <ProceduralRigBody {...rigMat} />
              </group>
              {runtimeBodyBundledModule != null || runtimeBodyGltfUrl ? (
                <GltfErrorBoundary
                  key={String(runtimeBodyBundledModule ?? runtimeBodyGltfUrl ?? "")}
                  fallback={null}
                  onLoadError={onRuntimeBodyLoadError}
                >
                  <Suspense fallback={null}>
                    <group
                      ref={gltfBodyRootRef}
                      position={toVec3Array([0, 0, 0])}
                      name="gltf_body_overlay_root"
                    >
                      <GltfRuntimeBody
                        url={runtimeBodyGltfUrl}
                        bundledAssetModule={runtimeBodyBundledModule}
                        pose={pose}
                        liveShading={liveShading}
                        bodyShape={bodyShape}
                        debugForceBrightMaterial={!!sceneSpaceDebug?.debugBrightBody}
                        onSceneReady={onRuntimeBodyLoaded}
                        onRigPoseReport={onSkinnedRigPoseReport}
                      />
                    </group>
                  </Suspense>
                </GltfErrorBoundary>
              ) : null}
            </group>
          ) : null}

          {showBodyMesh &&
          !hideGarments &&
          !runtimeTopGltfUrl &&
          (runtimeBodyBundledModule != null || runtimeBodyGltfUrl) ? (
            <SleeveGarmentPair
              {...rigMat}
              sleeveRadius={sleeveRadius}
              skinnedBoneFollow={attachmentDriverEnabled}
              leftSleevePivotRef={leftSleevePivotRef}
              rightSleevePivotRef={rightSleevePivotRef}
              leftSleeveBoneFollowRef={leftSleeveBoneFollowRef}
              rightSleeveBoneFollowRef={rightSleeveBoneFollowRef}
            />
          ) : null}

          {/* Top: torso hull (sleeves ride on arms inside procedural rig) */}
          {!hideGarments ? (
          <group ref={garmentRootRef} name="garment_root">
          <group
            ref={topAnchorRef}
            name="garment_top_anchor"
            position={toVec3Array([0, topAnchorY, topAnchorZ])}
            scale={toScaleArray([shirtInfl, 1 + r.torso.inflate * 1.2, shirtInfl])}
          >
            {runtimeTopGltfUrl ? (
              <GltfErrorBoundary
                key={runtimeTopGltfUrl}
                fallback={
                  <ShirtTorsoProxy
                    rig={rig}
                    jointMap={jointMap}
                    garmentPoseSkin={garmentPoseSkin}
                    topColor={topColor}
                    shirtOpacity={shirtOpacity}
                    topEmissive={topEmissive}
                    clipEmissiveAdd={clipEmissiveTop}
                    garmentFit={garmentFit}
                    inflateK={1.04}
                    torsoMountMode={shirtTorsoMount}
                  />
                }
              >
                <Suspense
                  fallback={
                    <ShirtTorsoProxy
                      rig={rig}
                      jointMap={jointMap}
                      garmentPoseSkin={garmentPoseSkin}
                      topColor={topColor}
                      shirtOpacity={shirtOpacity}
                      topEmissive={topEmissive}
                      clipEmissiveAdd={clipEmissiveTop}
                      garmentFit={garmentFit}
                      inflateK={1.04}
                      torsoMountMode={shirtTorsoMount}
                    />
                  }
                >
                  <group position={toVec3Array([0, rig.gltfTopMountY, 0])}>
                    <GltfRuntimeGarment
                      url={runtimeTopGltfUrl}
                      liveShading={liveShading}
                      normalizeHeight={0.44}
                      garmentFit={garmentFit}
                      deformProfile="top"
                      garmentPoseSkin={garmentPoseSkin}
                      clipEmissiveAdd={clipEmissiveTop ?? undefined}
                    />
                  </group>
                </Suspense>
              </GltfErrorBoundary>
            ) : (
              <ShirtTorsoProxy
                rig={rig}
                jointMap={jointMap}
                garmentPoseSkin={garmentPoseSkin}
                topColor={topColor}
                shirtOpacity={shirtOpacity}
                topEmissive={topEmissive}
                clipEmissiveAdd={clipEmissiveTop}
                garmentFit={garmentFit}
                inflateK={1.02 + r.torso.inflate}
                torsoMountMode={shirtTorsoMount}
              />
            )}
          </group>

          <group
            ref={bottomAnchorRef}
            name="garment_bottom_anchor"
            position={toVec3Array([0, bottomAnchorY, bottomAnchorZ])}
            scale={toScaleArray([
              1 - r.waist.tighten * 0.48,
              1 - r.waist.tighten * 0.32,
              1 - r.waist.tighten * 0.26,
            ])}
          >
            {runtimeBottomGltfUrl ? (
              <GltfErrorBoundary
                key={runtimeBottomGltfUrl}
                fallback={
                  <PantsGarmentProxies
                    rig={rig}
                    jointMap={jointMap}
                    garmentPoseSkin={garmentPoseSkin}
                    bottomColor={bottomColor}
                    pantOpacity={pantOpacity}
                    bottomEmissive={bottomEmissive}
                    clipEmissiveAdd={clipEmissiveBottom}
                    hemYOffset={r.hem.offsetY}
                    garmentFit={garmentFit}
                    bottomMountMode={pantsBottomMount}
                  />
                }
              >
                <Suspense
                  fallback={
                    <PantsGarmentProxies
                      rig={rig}
                      jointMap={jointMap}
                      garmentPoseSkin={garmentPoseSkin}
                      bottomColor={bottomColor}
                      pantOpacity={pantOpacity}
                      bottomEmissive={bottomEmissive}
                      clipEmissiveAdd={clipEmissiveBottom}
                      hemYOffset={r.hem.offsetY}
                      garmentFit={garmentFit}
                      bottomMountMode={pantsBottomMount}
                    />
                  }
                >
                  <group position={toVec3Array([0, rig.gltfBottomMountY + r.hem.offsetY, 0])}>
                    <GltfRuntimeGarment
                      url={runtimeBottomGltfUrl}
                      liveShading={liveShading}
                      normalizeHeight={0.52}
                      garmentFit={garmentFit}
                      deformProfile="bottom"
                      garmentPoseSkin={garmentPoseSkin}
                      clipEmissiveAdd={clipEmissiveBottom ?? undefined}
                    />
                  </group>
                </Suspense>
              </GltfErrorBoundary>
            ) : (
              <PantsGarmentProxies
                rig={rig}
                jointMap={jointMap}
                garmentPoseSkin={garmentPoseSkin}
                bottomColor={bottomColor}
                pantOpacity={pantOpacity}
                bottomEmissive={bottomEmissive}
                clipEmissiveAdd={clipEmissiveBottom}
                hemYOffset={r.hem.offsetY}
                garmentFit={garmentFit}
                bottomMountMode={pantsBottomMount}
              />
            )}
          </group>
          </group>
          ) : null}

          {attachmentDriverEnabled ? (
            <>
              <SkinnedGarmentAttachmentDriver
                enabled
                rig={rig}
                torsoOffsetZ={tz}
                garmentFit={garmentFit}
                waistOffsetZVis={bottomAnchorZ}
                bodyRootRef={bodyRootRef}
                torsoRegionFitRef={torsoRegionFitRef}
                leftSleevePivotRef={leftSleevePivotRef}
                rightSleevePivotRef={rightSleevePivotRef}
                leftSleeveBoneFollowRef={leftSleeveBoneFollowRef}
                rightSleeveBoneFollowRef={rightSleeveBoneFollowRef}
                topAnchorRef={topAnchorRef}
                bottomAnchorRef={bottomAnchorRef}
                showMarkers={!!garmentAttachmentDebug}
                markersGroupRef={attachmentMarkersRef}
                onAttachmentSnapshot={onGarmentAttachmentSnapshot}
              />
              <group ref={attachmentMarkersRef}>
                {["#22c55e", "#3b82f6", "#eab308", "#22d3ee", "#db2777"].map((color, i) => (
                  <mesh key={i} position={toVec3Array([0, 0, 0])}>
                    <sphereGeometry args={[0.016, 6, 6]} />
                    <meshBasicMaterial color={color} depthTest={false} />
                  </mesh>
                ))}
              </group>
            </>
          ) : null}

          {showShoes && !hideGarments ? (
            <group position={toVec3Array([0, r.hem.offsetY * 0.35, 0])} name="shoes_proxy">
              <mesh
                position={toVec3Array(jointMap.footL)}
                rotation={toEulerArray([0, -0.08, 0.045])}
                scale={toScaleArray([1, 1, 1.08])}
              >
                <boxGeometry args={[0.11, 0.052, 0.19]} />
                <meshStandardMaterial
                  color={shoeColor}
                  transparent
                  opacity={shoeOpacity}
                  roughness={0.78}
                />
              </mesh>
              <mesh
                position={toVec3Array(jointMap.footR)}
                rotation={toEulerArray([0, 0.08, -0.045])}
                scale={toScaleArray([1, 1, 1.08])}
              >
                <boxGeometry args={[0.11, 0.052, 0.19]} />
                <meshStandardMaterial
                  color={shoeColor}
                  transparent
                  opacity={shoeOpacity}
                  roughness={0.78}
                />
              </mesh>
            </group>
          ) : null}
        </group>
      </group>
    </>
  );
}
