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
      };
    default:
      return { laz: 0, raz: 0, lax: 0, rax: 0, laxz: 0, llx: 0, rlx: 0 };
  }
}

export type PoseAngleSet = ReturnType<typeof poseAngles>;
