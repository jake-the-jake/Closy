import type { DevAvatarPoseKey } from "@/features/avatar-export/dev-avatar-shared";

/**
 * Pose joint targets (radians). Matches `ProceduralRigBody` / runtime clipping.
 */
export function poseAngles(pose: DevAvatarPoseKey) {
  switch (pose) {
    case "relaxed":
      return {
        laz: 0.12,
        raz: -0.12,
        lax: 0.48,
        rax: 0.48,
        laxz: 0.02,
        llx: 0.04,
        rlx: -0.06,
        /** Torso / spine forward flex (radians) for skinned spine bones. */
        spineRx: 0.04,
        spineUpperRx: 0.025,
        neckRx: -0.02,
        spineTwistY: 0,
      };
    case "walk":
      return {
        laz: 0.38,
        raz: -0.38,
        lax: 0.36,
        rax: 0.36,
        laxz: 0.1,
        llx: 0.28,
        rlx: -0.32,
        spineRx: 0.11,
        spineUpperRx: 0.08,
        neckRx: -0.04,
        spineTwistY: 0.12,
      };
    case "tpose":
      return {
        laz: 1.38,
        raz: -1.38,
        lax: 0,
        rax: 0,
        laxz: 0,
        llx: 0,
        rlx: 0,
        spineRx: 0,
        spineUpperRx: 0,
        neckRx: 0,
        spineTwistY: 0,
      };
    case "apose":
      return {
        laz: 0.55,
        raz: -0.55,
        lax: 0,
        rax: 0,
        laxz: 0,
        llx: 0,
        rlx: 0,
        spineRx: 0.02,
        spineUpperRx: 0.015,
        neckRx: -0.015,
        spineTwistY: 0,
      };
    default:
      return {
        laz: 0,
        raz: 0,
        lax: 0,
        rax: 0,
        laxz: 0,
        llx: 0,
        rlx: 0,
        spineRx: 0,
        spineUpperRx: 0,
        neckRx: 0,
        spineTwistY: 0,
      };
  }
}

export type PoseAngleSet = ReturnType<typeof poseAngles>;
