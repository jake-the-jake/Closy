import * as FileSystem from "expo-file-system/legacy";
import { Platform } from "react-native";

import {
  joinPathSegments,
  requestRelativePathForRenderId,
} from "./contract";
import { serializeAvatarExportRequestForDisk } from "./build-export-request";
import { toExpoFileUri } from "./paths";
import { getClosyRepoRoot } from "./repo-root";
import type { AvatarExportRequest, SaveAvatarRequestResult } from "./types";

async function writeRepoRequest(
  repoRoot: string,
  renderId: string,
  json: string,
): Promise<{ uri: string | null; ok: boolean; detail?: string }> {
  const rel = requestRelativePathForRenderId(renderId);
  const absolutePath = joinPathSegments(repoRoot, rel);
  const repoRequestFileUri = toExpoFileUri(absolutePath);
  try {
    const parent = absolutePath.replace(/[/\\][^/\\]+$/, "");
    await FileSystem.makeDirectoryAsync(toExpoFileUri(parent), {
      intermediates: true,
    });
    await FileSystem.writeAsStringAsync(repoRequestFileUri, json, {
      encoding: "utf8",
    });
    return { uri: repoRequestFileUri, ok: true };
  } catch (e) {
    const detail = e instanceof Error ? e.message : String(e);
    return { uri: repoRequestFileUri, ok: false, detail };
  }
}

async function writeCacheRequest(
  renderId: string,
  json: string,
): Promise<{ uri: string | null; ok: boolean; detail?: string }> {
  const cacheBase = FileSystem.cacheDirectory;
  if (cacheBase == null) {
    return { uri: null, ok: false, detail: "cacheDirectory_unavailable" };
  }
  const cacheDir = `${cacheBase}closy_avatar/avatar_requests/`;
  const cacheFileUri = `${cacheDir}${renderId.replace(/[/\\]/g, "_")}.json`;
  try {
    await FileSystem.makeDirectoryAsync(cacheDir, { intermediates: true });
    await FileSystem.writeAsStringAsync(cacheFileUri, json, { encoding: "utf8" });
    return { uri: cacheFileUri, ok: true };
  } catch (e) {
    const detail = e instanceof Error ? e.message : String(e);
    return { uri: cacheFileUri, ok: false, detail };
  }
}

/**
 * Persists export request JSON: **repo first** (`generated/avatar_requests/`), then **cache**
 * on native when `cacheDirectory` exists. Web skips cache entirely.
 * At least one successful write is enough for a usable handoff to the CLI.
 */
export async function saveAvatarExportRequest(
  request: AvatarExportRequest,
): Promise<SaveAvatarRequestResult> {
  const json = serializeAvatarExportRequestForDisk(request);
  const warnings: string[] = [];
  const repoRoot = getClosyRepoRoot();

  let repoRequestFileUri: string | null = null;
  let repoWriteSucceeded = false;

  if (repoRoot != null) {
    const repoResult = await writeRepoRequest(
      repoRoot,
      request.renderId,
      json,
    );
    repoRequestFileUri = repoResult.uri;
    repoWriteSucceeded = repoResult.ok;
    if (!repoResult.ok) {
      warnings.push(
        `Could not write to generated/avatar_requests/${request.renderId}.json${repoResult.detail ? `: ${repoResult.detail}` : ""}.`,
      );
    }
  } else {
    warnings.push(
      "EXPO_PUBLIC_CLOSY_REPO_ROOT is not loaded. Set it in .env and restart Expo so the app can write generated/avatar_requests/.",
    );
  }

  let cacheRequestFileUri: string | null = null;
  let cacheWriteSucceeded = false;

  if (Platform.OS === "web") {
    /* intentional — no app cache for export bridge on web */
  } else if (FileSystem.cacheDirectory == null) {
    if (repoWriteSucceeded) {
      warnings.push(
        "App cache is unavailable (normal on some sandboxes); the request is only under the repo path.",
      );
    }
  } else {
    const cacheResult = await writeCacheRequest(request.renderId, json);
    cacheRequestFileUri = cacheResult.uri;
    cacheWriteSucceeded = cacheResult.ok;
    if (!cacheResult.ok) {
      const suffix = repoWriteSucceeded
        ? " Request file is still in generated/avatar_requests if repo write succeeded."
        : "";
      warnings.push(
        `Could not copy request to app cache${cacheResult.detail ? ` (${cacheResult.detail})` : ""}.${suffix}`,
      );
    }
  }

  return {
    renderId: request.renderId,
    jsonForEngine: json,
    repoRequestFileUri,
    cacheRequestFileUri,
    repoWriteSucceeded,
    cacheWriteSucceeded,
    repoRootUsed: repoRoot,
    warnings,
  };
}
