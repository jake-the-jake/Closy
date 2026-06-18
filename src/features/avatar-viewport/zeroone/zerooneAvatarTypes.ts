import type { DevAvatarPoseKey } from "@/features/avatar-export/dev-avatar-shared";
import type { BodyShapeParams } from "@/features/avatar-export";

import type { AvatarSourcePreference } from "../avatar-source/resolveAvatarSource";
import type { AvatarRuntimeAssetUrls } from "../runtime-asset-sources";

export type ZeroOneAvatarBridgeMode =
  | "local-placeholder"
  | "offline-export"
  | "future-native-engine";

export type ZeroOneRenderQuality =
  | "mobile-preview"
  | "balanced"
  | "high-quality"
  | "debug";

export type ZeroOneTargetPlatform =
  | "expo-gl"
  | "ios"
  | "android"
  | "web"
  | "desktop";

export type ZeroOneRequestedOutput =
  | "preview-image"
  | "optimized-glb"
  | "optimized-usdz"
  | "fit-diagnostics"
  | "simulation-metadata";

export type ZeroOneAvatarCamera = {
  position: [number, number, number];
  target: [number, number, number];
  fovDegrees: number;
};

export type ZeroOneOutfitItem = {
  itemId: string;
  slot: "top" | "bottom" | "dress" | "outerwear" | "shoes" | "accessory";
  displayName?: string;
  assetUri?: string;
  metadata?: Record<string, unknown>;
};

export type ZeroOneGarmentSource = {
  garmentId: string;
  sourceUri?: string;
  runtimeAssetUrls?: Partial<AvatarRuntimeAssetUrls>;
  materialHints?: Record<string, unknown>;
};

export type ZeroOneAvatarRequest = {
  userId: string;
  avatarAssetId: string;
  avatarSourcePreference: AvatarSourcePreference;
  bodyParams: BodyShapeParams;
  pose: DevAvatarPoseKey;
  outfitItems: ZeroOneOutfitItem[];
  garmentSources: ZeroOneGarmentSource[];
  renderQuality: ZeroOneRenderQuality;
  targetPlatform: ZeroOneTargetPlatform;
  camera: ZeroOneAvatarCamera;
  requestedOutputs: ZeroOneRequestedOutput[];
};

export type ZeroOneFitDiagnostics = {
  clippingScore?: number;
  tensionScore?: number;
  confidence?: number;
  notes?: string[];
};

export type ZeroOneSimulationMetadata = {
  solverName?: string;
  solverVersion?: string;
  elapsedMs?: number;
  settings?: Record<string, unknown>;
};

export type ZeroOneAvatarResult = {
  status: "pending" | "ok" | "warning" | "failed";
  previewImageUri?: string;
  glbUri?: string;
  usdzUri?: string;
  fitDiagnostics?: ZeroOneFitDiagnostics;
  simulationMetadata?: ZeroOneSimulationMetadata;
  errors?: string[];
};

export type ZeroOneAvatarBridge = {
  mode: ZeroOneAvatarBridgeMode;
  createRequest(input: ZeroOneAvatarRequest): ZeroOneAvatarRequest;
  consumeResult(result: ZeroOneAvatarResult): ZeroOneAvatarResult;
  validateResult(result: ZeroOneAvatarResult): {
    valid: boolean;
    errors: string[];
  };
};

export const LOCAL_PLACEHOLDER_ZEROONE_AVATAR_BRIDGE: ZeroOneAvatarBridge = {
  mode: "local-placeholder",
  createRequest(input) {
    return input;
  },
  consumeResult(result) {
    return result;
  },
  validateResult(result) {
    const errors: string[] = [];
    if (result.status === "failed" && (!result.errors || result.errors.length === 0)) {
      errors.push("failed_result_missing_errors");
    }
    if (
      result.status === "ok" &&
      !result.previewImageUri &&
      !result.glbUri &&
      !result.usdzUri &&
      !result.fitDiagnostics &&
      !result.simulationMetadata
    ) {
      errors.push("ok_result_missing_outputs");
    }
    return {
      valid: errors.length === 0,
      errors,
    };
  },
};
