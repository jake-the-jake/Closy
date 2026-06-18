import type { DevAvatarPoseKey } from "@/features/avatar-export/dev-avatar-shared";
import { bindAvatarAnimationForPose, type AvatarAnimationBinding } from "../avatar-loader/avatarAnimationBinder";
import { THREE } from "../three";

export type AvatarAnimationControllerState = {
  pose: DevAvatarPoseKey;
  binding: AvatarAnimationBinding;
};

export function resolveAvatarAnimationState(
  clips: THREE.AnimationClip[] | undefined,
  pose: DevAvatarPoseKey,
  hasSkeleton: boolean,
): AvatarAnimationControllerState {
  return {
    pose,
    binding: bindAvatarAnimationForPose(clips, pose, hasSkeleton),
  };
}
