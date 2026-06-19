import type { AvatarRenderAudit } from "../live-viewport-debug-types";
import type { AvatarRenderableReport } from "../live-viewport-debug-types";

export type AvatarCandidateValidation = {
  assetAuditValid: boolean;
  mountAuditValid: boolean;
  renderable: boolean;
  assetReason: string;
  mountReason: string;
  sourceKey: string;
};

export type AvatarRenderableValidation = AvatarCandidateValidation & {
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
  sceneUuid?: string | null;
  sourceVersion?: number | null;
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
      assetAuditValid: false,
      mountAuditValid: false,
      renderable: false,
      assetReason: "missing_render_audit",
      mountReason: "missing_render_audit",
      sourceKey: "legacy_parent_audit",
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
      assetAuditValid: false,
      mountAuditValid: false,
      renderable: false,
      assetReason: "avatar_root_not_mounted",
      mountReason: "avatar_root_not_mounted",
      sourceKey: "legacy_parent_audit",
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
      assetAuditValid: false,
      mountAuditValid: audit.mountedAvatarRoot,
      renderable: false,
      assetReason: audit.gltfTotalMeshCount > 0 ? "gltf_loaded_but_no_visible_meshes" : "gltf_not_attached",
      mountReason: audit.mountedAvatarRoot ? "mounted" : "avatar_root_not_mounted",
      sourceKey: "legacy_parent_audit",
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
      assetAuditValid: false,
      mountAuditValid: audit.mountedAvatarRoot,
      renderable: false,
      assetReason: "no_renderable_meshes",
      mountReason: audit.mountedAvatarRoot ? "mounted" : "avatar_root_not_mounted",
      sourceKey: "legacy_parent_audit",
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
      assetAuditValid: false,
      mountAuditValid: audit.mountedAvatarRoot,
      renderable: false,
      assetReason: "no_visible_meshes",
      mountReason: audit.mountedAvatarRoot ? "mounted" : "avatar_root_not_mounted",
      sourceKey: "legacy_parent_audit",
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
      assetAuditValid: false,
      mountAuditValid: audit.mountedAvatarRoot,
      renderable: false,
      assetReason: "first_mesh_material_fully_transparent",
      mountReason: audit.mountedAvatarRoot ? "mounted" : "avatar_root_not_mounted",
      sourceKey: "legacy_parent_audit",
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
      assetAuditValid: true,
      mountAuditValid: false,
      renderable: false,
      assetReason: "asset_audit_valid",
      mountReason: "first_mesh_world_position_invalid",
      sourceKey: "legacy_parent_audit",
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
      assetAuditValid: true,
      mountAuditValid: false,
      renderable: false,
      assetReason: "asset_audit_valid",
      mountReason: "first_mesh_world_scale_invalid",
      sourceKey: "legacy_parent_audit",
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
    assetAuditValid: true,
    mountAuditValid: true,
    renderable: true,
    assetReason: "asset_audit_valid",
    mountReason: "mounted",
    sourceKey: "legacy_parent_audit",
    reason: "renderable",
    meshCount: audit.totalMeshCount,
    visibleMeshCount: audit.visibleMeshCount,
    materialCount: 1,
    firstMeshWorldPosition: audit.firstMeshWorldPosition,
    firstMeshWorldScale: audit.firstMeshScale,
  };
}

function validBounds(bounds: AvatarRenderableReport["bounds"]): boolean {
  if (!bounds) return false;
  return (
    finiteTuple(bounds.min) &&
    finiteTuple(bounds.max) &&
    finiteTuple(bounds.center) &&
    finiteNonZeroTuple(bounds.size)
  );
}

export function validateAvatarCandidateRenderable({
  parentAudit,
  childReport,
  expectedSourceKey,
  currentSourceVersion,
  reportSourceVersion,
}: {
  parentAudit: AvatarRenderAudit | null | undefined;
  childReport: AvatarRenderableReport | null | undefined;
  expectedSourceKey: string;
  currentSourceVersion: number;
  reportSourceVersion: number | null | undefined;
}): AvatarRenderableValidation {
  if (!childReport) {
    return {
      valid: false,
      assetAuditValid: false,
      mountAuditValid: false,
      renderable: false,
      assetReason: "missing_child_renderable_report",
      mountReason: "missing_child_renderable_report",
      sourceKey: expectedSourceKey,
      reason: "missing_child_renderable_report",
      meshCount: parentAudit?.gltfTotalMeshCount ?? 0,
      visibleMeshCount: parentAudit?.gltfVisibleMeshCount ?? 0,
      materialCount: 0,
      firstMeshWorldPosition: parentAudit?.firstMeshWorldPosition ?? null,
      firstMeshWorldScale: parentAudit?.firstMeshScale ?? null,
      sceneUuid: null,
      sourceVersion: currentSourceVersion,
    };
  }

  const assetAuditValid =
    childReport.meshCount > 0 &&
    childReport.visibleMeshCount > 0 &&
    validBounds(childReport.bounds) &&
    !(childReport.firstMaterialTransparent === true && (childReport.firstMaterialOpacity ?? 0) <= 0.01);
  const assetReason = assetAuditValid ? "asset_audit_valid" : childReport.reason;
  const mountAuditValid =
    childReport.mounted === true &&
    childReport.sourceKey === expectedSourceKey &&
    !!childReport.sceneUuid &&
    reportSourceVersion === currentSourceVersion &&
    finiteTuple(childReport.firstMeshWorldPosition) &&
    finiteNonZeroTuple(childReport.firstMeshWorldScale);
  const mountReason =
    childReport.sourceKey !== expectedSourceKey
      ? "stale_source_report"
      : reportSourceVersion !== currentSourceVersion
        ? "stale_source_version"
        : !childReport.mounted
          ? "scene_not_mounted"
          : !childReport.sceneUuid
            ? "missing_scene_uuid"
            : !finiteTuple(childReport.firstMeshWorldPosition)
              ? "first_mesh_world_position_invalid"
              : !finiteNonZeroTuple(childReport.firstMeshWorldScale)
                ? "first_mesh_world_scale_invalid"
                : "mounted";
  const renderable = assetAuditValid && mountAuditValid && childReport.valid;

  return {
    valid: renderable,
    assetAuditValid,
    mountAuditValid,
    renderable,
    assetReason,
    mountReason,
    sourceKey: childReport.sourceKey,
    reason: renderable ? "renderable" : !assetAuditValid ? assetReason : mountReason,
    meshCount: childReport.meshCount,
    visibleMeshCount: childReport.visibleMeshCount,
    materialCount: childReport.materialCount,
    bounds: childReport.bounds
      ? {
          width: childReport.bounds.size[0],
          height: childReport.bounds.size[1],
          depth: childReport.bounds.size[2],
        }
      : undefined,
    firstMeshName: childReport.firstMeshName,
    firstMeshWorldPosition: childReport.firstMeshWorldPosition,
    firstMeshWorldScale: childReport.firstMeshWorldScale,
    sceneUuid: childReport.sceneUuid,
    sourceVersion: reportSourceVersion ?? null,
  };
}
