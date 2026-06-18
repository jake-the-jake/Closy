import { THREE } from "../three";
import type { DevAvatarPoseKey } from "@/features/avatar-export/dev-avatar-shared";

export type AvatarAnimationBinding = {
  pose: DevAvatarPoseKey;
  clip: THREE.AnimationClip | null;
  source: "embedded" | "procedural_bone_pose" | "none";
};

function matchClipForPose(clips: THREE.AnimationClip[], pose: DevAvatarPoseKey): THREE.AnimationClip | null {
  const hints: Record<DevAvatarPoseKey, RegExp> = {
    relaxed: /idle|relaxed|neutral/i,
    walk: /walk|stride/i,
    tpose: /t[_-]?pose|tpose/i,
    apose: /a[_-]?pose|apose/i,
  };
  return clips.find((clip) => hints[pose].test(clip.name)) ?? null;
}

export function bindAvatarAnimationForPose(
  clips: THREE.AnimationClip[] | undefined,
  pose: DevAvatarPoseKey,
  hasSkeleton: boolean,
): AvatarAnimationBinding {
  const clip = matchClipForPose(clips ?? [], pose);
  if (clip) return { pose, clip, source: "embedded" };
  if (hasSkeleton) return { pose, clip: null, source: "procedural_bone_pose" };
  return { pose, clip: null, source: "none" };
}
