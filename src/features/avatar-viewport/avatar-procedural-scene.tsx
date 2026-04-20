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

function GarmentSleeveProxyMesh({
  garmentFit,
  side,
  zRot,
  shirtOpacity,
  topColor,
  topEmissive,
  clipEmissiveAdd,
  sleeveS,
  sleeveRadius,
  spx,
  spy,
  spz,
}: {
  garmentFit: GarmentFitState;
  side: 1 | -1;
  zRot: number;
  shirtOpacity: number;
  topColor: THREE.Color;
  topEmissive: THREE.Color;
  clipEmissiveAdd?: THREE.Color | null;
  sleeveS: number;
  sleeveRadius: number;
  spx: number;
  spy: number;
  spz: number;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
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
      position={[side * 0.15, -0.04 + spy * 0.25, spz * 0.3]}
      rotation={[0, 0, zRot]}
      castShadow
    >
      <capsuleGeometry args={[sleeveRadius * sleeveS, 0.34, 8, 16]} />
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
  const chestK = rig.metrics.torsoCapsuleRadius / 0.114;
  const shirtY =
    torsoMountMode === "skinned_chest"
      ? rig.metrics.torsoCapsuleLength * 0.042
      : rig.chestY + rig.metrics.torsoCapsuleLength * 0.07;
  return (
    <mesh ref={meshRef} position={[0, shirtY, 0]} castShadow>
      <boxGeometry
        args={[
          0.48 * inflateK * chestK,
          0.36 * inflateK * chestK,
          0.3 * inflateK * chestK,
          10,
          10,
          10,
        ]}
      />
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
  const y =
    bottomMountMode === "skinned_pelvis"
      ? rig.pantsProxyHemY * 0.4 + 0.035
      : rig.pantsProxyHemY;
  const thighDrop = bottomMountMode === "skinned_pelvis" ? -0.27 : -0.34;
  const hipK = rig.metrics.pelvisBox[0] / 0.262;
  const legRK = rig.metrics.upperLegCapsule[0] / 0.066;
  const thighX = 0.09 * hipK;
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
  return (
    <group ref={groupRef}>
      <mesh position={[0, y + hemYOffset, 0]}>
        <boxGeometry args={[0.33 * hipK, 0.46, 0.26 * hipK, 10, 12, 8]} />
        <meshStandardMaterial
          color={bottomColor}
          transparent
          opacity={pantOpacity}
          emissive={pantsEmissive}
          roughness={0.7}
        />
      </mesh>
      <mesh position={[thighX, y + thighDrop + hemYOffset, 0]}>
        <capsuleGeometry args={[0.085 * legRK, 0.48, 8, 16]} />
        <meshStandardMaterial
          color={bottomColor}
          transparent
          opacity={pantOpacity}
          emissive={pantsEmissive}
        />
      </mesh>
      <mesh position={[-thighX, y + thighDrop + hemYOffset, 0]}>
        <capsuleGeometry args={[0.085 * legRK, 0.48, 8, 16]} />
        <meshStandardMaterial
          color={bottomColor}
          transparent
          opacity={pantOpacity}
          emissive={pantsEmissive}
        />
      </mesh>
    </group>
  );
}

function RigDebugAnchors({ rig }: { rig: BodySceneAnchors }) {
  const m = 0.028;
  const M = rig.metrics;
  const [, , neckH] = M.neckCylinder;
  const neckMidY = M.neckBaseY + neckH * 0.5;
  const hipY = rig.pelvisY + M.hipPitchLocalY;
  const mk = (color: string, pos: [number, number, number], key: string) => (
    <mesh key={key} position={pos}>
      <sphereGeometry args={[m, 8, 8]} />
      <meshBasicMaterial color={color} depthTest={false} />
    </mesh>
  );
  return (
    <group>
      {mk("#22c55e", [0, rig.pelvisY, 0], "pelvis")}
      {mk("#84cc16", [0, M.pelvisTopY, 0], "pelvis_top")}
      {mk("#06b6d4", [M.legGroupOffsetX, hipY, 0], "hip_l")}
      {mk("#06b6d4", [-M.legGroupOffsetX, hipY, 0], "hip_r")}
      {mk("#3b82f6", [0, rig.chestY, 0], "torso")}
      {mk("#38bdf8", [0, M.torsoBotY, 0], "torso_bot")}
      {mk("#a855f7", [0, neckMidY, 0], "neck")}
      {mk("#eab308", [rig.shoulderHalf, rig.shoulderY, 0], "sh_l")}
      {mk("#eab308", [-rig.shoulderHalf, rig.shoulderY, 0], "sh_r")}
      {mk("#f97316", [0, rig.headY, 0], "head")}
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
              side={1}
              zRot={0.08}
              shirtOpacity={shirtOpacity}
              topColor={topColor}
              topEmissive={topEmissive}
              clipEmissiveAdd={clipEmissiveSleeve}
              sleeveS={sleeveS}
              sleeveRadius={sleeveRadius}
              spx={spx}
              spy={spy}
              spz={spz}
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
              side={-1}
              zRot={-0.08}
              shirtOpacity={shirtOpacity}
              topColor={topColor}
              topEmissive={topEmissive}
              clipEmissiveAdd={clipEmissiveSleeve}
              sleeveS={sleeveS}
              sleeveRadius={sleeveRadius}
              spx={spx}
              spy={spy}
              spz={spz}
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
  ang,
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
  const { pelvisY, chestY, shoulderY, shoulderHalf, headY } = rig;
  const M = rig.metrics;
  const [neckRt, neckRb, neckH] = M.neckCylinder;
  const sleeveRadius = M.upperArmCapsule[0];
  const [legRad, thighLen] = M.upperLegCapsule;
  const [shinRad, shinLen] = M.shinCapsule;
  const [armRad, upperArmLen] = M.upperArmCapsule;
  const [foreRad, foreLen] = M.forearmCapsule;
  const neckCenterY = M.neckBaseY + neckH * 0.5;

  const { torsoBotY, pelvisTopY } = M;
  const lumbarGap = torsoBotY - pelvisTopY;
  const torsoPelvisOverlap = pelvisTopY - torsoBotY;

  const thighMeshY = -0.45 * thighLen;
  const kneeY = -0.9 * thighLen;
  const shinMeshY = -0.42 * shinLen;
  const kneeFlexL = -ang.llx * 0.52;
  const kneeFlexR = -ang.rlx * 0.52;

  const upperArmY = -0.4 * upperArmLen;
  const elbowY = -0.82 * upperArmLen;
  const forearmY = -0.38 * foreLen;

  const matProps = (opacity: number, roughness = 0.62) => ({
    color: bodyColor,
    transparent: liveShading !== "overlay_style",
    opacity,
    emissive: bodyEmissive,
    roughness,
  });

  const spx = sleevePos[0] * FIT_VIS.sleevePosMul;
  const spy = sleevePos[1] * FIT_VIS.sleevePosMul;
  const spz = sleevePos[2] * FIT_VIS.sleevePosMul;

  return (
    <group name="avatar_procedural_rig">
      <group name="pelvis_root" position={[0, pelvisY, 0]}>
        <mesh castShadow name="pelvis_mesh">
          <boxGeometry args={M.pelvisBox} />
          <meshStandardMaterial {...matProps(bodyOpacity)} />
        </mesh>

        <group
          name="hip_l"
          position={[M.legGroupOffsetX, M.hipPitchLocalY, 0]}
          rotation={[ang.llx, 0, 0]}
        >
          <mesh position={[M.legMeshOffsetX, thighMeshY, 0]} castShadow name="thigh_l">
            <capsuleGeometry args={[legRad, thighLen, 4, 10]} />
            <meshStandardMaterial {...matProps(bodyOpacity)} />
          </mesh>
          <group
            name="knee_l"
            position={[M.legMeshOffsetX, kneeY, 0]}
            rotation={[kneeFlexL, 0, 0]}
          >
            <mesh position={[0, shinMeshY, 0]} castShadow name="shin_l">
              <capsuleGeometry args={[shinRad, shinLen, 4, 10]} />
              <meshStandardMaterial {...matProps(bodyOpacity)} />
            </mesh>
          </group>
        </group>

        <group
          name="hip_r"
          position={[-M.legGroupOffsetX, M.hipPitchLocalY, 0]}
          rotation={[ang.rlx, 0, 0]}
        >
          <mesh position={[-M.legMeshOffsetX, thighMeshY, 0]} castShadow name="thigh_r">
            <capsuleGeometry args={[legRad, thighLen, 4, 10]} />
            <meshStandardMaterial {...matProps(bodyOpacity)} />
          </mesh>
          <group
            name="knee_r"
            position={[-M.legMeshOffsetX, kneeY, 0]}
            rotation={[kneeFlexR, 0, 0]}
          >
            <mesh position={[0, shinMeshY, 0]} castShadow name="shin_r">
              <capsuleGeometry args={[shinRad, shinLen, 4, 10]} />
              <meshStandardMaterial {...matProps(bodyOpacity)} />
            </mesh>
          </group>
        </group>
      </group>

      {lumbarGap > 0.004 ? (
        <mesh
          position={[0, (pelvisTopY + torsoBotY) * 0.5, 0]}
          castShadow
          name="lumbar_bridge"
        >
          <cylinderGeometry
            args={[
              M.torsoCapsuleRadius * 0.74,
              M.pelvisBox[0] * 0.36,
              lumbarGap,
              10,
            ]}
          />
          <meshStandardMaterial {...matProps(bodyOpacity, 0.66)} />
        </mesh>
      ) : null}
      {torsoPelvisOverlap > 0.003 ? (
        <mesh
          position={[0, (pelvisTopY + torsoBotY) * 0.5, 0]}
          castShadow
          name="waist_blend"
        >
          <cylinderGeometry
            args={[
              M.torsoCapsuleRadius * 0.82,
              Math.min(M.pelvisBox[0], M.pelvisBox[2]) * 0.44,
              torsoPelvisOverlap + 0.01,
              10,
            ]}
          />
          <meshStandardMaterial {...matProps(bodyOpacity, 0.68)} />
        </mesh>
      ) : null}

      <group name="spine_torso" position={[0, chestY, 0]}>
        <mesh castShadow name="torso_capsule">
          <capsuleGeometry args={[M.torsoCapsuleRadius, M.torsoCapsuleLength, 6, 12]} />
          <meshStandardMaterial {...matProps(bodyOpacity, 0.64)} />
        </mesh>
      </group>

      <mesh position={[0, neckCenterY, 0]} castShadow name="neck_stub">
        <cylinderGeometry args={[neckRt, neckRb, neckH, 10]} />
        <meshStandardMaterial {...matProps(bodyOpacity)} />
      </mesh>

      <group name="head" position={[0, headY, 0]}>
        <mesh castShadow name="head_sphere">
          <sphereGeometry args={[M.headRadius, 14, 14]} />
          <meshStandardMaterial {...matProps(bodyOpacity, 0.52)} />
        </mesh>
      </group>

      <group
        name="shoulder_l"
        position={[shoulderHalf, shoulderY, 0]}
        rotation={[ang.laxz, 0, ang.laz]}
      >
        <group name="upper_arm_l" rotation={[0, 0, ang.lax]}>
          <mesh position={[M.armMeshOffsetX, upperArmY, 0]} castShadow name="humerus_l">
            <capsuleGeometry args={[armRad, upperArmLen, 4, 8]} />
            <meshStandardMaterial {...matProps(bodyOpacity)} />
          </mesh>
          <group
            name="forearm_l"
            position={[M.armMeshOffsetX, elbowY, 0]}
            rotation={[0, 0, ang.lax * 0.32]}
          >
            <mesh position={[0, forearmY, 0]} castShadow name="radius_l">
              <capsuleGeometry args={[foreRad, foreLen, 4, 8]} />
              <meshStandardMaterial {...matProps(bodyOpacity)} />
            </mesh>
          </group>
          {/* Sleeve after forearm so garment proxy sorts above skin */}
          <group position={[spx, spy, spz]} scale={[sleeveS, sleeveS, sleeveS]}>
            <GarmentSleeveProxyMesh
              garmentFit={garmentFit}
              side={1}
              zRot={0.08}
              shirtOpacity={shirtOpacity}
              topColor={topColor}
              topEmissive={topEmissive}
              clipEmissiveAdd={clipEmissiveSleeve}
              sleeveS={sleeveS}
              sleeveRadius={sleeveRadius}
              spx={spx}
              spy={spy}
              spz={spz}
            />
          </group>
        </group>
      </group>

      <group
        name="shoulder_r"
        position={[-shoulderHalf, shoulderY, 0]}
        rotation={[-ang.laxz, 0, ang.raz]}
      >
        <group name="upper_arm_r" rotation={[0, 0, -ang.rax]}>
          <mesh position={[-M.armMeshOffsetX, upperArmY, 0]} castShadow name="humerus_r">
            <capsuleGeometry args={[armRad, upperArmLen, 4, 8]} />
            <meshStandardMaterial {...matProps(bodyOpacity)} />
          </mesh>
          <group
            name="forearm_r"
            position={[-M.armMeshOffsetX, elbowY, 0]}
            rotation={[0, 0, -ang.rax * 0.32]}
          >
            <mesh position={[0, forearmY, 0]} castShadow name="radius_r">
              <capsuleGeometry args={[foreRad, foreLen, 4, 8]} />
              <meshStandardMaterial {...matProps(bodyOpacity)} />
            </mesh>
          </group>
          <group position={[-spx, spy, spz]} scale={[sleeveS, sleeveS, sleeveS]}>
            <GarmentSleeveProxyMesh
              garmentFit={garmentFit}
              side={-1}
              zRot={-0.08}
              shirtOpacity={shirtOpacity}
              topColor={topColor}
              topEmissive={topEmissive}
              clipEmissiveAdd={clipEmissiveSleeve}
              sleeveS={sleeveS}
              sleeveRadius={sleeveRadius}
              spx={spx}
              spy={spy}
              spz={spz}
            />
          </group>
        </group>
      </group>
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
          {showRigDebug ? <RigDebugAnchors rig={rig} /> : null}
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
