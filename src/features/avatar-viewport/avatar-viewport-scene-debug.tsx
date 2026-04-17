import { useFrame, useThree } from "@react-three/fiber/native";
import { useMemo, useRef } from "react";
import type { MutableRefObject, RefObject } from "react";
import * as THREE from "three";

import type { AvatarViewportNavSettings } from "./avatar-viewport-nav-settings";
import type { LiveViewportSceneDiagnostics } from "./live-viewport-debug-types";
import { findFirstSkinnedMesh } from "./skinned-body-pose";

type OrbitSpherical = { theta: number; phi: number; radius: number };

export type SceneSpaceDebugOrbitBindings = {
  desiredRef: RefObject<OrbitSpherical>;
  smoothRef: RefObject<OrbitSpherical>;
  navRef: RefObject<AvatarViewportNavSettings>;
  targetBaseRef: RefObject<[number, number, number]>;
  targetPanRef: RefObject<{ x: number; z: number }>;
};

function clampOrbit(o: OrbitSpherical, nav: AvatarViewportNavSettings): OrbitSpherical {
  return {
    theta: o.theta,
    phi: Math.min(nav.polarMax, Math.max(nav.polarMin, o.phi)),
    radius: Math.min(nav.maxRadius, Math.max(nav.minRadius, o.radius)),
  };
}

function computeLookTarget(
  nav: AvatarViewportNavSettings,
  targetBaseRef: RefObject<[number, number, number]>,
  targetPanRef: RefObject<{ x: number; z: number }>,
  out: THREE.Vector3,
): THREE.Vector3 {
  const tb = targetBaseRef.current ?? [0, 1.12, 0];
  const pan = targetPanRef.current ?? { x: 0, z: 0 };
  out.set(tb[0] + pan.x, tb[1] + nav.targetYOffset, tb[2] + pan.z);
  return out;
}

function bodyBoundsValid(box: THREE.Box3, sizeOut: THREE.Vector3): boolean {
  if (box.isEmpty()) return false;
  box.getSize(sizeOut);
  return (
    Number.isFinite(sizeOut.x) &&
    Number.isFinite(sizeOut.y) &&
    Number.isFinite(sizeOut.z) &&
    sizeOut.lengthSq() > 1e-10
  );
}

function applyFramingToOrbit(
  box: THREE.Box3,
  nav: AvatarViewportNavSettings,
  orbit: SceneSpaceDebugOrbitBindings,
  camera: THREE.PerspectiveCamera,
  logTag: string,
): void {
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const halfMax = Math.max(size.x, size.y, size.z) * 0.5;
  const vFov = THREE.MathUtils.degToRad(camera.fov);
  const margin = 0.18;
  const distByFov = halfMax > 1e-6 ? halfMax / Math.tan(vFov * 0.5) + margin : 2.4;
  const dist = Math.max(distByFov, halfMax * 1.75 + 0.28, 1.15);
  const radius = Math.min(nav.maxRadius, Math.max(nav.minRadius, dist));
  const targetYBias = size.y * 0.07;
  const tb = orbit.targetBaseRef as MutableRefObject<[number, number, number]>;
  tb.current = [center.x, center.y + targetYBias, center.z];
  const pan = orbit.targetPanRef as MutableRefObject<{ x: number; z: number }>;
  pan.current = { x: 0, z: 0 };
  const framed: OrbitSpherical = clampOrbit(
    { theta: 0.52, phi: 1.02, radius },
    nav,
  );
  const d = orbit.desiredRef as MutableRefObject<OrbitSpherical>;
  const s = orbit.smoothRef as MutableRefObject<OrbitSpherical>;
  d.current = { ...framed };
  s.current = { ...framed };
  if (__DEV__) {
    console.log(`[AvatarViewportScene] ${logTag}`, {
      target: [...tb.current] as [number, number, number],
      radius: framed.radius,
      boundsCenter: center.toArray(),
      boundsSize: size.toArray(),
    });
  }
}

type Props = {
  enabled: boolean;
  showMarkers: boolean;
  bodyRootRef: RefObject<THREE.Group | null>;
  avatarWorldFitRef: RefObject<THREE.Group | null>;
  torsoRegionFitRef: RefObject<THREE.Group | null>;
  orbit: SceneSpaceDebugOrbitBindings;
  bodyLoadGeneration: number;
  /** Increments on "Frame avatar bounds" — only reacts when `> last applied`. */
  manualFrameBoundsNonce: number;
  onDiagnostics?: (d: LiveViewportSceneDiagnostics) => void;
};

