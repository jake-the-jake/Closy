import type { AvatarSourceType } from "./avatar-source-manager";
import type { AvatarStartupPhase } from "./live-viewport-debug-types";

export type AvatarStartupMachineInput = {
  usingProceduralFallback: boolean;
  failedSourceType: AvatarSourceType | null;
  bodyLoadStatus: "idle" | "pending" | "loaded" | "failed";
  sceneReady: boolean;
  visibleMeshCount: number;
};

export function resolveAvatarStartupPhase({
  usingProceduralFallback,
  failedSourceType,
  bodyLoadStatus,
  sceneReady,
  visibleMeshCount,
}: AvatarStartupMachineInput): AvatarStartupPhase {
  if (usingProceduralFallback && failedSourceType != null) {
    return sceneReady && visibleMeshCount > 0 ? "failedWithFallback" : "loadingBody";
  }
  if (bodyLoadStatus === "pending") return "loadingBody";
  if (bodyLoadStatus === "loaded" && !sceneReady) return "bodyLoaded";
  if (sceneReady && visibleMeshCount > 0) return "visible";
  if (sceneReady) return "sceneReady";
  return "idle";
}
