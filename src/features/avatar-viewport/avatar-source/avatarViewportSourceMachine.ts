import type {
  AvatarResolvedRouteSource,
  AvatarSourceLoadState,
  AvatarSourcePreference,
} from "../avatarSourceResolver";
import type { AvatarRenderableValidation } from "./validateAvatarRenderable";

export type AvatarViewportSourcePhase =
  | "idle"
  | "resolving"
  | "loading_candidate"
  | "validating_candidate"
  | "candidate_ready"
  | "visible"
  | "candidate_failed"
  | "fallback_visible";

export type AvatarViewportSourceMachineSnapshot = {
  requestedPreference: AvatarSourcePreference;
  resolvedCandidateSource: string;
  resolvedCandidateAssetId: string;
  renderSource: string;
  renderAssetId: string;
  activeVisibleSource: string;
  activeVisibleAssetId: string;
  candidateSource: string;
  candidateAssetId: string;
  candidateLoadState: AvatarSourceLoadState;
  lastGoodVisibleSource: string | null;
  lastGoodVisibleAssetId: string | null;
  fallbackReason: string | null;
  failureReason: string | null;
  validationReason: string | null;
  preflightValid: boolean | null;
  assetAuditValid: boolean | null;
  mountAuditValid: boolean | null;
  renderValid: boolean | null;
  promotionValid: boolean | null;
  assetReason: string | null;
  mountReason: string | null;
  visibleMeshCount: number;
  candidateVisibleMeshCount: number;
  sourceVersion: number;
  phase: AvatarViewportSourcePhase;
};

export function avatarRouteSourceKey(source: AvatarResolvedRouteSource): string {
  return [
    source.assetManifestId,
    source.source.sourceType,
    source.source.bundledAssetModule ?? "",
    source.source.resolvedUri ?? "",
    source.source.fallbackReason,
  ].join("|");
}

export function isRenderableValidationReady(
  validation: AvatarRenderableValidation | null | undefined,
): boolean {
  return validation?.valid === true && validation.visibleMeshCount > 0;
}

export function routeSourceRequiresRenderableValidation(source: AvatarResolvedRouteSource): boolean {
  return !source.source.usingProceduralFallback;
}

export function buildAvatarViewportSourceMachineSnapshot(input: {
  requestedPreference: AvatarSourcePreference;
  candidate: AvatarResolvedRouteSource;
  renderSource: AvatarResolvedRouteSource;
  activeVisible: AvatarResolvedRouteSource;
  lastGood: AvatarResolvedRouteSource | null;
  candidateLoadState: AvatarSourceLoadState;
  sourceVersion: number;
  validation: AvatarRenderableValidation | null;
  failureReason: string | null;
  fallbackReason: string | null;
}): AvatarViewportSourceMachineSnapshot {
  const candidateVisibleMeshCount = input.validation?.visibleMeshCount ?? 0;
  const activeVisibleMeshCount =
    avatarRouteSourceKey(input.renderSource) === avatarRouteSourceKey(input.activeVisible)
      ? candidateVisibleMeshCount
      : input.lastGood != null
        ? Math.max(1, input.lastGood.source.usingProceduralFallback ? candidateVisibleMeshCount : 1)
        : 0;
  const hasVisible = input.lastGood != null || input.activeVisible.source.usingProceduralFallback;
  const phase: AvatarViewportSourcePhase = input.failureReason
    ? input.activeVisible.source.usingProceduralFallback
      ? "fallback_visible"
      : "candidate_failed"
    : input.validation?.valid
      ? "visible"
      : input.candidateLoadState === "loading"
        ? "loading_candidate"
        : input.candidateLoadState === "loaded"
          ? "validating_candidate"
          : hasVisible
            ? "visible"
            : "resolving";

  return {
    requestedPreference: input.requestedPreference,
    resolvedCandidateSource: input.candidate.source.sourceType,
    resolvedCandidateAssetId: input.candidate.assetManifestId,
    renderSource: input.renderSource.source.sourceType,
    renderAssetId: input.renderSource.assetManifestId,
    activeVisibleSource: input.activeVisible.source.sourceType,
    activeVisibleAssetId: input.activeVisible.assetManifestId,
    candidateSource: input.candidate.source.sourceType,
    candidateAssetId: input.candidate.assetManifestId,
    candidateLoadState: input.candidateLoadState,
    lastGoodVisibleSource: input.lastGood?.source.sourceType ?? null,
    lastGoodVisibleAssetId: input.lastGood?.assetManifestId ?? null,
    fallbackReason: input.fallbackReason,
    failureReason: input.failureReason,
    validationReason: input.validation?.reason ?? null,
    preflightValid: input.validation?.preflightValid ?? null,
    assetAuditValid: input.validation?.assetAuditValid ?? null,
    mountAuditValid: input.validation?.mountAuditValid ?? null,
    renderValid: input.validation?.renderValid ?? null,
    promotionValid: input.validation?.promotionValid ?? null,
    assetReason: input.validation?.assetReason ?? null,
    mountReason: input.validation?.mountReason ?? null,
    visibleMeshCount: activeVisibleMeshCount,
    candidateVisibleMeshCount,
    sourceVersion: input.sourceVersion,
    phase,
  };
}
