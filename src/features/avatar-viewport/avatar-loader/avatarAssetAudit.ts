import { THREE, type GLTF } from "../three";
import type { AvatarNormalizeReport } from "../avatar-normalize";

export type AvatarAssetAudit = {
  assetId?: string;
  sourcePreference?: string;
  meshCount: number;
  visibleMeshCount: number;
  skinnedMeshCount: number;
  boneCount: number;
  animationCount: number;
  materialCount: number;
  textureCount: number;
  materialNames: string[];
  transparentMaterialCount: number;
  triangleEstimate: number;
  sceneChildCount: number;
  worldScale: [number, number, number];
  bounds: {
    min: [number, number, number];
    max: [number, number, number];
    size: [number, number, number];
    center: [number, number, number];
  };
  normalizedScale: number;
  materialSafetyStatus?: "mobile_safe" | "mobile_sanitized";
  validity: "valid" | "invalid";
  failureReason: string | null;
};

function tuple(v: THREE.Vector3): [number, number, number] {
  return [v.x, v.y, v.z];
}

function isMeshLike(o: THREE.Object3D): o is THREE.Mesh | THREE.SkinnedMesh {
  const flags = o as { isMesh?: boolean; isSkinnedMesh?: boolean };
  return flags.isMesh === true || flags.isSkinnedMesh === true;
}

function materialList(mesh: THREE.Mesh | THREE.SkinnedMesh): THREE.Material[] {
  if (Array.isArray(mesh.material)) return mesh.material.filter(Boolean);
  return mesh.material ? [mesh.material] : [];
}

function materialTextures(material: THREE.Material): THREE.Texture[] {
  const record = material as unknown as Record<string, unknown>;
  const out: THREE.Texture[] = [];
  for (const key of [
    "map",
    "normalMap",
    "roughnessMap",
    "metalnessMap",
    "aoMap",
    "emissiveMap",
    "alphaMap",
  ]) {
    const value = record[key];
    if (value instanceof THREE.Texture) out.push(value);
  }
  return out;
}

function estimateMeshTriangles(mesh: THREE.Mesh | THREE.SkinnedMesh): number {
  const geometry = mesh.geometry;
  if (!geometry) return 0;
  if (geometry.index) return Math.floor(geometry.index.count / 3);
  const position = geometry.getAttribute("position");
  return position ? Math.floor(position.count / 3) : 0;
}

export function auditAvatarObject3D(
  root: THREE.Object3D,
  options: {
    gltf?: GLTF;
    normalizeReport?: AvatarNormalizeReport;
    materialTextureCount?: number;
    assetId?: string;
    sourcePreference?: string;
    materialSafetyStatus?: "mobile_safe" | "mobile_sanitized";
  } = {},
): AvatarAssetAudit {
  const materials = new Set<THREE.Material>();
  const textures = new Set<THREE.Texture>();
  const bones = new Set<THREE.Bone>();
  let meshCount = 0;
  let visibleMeshCount = 0;
  let skinnedMeshCount = 0;
  let triangleEstimate = 0;
  let transparentMaterialCount = 0;

  root.updateMatrixWorld(true);
  root.traverse((o) => {
    if (o instanceof THREE.Bone) bones.add(o);
    if (!isMeshLike(o)) return;
    meshCount += 1;
    if (o.visible) visibleMeshCount += 1;
    if ((o as THREE.SkinnedMesh).isSkinnedMesh) skinnedMeshCount += 1;
    triangleEstimate += estimateMeshTriangles(o);
    for (const material of materialList(o)) {
      materials.add(material);
      if (material.transparent || material.opacity < 0.999) transparentMaterialCount += 1;
      for (const texture of materialTextures(material)) textures.add(texture);
    }
  });

  const box = new THREE.Box3().setFromObject(root);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const failureReason =
    meshCount <= 0
      ? "asset_has_no_meshes"
      : visibleMeshCount <= 0
        ? "asset_has_no_visible_meshes"
        : null;

  return {
    assetId: options.assetId,
    sourcePreference: options.sourcePreference,
    meshCount,
    visibleMeshCount,
    skinnedMeshCount,
    boneCount: bones.size,
    animationCount: options.gltf?.animations?.length ?? 0,
    materialCount: materials.size,
    textureCount: Math.max(textures.size, options.materialTextureCount ?? 0),
    materialNames: [...materials].map((material) => material.name || material.type),
    transparentMaterialCount,
    triangleEstimate,
    sceneChildCount: root.children.length,
    worldScale: tuple(root.getWorldScale(new THREE.Vector3())),
    bounds: {
      min: tuple(box.min),
      max: tuple(box.max),
      size: tuple(size),
      center: tuple(center),
    },
    normalizedScale: options.normalizeReport?.scaleApplied ?? 1,
    materialSafetyStatus: options.materialSafetyStatus,
    validity: failureReason == null ? "valid" : "invalid",
    failureReason,
  };
}
