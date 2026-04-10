import { useFrame, useThree } from "@react-three/fiber/native";
import { Suspense, useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";

import type { GarmentFitState } from "@/features/avatar-export";
import {
  DEV_AVATAR_PRESETS,
  type DevAvatarPoseKey,
  type DevAvatarPresetKey,
  presetGarmentColors,
} from "@/features/avatar-export/dev-avatar-shared";

import {
  applySleeveGarmentDeformation,
  applyTopGarmentDeformation,
  deformGarmentObject3D,
} from "./garment-deformation";
import {
  GltfErrorBoundary,
  GltfRuntimeBody,
  GltfRuntimeGarment,
} from "./gltf-runtime-body";
import type { LiveViewportShadingMode } from "./live-viewport-shading";

const SKIN = new THREE.Color(0xd4a574);
const SKIN_DIM = new THREE.Color(0xa07850);

/**
 * Scene-space anchors (meters-ish, ~1.78m footprint). Ground y=0; rig built upward.
 * Garments and GLTF placeholders should use these instead of magic numbers.
 */
export const AVATAR_RIG_ANCHORS = {
  /** Hip / pelvis center */
  pelvisY: 0.98,
  /** Torso (chest) capsule center */
  chestY: 1.15,
  /** Shoulder joint height */
  shoulderY: 1.34,
  /** Half shoulder span (left shoulder at +x) */
  shoulderHalf: 0.188,
  /** Head center */
  headY: 1.52,
  /** Hem / pant top proxy anchor (below pelvis, standing on ground plane) */
  pantsProxyHemY: 0.56,
  /** GLB top mesh mount under chest garment group */
  gltfTopMountY: 1.12,
  /** GLB bottom mount relative to waist garment group */
  gltfBottomMountY: 0.44,
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

type Orbit = { theta: number; phi: number; radius: number };

/** Orbits camera around `target` using spherical coords (theta=yaw, phi=polar, radius). */
export function CameraRig({
  orbit,
  target,
}: {
  orbit: Orbit;
  target: [number, number, number];
}) {
  const { camera } = useThree();
  const t = useMemo(() => new THREE.Vector3(...target), [target]);

  useFrame(() => {
    const { theta, phi, radius } = orbit;
    const x = t.x + radius * Math.sin(phi) * Math.cos(theta);
    const y = t.y + radius * Math.cos(phi);
    const z = t.z + radius * Math.sin(phi) * Math.sin(theta);
    camera.position.set(x, y, z);
    camera.lookAt(t);
    camera.updateProjectionMatrix();
  });
  return null;
}

/**
 * Pose joint targets (radians). Left/right arm Z rotations are opposite signs at the shoulder;
 * right upper-arm local flex uses negated rax so elbows mirror in world space.
 */
export function poseAngles(pose: DevAvatarPoseKey) {
  switch (pose) {
    case "relaxed":
      return {
        laz: 0.12,
        raz: -0.12,
        lax: 0.48,
        rax: 0.48,
        laxz: 0.02,
        llx: 0.04,
        rlx: -0.06,
      };
    case "walk":
      return {
        laz: 0.38,
        raz: -0.38,
        lax: 0.36,
        rax: 0.36,
        laxz: 0.1,
        llx: 0.28,
        rlx: -0.32,
      };
    case "tpose":
      return {
        laz: 1.38,
        raz: -1.38,
        lax: 0,
        rax: 0,
        laxz: 0,
        llx: 0,
        rlx: 0,
      };
    case "apose":
      return {
        laz: 0.55,
        raz: -0.55,
        lax: 0,
        rax: 0,
        laxz: 0,
        llx: 0,
        rlx: 0,
      };
    default:
      return { laz: 0, raz: 0, lax: 0, rax: 0, laxz: 0, llx: 0, rlx: 0 };
  }
}

type RigMaterialProps = {
  ang: ReturnType<typeof poseAngles>;
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
  spx: number;
  spy: number;
  spz: number;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  useLayoutEffect(() => {
    const m = meshRef.current;
    if (!m?.geometry) return;
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
      <capsuleGeometry args={[0.075 * sleeveS, 0.34, 8, 16]} />
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
  topColor,
  shirtOpacity,
  topEmissive,
  clipEmissiveAdd,
  garmentFit,
  inflateK,
}: {
  topColor: THREE.Color;
  shirtOpacity: number;
  topEmissive: THREE.Color;
  clipEmissiveAdd?: THREE.Color | null;
  garmentFit: GarmentFitState;
  inflateK: number;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  useLayoutEffect(() => {
    const m = meshRef.current;
    if (!m?.geometry) return;
    applyTopGarmentDeformation(m.geometry, garmentFit);
  }, [garmentFit]);
  const shirtEmissive = useMemo(() => {
    const e = topEmissive.clone();
    if (clipEmissiveAdd) e.add(clipEmissiveAdd);
    return e;
  }, [topEmissive, clipEmissiveAdd]);
  return (
    <mesh ref={meshRef} position={[0, AVATAR_RIG_ANCHORS.chestY, 0]} castShadow>
      <boxGeometry args={[0.48 * inflateK, 0.36 * inflateK, 0.3 * inflateK, 10, 10, 10]} />
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
  bottomColor,
  pantOpacity,
  bottomEmissive,
  clipEmissiveAdd,
  hemYOffset,
  garmentFit,
}: {
  bottomColor: THREE.Color;
  pantOpacity: number;
  bottomEmissive: THREE.Color;
  clipEmissiveAdd?: THREE.Color | null;
  hemYOffset: number;
  garmentFit: GarmentFitState;
}) {
  const y = AVATAR_RIG_ANCHORS.pantsProxyHemY;
  const groupRef = useRef<THREE.Group>(null);
  useLayoutEffect(() => {
    const root = groupRef.current;
    if (!root) return;
    deformGarmentObject3D(root, garmentFit, "bottom");
  }, [garmentFit]);
  const pantsEmissive = useMemo(() => {
    const e = bottomEmissive.clone();
    if (clipEmissiveAdd) e.add(clipEmissiveAdd);
    return e;
  }, [bottomEmissive, clipEmissiveAdd]);
  return (
    <group ref={groupRef}>
      <mesh position={[0, y + hemYOffset, 0]}>
        <boxGeometry args={[0.33, 0.46, 0.26, 10, 12, 8]} />
        <meshStandardMaterial
          color={bottomColor}
          transparent
          opacity={pantOpacity}
          emissive={pantsEmissive}
          roughness={0.7}
        />
      </mesh>
      <mesh position={[0.09, y - 0.34 + hemYOffset, 0]}>
        <capsuleGeometry args={[0.085, 0.48, 8, 16]} />
        <meshStandardMaterial
          color={bottomColor}
          transparent
          opacity={pantOpacity}
          emissive={pantsEmissive}
        />
      </mesh>
      <mesh position={[-0.09, y - 0.34 + hemYOffset, 0]}>
        <capsuleGeometry args={[0.085, 0.48, 8, 16]} />
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

function RigDebugAnchors() {
  const m = 0.028;
  const mk = (color: string, pos: [number, number, number]) => (
    <mesh key={`${pos.join(",")}`} position={pos}>
      <sphereGeometry args={[m, 8, 8]} />
      <meshBasicMaterial color={color} depthTest={false} />
    </mesh>
  );
  return (
    <group>
      {mk("#22c55e", [0, AVATAR_RIG_ANCHORS.pelvisY, 0])}
      {mk("#3b82f6", [0, AVATAR_RIG_ANCHORS.chestY, 0])}
      {mk("#eab308", [AVATAR_RIG_ANCHORS.shoulderHalf, AVATAR_RIG_ANCHORS.shoulderY, 0])}
      {mk("#eab308", [-AVATAR_RIG_ANCHORS.shoulderHalf, AVATAR_RIG_ANCHORS.shoulderY, 0])}
      {mk("#f97316", [0, AVATAR_RIG_ANCHORS.headY, 0])}
    </group>
  );
}

/** Sleeve proxies matching arm pose when the skin body is GLTF (no procedural arms). */
function SleeveGarmentPair({
  ang,
  shirtOpacity,
  topColor,
  topEmissive,
  clipEmissiveSleeve,
  sleeveS,
  sleevePos,
  garmentFit,
}: Pick<
  RigMaterialProps,
  | "ang"
  | "shirtOpacity"
  | "topColor"
  | "topEmissive"
  | "clipEmissiveSleeve"
  | "sleeveS"
  | "sleevePos"
  | "garmentFit"
>) {
  const { shoulderY, shoulderHalf } = AVATAR_RIG_ANCHORS;
  const spx = sleevePos[0] * FIT_VIS.sleevePosMul;
  const spy = sleevePos[1] * FIT_VIS.sleevePosMul;
  const spz = sleevePos[2] * FIT_VIS.sleevePosMul;

  return (
    <group name="sleeve_garment_pair_gltf_body">
      <group
        position={[shoulderHalf, shoulderY, 0]}
        rotation={[ang.laxz, 0, ang.laz]}
      >
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
              spx={spx}
              spy={spy}
              spz={spz}
            />
          </group>
        </group>
      </group>
      <group
        position={[-shoulderHalf, shoulderY, 0]}
        rotation={[-ang.laxz, 0, ang.raz]}
      >
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

/**
 * avatarRoot (world fit)
 * └─ bodyAnchor (torso region: slide + scaleY)
 *    ├─ pelvis + legs
 *    ├─ torso + neck + head
 *    ├─ arms (+ sleeve proxies parented to shoulders)
 */
function ProceduralRigBody({
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
  const { pelvisY, chestY, shoulderY, shoulderHalf, headY } = AVATAR_RIG_ANCHORS;
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
      {/* ——— Pelvis & upper legs (thighs) ——— */}
      <group name="pelvis" position={[0, pelvisY, 0]}>
        <mesh castShadow>
          <boxGeometry args={[0.27, 0.2, 0.2]} />
          <meshStandardMaterial {...matProps(bodyOpacity)} />
        </mesh>
        <group name="leg_upper_l" position={[0.075, -0.06, 0]} rotation={[ang.llx, 0, 0]}>
          <mesh position={[0.02, -0.2, 0]} castShadow>
            <capsuleGeometry args={[0.072, 0.4, 4, 10]} />
            <meshStandardMaterial {...matProps(bodyOpacity)} />
          </mesh>
        </group>
        <group name="leg_upper_r" position={[-0.075, -0.06, 0]} rotation={[ang.rlx, 0, 0]}>
          <mesh position={[-0.02, -0.2, 0]} castShadow>
            <capsuleGeometry args={[0.072, 0.4, 4, 10]} />
            <meshStandardMaterial {...matProps(bodyOpacity)} />
          </mesh>
        </group>
      </group>

      {/* ——— Torso (chest / abdomen) ——— */}
      <group name="torso" position={[0, chestY, 0]}>
        <mesh castShadow>
          <capsuleGeometry args={[0.12, 0.34, 6, 12]} />
          <meshStandardMaterial {...matProps(bodyOpacity, 0.64)} />
        </mesh>
      </group>

      {/* ——— Neck stub (visual bridge) ——— */}
      <mesh position={[0, (chestY + headY) * 0.52, 0]} castShadow>
        <cylinderGeometry args={[0.07, 0.09, 0.1, 10]} />
        <meshStandardMaterial {...matProps(bodyOpacity)} />
      </mesh>

      {/* ——— Head ——— */}
      <group name="head" position={[0, headY, 0]}>
        <mesh castShadow>
          <sphereGeometry args={[0.11, 14, 14]} />
          <meshStandardMaterial {...matProps(bodyOpacity, 0.52)} />
        </mesh>
      </group>

      {/* ——— Arms: mirrored shoulder swing (right uses -laxz on X); right elbow -rax on Z ——— */}
      <group
        name="arm_l_bind"
        position={[shoulderHalf, shoulderY, 0]}
        rotation={[ang.laxz, 0, ang.laz]}
      >
        <group rotation={[0, 0, ang.lax]}>
          <mesh position={[0.14, -0.065, 0]} castShadow>
            <capsuleGeometry args={[0.054, 0.4, 4, 8]} />
            <meshStandardMaterial {...matProps(bodyOpacity)} />
          </mesh>
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
              spx={spx}
              spy={spy}
              spz={spz}
            />
          </group>
        </group>
      </group>

      <group
        name="arm_r_bind"
        position={[-shoulderHalf, shoulderY, 0]}
        rotation={[-ang.laxz, 0, ang.raz]}
      >
        <group rotation={[0, 0, -ang.rax]}>
          <mesh position={[-0.14, -0.065, 0]} castShadow>
            <capsuleGeometry args={[0.054, 0.4, 4, 8]} />
            <meshStandardMaterial {...matProps(bodyOpacity)} />
          </mesh>
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
  runtimeBodyGltfUrl = null,
  runtimeTopGltfUrl = null,
  runtimeBottomGltfUrl = null,
  includeSceneLights = true,
  showRigDebug = false,
  clipEmissiveTop = null,
  clipEmissiveBottom = null,
  clipEmissiveSleeve = null,
}: {
  pose: DevAvatarPoseKey;
  preset: DevAvatarPresetKey;
  garmentFit: GarmentFitState;
  liveShading: LiveViewportShadingMode;
  runtimeBodyGltfUrl?: string | null;
  runtimeTopGltfUrl?: string | null;
  runtimeBottomGltfUrl?: string | null;
  includeSceneLights?: boolean;
  /** Dev: small spheres at pelvis, chest, shoulders, head (depthTest off). */
  showRigDebug?: boolean;
  /** Runtime clipping overlay: emissive add for shirt / GLB top. */
  clipEmissiveTop?: THREE.Color | null;
  clipEmissiveBottom?: THREE.Color | null;
  clipEmissiveSleeve?: THREE.Color | null;
}) {
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

  if (liveShading === "body_focus") {
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
  const bodyAnchorPos = [
    0,
    tz * FIT_VIS.torsoOffsetY,
    tz * FIT_VIS.torsoOffsetZ,
  ] as [number, number, number];
  const bodyAnchorScale = [
    1 + r.torso.inflate * FIT_VIS.torsoInflateMul,
    r.torso.scaleY * (1 + r.torso.inflate * FIT_VIS.torsoInflateYMul),
    1 + r.torso.inflate * FIT_VIS.torsoInflateMul,
  ] as [number, number, number];

  const shirtInfl = 1 + r.torso.inflate * 2.2;

  const rigMat: RigMaterialProps = {
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

      <group position={worldOff} scale={[gsx, gsy, gsz]} name="avatar_world_fit">
        <group
          position={bodyAnchorPos}
          scale={bodyAnchorScale}
          name="avatar_torso_region_fit"
        >
          {showRigDebug ? <RigDebugAnchors /> : null}

          {runtimeBodyGltfUrl ? (
            <GltfErrorBoundary
              key={runtimeBodyGltfUrl}
              fallback={<ProceduralRigBody {...rigMat} />}
            >
              <Suspense fallback={<ProceduralRigBody {...rigMat} />}>
                <group position={[0, 0.04, 0]} name="gltf_body_align_lift">
                  <GltfRuntimeBody
                    url={runtimeBodyGltfUrl}
                    pose={pose}
                    liveShading={liveShading}
                  />
                </group>
              </Suspense>
              {!runtimeTopGltfUrl ? (
                <SleeveGarmentPair
                  ang={ang}
                  shirtOpacity={shirtOpacity}
                  topColor={topColor}
                  topEmissive={topEmissive}
                  clipEmissiveSleeve={clipEmissiveSleeve}
                  sleeveS={sleeveS}
                  sleevePos={sleevePos}
                  garmentFit={garmentFit}
                />
              ) : null}
            </GltfErrorBoundary>
          ) : (
            <ProceduralRigBody {...rigMat} />
          )}

          {/* Top: torso hull (sleeves ride on arms inside procedural rig) */}
          <group
            name="garment_top_anchor"
            position={[0, tz * 0.18, tz * 0.35]}
            scale={[shirtInfl, 1 + r.torso.inflate * 1.2, shirtInfl]}
          >
            {runtimeTopGltfUrl ? (
              <GltfErrorBoundary
                key={runtimeTopGltfUrl}
                fallback={
                  <ShirtTorsoProxy
                    topColor={topColor}
                    shirtOpacity={shirtOpacity}
                    topEmissive={topEmissive}
                    clipEmissiveAdd={clipEmissiveTop}
                    garmentFit={garmentFit}
                    inflateK={1.04}
                  />
                }
              >
                <Suspense
                  fallback={
                    <ShirtTorsoProxy
                      topColor={topColor}
                      shirtOpacity={shirtOpacity}
                      topEmissive={topEmissive}
                      clipEmissiveAdd={clipEmissiveTop}
                      garmentFit={garmentFit}
                      inflateK={1.04}
                    />
                  }
                >
                  <group position={[0, AVATAR_RIG_ANCHORS.gltfTopMountY, 0]}>
                    <GltfRuntimeGarment
                      url={runtimeTopGltfUrl}
                      liveShading={liveShading}
                      normalizeHeight={0.44}
                      garmentFit={garmentFit}
                      deformProfile="top"
                      clipEmissiveAdd={clipEmissiveTop ?? undefined}
                    />
                  </group>
                </Suspense>
              </GltfErrorBoundary>
            ) : (
              <ShirtTorsoProxy
                topColor={topColor}
                shirtOpacity={shirtOpacity}
                topEmissive={topEmissive}
                clipEmissiveAdd={clipEmissiveTop}
                garmentFit={garmentFit}
                inflateK={1.02 + r.torso.inflate}
              />
            )}
          </group>

          <group
            name="garment_bottom_anchor"
            position={[
              0,
              garmentFit.legacy.waistAdjustY,
              r.waist.offsetZ * FIT_VIS.waistOffsetZ,
            ]}
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
                    bottomColor={bottomColor}
                    pantOpacity={pantOpacity}
                    bottomEmissive={bottomEmissive}
                    clipEmissiveAdd={clipEmissiveBottom}
                    hemYOffset={r.hem.offsetY}
                    garmentFit={garmentFit}
                  />
                }
              >
                <Suspense
                  fallback={
                    <PantsGarmentProxies
                      bottomColor={bottomColor}
                      pantOpacity={pantOpacity}
                      bottomEmissive={bottomEmissive}
                      clipEmissiveAdd={clipEmissiveBottom}
                      hemYOffset={r.hem.offsetY}
                      garmentFit={garmentFit}
                    />
                  }
                >
                  <group position={[0, AVATAR_RIG_ANCHORS.gltfBottomMountY + r.hem.offsetY, 0]}>
                    <GltfRuntimeGarment
                      url={runtimeBottomGltfUrl}
                      liveShading={liveShading}
                      normalizeHeight={0.52}
                      garmentFit={garmentFit}
                      deformProfile="bottom"
                      clipEmissiveAdd={clipEmissiveBottom ?? undefined}
                    />
                  </group>
                </Suspense>
              </GltfErrorBoundary>
            ) : (
              <PantsGarmentProxies
                bottomColor={bottomColor}
                pantOpacity={pantOpacity}
                bottomEmissive={bottomEmissive}
                clipEmissiveAdd={clipEmissiveBottom}
                hemYOffset={r.hem.offsetY}
                garmentFit={garmentFit}
              />
            )}
          </group>

          {showShoes ? (
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