/**
 * Dev-only: world markers, bounds helper, orbit framing from measured body AABB, throttled diagnostics.
 * Runs logic in `useFrame` — avoids per-frame React setState.
 */
export function ViewportSceneSpaceDebug({
  enabled,
  showMarkers,
  bodyRootRef,
  avatarWorldFitRef,
  torsoRegionFitRef,
  orbit,
  bodyLoadGeneration,
  manualFrameBoundsNonce,
  onDiagnostics,
}: Props) {
  const { camera, scene } = useThree();
  const box = useMemo(() => new THREE.Box3(), []);
  const size = useMemo(() => new THREE.Vector3(), []);
  const center = useMemo(() => new THREE.Vector3(), []);
  const tmp = useMemo(() => new THREE.Vector3(), []);
  const fwd = useMemo(() => new THREE.Vector3(), []);
  const toBody = useMemo(() => new THREE.Vector3(), []);
  const rootWorld = useMemo(() => new THREE.Vector3(), []);
  const lookTarget = useMemo(() => new THREE.Vector3(), []);
  const lastDiagJson = useRef("");
  const frameI = useRef(0);
  const lastManualFrameNonceApplied = useRef(0);
  const lastBodyGen = useRef(-1);
  const didAutoFrameForGen = useRef(false);
  const tryAutoFrames = useRef(0);
  const skinnedCache = useRef<THREE.SkinnedMesh | null>(null);
  const skinnedScan = useRef(0);

  const boxHelper = useMemo(() => new THREE.Box3Helper(new THREE.Box3(), 0xff00cc), []);
  const worldAxes = useMemo(() => new THREE.AxesHelper(0.42), []);
  const grid = useMemo(
    () => new THREE.GridHelper(5.5, 22, 0x777777, 0x3a3a3a),
    [],
  );

  const camTargetGrp = useRef<THREE.Group>(null);
  const bodyCenterGrp = useRef<THREE.Group>(null);
  const avatarRootGrp = useRef<THREE.Group>(null);
  const torsoGrp = useRef<THREE.Group>(null);
  const skelGrp = useRef<THREE.Group>(null);

  useFrame(() => {
    if (!enabled) return;

    scene.updateMatrixWorld(true);
    const root = bodyRootRef.current;
    box.makeEmpty();
    let loaded = false;
    if (root) {
      box.setFromObject(root);
      loaded = bodyBoundsValid(box, size);
    }

    const nav = orbit.navRef.current!;
    computeLookTarget(nav, orbit.targetBaseRef, orbit.targetPanRef, lookTarget);
    skinnedScan.current += 1;
    if (root && (skinnedScan.current % 10 === 0 || !skinnedCache.current)) {
      skinnedCache.current = findFirstSkinnedMesh(root);
    }
    const sm = skinnedCache.current;
    let skelPos: [number, number, number] | null = null;
    if (sm?.skeleton?.bones?.[0]) {
      sm.skeleton.bones[0].getWorldPosition(tmp);
      skelPos = [tmp.x, tmp.y, tmp.z];
      if (skelGrp.current) {
        skelGrp.current.visible = showMarkers;
        skelGrp.current.position.copy(tmp);
      }
    } else if (skelGrp.current) {
      skelGrp.current.visible = false;
    }

    if (loaded) {
      box.getCenter(center);
        boxHelper.box.copy(box);
      boxHelper.visible = !!(showMarkers && loaded);
      boxHelper.updateMatrixWorld(true);
      if (bodyCenterGrp.current) {
        bodyCenterGrp.current.visible = showMarkers;
        bodyCenterGrp.current.position.copy(center);
      }
    } else {
      boxHelper.visible = false;
      if (bodyCenterGrp.current) bodyCenterGrp.current.visible = false;
    }

    if (camTargetGrp.current) {
      camTargetGrp.current.visible = showMarkers;
      camTargetGrp.current.position.copy(lookTarget);
    }
    if (avatarRootGrp.current && avatarWorldFitRef.current) {
      avatarWorldFitRef.current.getWorldPosition(tmp);
      avatarRootGrp.current.visible = showMarkers;
      avatarRootGrp.current.position.copy(tmp);
    }
    if (torsoGrp.current && torsoRegionFitRef.current) {
      torsoRegionFitRef.current.getWorldPosition(tmp);
      torsoGrp.current.visible = showMarkers;
      torsoGrp.current.position.copy(tmp);
    }

    const pcam = camera as THREE.PerspectiveCamera;
    fwd.subVectors(lookTarget, camera.position);
    if (fwd.lengthSq() > 1e-12) fwd.normalize();
    toBody.subVectors(center, camera.position);
    const depthAlong = toBody.dot(fwd);
    const distTargetToBody = center.distanceTo(lookTarget);
    const framed =
      loaded &&
      depthAlong > pcam.near * 0.9 &&
      depthAlong < pcam.far * 0.98 &&
      distTargetToBody < orbit.smoothRef.current!.radius * 2.4 + size.length() * 0.35;

    if (root) {
      root.getWorldPosition(rootWorld);
    }

    const diag: LiveViewportSceneDiagnostics = {
      bodyLoaded: loaded,
      bodyRootWorld: root ? (rootWorld.toArray() as [number, number, number]) : [0, 0, 0],
      boundsCenter: loaded ? center.toArray() as [number, number, number] : [0, 0, 0],
      boundsSize: loaded ? size.toArray() as [number, number, number] : [0, 0, 0],
      cameraPosition: camera.position.toArray() as [number, number, number],
      cameraTarget: lookTarget.toArray() as [number, number, number],
      distTargetToBodyCenter: loaded ? distTargetToBody : -1,
      framedHeuristic: framed,
      skeletonRootWorld: skelPos,
    };

    frameI.current += 1;
    if (onDiagnostics && frameI.current % 8 === 0) {
      const j = JSON.stringify(diag);
      if (j !== lastDiagJson.current) {
        lastDiagJson.current = j;
        onDiagnostics(diag);
      }
    }

    if (bodyLoadGeneration !== lastBodyGen.current) {
      lastBodyGen.current = bodyLoadGeneration;
      didAutoFrameForGen.current = false;
      tryAutoFrames.current = 0;
      lastManualFrameNonceApplied.current = 0;
    }

    if (
      loaded &&
      manualFrameBoundsNonce > lastManualFrameNonceApplied.current
    ) {
      applyFramingToOrbit(box, nav, orbit, pcam, "manual frame avatar bounds");
      lastManualFrameNonceApplied.current = manualFrameBoundsNonce;
      didAutoFrameForGen.current = true;
    } else if (loaded && !didAutoFrameForGen.current) {
      tryAutoFrames.current += 1;
      if (tryAutoFrames.current >= 2) {
        applyFramingToOrbit(box, nav, orbit, pcam, "auto-framed loaded body from runtime bounds");
        didAutoFrameForGen.current = true;
      }
    }

    if (!root) {
      skinnedCache.current = null;
    }
  });

  if (!enabled) return null;

  return (
    <>
      {showMarkers ? (
        <>
          <primitive object={worldAxes} position={[0, 0, 0]} />
          <primitive object={grid} position={[0, 0, 0]} />
          <group ref={camTargetGrp}>
            <mesh>
              <sphereGeometry args={[0.045, 10, 10]} />
              <meshBasicMaterial color="#ff3322" depthTest={false} />
            </mesh>
          </group>
          <group ref={avatarRootGrp}>
            <mesh>
              <sphereGeometry args={[0.038, 8, 8]} />
              <meshBasicMaterial color="#22ccff" depthTest={false} />
            </mesh>
          </group>
          <group ref={torsoGrp}>
            <mesh>
              <octahedronGeometry args={[0.034, 0]} />
              <meshBasicMaterial color="#ffcc00" depthTest={false} wireframe />
            </mesh>
          </group>
          <group ref={bodyCenterGrp}>
            <mesh>
              <sphereGeometry args={[0.055, 10, 10]} />
              <meshBasicMaterial color="#00ff88" depthTest={false} transparent opacity={0.85} />
            </mesh>
          </group>
          <group ref={skelGrp}>
            <mesh>
              <sphereGeometry args={[0.028, 8, 8]} />
              <meshBasicMaterial color="#ffffff" depthTest={false} />
            </mesh>
          </group>
        </>
      ) : null}
      <primitive object={boxHelper} />
    </>
  );
}
