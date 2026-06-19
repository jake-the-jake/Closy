import type {
  BodyShapeParams,
  GarmentFitState,
} from "@/features/avatar-export";
import type {
  DevAvatarPoseKey,
  DevAvatarPresetKey,
} from "@/features/avatar-export/dev-avatar-shared";

export type ZeroOneAvatarOutputRequest = {
  previewPng?: boolean;
  glb?: boolean;
  fitDiagnostics?: boolean;
  simulationCache?: boolean;
};

export type ZeroOneAvatarQuality =
  | "mobilePreview"
  | "highQualityPreview"
  | "offlineRender";

export type ZeroOneAvatarCamera = {
  target: [number, number, number];
  radius: number;
  yaw: number;
  pitch: number;
  fovDegrees: number;
};

export type ZeroOneAvatarRenderRequest = {
  requestId: string;
  userId?: string;
  avatarSourceId: string;
  wardrobeItemIds: string[];
  outfitPreset: DevAvatarPresetKey;
  pose: DevAvatarPoseKey;
  bodyShapeParams: BodyShapeParams;
  garmentFitState: GarmentFitState;
  camera: ZeroOneAvatarCamera;
  output: ZeroOneAvatarOutputRequest;
  quality: ZeroOneAvatarQuality;
};

export type ZeroOneAvatarRenderResult = {
  requestId: string;
  status: "queued" | "running" | "complete" | "failed";
  previewImageUri?: string;
  glbUri?: string;
  diagnostics?: Record<string, unknown>;
  errors?: string[];
};

export type ZeroOneAvatarBridge = {
  createRequestFromClosyState(input: ZeroOneAvatarRenderRequest): ZeroOneAvatarRenderRequest;
  validateResult(result: ZeroOneAvatarRenderResult): { valid: boolean; errors: string[] };
  consumePreviewResult(result: ZeroOneAvatarRenderResult): string | null;
  consumeGlbResult(result: ZeroOneAvatarRenderResult): string | null;
};
