/**
 * Android-safe loading for bundled `.glb` modules.
 * `useLoader(GLTFLoader, file:///…ExponentAsset…)` often fails on RN; we always pass binary
 * to `GLTFLoader.parse` after `Asset.downloadAsync` + `fetch` or `expo-file-system` base64.
 */

import { Asset } from "expo-asset";
import * as FileSystem from "expo-file-system/legacy";
import type { GLTF } from "three/examples/jsm/loaders/GLTFLoader.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

import { stripEmbeddedTexturesFromGlb } from "./gltf-strip-embedded-textures";

const promiseCache = new Map<number, Promise<GLTF>>();

function decodeBase64ToArrayBuffer(b64: string): ArrayBuffer {
  const binary = globalThis.atob(b64);
  const len = binary.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

async function readUriAsArrayBuffer(uri: string): Promise<ArrayBuffer> {
  try {
    const res = await fetch(uri);
    if (!res.ok) throw new Error(`fetch status ${res.status}`);
    return await res.arrayBuffer();
  } catch {
    const b64 = await FileSystem.readAsStringAsync(uri, {
      encoding: FileSystem.EncodingType.Base64,
    });
    return decodeBase64ToArrayBuffer(b64);
  }
}

/**
 * Load a Metro-bundled GLB module into a THREE.GLTF (cached per module id).
 * Embedded images are stripped from the GLB JSON before parse so Expo / expo-gl never
 * hits `data:image/...;base64,...` texture URLs (often unsupported or unstable).
 */
export function loadBundledGltfModule(moduleId: number): Promise<GLTF> {
  let p = promiseCache.get(moduleId);
  if (!p) {
    p = (async () => {
      const asset = Asset.fromModule(moduleId);
      await asset.downloadAsync();
      const uri = asset.localUri ?? asset.uri;
      if (!uri) throw new Error("Bundled GLB: Asset has no localUri/uri after downloadAsync");
      const buffer = await readUriAsArrayBuffer(uri);
      const stripped = stripEmbeddedTexturesFromGlb(buffer);
      const loader = new GLTFLoader();
      return await new Promise<GLTF>((resolve, reject) => {
        loader.parse(
          stripped,
          "",
          (gltf) => resolve(gltf),
          (err) =>
            reject(err instanceof Error ? err : new Error(String(err ?? "GLTF parse error"))),
        );
      });
    })();
    promiseCache.set(moduleId, p);
  }
  return p;
}

export function clearBundledGltfModuleCache(moduleId?: number) {
  if (moduleId == null) promiseCache.clear();
  else promiseCache.delete(moduleId);
}
