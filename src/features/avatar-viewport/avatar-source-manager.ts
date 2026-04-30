import type { AvatarRuntimeAssetUrls } from "./runtime-asset-sources";

export type AvatarSourceType =
  | "realistic_glb"
  | "stylised_glb"
  | "procedural_fallback";

export type AvatarSourcePreference = "auto" | AvatarSourceType;

export type AvatarSourceLoadState = "idle" | "loading" | "loaded" | "failed";

export type AvatarSourceFailureReason =
  | "none"
  | "env_forced_procedural"
  | "explicit_procedural"
  | "missing_realistic_glb"
  | "missing_stylised_glb"
  | "glb_load_failed"
  | "no_glb_available";

export type AvatarSourceDescriptor = {
  sourceType: AvatarSourceType;
  assetId: string;
  label: string;
  bundledAssetModule: number | null;
  uri: string | null;
  available: boolean;
};

export type AvatarResolvedSource = {
  sourceType: AvatarSourceType;
  loadState: AvatarSourceLoadState;
  errorReason: string | null;
  resolvedUri: string | null;
  bundledAssetModule: number | null;
  fallbackReason: AvatarSourceFailureReason;
  debugLabel: string;
  requested: AvatarSourcePreference;
  usingProceduralFallback: boolean;
};

export type ResolveAvatarSourceInput = {
  preference: AvatarSourcePreference;
  runtimeAssets?: Partial<AvatarRuntimeAssetUrls>;
  envRuntimeUrls: AvatarRuntimeAssetUrls;
  stylisedBundledAssetModule?: number | null;
  forceProcedural?: boolean;
  failedSourceType?: AvatarSourceType | null;
  loadState?: AvatarSourceLoadState;
  errorReason?: string | null;
};

function externalBodyUrl(
  runtimeAssets: Partial<AvatarRuntimeAssetUrls> | undefined,
  envRuntimeUrls: AvatarRuntimeAssetUrls,
): string | null {
  return runtimeAssets?.bodyGltfUrl ?? envRuntimeUrls.bodyGltfUrl ?? null;
}

function proceduralResolved(
  input: ResolveAvatarSourceInput,
  fallbackReason: AvatarSourceFailureReason,
  errorReason: string | null = null,
): AvatarResolvedSource {
  return {
    sourceType: "procedural_fallback",
    loadState: "loaded",
    errorReason,
    resolvedUri: null,
    bundledAssetModule: null,
    fallbackReason,
    debugLabel: `Procedural fallback (${fallbackReason})`,
    requested: input.preference,
    usingProceduralFallback: true,
  };
}

function glbResolved(
  input: ResolveAvatarSourceInput,
  descriptor: AvatarSourceDescriptor,
): AvatarResolvedSource {
  const failed = input.failedSourceType === descriptor.sourceType;
  if (failed) {
    return proceduralResolved(input, "glb_load_failed", input.errorReason);
  }
  return {
    sourceType: descriptor.sourceType,
    loadState: input.loadState ?? "idle",
    errorReason: input.errorReason ?? null,
    resolvedUri: descriptor.uri,
    bundledAssetModule: descriptor.bundledAssetModule,
    fallbackReason: "none",
    debugLabel: descriptor.label,
    requested: input.preference,
    usingProceduralFallback: false,
  };
}

export function resolveAvatarSource(
  input: ResolveAvatarSourceInput,
): AvatarResolvedSource {
  if (input.forceProcedural) {
    return proceduralResolved(input, "env_forced_procedural");
  }
  if (input.preference === "procedural_fallback") {
    return proceduralResolved(input, "explicit_procedural");
  }

  const realisticUrl = externalBodyUrl(input.runtimeAssets, input.envRuntimeUrls);
  const realistic: AvatarSourceDescriptor = {
    sourceType: "realistic_glb",
    assetId: "runtime-realistic-avatar",
    label: "Realistic GLB (runtime URL)",
    bundledAssetModule: null,
    uri: realisticUrl,
    available: realisticUrl != null,
  };
  const stylised: AvatarSourceDescriptor = {
    sourceType: "stylised_glb",
    assetId: "bundled-stylised-mannequin",
    label: "Bundled stylised GLB",
    bundledAssetModule: input.stylisedBundledAssetModule ?? null,
    uri: null,
    available: input.stylisedBundledAssetModule != null,
  };

  if (input.preference === "realistic_glb") {
    return realistic.available
      ? glbResolved(input, realistic)
      : proceduralResolved(input, "missing_realistic_glb");
  }

  if (input.preference === "stylised_glb") {
    return stylised.available
      ? glbResolved(input, stylised)
      : proceduralResolved(input, "missing_stylised_glb");
  }

  if (realistic.available) return glbResolved(input, realistic);
  if (stylised.available) return glbResolved(input, stylised);
  return proceduralResolved(input, "no_glb_available");
}

export function avatarSourceLoadStateLabel(
  source: AvatarResolvedSource,
): string {
  const fallback = source.fallbackReason === "none" ? "" : `, ${source.fallbackReason}`;
  return `${source.sourceType}:${source.loadState}${fallback}`;
}
