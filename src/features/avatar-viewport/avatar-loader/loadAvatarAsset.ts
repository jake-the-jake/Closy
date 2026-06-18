import { loadBundledGltfModule } from "../gltf-bundled-load";
import { GLTFLoader, type GLTF } from "../three";
import type { AvatarAssetManifest } from "../assets/avatarAssetManifest";

export type LoadedAvatarAsset = {
  manifest: AvatarAssetManifest;
  gltf: GLTF;
  source: "localModule" | "uri";
};

export async function loadAvatarAsset(
  manifest: AvatarAssetManifest,
): Promise<LoadedAvatarAsset> {
  if (manifest.localModule != null) {
    return {
      manifest,
      gltf: await loadBundledGltfModule(manifest.localModule),
      source: "localModule",
    };
  }

  if (manifest.uri) {
    const loader = new GLTFLoader();
    const gltf = await loader.loadAsync(manifest.uri);
    return { manifest, gltf, source: "uri" };
  }

  throw new Error(
    manifest.status === "missing"
      ? manifest.missingReason ?? `Avatar asset ${manifest.id} is missing`
      : `Avatar asset ${manifest.id} has no uri/localModule`,
  );
}
