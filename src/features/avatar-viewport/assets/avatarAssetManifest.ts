import { DEFAULT_STYLISED_AVATAR_GLTF } from "../avatar-assets";

export type AvatarAssetKind =
  | "production-rigged-avatar"
  | "stylised-rigged-avatar"
  | "procedural-fallback";

export type AvatarAssetNamingProfile = "mixamo" | "vrm" | "readyplayerme" | "custom";

export type AvatarAssetManifest = {
  id: string;
  label: string;
  kind: AvatarAssetKind;
  uri?: string;
  localModule?: number;
  scale: number;
  rotation?: [number, number, number];
  position?: [number, number, number];
  expectedHeightMeters: number;
  skeleton?: {
    requiredBones: string[];
    optionalBones: string[];
    namingProfile: AvatarAssetNamingProfile;
  };
  materials?: {
    skin?: string[];
    hair?: string[];
    eyes?: string[];
    clothing?: string[];
  };
  mobileBudget: {
    maxTriangles: number;
    maxTextureSize: number;
    maxBones: number;
    maxDrawCalls: number;
  };
  status: "available" | "missing" | "procedural";
  missingReason?: string;
  canonicalAssetPath?: string;
};

const HUMANOID_REQUIRED_BONES = [
  "hips",
  "spine",
  "chest",
  "neck",
  "head",
  "upperArm_L",
  "upperArm_R",
  "lowerArm_L",
  "lowerArm_R",
  "hand_L",
  "hand_R",
  "upperLeg_L",
  "upperLeg_R",
  "lowerLeg_L",
  "lowerLeg_R",
  "foot_L",
  "foot_R",
];

const HUMANOID_OPTIONAL_BONES = [
  "shoulder_L",
  "shoulder_R",
  "toe_L",
  "toe_R",
  "eye_L",
  "eye_R",
  "jaw",
  "finger_*",
];

export const AVATAR_ASSET_MANIFESTS = {
  productionAvatar: {
    id: "productionAvatar",
    label: "Production polished avatar",
    kind: "production-rigged-avatar",
    localModule: DEFAULT_STYLISED_AVATAR_GLTF,
    scale: 1,
    expectedHeightMeters: 1.78,
    skeleton: {
      requiredBones: HUMANOID_REQUIRED_BONES,
      optionalBones: HUMANOID_OPTIONAL_BONES,
      namingProfile: "custom",
    },
    materials: {
      skin: ["Skin", "Body", "Face"],
      hair: ["Hair"],
      eyes: ["Eye", "Cornea"],
      clothing: ["Cloth", "Outfit", "Garment"],
    },
    mobileBudget: {
      maxTriangles: 70_000,
      maxTextureSize: 2048,
      maxBones: 96,
      maxDrawCalls: 12,
    },
    status: "available",
    missingReason:
      "Bridge asset is using assets/models/avatar/default-stylised-avatar.glb until production_avatar.glb is added and wired.",
    canonicalAssetPath: "assets/models/avatar/production/production_avatar.glb",
  },
  stylisedAvatar: {
    id: "stylisedAvatar",
    label: "Bundled stylised avatar",
    kind: "stylised-rigged-avatar",
    scale: 1,
    expectedHeightMeters: 1.78,
    skeleton: {
      requiredBones: HUMANOID_REQUIRED_BONES,
      optionalBones: HUMANOID_OPTIONAL_BONES,
      namingProfile: "custom",
    },
    materials: {
      skin: ["Skin", "Body", "Mannequin"],
      hair: ["Hair"],
      eyes: ["Eye"],
      clothing: ["Cloth", "Garment"],
    },
    mobileBudget: {
      maxTriangles: 45_000,
      maxTextureSize: 1024,
      maxBones: 72,
      maxDrawCalls: 8,
    },
    status: "missing",
    missingReason:
      "No separate stylised_avatar.glb has been added yet. The current bundled GLB is reserved as the Production Avatar bridge.",
    canonicalAssetPath: "assets/models/avatar/stylised/stylised_avatar.glb",
  },
  fallbackMannequin: {
    id: "fallbackMannequin",
    label: "Emergency procedural fallback mannequin",
    kind: "procedural-fallback",
    scale: 1,
    expectedHeightMeters: 1.78,
    mobileBudget: {
      maxTriangles: 20_000,
      maxTextureSize: 0,
      maxBones: 0,
      maxDrawCalls: 18,
    },
    status: "procedural",
    missingReason: "Generated in runtime code; no GLB asset is expected for this fallback.",
  },
} satisfies Record<string, AvatarAssetManifest>;

export type AvatarAssetManifestId = keyof typeof AVATAR_ASSET_MANIFESTS;

export function getAvatarAssetManifest(id: AvatarAssetManifestId): AvatarAssetManifest {
  return AVATAR_ASSET_MANIFESTS[id];
}

export function avatarAssetAvailabilityLabel(manifest: AvatarAssetManifest): string {
  if (manifest.status === "available") return "available";
  if (manifest.status === "procedural") return "procedural fallback";
  return `missing asset: ${manifest.missingReason ?? manifest.canonicalAssetPath ?? manifest.id}`;
}
