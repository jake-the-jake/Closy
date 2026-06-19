import {
  resolveAvatarSource as resolveLegacyAvatarSource,
  type AvatarResolvedSource,
  type AvatarSourceLoadState,
  type AvatarSourceType,
} from "../avatar-source-manager";
import {
  avatarAssetAvailabilityLabel,
  getAvatarAssetManifest,
  type AvatarAssetManifest,
  type AvatarAssetManifestId,
} from "../assets/avatarAssetManifest";
import type { AvatarRuntimeAssetUrls } from "../runtime-asset-sources";

export type AvatarSourcePreference =
  | "best"
  | "production"
  | "realistic"
  | "stylised"
  | "fallback";

export type AvatarSelectedSourceType =
  | "production-avatar"
  | "realistic-avatar"
  | "stylised-avatar"
  | "fallback-mannequin";

export type AvatarSourceResolution = {
  selectedAsset: AvatarAssetManifest;
  selectedAssetId: AvatarAssetManifestId;
  selectedSourceType: AvatarSelectedSourceType;
  legacySource: AvatarResolvedSource;
  reason: string;
  isFallback: boolean;
  diagnostics: {
    requestedPreference: AvatarSourcePreference;
    effectivePreference: AvatarSourcePreference;
    assetAvailability: string;
    productionAvailability: string;
    realisticAvailability: string;
    stylisedAvailability: string;
    fallbackReason: string;
    loadState: AvatarSourceLoadState;
    errorReason: string | null;
  };
};

export type ResolveAvatarSourceContext = {
  runtimeAssets?: Partial<AvatarRuntimeAssetUrls>;
  envRuntimeUrls: AvatarRuntimeAssetUrls;
  forceProcedural?: boolean;
  failedSourceType?: AvatarSourceType | null;
  loadState?: AvatarSourceLoadState;
  errorReason?: string | null;
};

const SOURCE_OPTIONS: readonly {
  id: AvatarSourcePreference;
  label: string;
  description: string;
}[] = [
  {
    id: "best",
    label: "Best available",
    description: "Production Avatar first, then a valid Stylised Avatar, then emergency fallback.",
  },
  {
    id: "production",
    label: "Production Avatar",
    description: "Current working rigged GLB asset path used by product startup.",
  },
  {
    id: "realistic",
    label: "Realistic Avatar",
    description: "Future high-quality scan/ZeroOne GLB slot; disabled until populated.",
  },
  {
    id: "stylised",
    label: "Stylised Avatar",
    description: "Optional alternate GLB slot; reports missing/invalid if not available.",
  },
  {
    id: "fallback",
    label: "Fallback Mannequin",
    description: "Procedural emergency fallback only.",
  },
] as const;

export const AVATAR_SOURCE_OPTIONS = SOURCE_OPTIONS;

function sourceTypeFor(assetId: AvatarAssetManifestId): AvatarSelectedSourceType {
  if (assetId === "productionAvatar") return "production-avatar";
  if (assetId === "realisticAvatar") return "realistic-avatar";
  if (assetId === "stylisedAvatar") return "stylised-avatar";
  return "fallback-mannequin";
}

function fallbackResolution(
  preference: AvatarSourcePreference,
  context: ResolveAvatarSourceContext,
  reason: string,
): AvatarSourceResolution {
  const selectedAssetId = "fallbackMannequin";
  const selectedAsset = getAvatarAssetManifest(selectedAssetId);
  const legacySource = resolveLegacyAvatarSource({
    preference: "procedural_fallback",
    runtimeAssets: context.runtimeAssets,
    envRuntimeUrls: context.envRuntimeUrls,
    forceProcedural: context.forceProcedural,
    failedSourceType: context.failedSourceType,
    loadState: context.loadState,
    errorReason: context.errorReason ?? reason,
  });
  return {
    selectedAsset,
    selectedAssetId,
    selectedSourceType: "fallback-mannequin",
    legacySource,
    reason,
    isFallback: true,
    diagnostics: buildDiagnostics(preference, "fallback", selectedAsset, legacySource),
  };
}

function buildDiagnostics(
  requestedPreference: AvatarSourcePreference,
  effectivePreference: AvatarSourcePreference,
  selectedAsset: AvatarAssetManifest,
  legacySource: AvatarResolvedSource,
): AvatarSourceResolution["diagnostics"] {
  return {
    requestedPreference,
    effectivePreference,
    assetAvailability: avatarAssetAvailabilityLabel(selectedAsset),
    productionAvailability: avatarAssetAvailabilityLabel(getAvatarAssetManifest("productionAvatar")),
    realisticAvailability: avatarAssetAvailabilityLabel(getAvatarAssetManifest("realisticAvatar")),
    stylisedAvailability: avatarAssetAvailabilityLabel(getAvatarAssetManifest("stylisedAvatar")),
    fallbackReason: legacySource.fallbackReason,
    loadState: legacySource.loadState,
    errorReason: legacySource.errorReason,
  };
}

