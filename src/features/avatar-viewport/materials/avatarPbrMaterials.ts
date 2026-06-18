import { THREE } from "../three";

export type AvatarMaterialRole = "skin" | "hair" | "eyes" | "clothing" | "unknown";

export type AvatarMaterialNormalizeReport = {
  materialCount: number;
  textureCount: number;
  replacedMaterialCount: number;
  unsupportedFeatureCount: number;
  materialSafetyStatus: "mobile_safe" | "mobile_sanitized";
};

function isMeshLike(o: THREE.Object3D): o is THREE.Mesh | THREE.SkinnedMesh {
  const flags = o as { isMesh?: boolean; isSkinnedMesh?: boolean };
  return flags.isMesh === true || flags.isSkinnedMesh === true;
}

function roleForMaterial(name: string): AvatarMaterialRole {
  if (/skin|body|face|mannequin/i.test(name)) return "skin";
  if (/hair|brow/i.test(name)) return "hair";
  if (/eye|cornea|iris/i.test(name)) return "eyes";
  if (/cloth|fabric|shirt|pant|dress|outfit|garment/i.test(name)) return "clothing";
  return "unknown";
}

function materialTextures(material: THREE.Material): THREE.Texture[] {
  const record = material as unknown as Record<string, unknown>;
  const textures: THREE.Texture[] = [];
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
    if (value instanceof THREE.Texture) textures.push(value);
  }
  return textures;
}

function pbrFallbackForRole(role: AvatarMaterialRole): THREE.MeshStandardMaterial {
  switch (role) {
    case "skin":
      return new THREE.MeshStandardMaterial({
        color: 0xd8b99d,
        roughness: 0.82,
        metalness: 0,
        emissive: 0x120806,
        emissiveIntensity: 0.08,
      });
    case "eyes":
      return new THREE.MeshStandardMaterial({
        color: 0xf6f3ea,
        roughness: 0.24,
        metalness: 0,
      });
    case "hair":
      return new THREE.MeshStandardMaterial({
        color: 0x4d3528,
        roughness: 0.72,
        metalness: 0,
      });
    case "clothing":
      return new THREE.MeshStandardMaterial({
        color: 0x8f9fb3,
        roughness: 0.9,
        metalness: 0,
      });
    default:
      return new THREE.MeshStandardMaterial({
        color: 0xd7c5b7,
        roughness: 0.86,
        metalness: 0,
      });
  }
}

function copyTextureSlot(
  source: THREE.MeshStandardMaterial,
  target: THREE.MeshStandardMaterial,
  key:
    | "map"
    | "normalMap"
    | "roughnessMap"
    | "metalnessMap"
    | "aoMap"
    | "emissiveMap",
) {
  target[key] = source[key];
}

function cloneAsMobileStandardMaterial(
  material: THREE.MeshStandardMaterial,
  role: AvatarMaterialRole,
): THREE.MeshStandardMaterial {
  const replacement = pbrFallbackForRole(role);
  replacement.name = material.name ? `${material.name}_mobileStandard` : `${role}_mobileStandard`;
  replacement.color.copy(material.color);
  copyTextureSlot(material, replacement, "map");
  copyTextureSlot(material, replacement, "normalMap");
  copyTextureSlot(material, replacement, "roughnessMap");
  copyTextureSlot(material, replacement, "metalnessMap");
  copyTextureSlot(material, replacement, "aoMap");
  copyTextureSlot(material, replacement, "emissiveMap");
  replacement.roughness = Number.isFinite(material.roughness) ? material.roughness : replacement.roughness;
  replacement.metalness = Number.isFinite(material.metalness) ? material.metalness : replacement.metalness;
  return replacement;
}

function usesUnsafePhysicalFeatures(material: THREE.MeshStandardMaterial): boolean {
  const record = material as unknown as Record<string, unknown>;
  return (
    material.type === "MeshPhysicalMaterial" ||
    Number(record.dispersion ?? 0) !== 0 ||
    Number(record.transmission ?? 0) !== 0 ||
    Number(record.clearcoat ?? 0) !== 0 ||
    Number(record.ior ?? 1.5) !== 1.5
  );
}

function normalizeStandardMaterial(material: THREE.MeshStandardMaterial, role: AvatarMaterialRole) {
  material.roughness = Math.min(1, Math.max(0.18, material.roughness || 0.82));
  material.metalness = Math.min(0.15, Math.max(0, material.metalness || 0));
  material.depthTest = true;
  material.depthWrite = true;
  // Expo GL is much more predictable when avatar body materials are opaque.
  material.opacity = 1;
  material.transparent = false;
  material.side = THREE.FrontSide;
  if (role === "skin" && material.emissiveIntensity === 0) {
    material.emissive.set(0x120806);
    material.emissiveIntensity = 0.05;
  }
  material.needsUpdate = true;
}

export function normalizeAvatarPbrMaterials(
  root: THREE.Object3D,
): AvatarMaterialNormalizeReport {
  const materials = new Set<THREE.Material>();
  const textures = new Set<THREE.Texture>();
  let replacedMaterialCount = 0;
  let unsupportedFeatureCount = 0;

  root.traverse((o) => {
    if (!isMeshLike(o)) return;
    const incoming = Array.isArray(o.material) ? o.material : [o.material];
    const normalized = incoming.map((material) => {
      const role = roleForMaterial(material?.name ?? o.name);
      if (!(material instanceof THREE.MeshStandardMaterial)) {
        replacedMaterialCount += 1;
        const replacement = pbrFallbackForRole(role);
        replacement.name = material?.name ? `${material.name}_mobilePbr` : `${role}_mobilePbr`;
        return replacement;
      }
      if (usesUnsafePhysicalFeatures(material)) {
        replacedMaterialCount += 1;
        unsupportedFeatureCount += 1;
        const replacement = cloneAsMobileStandardMaterial(material, role);
        normalizeStandardMaterial(replacement, role);
        return replacement;
      }
      normalizeStandardMaterial(material, role);
      return material;
    });

    for (const material of normalized) {
      materials.add(material);
      for (const texture of materialTextures(material)) textures.add(texture);
    }
    o.material = Array.isArray(o.material) ? normalized : normalized[0];
  });

  return {
    materialCount: materials.size,
    textureCount: textures.size,
    replacedMaterialCount,
    unsupportedFeatureCount,
    materialSafetyStatus: replacedMaterialCount > 0 ? "mobile_sanitized" : "mobile_safe",
  };
}
