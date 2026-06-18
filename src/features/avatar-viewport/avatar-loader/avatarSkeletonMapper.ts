import {
  inspectAvatarRig,
  type AvatarRigInspection,
  type AvatarRigSlot,
} from "../avatar-rig-inspector";
import { THREE } from "../three";

export type AvatarSkeletonMap = {
  inspection: AvatarRigInspection;
  mappedBones: Partial<Record<AvatarRigSlot, THREE.Bone>>;
  isRigged: boolean;
};

export function mapAvatarSkeleton(root: THREE.Object3D): AvatarSkeletonMap {
  const inspection = inspectAvatarRig(root);
  return {
    inspection,
    mappedBones: inspection.boneMap,
    isRigged: inspection.boneCount > 0 && inspection.confidence > 0.35,
  };
}
