import { normalizeAvatarRoot, type AvatarNormalizeReport } from "../avatar-normalize";
import { THREE } from "../three";

export type NormalizeAvatarSceneOptions = {
  expectedHeightMeters?: number;
  rotation?: [number, number, number];
  position?: [number, number, number];
  scale?: number;
};

export function normalizeAvatarScene(
  root: THREE.Object3D,
  options: NormalizeAvatarSceneOptions = {},
): AvatarNormalizeReport {
  const scale = options.scale ?? 1;
  root.scale.multiplyScalar(scale);
  if (options.rotation) root.rotation.set(...options.rotation);
  if (options.position) root.position.set(...options.position);
  return normalizeAvatarRoot(root, {
    targetHeight: options.expectedHeightMeters ?? 1.78,
    centerXZ: true,
    groundY: 0,
  });
}
