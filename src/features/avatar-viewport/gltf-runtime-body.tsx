import { useLoader } from "@react-three/fiber/native";
import { Component, type ErrorInfo, type ReactNode, useLayoutEffect, useMemo } from "react";
import * as THREE from "three";
import type { GLTF } from "three/examples/jsm/loaders/GLTFLoader.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

import type { GarmentFitState } from "@/features/avatar-export";
import type { DevAvatarPoseKey } from "@/features/avatar-export/dev-avatar-shared";

import { deformGarmentObject3D, type GarmentDeformProfile } from "./garment-deformation";
import type { LiveViewportShadingMode } from "./live-viewport-shading";

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

function usePreparedGltf(url: string, gltf: GLTF, normalizeY: number): PreparedGltf {
  return useMemo(() => {
    const root = gltf.scene.clone(true);
    normalizeRootToHeight(root, normalizeY);
    const baseline = buildMaterialBaseline(root);
    return { scene: root, baseline };
  }, [gltf, url, normalizeY]);
}

type GltfRuntimeBodyProps = {
  url: string;
  pose: DevAvatarPoseKey;
  liveShading: LiveViewportShadingMode;
};

/**
 * Loads an optional runtime GLB (non-Draco for first pass). Normalizes height ~1.85m,
 * applies coarse root rotation per pose, and live shading. Skeletal poses are staged later.
 */
export function GltfRuntimeBody({ url, pose, liveShading }: GltfRuntimeBodyProps) {
  const gltf = useLoader(GLTFLoader, url);
  const { scene, baseline } = usePreparedGltf(url, gltf, 1.85);

  useLayoutEffect(() => {
    const euler = poseRootEulerApprox(pose);
    scene.rotation.set(euler[0], euler[1], euler[2]);
    applyLiveShadingToGltfMaterials(scene, liveShading, "body", baseline);
    scene.traverse((o) => {
      if (o instanceof THREE.Mesh) o.updateMatrixWorld(true);
    });
  }, [scene, pose, liveShading, baseline]);

  return <primitive object={scene} />;
}

type GltfRuntimeGarmentProps = {
  url: string;
  liveShading: LiveViewportShadingMode;
  /** Target height in scene units after normalization (shirt ~0.42, pants ~0.52). */
  normalizeHeight?: number;
  /** Shared live fit; drives regional vertex deformation (see `garment-deformation.ts`). */
  garmentFit: GarmentFitState;
  deformProfile: GarmentDeformProfile;
  /** Runtime clipping overlay emissive add (garment materials only). */
  clipEmissiveAdd?: THREE.Color;
};

/**
 * Static garment GLB under a parent group that already applies fit offsets.
 * Pipeline: base placement + parent transforms → regional mesh deformation → live shading.
 */
export function GltfRuntimeGarment({
  url,
  liveShading,
  normalizeHeight = 0.48,
  garmentFit,
  deformProfile,
  clipEmissiveAdd,
}: GltfRuntimeGarmentProps) {
  const gltf = useLoader(GLTFLoader, url);
  const { scene, baseline } = usePreparedGltf(url, gltf, normalizeHeight);

  useLayoutEffect(() => {
    deformGarmentObject3D(scene, garmentFit, deformProfile);
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
  }, [scene, liveShading, baseline, garmentFit, deformProfile, clipEmissiveAdd]);

  return <primitive object={scene} />;
}

type EBProps = { children: ReactNode; fallback: ReactNode };

type EBState = { hasError: boolean };

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
      console.warn("[AvatarViewport] GLTF fallback:", error.message, info.componentStack);
    }
  }

  override render() {
    if (this.state.hasError) return this.props.fallback;
    return this.props.children;
  }
}
