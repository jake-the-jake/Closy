import { THREE } from "../three";
import { resolveAvatarAnchors, type AvatarAnchorMap } from "../avatar-anchors";

export type AvatarBodyLandmarks = AvatarAnchorMap & {
  source: "skeleton" | "bounds";
};

export function computeAvatarBodyLandmarks(root: THREE.Object3D): AvatarBodyLandmarks {
  const report = resolveAvatarAnchors(root);
  return {
    ...report.anchors,
    source: report.source === "bones" ? "skeleton" : "bounds",
  };
}
