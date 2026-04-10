import Constants from "expo-constants";
import { NativeModules, Platform } from "react-native";

import { renderRelativePathForRenderId } from "./contract";

const DEFAULT_SERVE_PORT = "3000";

function stripTrailingSlashes(s: string): string {
  return s.replace(/\/+$/, "");
}

/**
 * Dev-only: base URL (no trailing slash) where `npx serve .` (or similar) exposes the repo root.
 *
 * Resolution order:
 * 1. `EXPO_PUBLIC_AVATAR_RENDER_BASE_URL` (e.g. `http://192.168.1.253:3000`)
 * 2. Hostname from Metro bundle `SourceCode.scriptURL` + `EXPO_PUBLIC_AVATAR_RENDER_SERVE_PORT` (default 3000).
 *    - Android emulator: `localhost` in script URL becomes `10.0.2.2` (host loopback).
 * 3. If still unknown, returns `null` (set the env var explicitly).
 */
export function getDevAvatarRenderBaseUrl(): string | null {
  const explicit = process.env.EXPO_PUBLIC_AVATAR_RENDER_BASE_URL?.trim();
  if (explicit && explicit.length > 0) {
    return stripTrailingSlashes(explicit);
  }

  const fromBundle = deriveBaseUrlFromDevBundle();
  if (fromBundle) return fromBundle;

  return null;
}

/**
 * Full URL for the PNG under the repo, e.g.
 * `http://192.168.1.253:3000/generated/avatar_renders/dev_….png`
 */
export function getAvatarRenderHttpUrl(renderId: string): string | null {
  const base = getDevAvatarRenderBaseUrl();
  if (!base) return null;
  const rel = renderRelativePathForRenderId(renderId).replace(/\\/g, "/");
  return `${base}/${rel}`;
}

function servePort(): string {
  return (
    process.env.EXPO_PUBLIC_AVATAR_RENDER_SERVE_PORT?.trim() || DEFAULT_SERVE_PORT
  );
}

function deriveBaseUrlFromDevBundle(): string | null {
  const port = servePort();

  const scriptURL =
    (NativeModules.SourceCode as { scriptURL?: string } | undefined)
      ?.scriptURL ?? null;
  if (typeof scriptURL === "string" && scriptURL.length > 0) {
    try {
      const u = new URL(scriptURL);
      let host = u.hostname;
      const h = host.toLowerCase();
      if (h === "localhost" || h === "127.0.0.1") {
        host = Platform.OS === "android" ? "10.0.2.2" : "127.0.0.1";
      }
      return `http://${host}:${port}`;
    } catch {
      /* fall through */
    }
  }

  const hostUri = Constants.expoConfig?.hostUri;
  if (typeof hostUri === "string" && hostUri.length > 0) {
    try {
      const u = new URL(
        hostUri.includes("://") ? hostUri : `http://${hostUri}`,
      );
      let host = u.hostname;
      const h = host.toLowerCase();
      if (h === "localhost" || h === "127.0.0.1") {
        host = Platform.OS === "android" ? "10.0.2.2" : "127.0.0.1";
      }
      return `http://${host}:${port}`;
    } catch {
      return null;
    }
  }

  return null;
}

export type AvatarRenderHttpProbe = {
  ok: boolean;
  status: number;
  detail?: string;
};

/** Lightweight availability check (HEAD, then GET bytes=0-0 if needed). */
export async function probeAvatarRenderHttp(
  url: string,
): Promise<AvatarRenderHttpProbe> {
  try {
    let res = await fetch(url, { method: "HEAD" });
    if (res.status === 405 || res.status === 501) {
      res = await fetch(url, {
        method: "GET",
        headers: { Range: "bytes=0-0" },
      });
    }
    return { ok: res.ok, status: res.status };
  } catch (e) {
    const detail = e instanceof Error ? e.message : String(e);
    return { ok: false, status: 0, detail };
  }
}

export type PollAvatarRenderHttpResult = {
  ok: boolean;
  imageUri?: string;
  polledMs: number;
  lastStatus: number;
  lastDetail?: string;
  error?: string;
};

export async function pollAvatarRenderHttp(
  renderId: string,
  options: { pollIntervalMs?: number; pollTimeoutMs?: number } = {},
): Promise<PollAvatarRenderHttpResult> {
  const url = getAvatarRenderHttpUrl(renderId);
  if (!url) {
    return {
      ok: false,
      polledMs: 0,
      lastStatus: 0,
      error:
        "No render base URL. Set EXPO_PUBLIC_AVATAR_RENDER_BASE_URL (e.g. http://YOUR_LAN_IP:3000) or rely on dev hostname inference, and run `npx serve .` from the repo root.",
    };
  }

  const pollIntervalMs = options.pollIntervalMs ?? 750;
  const pollTimeoutMs = options.pollTimeoutMs ?? 120_000;
  const start = Date.now();
  let lastStatus = 0;
  let lastDetail: string | undefined;

  while (Date.now() - start < pollTimeoutMs) {
    const p = await probeAvatarRenderHttp(url);
    lastStatus = p.status;
    lastDetail = p.detail;
    if (p.ok) {
      return {
        ok: true,
        imageUri: url,
        polledMs: Date.now() - start,
        lastStatus: p.status,
      };
    }
    await new Promise((r) => setTimeout(r, pollIntervalMs));
  }

  return {
    ok: false,
    polledMs: Date.now() - start,
    lastStatus,
    lastDetail,
    error:
      lastDetail ??
      (lastStatus > 0
        ? `HTTP ${lastStatus}`
        : "Request failed (network or blocked cleartext HTTP?)"),
  };
}
