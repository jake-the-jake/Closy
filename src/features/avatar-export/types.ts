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

export type AvatarExportRequest = {
  renderId: string;
  engine: AvatarEngineOutfitFile;
  closy: {
    contractVersion: 1;
    expectedOutputRelativePath: string;
    requestRelativePath: string;
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
  /** `file://` URI when written, else null */
  repoRequestFileUri: string | null;
  cacheRequestFileUri: string | null;
  repoWriteSucceeded: boolean;
  cacheWriteSucceeded: boolean;
  repoRootUsed: string | null;
  /** Non-fatal notices (e.g. cache unavailable when repo write succeeded). */
  warnings: string[];
};

export type ExportResult =
  | {
      ok: true;
      variant: "image";
      imageUri: string;
      outputPathForDisplay: string;
      mode: "mock" | "file";
    }
  | {
      ok: true;
      variant: "manual_cli";
      message: string;
      cliCommand: string;
      outputPathForDisplay: string;
    }
  | {
      ok: false;
      code:
        | "MOCK_DISABLED"
        | "REPO_ROOT_REQUIRED"
        | "OUTPUT_NOT_FOUND"
        | "POLL_TIMEOUT"
        | "UNSUPPORTED_RUNTIME"
        | "INVALID_REQUEST_PATH";
      message: string;
      cliCommand?: string;
      polledMs?: number;
    };
