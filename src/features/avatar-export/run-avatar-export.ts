import * as FileSystem from "expo-file-system/legacy";
import { Platform } from "react-native";

import { renderRelativePathForRenderId } from "./contract";
import { absoluteRenderPathForId } from "./paths";
import type { ExportResult, SaveAvatarRequestResult } from "./types";

export type RunAvatarExportOptions = {
  poll?: boolean;
  pollIntervalMs?: number;
  pollTimeoutMs?: number;
};

/** Cross-platform; uses positional render id for npm on Windows. */
export function buildNpmCliCommand(renderId: string): string {
  return `npm run closy:avatar-export -- ${renderId}`;
}

/**
 * After `saveAvatarExportRequest`, run the native exporter from a shell, then call this to
 * pick up the PNG (native only). On **web**, returns `variant: "manual_cli"` (not an error).
 *
 * With `EXPO_PUBLIC_AVATAR_EXPORT_MOCK=1`, returns a placeholder image immediately.
 */
export async function runAvatarExport(
  saved: SaveAvatarRequestResult,
  options: RunAvatarExportOptions = {},
): Promise<ExportResult> {
  if (process.env.EXPO_PUBLIC_AVATAR_EXPORT_MOCK === "1") {
    const uri =
      process.env.EXPO_PUBLIC_AVATAR_EXPORT_MOCK_URI?.trim() ||
      "https://picsum.photos/seed/closy-avatar-mock/512/512";
    return {
      ok: true,
      variant: "image",
      imageUri: uri,
      outputPathForDisplay: "(mock)",
      mode: "mock",
    };
  }

  if (Platform.OS === "web") {
    const outRel = renderRelativePathForRenderId(saved.renderId);
    return {
      ok: true,
      variant: "manual_cli",
      message:
        "Browser cannot load the PNG from disk automatically. From the repo root, run the command below, then open the file in your file explorer.",
      cliCommand: buildNpmCliCommand(saved.renderId),
      outputPathForDisplay: outRel,
    };
  }

  const output = absoluteRenderPathForId(saved.renderId);
  if (output == null) {
    return {
      ok: false,
      code: "REPO_ROOT_REQUIRED",
      message:
        "Set EXPO_PUBLIC_CLOSY_REPO_ROOT so the app can read generated/avatar_renders/.",
      cliCommand: buildNpmCliCommand(saved.renderId),
    };
  }

  const poll = options.poll ?? true;
  const pollIntervalMs = options.pollIntervalMs ?? 700;
  const pollTimeoutMs = options.pollTimeoutMs ?? 120_000;

  const fileReady = async (): Promise<boolean> => {
    try {
      const info = await FileSystem.getInfoAsync(output.fileUri);
      return info.exists;
    } catch {
      return false;
    }
  };

  if (await fileReady()) {
    return {
      ok: true,
      variant: "image",
      imageUri: output.fileUri,
      outputPathForDisplay: output.absolutePath,
      mode: "file",
    };
  }

  if (!poll) {
    return {
      ok: false,
      code: "OUTPUT_NOT_FOUND",
      message:
        "Rendered PNG not found yet. From the repo root, run the export command below.",
      cliCommand: buildNpmCliCommand(saved.renderId),
    };
  }

  const start = Date.now();
  while (Date.now() - start < pollTimeoutMs) {
    if (await fileReady()) {
      return {
        ok: true,
        variant: "image",
        imageUri: output.fileUri,
        outputPathForDisplay: output.absolutePath,
        mode: "file",
      };
    }
    await new Promise((r) => setTimeout(r, pollIntervalMs));
  }

  return {
    ok: false,
    code: "POLL_TIMEOUT",
    message: `Timed out waiting for ${output.absolutePath}. Run:\n${buildNpmCliCommand(saved.renderId)}`,
    cliCommand: buildNpmCliCommand(saved.renderId),
    polledMs: Date.now() - start,
  };
}