function resolveProduction(
  requestedPreference: AvatarSourcePreference,
  context: ResolveAvatarSourceContext,
): AvatarSourceResolution | null {
  const selectedAssetId = "productionAvatar";
  const selectedAsset = getAvatarAssetManifest(selectedAssetId);
  if (
    selectedAsset.status !== "available" &&
    selectedAsset.status !== "bridge" &&
    !context.runtimeAssets?.bodyGltfUrl &&
    !context.envRuntimeUrls.bodyGltfUrl
  ) {
    return null;
  }
  const legacySource = resolveLegacyAvatarSource({
    preference: "realistic_glb",
    runtimeAssets: context.runtimeAssets,
    envRuntimeUrls: context.envRuntimeUrls,
    productionBundledAssetModule: selectedAsset.localModule ?? null,
    forceProcedural: context.forceProcedural,
    failedSourceType: context.failedSourceType,
    loadState: context.loadState,
    errorReason: context.errorReason,
  });
  if (legacySource.usingProceduralFallback) return null;
  return {
    selectedAsset,
    selectedAssetId,
    selectedSourceType: sourceTypeFor(selectedAssetId),
    legacySource,
    reason:
      context.envRuntimeUrls.bodyGltfUrl || context.runtimeAssets?.bodyGltfUrl
        ? "production_runtime_url"
        : "production_bundled_bridge",
    isFallback: false,
    diagnostics: buildDiagnostics(requestedPreference, "production", selectedAsset, legacySource),
  };
}

function resolveRealistic(
  requestedPreference: AvatarSourcePreference,
  context: ResolveAvatarSourceContext,
): AvatarSourceResolution | null {
  const selectedAssetId = "realisticAvatar";
  const selectedAsset = getAvatarAssetManifest(selectedAssetId);
  if (selectedAsset.status !== "available" || (selectedAsset.localModule == null && !selectedAsset.uri)) {
    return null;
  }
  const legacySource = resolveLegacyAvatarSource({
    preference: "realistic_glb",
    runtimeAssets: selectedAsset.uri ? { ...context.runtimeAssets, bodyGltfUrl: selectedAsset.uri } : context.runtimeAssets,
    envRuntimeUrls: context.envRuntimeUrls,
    productionBundledAssetModule: selectedAsset.localModule ?? null,
    forceProcedural: context.forceProcedural,
    failedSourceType: context.failedSourceType,
    loadState: context.loadState,
    errorReason: context.errorReason,
  });
  if (legacySource.usingProceduralFallback) return null;
  return {
    selectedAsset,
    selectedAssetId,
    selectedSourceType: sourceTypeFor(selectedAssetId),
    legacySource,
    reason: selectedAsset.uri ? "realistic_avatar_uri" : "realistic_avatar_bundled",
    isFallback: false,
    diagnostics: buildDiagnostics(requestedPreference, "realistic", selectedAsset, legacySource),
  };
}

function resolveStylised(
  requestedPreference: AvatarSourcePreference,
  context: ResolveAvatarSourceContext,
): AvatarSourceResolution | null {
  const selectedAssetId = "stylisedAvatar";
  const selectedAsset = getAvatarAssetManifest(selectedAssetId);
  if (selectedAsset.status !== "available" || selectedAsset.localModule == null) return null;
  const legacySource = resolveLegacyAvatarSource({
    preference: "stylised_glb",
    runtimeAssets: context.runtimeAssets,
    envRuntimeUrls: context.envRuntimeUrls,
    stylisedBundledAssetModule: selectedAsset.localModule,
    forceProcedural: context.forceProcedural,
    failedSourceType: context.failedSourceType,
    loadState: context.loadState,
    errorReason: context.errorReason,
  });
  if (legacySource.usingProceduralFallback) return null;
  return {
    selectedAsset,
    selectedAssetId,
    selectedSourceType: sourceTypeFor(selectedAssetId),
    legacySource,
    reason: "stylised_bundled_asset",
    isFallback: false,
    diagnostics: buildDiagnostics(requestedPreference, "stylised", selectedAsset, legacySource),
  };
}

export function resolveAvatarSource(
  preference: AvatarSourcePreference,
  context: ResolveAvatarSourceContext,
): AvatarSourceResolution {
  if (context.forceProcedural || preference === "fallback") {
    return fallbackResolution(preference, context, context.forceProcedural ? "env_forced_procedural" : "explicit_fallback");
  }

  if (preference === "production") {
    return (
      resolveProduction(preference, context) ??
      fallbackResolution(preference, context, "production_avatar_missing_or_failed")
    );
  }

  if (preference === "realistic") {
    return (
      resolveRealistic(preference, context) ??
      fallbackResolution(preference, context, "realistic_asset_missing_or_invalid")
    );
  }

  if (preference === "stylised") {
    return (
      resolveStylised(preference, context) ??
      fallbackResolution(preference, context, "stylised_asset_missing_or_invalid")
    );
  }

  return (
    resolveProduction(preference, context) ??
    resolveStylised(preference, context) ??
    fallbackResolution(preference, context, "no_valid_glb_avatar_available")
  );
}

export function avatarSourcePreferenceToLegacyLabel(preference: AvatarSourcePreference): string {
  return SOURCE_OPTIONS.find((option) => option.id === preference)?.label ?? preference;
}
