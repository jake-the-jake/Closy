import * as FileSystem from "expo-file-system/legacy";
import { Platform } from "react-native";

import {
  pollAvatarRenderHttp,
  probeAvatarRenderHttp,
  getAvatarRenderHttpUrl,
} from "./avatar-render-http";
import {
  joinPathSegments,
  renderRelativePathForRenderId,
  requestRelativePathForRenderId,
} from "./contract";
import { absoluteRenderPathForId } from "./paths";
import type { ExportResult, SaveAvatarRequestResult } from "./types";

export type RunAvatarExportOptions = {
  poll?: boolean;
  pollIntervalMs?: number;
  pollTimeoutMs?: number;
};

/** Host (Windows): drop JSON into repo before `closy:avatar-export`. */
export function buildNpmAvatarRequestCommand(renderId: string): string {
  return `npm run closy:avatar-request -- --id ${renderId} --file <PATH_TO_SAVED_JSON>`;
}

/** Cross-platform; uses positional render id for npm on Windows. */
export function buildNpmCliCommand(renderId: string): string {
  return `npm run closy:avatar-export -- ${renderId}`;
}

function hostHandoffResult(
  saved: SaveAvatarRequestResult,
  extraMessage?: string,
): ExportResult {
  const reqRel = requestRelativePathForRenderId(saved.renderId);
  const pngRel = renderRelativePathForRenderId(saved.renderId);
  return {
    ok: true,
    variant: "host_handoff_required",
    message:
      extraMessage ??
      "Run the host commands on your PC after saving the JSON there (see Step 2).",
    renderId: saved.renderId,
    requestJson: saved.jsonForEngine,
    cliRequestCommand: buildNpmAvatarRequestCommand(saved.renderId),
    cliExportCommand: buildNpmCliCommand(saved.renderId),
    expectedRequestRelativePath: reqRel,
    expectedRenderRelativePath: pngRel,
    warnings: saved.warnings,
  };
}

function httpImageResult(httpUrl: string): ExportResult {
  return {
    ok: true,
    variant: "image",
    imageUri: httpUrl,
    outputPathForDisplay: httpUrl,
    mode: "http",
  };
}

/**
 * After `saveAvatarExportRequest`: on **web**, `manual_cli`; on **Android/iOS**, uses HTTP
 * (dev static server) for renders when `EXPO_PUBLIC_AVATAR_RENDER_BASE_URL` or inferred dev
 * host + `npx serve .` is available — not direct Windows `file://` reads.
 *
 * **`poll: true`** — poll the HTTP URL until the PNG exists or timeout.
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
        "Browser cannot load the PNG from disk automatically. From the repo root, run the commands below, then open the PNG in your file explorer (or use the same HTTP URL as native if you serve the repo).",
      cliCommand: buildNpmCliCommand(saved.renderId),
      outputPathForDisplay: outRel,
    };
  }

  const wantPoll = options.poll === true;
  const pollIntervalMs = options.pollIntervalMs ?? 750;
  const pollTimeoutMs = options.pollTimeoutMs ?? 120_000;

  const httpUrl = getAvatarRenderHttpUrl(saved.renderId);

  if (httpUrl != null) {
    if ((await probeAvatarRenderHttp(httpUrl)).ok) {
      return httpImageResult(httpUrl);
    }

    if (!wantPoll) {
      if (saved.hostRepoWriteSkipped) {
        return hostHandoffResult(saved);
      }
      return {
        ok: false,
        code: "OUTPUT_NOT_FOUND",
        message:
          "Rendered PNG not at the HTTP preview URL yet. Run host export, serve the repo (`npx serve .`), then poll again.",
        cliCommand: buildNpmCliCommand(saved.renderId),
      };
    }

    const polled = await pollAvatarRenderHttp(saved.renderId, {
      pollIntervalMs,
      pollTimeoutMs,
    });
    if (polled.ok && polled.imageUri != null) {
      return httpImageResult(polled.imageUri);
    }

    return {
      ok: false,
      code: "POLL_TIMEOUT",
      message: `No PNG at ${httpUrl} within ${Math.round(polled.polledMs / 1000)}s. Serve the repo from the PC (\`npx serve .\` at repo root), confirm ${renderRelativePathForRenderId(saved.renderId)} exists, and retry.${polled.error ? `\n\nLast error: ${polled.error}` : ""}`,
      cliCommand: buildNpmCliCommand(saved.renderId),
      polledMs: polled.polledMs,
    };
  }

  if (saved.hostRepoWriteSkipped && !wantPoll) {
    return hostHandoffResult(saved);
  }

  if (saved.hostRepoWriteSkipped && wantPoll) {
    return {
      ok: false,
      code: "RENDER_HTTP_BASE_REQUIRED",
      message:
        "Native preview needs an HTTP URL to load the PNG (the emulator cannot read your Windows repo path). Set EXPO_PUBLIC_AVATAR_RENDER_BASE_URL (e.g. http://192.168.1.253:3000), run `npx serve .` from the repo root, restart Expo, then retry.",
      cliCommand: buildNpmCliCommand(saved.renderId),
    };
  }

  const output = absoluteRenderPathForId(saved.renderId);
  if (output == null) {
    return {
      ok: false,
      code: "REPO_ROOT_REQUIRED",
      message:
        "Set EXPO_PUBLIC_CLOSY_REPO_ROOT for path hints, or EXPO_PUBLIC_AVATAR_RENDER_BASE_URL for HTTP preview.",
      cliCommand: buildNpmCliCommand(saved.renderId),
    };
  }

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

  if (!wantPoll) {
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

  const pngHostHint =
    saved.repoRootUsed != null
      ? joinPathSegments(
          saved.repoRootUsed,
          renderRelativePathForRenderId(saved.renderId),
        )
      : renderRelativePathForRenderId(saved.renderId);

  return {
    ok: false,
    code: "POLL_TIMEOUT",
    message: `Could not read PNG from this path. On your PC open:\n${pngHostHint}\n\nFor Android dev preview, prefer HTTP: set EXPO_PUBLIC_AVATAR_RENDER_BASE_URL and \`npx serve .\`.`,
    cliCommand: buildNpmCliCommand(saved.renderId),
    polledMs: Date.now() - start,
  };
}
