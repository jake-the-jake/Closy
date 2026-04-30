import * as THREE from "three";

export type AvatarNormalizeReport = {
  height: number;
  bounds: {
    min: [number, number, number];
    max: [number, number, number];
    size: [number, number, number];
    center: [number, number, number];
  };
  scaleApplied: number;
  footY: number;
  center: [number, number, number];
};

export type AvatarNormalizeOptions = {
  targetHeight?: number;
  centerXZ?: boolean;
  groundY?: number;
};

function tuple(v: THREE.Vector3): [number, number, number] {
  return [v.x, v.y, v.z];
}

function reportFromBox(box: THREE.Box3, scaleApplied: number): AvatarNormalizeReport {
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  return {
    height: size.y,
    bounds: {
      min: tuple(box.min),
      max: tuple(box.max),
      size: tuple(size),
      center: tuple(center),
    },
    scaleApplied,
    footY: box.min.y,
    center: tuple(center),
  };
}

/**
 * Normalize imported avatar GLBs to Closy's scene convention:
 * Y-up, feet on ground, centered on X/Z, roughly human height.
 */
export function normalizeAvatarRoot(
  root: THREE.Object3D,
  options: AvatarNormalizeOptions = {},
): AvatarNormalizeReport {
  const targetHeight = options.targetHeight ?? 1.78;
  const groundY = options.groundY ?? 0;
  root.updateMatrixWorld(true);

  let box = new THREE.Box3().setFromObject(root);
  let size = box.getSize(new THREE.Vector3());
  let scaleApplied = 1;
  if (Number.isFinite(size.y) && size.y > 1e-5 && targetHeight > 0) {
    scaleApplied = targetHeight / size.y;
    root.scale.multiplyScalar(scaleApplied);
    root.updateMatrixWorld(true);
    box = new THREE.Box3().setFromObject(root);
    size = box.getSize(new THREE.Vector3());
  }

  const center = box.getCenter(new THREE.Vector3());
  root.position.y += groundY - box.min.y;
  if (options.centerXZ !== false) {
    root.position.x -= center.x;
    root.position.z -= center.z;
  }
  root.updateMatrixWorld(true);
  box = new THREE.Box3().setFromObject(root);
  return reportFromBox(box, scaleApplied);
}
