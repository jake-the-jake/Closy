import * as THREE from "three";

const FALLBACK_COLOR = 0xc4957a;

/**
 * Replace all mesh materials with a simple untextured MeshStandardMaterial so
 * Expo GL never samples broken or unsupported GPU textures from the GLB.
 */
export function applySkinnedBodyFallbackMaterials(root: THREE.Object3D): void {
  root.traverse((o) => {
    if (!(o instanceof THREE.Mesh)) return;
    const prev = Array.isArray(o.material) ? o.material : [o.material];
    const hasVertexColors =
      o.geometry instanceof THREE.BufferGeometry &&
      !!o.geometry.getAttribute("color");
    const next: THREE.MeshStandardMaterial[] = prev.map(
      () =>
        new THREE.MeshStandardMaterial({
          color: FALLBACK_COLOR,
          roughness: 0.62,
          metalness: 0.04,
          vertexColors: hasVertexColors,
        }),
    );
    o.material = next.length === 1 ? next[0]! : next;
    for (const m of prev) m.dispose();
  });
}
