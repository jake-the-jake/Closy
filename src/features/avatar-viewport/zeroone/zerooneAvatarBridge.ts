import type {
  ZeroOneAvatarBridge,
  ZeroOneAvatarRenderRequest,
  ZeroOneAvatarRenderResult,
} from "./zerooneAvatarBridgeTypes";

export const localPlaceholderZeroOneAvatarBridge: ZeroOneAvatarBridge = {
  createRequestFromClosyState(input: ZeroOneAvatarRenderRequest) {
    return input;
  },
  validateResult(result: ZeroOneAvatarRenderResult) {
    const errors: string[] = [];
    if (!result.requestId) errors.push("missing_request_id");
    if (result.status === "failed" && (!result.errors || result.errors.length === 0)) {
      errors.push("failed_result_missing_errors");
    }
    if (
      result.status === "complete" &&
      !result.previewImageUri &&
      !result.glbUri &&
      !result.diagnostics
    ) {
      errors.push("complete_result_missing_outputs");
    }
    return {
      valid: errors.length === 0,
      errors,
    };
  },
  consumePreviewResult(result: ZeroOneAvatarRenderResult) {
    return result.status === "complete" ? result.previewImageUri ?? null : null;
  },
  consumeGlbResult(result: ZeroOneAvatarRenderResult) {
    return result.status === "complete" ? result.glbUri ?? null : null;
  },
};
