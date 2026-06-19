import {
  AVATAR_SOURCE_OPTIONS,
  resolveAvatarSource,
  type AvatarSelectedSourceType,
  type AvatarSourcePreference,
  type AvatarSourceResolution,
} from "./avatar-source/resolveAvatarSource";
export {
  getAvatarSourceOptionsForRoute,
  type AvatarSourceRouteMode,
  type AvatarSourceRouteOption,
  type AvatarSourceRouteOptionId,
  type AvatarSourceRouteOptions,
} from "./avatar-source/getAvatarSourceOptionsForRoute";
import { avatarSourceLoadStateLabel } from "./avatar-source-manager";
import type {
  AvatarResolvedSource,
  AvatarSourceFailureReason,
  AvatarSourceLoadState,
  AvatarSourceType,
} from "./avatar-source-manager";
import type { AvatarRuntimeAssetUrls } from "./runtime-asset-sources";

export type AvatarRouteMode = "user" | "dev";
export type AvatarRouteActiveSource = AvatarSelectedSourceType;
export type AvatarSourceOption = (typeof AVATAR_SOURCE_OPTIONS)[number];

export type ResolveAvatarRouteSourceInput = {
  routeMode: AvatarRouteMode;
  preference: AvatarSourcePreference;
  runtimeAssets?: Partial<AvatarRuntimeAssetUrls>;
  envRuntimeUrls: AvatarRuntimeAssetUrls;
  forceProcedural?: boolean;
  failedSourceType?: AvatarSourceType | null;
  loadState?: AvatarSourceLoadState;
  errorReason?: string | null;
};

export type AvatarResolvedRouteSource = {
  source: AvatarResolvedSource;
  routeMode: AvatarRouteMode;
  routeRequestedPreference: AvatarSourcePreference;
  effectivePreference: AvatarSourcePreference;
  activeSource: AvatarRouteActiveSource;
  bodyUrl: string | null;
  loadIntent: string;
  visibleByDefault: boolean;
  displayLabel: string;
  fallbackReason: AvatarSourceFailureReason;
  assetManifestId: AvatarSourceResolution["selectedAssetId"];
  assetAvailability: string;
  resolution: AvatarSourceResolution;
};

export function resolveAvatarSourceForRoute(
  input: ResolveAvatarRouteSourceInput,
): AvatarResolvedRouteSource {
  const resolution = resolveAvatarSource(input.preference, {
    runtimeAssets: input.runtimeAssets,
    envRuntimeUrls: input.envRuntimeUrls,
    forceProcedural: input.forceProcedural,
    failedSourceType: input.failedSourceType,
    loadState: input.loadState,
    errorReason: input.errorReason,
  });

  return {
    source: resolution.legacySource,
    routeMode: input.routeMode,
    routeRequestedPreference: input.preference,
    effectivePreference: resolution.diagnostics.effectivePreference,
    activeSource: resolution.selectedSourceType,
    bodyUrl: resolution.legacySource.resolvedUri,
    loadIntent:
      input.preference === "best"
        ? `${input.routeMode}_best_production_then_stylised_then_fallback`
        : "explicit_source_selection",
    visibleByDefault: true,
    displayLabel: resolution.selectedAsset.label,
    fallbackReason: resolution.legacySource.fallbackReason,
    assetManifestId: resolution.selectedAssetId,
    assetAvailability: resolution.diagnostics.assetAvailability,
    resolution,
  };
}

export { AVATAR_SOURCE_OPTIONS, avatarSourceLoadStateLabel, resolveAvatarSource };
export type {
  AvatarResolvedSource,
  AvatarSourceFailureReason,
  AvatarSourceLoadState,
  AvatarSourcePreference,
  AvatarSourceResolution,
  AvatarSourceType,
};
