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

/** Android/iOS cannot reliably write or read the developer's host repo tree (e.g. `E:/apps/Closy`). */
function skipDirectHostRepoWrite(): boolean {
  return Platform.OS === "android" || Platform.OS === "ios";
}

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
 * Persists export request JSON.
 * - **Web:** writes to `generated/avatar_requests/` under `EXPO_PUBLIC_CLOSY_REPO_ROOT` when set.
 * - **Android/iOS:** never writes to the host repo path; saves to app cache only, then use host CLI handoff.
 */
export async function saveAvatarExportRequest(
  request: AvatarExportRequest,
): Promise<SaveAvatarRequestResult> {
  const json = serializeAvatarExportRequestForDisk(request);
  const warnings: string[] = [];
  const repoRoot = getClosyRepoRoot();
  const hostRepoWriteSkipped = skipDirectHostRepoWrite();

  const expectedHostRequestPathDisplay =
    repoRoot != null
      ? joinPathSegments(repoRoot, requestRelativePathForRenderId(request.renderId))
      : null;

  let repoRequestFileUri: string | null = null;
  let repoWriteSucceeded = false;

  if (hostRepoWriteSkipped) {
    if (repoRoot != null) {
      warnings.push(
        "Android/iOS cannot write your PC repo path. The request JSON is in app cache — use Share/Copy JSON, then on Windows run `npm run closy:avatar-request`, then `npm run closy:avatar-export`, serve the repo (`npx serve .`), and load the PNG over HTTP on the dev screen.",
      );
    } else {
      warnings.push(
        "EXPO_PUBLIC_CLOSY_REPO_ROOT is not loaded. Set it for path hints; JSON is still saved to app cache when possible.",
      );
    }
  } else if (repoRoot != null) {
    const repoResult = await writeRepoRequest(
      repoRoot,
      request.renderId,
      json,
    );
    repoRequestFileUri = repoResult.uri;
    repoWriteSucceeded = repoResult.ok;
    if (!repoResult.ok) {
      warnings.push(
        `Could not write to ${requestRelativePathForRenderId(request.renderId)}${repoResult.detail ? `: ${repoResult.detail}` : ""}.`,
      );
    }
  } else {
    warnings.push(
      "EXPO_PUBLIC_CLOSY_REPO_ROOT is not loaded. Set it in .env and restart Expo for repo-relative writes (web).",
    );
  }

  let cacheRequestFileUri: string | null = null;
  let cacheWriteSucceeded = false;

  if (Platform.OS === "web") {
    /* no app cache on web */
  } else if (FileSystem.cacheDirectory == null) {
    warnings.push(
      "App cache directory is unavailable; could not store a local copy of the request JSON.",
    );
  } else {
    const cacheResult = await writeCacheRequest(request.renderId, json);
    cacheRequestFileUri = cacheResult.uri;
    cacheWriteSucceeded = cacheResult.ok;
    if (!cacheResult.ok) {
      warnings.push(
        `Could not save request to app cache${cacheResult.detail ? ` (${cacheResult.detail})` : ""}.`,
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
    hostRepoWriteSkipped,
    expectedHostRequestPathDisplay,
    warnings,
  };
}
