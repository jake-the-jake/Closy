import type { AvatarRenderAudit } from "../live-viewport-debug-types";

export type AvatarRenderableValidation = {
  valid: boolean;
  reason: string;
  meshCount: number;
  visibleMeshCount: number;
  materialCount: number;
  bounds?: {
    height?: number;
    width?: number;
    depth?: number;
  };
  firstMeshName?: string | null;
  firstMeshWorldPosition: [number, number, number] | null;
  firstMeshWorldScale: [number, number, number] | null;
};

function finiteNonZeroTuple(value: [number, number, number] | null | undefined): boolean {
  if (!value) return false;
  return value.every((n) => Number.isFinite(n)) && value.some((n) => Math.abs(n) > 1e-6);
}

function finiteTuple(value: [number, number, number] | null | undefined): boolean {
  if (!value) return false;
  return value.every((n) => Number.isFinite(n));
}

export function validateAvatarRenderableFromAudit(
  audit: AvatarRenderAudit | null | undefined,
  options: { requireGltfVisibleMesh?: boolean } = {},
): AvatarRenderableValidation {
  if (!audit) {
    return {
      valid: false,
      reason: "missing_render_audit",
      meshCount: 0,
      visibleMeshCount: 0,
      materialCount: 0,
      firstMeshWorldPosition: null,
      firstMeshWorldScale: null,
    };
  }

  if (!audit.mountedAvatarRoot) {
    return {
      valid: false,
      reason: "avatar_root_not_mounted",
      meshCount: audit.totalMeshCount,
      visibleMeshCount: audit.visibleMeshCount,
      materialCount: 0,
      firstMeshWorldPosition: audit.firstMeshWorldPosition,
      firstMeshWorldScale: audit.firstMeshScale,
    };
  }

  if (options.requireGltfVisibleMesh && audit.gltfVisibleMeshCount <= 0) {
    return {
      valid: false,
      reason: audit.gltfTotalMeshCount > 0 ? "gltf_loaded_but_no_visible_meshes" : "gltf_not_attached",
      meshCount: audit.gltfTotalMeshCount,
      visibleMeshCount: audit.gltfVisibleMeshCount,
      materialCount: 0,
      firstMeshWorldPosition: audit.firstMeshWorldPosition,
      firstMeshWorldScale: audit.firstMeshScale,
    };
  }

  if (audit.totalMeshCount <= 0) {
    return {
      valid: false,
      reason: "no_renderable_meshes",
      meshCount: audit.totalMeshCount,
      visibleMeshCount: audit.visibleMeshCount,
      materialCount: 0,
      firstMeshWorldPosition: audit.firstMeshWorldPosition,
      firstMeshWorldScale: audit.firstMeshScale,
    };
  }

  if (audit.visibleMeshCount <= 0) {
    return {
      valid: false,
      reason: "no_visible_meshes",
      meshCount: audit.totalMeshCount,
      visibleMeshCount: audit.visibleMeshCount,
      materialCount: 0,
      firstMeshWorldPosition: audit.firstMeshWorldPosition,
      firstMeshWorldScale: audit.firstMeshScale,
    };
  }

  if (audit.firstMeshMaterialTransparent === true && (audit.firstMeshMaterialOpacity ?? 0) <= 0.01) {
    return {
      valid: false,
      reason: "first_mesh_material_fully_transparent",
      meshCount: audit.totalMeshCount,
      visibleMeshCount: audit.visibleMeshCount,
      materialCount: 1,
      firstMeshWorldPosition: audit.firstMeshWorldPosition,
      firstMeshWorldScale: audit.firstMeshScale,
    };
  }

  if (!finiteTuple(audit.firstMeshWorldPosition)) {
    return {
      valid: false,
      reason: "first_mesh_world_position_invalid",
      meshCount: audit.totalMeshCount,
      visibleMeshCount: audit.visibleMeshCount,
      materialCount: 1,
      firstMeshWorldPosition: audit.firstMeshWorldPosition,
      firstMeshWorldScale: audit.firstMeshScale,
    };
  }

  if (!finiteNonZeroTuple(audit.firstMeshScale)) {
    return {
      valid: false,
      reason: "first_mesh_world_scale_invalid",
      meshCount: audit.totalMeshCount,
      visibleMeshCount: audit.visibleMeshCount,
      materialCount: 1,
      firstMeshWorldPosition: audit.firstMeshWorldPosition,
      firstMeshWorldScale: audit.firstMeshScale,
    };
  }

  return {
    valid: true,
    reason: "renderable",
    meshCount: audit.totalMeshCount,
    visibleMeshCount: audit.visibleMeshCount,
    materialCount: 1,
    firstMeshWorldPosition: audit.firstMeshWorldPosition,
    firstMeshWorldScale: audit.firstMeshScale,
  };
}
