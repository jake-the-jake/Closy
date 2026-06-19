import {
  avatarAssetAvailabilityLabel,
  getAvatarAssetManifest,
  type AvatarAssetManifestId,
} from "../assets/avatarAssetManifest";
import type { AvatarSourcePreference } from "./resolveAvatarSource";

export type AvatarSourceRouteMode = "user" | "dev";
export type AvatarSourceRouteOptionId =
  | "best"
  | "production"
  | "realistic"
  | "stylised"
  | "fallback";

export type AvatarSourceRouteOption = {
  id: AvatarSourceRouteOptionId;
  preference: AvatarSourcePreference;
  label: string;
  description: string;
  disabled: boolean;
  hidden: boolean;
  assetManifestId?: AvatarAssetManifestId;
  availability: string;
  missingReason?: string;
  devOnly: boolean;
};

export type AvatarSourceRouteOptions = {
  routeMode: AvatarSourceRouteMode;
  defaultPreference: AvatarSourcePreference;
  options: AvatarSourceRouteOption[];
};

function manifestState(id: AvatarAssetManifestId) {
  const manifest = getAvatarAssetManifest(id);
  return {
    manifest,
    available:
      manifest.status === "available" ||
      manifest.status === "bridge" ||
      manifest.status === "procedural",
    availability: avatarAssetAvailabilityLabel(manifest),
    missingReason:
      manifest.status === "missing" || manifest.status === "invalid"
        ? manifest.missingReason
        : undefined,
  };
}

function option(
  input: Omit<AvatarSourceRouteOption, "availability" | "missingReason"> & {
    availability?: string;
    missingReason?: string;
  },
): AvatarSourceRouteOption {
  if (!input.assetManifestId) {
    return {
      ...input,
      availability: input.availability ?? "available",
      missingReason: input.missingReason,
    };
  }
  const state = manifestState(input.assetManifestId);
  return {
    ...input,
    availability: input.availability ?? state.availability,
    missingReason: input.missingReason ?? state.missingReason,
  };
}

export function getAvatarSourceOptionsForRoute(
  routeMode: AvatarSourceRouteMode,
): AvatarSourceRouteOptions {
  const production = manifestState("productionAvatar");
  const stylised = manifestState("stylisedAvatar");
  const realistic = manifestState("realisticAvatar");
  const bestAssetId: AvatarAssetManifestId = production.available
    ? "productionAvatar"
    : stylised.available
        ? "stylisedAvatar"
        : "fallbackMannequin";
  const bestAvailability =
    bestAssetId === "productionAvatar"
      ? "resolves to Production Avatar"
      : bestAssetId === "stylisedAvatar"
          ? "resolves to Stylised Avatar"
          : "fallback only";

  if (routeMode === "user") {
    const userOptions: AvatarSourceRouteOption[] = [
      option({
        id: "best",
        preference: "best",
        label: "Best available avatar",
        description:
          bestAssetId === "fallbackMannequin"
            ? "Uses the safe fitting fallback until a production avatar asset is available."
            : "Uses the best bundled avatar available for outfit preview.",
        disabled: false,
        hidden: false,
        assetManifestId: bestAssetId,
        availability: bestAvailability,
        devOnly: false,
      }),
    ];

    return {
      routeMode,
      defaultPreference: "best",
      options: userOptions.filter((sourceOption) => !sourceOption.hidden),
    };
  }

  return {
    routeMode,
    defaultPreference: "best",
    options: [
      option({
        id: "best",
        preference: "best",
        label: "Best / Auto",
        description: "Production Avatar first, then valid Stylised Avatar, then fallback.",
        disabled: false,
        hidden: false,
        assetManifestId: bestAssetId,
        availability: bestAvailability,
        devOnly: false,
      }),
      option({
        id: "production",
        preference: "production",
        label: "Production Avatar",
        description: "Current working GLB bridge used by product startup.",
        disabled: !production.available,
        hidden: false,
        assetManifestId: "productionAvatar",
        devOnly: false,
      }),
      option({
        id: "realistic",
        preference: "realistic",
        label: "Realistic Avatar",
        description: "Future high-quality realistic/scan/ZeroOne slot.",
        disabled: !realistic.available,
        hidden: false,
        assetManifestId: "realisticAvatar",
        devOnly: true,
      }),
      option({
        id: "stylised",
        preference: "stylised",
        label: "Stylised Avatar",
        description: "Optional alternate GLB slot; disabled until a distinct asset exists.",
        disabled: !stylised.available,
        hidden: false,
        assetManifestId: "stylisedAvatar",
        devOnly: true,
      }),
      option({
        id: "fallback",
        preference: "fallback",
        label: "Fallback Mannequin",
        description: "Procedural emergency fallback for debug only.",
        disabled: false,
        hidden: false,
        assetManifestId: "fallbackMannequin",
        devOnly: true,
      }),
    ],
  };
}
