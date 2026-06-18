import type { DevAvatarPoseKey } from "@/features/avatar-export/dev-avatar-shared";
import type { HumanoidBoneMap } from "./humanoidBoneMap";

export function applyHumanoidPose(
  bones: HumanoidBoneMap,
  pose: DevAvatarPoseKey,
): boolean {
  if (!bones.hips) return false;
  const armLift =
    pose === "tpose" ? 1.42 : pose === "apose" ? 0.78 : pose === "walk" ? 0.28 : 0.18;
  const walk = pose === "walk";

  bones.upperArmL?.rotation.set(0, 0, armLift);
  bones.upperArmR?.rotation.set(0, 0, -armLift);
  bones.lowerArmL?.rotation.set(0, 0, pose === "relaxed" ? 0.18 : 0);
  bones.lowerArmR?.rotation.set(0, 0, pose === "relaxed" ? -0.18 : 0);
  bones.thighL?.rotation.set(walk ? -0.22 : 0, 0, 0);
  bones.thighR?.rotation.set(walk ? 0.22 : 0, 0, 0);
  bones.shinL?.rotation.set(walk ? 0.18 : 0, 0, 0);
  bones.shinR?.rotation.set(walk ? -0.08 : 0, 0, 0);
  bones.chest?.rotation.set(pose === "walk" ? 0.04 : 0, 0, 0);
  return true;
}
