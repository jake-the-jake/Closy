/** Subset written to disk for `avatar_export --outfit` (engine schema). */
export type AvatarEngineOutfitFile = {
  pose: string;
  width: number;
  height: number;
  camera: string;
  items: AvatarEngineOutfitItem[];
};

export type AvatarEngineOutfitItem = {
  slot: string;
  type: string;
  color?: [number, number, number];
};

/**
 * Optional dev/debug render flags under `closy.debug` in the export JSON.
 * Engine / `avatar_export` may ignore until implemented — keeps contract backward-compatible.
 */
export type AvatarExportDebugFlags = {
  showBodyOnly?: boolean;
  showGarmentOnly?: boolean;
  showOverlay?: boolean;
  showSilhouette?: boolean;
  showWireframe?: boolean;
  showSkeleton?: boolean;
};

export type AvatarExportRequest = {
  renderId: string;
  engine: AvatarEngineOutfitFile;
  closy: {
    contractVersion: 1;
    expectedOutputRelativePath: string;
    requestRelativePath: string;
    /** Dev-only; optional visualisation hints for native exporter (staged). */
    debug?: AvatarExportDebugFlags;
  };
};

/** Minimal outfit shape for building export JSON without full wardrobe sync. */
export type AvatarOutfitLike = {
  top?: { kind: "jumper" | "shirt"; color?: [number, number, number] };
  bottom?: { kind: "trousers"; color?: [number, number, number] };
  shoes?: { kind: "shoes"; color?: [number, number, number] };
};

export type SaveAvatarRequestResult = {
  renderId: string;
  jsonForEngine: string;
  /** `file://` URI when a repo write succeeded (typically web). */
  repoRequestFileUri: string | null;
  cacheRequestFileUri: string | null;
  repoWriteSucceeded: boolean;
  cacheWriteSucceeded: boolean;
  repoRootUsed: string | null;
  /**
   * True on Android/iOS: the app does not write to EXPO_PUBLIC_CLOSY_REPO_ROOT
   * (host PC path). Use cache + host CLI handoff instead.
   */
  hostRepoWriteSkipped: boolean;
  /**
   * Human path for docs (forward slashes), e.g. `E:/apps/Closy/generated/avatar_requests/id.json`
   * when repo root is set and host write was skipped.
   */
  expectedHostRequestPathDisplay: string | null;
  /** Non-fatal notices. */
  warnings: string[];
};

export type ExportResult =
  | {
      ok: true;
      variant: "image";
      imageUri: string;
      outputPathForDisplay: string;
      /** `http` = dev preview via static server; `file` = direct `file://` read; `mock` = env mock. */
      mode: "mock" | "file" | "http";
    }
  | {
      ok: true;
      variant: "manual_cli";
      message: string;
      cliCommand: string;
      outputPathForDisplay: string;
    }
  | {
      ok: true;
      variant: "host_handoff_required";
      message: string;
      renderId: string;
      requestJson: string;
      /** Host: write JSON into repo, then export. */
      cliRequestCommand: string;
      cliExportCommand: string;
      expectedRequestRelativePath: string;
      expectedRenderRelativePath: string;
      warnings: string[];
    }
  | {
      ok: false;
      code:
        | "MOCK_DISABLED"
        | "REPO_ROOT_REQUIRED"
        | "OUTPUT_NOT_FOUND"
        | "POLL_TIMEOUT"
        | "RENDER_HTTP_BASE_REQUIRED"
        | "UNSUPPORTED_RUNTIME"
        | "INVALID_REQUEST_PATH";
      message: string;
      cliCommand?: string;
      polledMs?: number;
    };
