import { auditAvatarObject3D, type AvatarAssetAudit } from "./avatarAssetAudit";
import { loadAvatarAsset } from "./loadAvatarAsset";
import { normalizeAvatarScene } from "./normalizeAvatarScene";
import { normalizeAvatarPbrMaterials } from "./avatarMaterialNormalizer";
import type { AvatarAssetManifest } from "../assets/avatarAssetManifest";
import { SkeletonUtils, THREE, type GLTF } from "../three";

export type PreparedAvatarAsset = {
  manifest: AvatarAssetManifest;
  gltf: GLTF;
  scene: THREE.Object3D;
  audit: AvatarAssetAudit;
};

const avatarAssetPromiseCache = new Map<string, Promise<PreparedAvatarAsset>>();

function cloneAvatarRoot(root: THREE.Object3D): THREE.Object3D {
  return SkeletonUtils.clone(root);
}

export async function loadPreparedAvatarAsset(
  manifest: AvatarAssetManifest,
): Promise<PreparedAvatarAsset> {
  const key = `${manifest.id}:${manifest.localModule ?? manifest.uri ?? "missing"}`;
  let cached = avatarAssetPromiseCache.get(key);
  if (!cached) {
    cached = (async () => {
      const loaded = await loadAvatarAsset(manifest);
      const scene = cloneAvatarRoot(loaded.gltf.scene);
      const normalizeReport = normalizeAvatarScene(scene, {
        expectedHeightMeters: manifest.expectedHeightMeters,
        rotation: manifest.rotation,
        position: manifest.position,
        scale: manifest.scale,
      });
      const materialReport = normalizeAvatarPbrMaterials(scene);
      const audit = auditAvatarObject3D(scene, {
        gltf: loaded.gltf,
        normalizeReport,
        materialTextureCount: materialReport.textureCount,
      });
      return { manifest, gltf: loaded.gltf, scene, audit };
    })();
    avatarAssetPromiseCache.set(key, cached);
  }
  return cached.then((prepared) => ({
    ...prepared,
    scene: cloneAvatarRoot(prepared.scene),
  }));
}

export function clearAvatarAssetCache(id?: string) {
  if (id == null) {
    avatarAssetPromiseCache.clear();
    return;
  }
  for (const key of avatarAssetPromiseCache.keys()) {
    if (key.startsWith(`${id}:`)) avatarAssetPromiseCache.delete(key);
  }
}
