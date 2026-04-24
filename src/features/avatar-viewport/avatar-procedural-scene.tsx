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
import { SkinnedGarmentAttachmentDriver } from "./skinned-garment-attachment-driver";
import type { LiveViewportShadingMode } from "./live-viewport-shading";
import type { AvatarViewportNavSettings } from "./avatar-viewport-nav-settings";

const SKIN = new THREE.Color(0xd4a574);
const SKIN_DIM = new THREE.Color(0xa07850);

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
      position={frame.center}
      quaternion={frame.quaternion}
      castShadow
    >
      <capsuleGeometry args={[radius, Math.max(0.001, frame.shaftLength - radius * 2), 10, 18]} />
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
  color,
  opacity = 1,
  emissive,
  roughness = 0.62,
  transparent = true,
}: {
  name: string;
  position: [number, number, number];
  scale: [number, number, number];
  color: THREE.Color;
  opacity?: number;
  emissive?: THREE.Color;
  roughness?: number;
  transparent?: boolean;
}) {
  return (
    <mesh name={name} position={position} scale={scale} castShadow>
      <sphereGeometry args={[1, 18, 18]} />
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
    <mesh ref={meshRef} position={frame.center} quaternion={frame.quaternion} castShadow>
      <capsuleGeometry
        args={[
          sleeveRadius,
          Math.max(0.001, frame.shaftLength - sleeveRadius * 2),
          8,
          16,
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
    ? new THREE.Vector3(0, P.chestY - rig.chestY + 0.01, 0.01)
    : follow.topCenter.clone().add(new THREE.Vector3(0, 0.02, 0.012));
  const topScale = [
    P.topShellScale[0] * inflateK,
    P.topShellScale[1] * inflateK,
    P.topShellScale[2] * inflateK,
  ] as [number, number, number];
  return (
    <mesh ref={meshRef} position={v3tuple(topCenter)} scale={topScale} castShadow>
      <sphereGeometry args={[1, 16, 16]} />
      <meshStandardMaterial
        color={topColor}
        transparent
        opacity={shirtOpacity}
        emissive={shirtEmissive}
        roughness={0.72}
      />
    </mesh>
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
      ? new THREE.Vector3(0, P.pelvisY - rig.pelvisY - 0.015 + hemYOffset * 0.2, 0)
      : follow.bottomCenter.clone().add(new THREE.Vector3(0, -0.02 + hemYOffset * 0.24, 0));
  const shellScale = [
    P.bottomShellScale[0],
    P.bottomShellScale[1],
    P.bottomShellScale[2],
  ] as [number, number, number];
  const thighUpperL = jointVector(jointMap, "hipL")
    .clone()
    .lerp(jointVector(jointMap, "kneeL"), 0.68)
    .add(new THREE.Vector3(0.01, hemYOffset * 0.55, 0));
  const thighUpperR = jointVector(jointMap, "hipR")
    .clone()
    .lerp(jointVector(jointMap, "kneeR"), 0.68)
    .add(new THREE.Vector3(-0.01, hemYOffset * 0.55, 0));
  return (
    <group ref={groupRef}>
      <mesh position={v3tuple(bottomCenter)} scale={shellScale}>
        <sphereGeometry args={[1, 16, 16]} />
        <meshStandardMaterial
          color={bottomColor}
          transparent
          opacity={pantOpacity}
          emissive={pantsEmissive}
          roughness={0.7}
        />
      </mesh>
      <CapsuleBetween
        name="pants_leg_l"
        start={jointVector(jointMap, "hipL")}
        end={thighUpperL}
        radius={P.thighRadius * 1.06}
        color={bottomColor}
        opacity={pantOpacity}
        emissive={pantsEmissive}
        roughness={0.68}
      />
      <CapsuleBetween
        name="pants_leg_r"
        start={jointVector(jointMap, "hipR")}
        end={thighUpperR}
        radius={P.thighRadius * 1.06}
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
    ["spine", "chest"],
    ["chest", "neck"],
    ["neck", "head"],
    ["chest", "shoulderL"],
    ["shoulderL", "elbowL"],
    ["elbowL", "wristL"],
    ["chest", "shoulderR"],
    ["shoulderR", "elbowR"],
    ["elbowR", "wristR"],
    ["pelvis", "hipL"],
    ["hipL", "kneeL"],
    ["kneeL", "ankleL"],
    ["pelvis", "hipR"],
    ["hipR", "kneeR"],
    ["kneeR", "ankleR"],
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
        <mesh key={joint} position={jointMap[joint]}>
          <sphereGeometry args={[radius, 8, 8]} />
          <meshBasicMaterial color="#f59e0b" depthTest={false} />
        </mesh>
      ))}
    </group>
  );
}

/** Dev: garment pose / skinning influence pivots (shoulders + hips). */
function GarmentRigDebugOverlay({ rig }: { rig: BodySceneAnchors }) {
  const M = rig.metrics;
  const hipY = rig.pelvisY + M.hipPitchLocalY;
  const pts: [string, [number, number, number]][] = [
    ["g_l_shoulder", [rig.shoulderHalf, rig.shoulderY, 0]],
    ["g_r_shoulder", [-rig.shoulderHalf, rig.shoulderY, 0]],
    ["g_l_hip", [M.legGroupOffsetX, hipY, 0]],
    ["g_r_hip", [-M.legGroupOffsetX, hipY, 0]],
  ];
  return (
    <group name="garment_rig_debug">
      {pts.map(([id, pos]) => (
        <mesh key={id} position={pos}>
          <sphereGeometry args={[0.024, 7, 7]} />
          <meshBasicMaterial color="#db2777" depthTest={false} />
        </mesh>
      ))}
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
        position={leftPos}
        rotation={[ang.laxz, 0, ang.laz]}
      >
        <group ref={skinnedBoneFollow ? leftSleeveBoneFollowRef : undefined}>
        <group rotation={[0, 0, ang.lax]}>
          <group position={[spx, spy, spz]} scale={[sleeveS, sleeveS, sleeveS]}>
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
        position={rightPos}
        rotation={[-ang.laxz, 0, ang.raz]}
      >
        <group ref={skinnedBoneFollow ? rightSleeveBoneFollowRef : undefined}>
        <group rotation={[0, 0, -ang.rax]}>
          <group position={[-spx, spy, spz]} scale={[sleeveS, sleeveS, sleeveS]}>
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
  const matProps = (opacity: number, roughness = 0.62) => ({
    color: bodyColor,
    transparent: liveShading !== "overlay_style",
    opacity,
    emissive: bodyEmissive,
    roughness,
  });

  const pelvis = jointVector(jointMap, "pelvis");
  const spine = jointVector(jointMap, "spine");
  const chest = jointVector(jointMap, "chest");
  const neck = jointVector(jointMap, "neck");
  const head = jointVector(jointMap, "head");
  const shoulderL = jointVector(jointMap, "shoulderL");
  const shoulderR = jointVector(jointMap, "shoulderR");
  const elbowL = jointVector(jointMap, "elbowL");
  const elbowR = jointVector(jointMap, "elbowR");
  const wristL = jointVector(jointMap, "wristL");
  const wristR = jointVector(jointMap, "wristR");
  const hipL = jointVector(jointMap, "hipL");
  const hipR = jointVector(jointMap, "hipR");
  const kneeL = jointVector(jointMap, "kneeL");
  const kneeR = jointVector(jointMap, "kneeR");
  const ankleL = jointVector(jointMap, "ankleL");
  const ankleR = jointVector(jointMap, "ankleR");

  const shoulderCapsuleColor = blendColor(bodyColor, 0.96);
  const pelvisShellCenter = averageJoints(jointMap, "pelvis", "hipL", "hipR", "spine");
  const torsoCenter = averageJoints(jointMap, "spine", "chest");
  const abdomenCenter = averageJoints(jointMap, "pelvis", "spine");
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
        position={v3tuple(pelvisShellCenter)}
        scale={[P.pelvisWidth * 0.5, P.pelvisHeight * 0.5, P.pelvisDepth * 0.5]}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.68}
        transparent={liveShading !== "overlay_style"}
      />
      <CapsuleBetween
        name="spine_segment"
        start={pelvis}
        end={spine}
        radius={P.abdomenWidth * 0.19}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.68}
        transparent={liveShading !== "overlay_style"}
      />
      <EllipsoidMesh
        name="abdomen_shell"
        position={v3tuple(abdomenCenter)}
        scale={[P.abdomenWidth * 0.5, P.abdomenHeight * 0.5, P.abdomenDepth * 0.5]}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.66}
        transparent={liveShading !== "overlay_style"}
      />
      <EllipsoidMesh
        name="torso_shell"
        position={v3tuple(torsoCenter)}
        scale={[P.chestWidth * 0.5, P.chestHeight * 0.5, P.chestDepth * 0.5]}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.62}
        transparent={liveShading !== "overlay_style"}
      />
      <CapsuleBetween
        name="neck_segment"
        start={chest}
        end={neck}
        radius={P.neckRadius}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.56}
        transparent={liveShading !== "overlay_style"}
      />
      <EllipsoidMesh
        name="head_shell"
        position={v3tuple(head)}
        scale={[
          P.headRadius * P.headScale[0],
          P.headRadius * P.headScale[1],
          P.headRadius * P.headScale[2],
        ]}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.5}
        transparent={liveShading !== "overlay_style"}
      />
      <EllipsoidMesh
        name="shoulder_cap_l"
        position={jointMap.shoulderL}
        scale={P.shoulderCapScale}
        color={shoulderCapsuleColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.6}
        transparent={liveShading !== "overlay_style"}
      />
      <EllipsoidMesh
        name="shoulder_cap_r"
        position={jointMap.shoulderR}
        scale={P.shoulderCapScale}
        color={shoulderCapsuleColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.6}
        transparent={liveShading !== "overlay_style"}
      />
      <CapsuleBetween
        name="upper_arm_l"
        start={shoulderL}
        end={elbowL}
        radius={P.upperArmRadius}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        transparent={liveShading !== "overlay_style"}
      />
      <CapsuleBetween
        name="forearm_l"
        start={elbowL}
        end={wristL}
        radius={P.forearmRadius}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        transparent={liveShading !== "overlay_style"}
      />
      <EllipsoidMesh
        name="hand_l"
        position={jointMap.wristL}
        scale={P.handScale}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.58}
        transparent={liveShading !== "overlay_style"}
      />
      <CapsuleBetween
        name="upper_arm_r"
        start={shoulderR}
        end={elbowR}
        radius={P.upperArmRadius}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        transparent={liveShading !== "overlay_style"}
      />
      <CapsuleBetween
        name="forearm_r"
        start={elbowR}
        end={wristR}
        radius={P.forearmRadius}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        transparent={liveShading !== "overlay_style"}
      />
      <EllipsoidMesh
        name="hand_r"
        position={jointMap.wristR}
        scale={P.handScale}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.58}
        transparent={liveShading !== "overlay_style"}
      />
      <CapsuleBetween
        name="thigh_l"
        start={hipL}
        end={kneeL}
        radius={P.thighRadius}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        transparent={liveShading !== "overlay_style"}
      />
      <CapsuleBetween
        name="calf_l"
        start={kneeL}
        end={ankleL}
        radius={P.calfRadius}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        transparent={liveShading !== "overlay_style"}
      />
      <EllipsoidMesh
        name="foot_l"
        position={[jointMap.ankleL[0] + 0.018, jointMap.ankleL[1] - 0.038, jointMap.ankleL[2] + 0.052]}
        scale={P.footScale}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.6}
        transparent={liveShading !== "overlay_style"}
      />
      <CapsuleBetween
        name="thigh_r"
        start={hipR}
        end={kneeR}
        radius={P.thighRadius}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        transparent={liveShading !== "overlay_style"}
      />
      <CapsuleBetween
        name="calf_r"
        start={kneeR}
        end={ankleR}
        radius={P.calfRadius}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        transparent={liveShading !== "overlay_style"}
      />
      <EllipsoidMesh
        name="foot_r"
        position={[jointMap.ankleR[0] - 0.018, jointMap.ankleR[1] - 0.038, jointMap.ankleR[2] + 0.052]}
        scale={P.footScale}
        color={bodyColor}
        opacity={bodyOpacity}
        emissive={bodyEmissive}
        roughness={0.6}
        transparent={liveShading !== "overlay_style"}
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
  const leftSleevePivotRef = useRef<THREE.Group>(null);
  const rightSleevePivotRef = useRef<THREE.Group>(null);
  const leftSleeveBoneFollowRef = useRef<THREE.Group>(null);
  const rightSleeveBoneFollowRef = useRef<THREE.Group>(null);
  const topAnchorRef = useRef<THREE.Group>(null);
  const bottomAnchorRef = useRef<THREE.Group>(null);
  const attachmentMarkersRef = useRef<THREE.Group>(null);
  const lastAnchorDebugJson = useRef("");

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
  } else if (liveShading === "overlay_style") {
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
          <ambientLight intensity={0.5} />
          <directionalLight position={[4, 10, 6]} intensity={0.9} />
          <directionalLight position={[-3, 4, -4]} intensity={0.35} />
        </>
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

      <group ref={avatarWorldFitRef} position={worldOff} scale={[gsx, gsy, gsz]} name="avatar_world_fit">
        <group
          ref={torsoRegionFitRef}
          position={bodyAnchorPos}
          scale={bodyAnchorScale}
          name="avatar_torso_region_fit"
        >
          {showRigDebug ? <RigDebugAnchors jointMap={jointMap} /> : null}
          {showGarmentRigDebug ? <GarmentRigDebugOverlay rig={rig} /> : null}

          {showBodyMesh && (runtimeBodyBundledModule != null || runtimeBodyGltfUrl) ? (
            <GltfErrorBoundary
              key={String(runtimeBodyBundledModule ?? runtimeBodyGltfUrl ?? "")}
              fallback={<ProceduralRigBody {...rigMat} />}
              onLoadError={onRuntimeBodyLoadError}
            >
              <Suspense fallback={<ProceduralRigBody {...rigMat} />}>
                <group ref={bodyRootRef} position={[0, 0, 0]} name="gltf_body_root">
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
              {!hideGarments && !runtimeTopGltfUrl ? (
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
            </GltfErrorBoundary>
          ) : showBodyMesh ? (
            <group ref={bodyRootRef} name="procedural_body_root">
              <ProceduralRigBody {...rigMat} />
            </group>
          ) : null}

          {/* Top: torso hull (sleeves ride on arms inside procedural rig) */}
          {!hideGarments ? (
          <group
            ref={topAnchorRef}
            name="garment_top_anchor"
            position={[0, topAnchorY, topAnchorZ]}
            scale={[shirtInfl, 1 + r.torso.inflate * 1.2, shirtInfl]}
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
                  <group position={[0, rig.gltfTopMountY, 0]}>
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
          ) : null}

          {!hideGarments ? (
          <group
            ref={bottomAnchorRef}
            name="garment_bottom_anchor"
            position={[0, bottomAnchorY, bottomAnchorZ]}
            scale={[
              1 - r.waist.tighten * 0.48,
              1 - r.waist.tighten * 0.32,
              1 - r.waist.tighten * 0.26,
            ]}
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
                  <group position={[0, rig.gltfBottomMountY + r.hem.offsetY, 0]}>
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
                  <mesh key={i} position={[0, 0, 0]}>
                    <sphereGeometry args={[0.016, 6, 6]} />
                    <meshBasicMaterial color={color} depthTest={false} />
                  </mesh>
                ))}
              </group>
            </>
          ) : null}

          {showShoes && !hideGarments ? (
            <group position={[0, r.hem.offsetY * 0.45, 0]} name="shoes_proxy">
              <mesh position={[0.09, 0.04, 0.04]}>
                <boxGeometry args={[0.12, 0.08, 0.22]} />
                <meshStandardMaterial
                  color={shoeColor}
                  transparent
                  opacity={shoeOpacity}
                  roughness={0.45}
                />
              </mesh>
              <mesh position={[-0.09, 0.04, 0.04]}>
                <boxGeometry args={[0.12, 0.08, 0.22]} />
                <meshStandardMaterial
                  color={shoeColor}
                  transparent
                  opacity={shoeOpacity}
                  roughness={0.45}
                />
              </mesh>
            </group>
          ) : null}
        </group>
      </group>
    </>
  );
}
