#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const input = process.argv[2];

if (!input) {
  console.error("Usage: npm run closy:avatar-audit -- assets/models/avatar/default-stylised-avatar.glb");
  process.exit(2);
}

const GLB_JSON_CHUNK = 0x4e4f534a;
const GLB_BIN_CHUNK = 0x004e4942;
const COMPONENT_BYTES = new Map([
  [5120, 1],
  [5121, 1],
  [5122, 2],
  [5123, 2],
  [5125, 4],
  [5126, 4],
]);
const TYPE_COMPONENTS = new Map([
  ["SCALAR", 1],
  ["VEC2", 2],
  ["VEC3", 3],
  ["VEC4", 4],
  ["MAT2", 4],
  ["MAT3", 9],
  ["MAT4", 16],
]);
const HUMANOID_PATTERNS = [
  /hips?|pelvis|root/i,
  /spine/i,
  /chest|torso/i,
  /neck/i,
  /head/i,
  /shoulder/i,
  /upperarm|arm.*upper|leftarm|rightarm/i,
  /lowerarm|forearm/i,
  /hand|wrist/i,
  /upperleg|thigh/i,
  /lowerleg|shin|calf/i,
  /foot|ankle/i,
  /toe/i,
];

function readGlb(filePath) {
  const bytes = fs.readFileSync(filePath);
  if (bytes.length < 20) throw new Error("malformed_glb_too_small");
  const magic = bytes.readUInt32LE(0);
  const version = bytes.readUInt32LE(4);
  const totalLength = bytes.readUInt32LE(8);
  if (magic !== 0x46546c67) throw new Error("malformed_glb_bad_magic");
  if (version !== 2) throw new Error(`unsupported_glb_version_${version}`);
  if (totalLength !== bytes.length) {
    throw new Error(`malformed_glb_length_mismatch_header_${totalLength}_actual_${bytes.length}`);
  }

  let offset = 12;
  let json = null;
  let binary = null;
  while (offset + 8 <= bytes.length) {
    const chunkLength = bytes.readUInt32LE(offset);
    const chunkType = bytes.readUInt32LE(offset + 4);
    const start = offset + 8;
    const end = start + chunkLength;
    if (end > bytes.length) throw new Error("malformed_glb_chunk_out_of_range");
    const chunk = bytes.subarray(start, end);
    if (chunkType === GLB_JSON_CHUNK) {
      json = JSON.parse(chunk.toString("utf8").replace(/\0+$/g, "").trim());
    } else if (chunkType === GLB_BIN_CHUNK) {
      binary = chunk;
    }
    offset = end;
  }
  if (!json) throw new Error("malformed_glb_missing_json_chunk");
  return { fileSize: bytes.length, json, binary };
}

function accessorByteSize(accessor) {
  const componentBytes = COMPONENT_BYTES.get(accessor.componentType);
  const componentCount = TYPE_COMPONENTS.get(accessor.type);
  if (!componentBytes || !componentCount) return null;
  return componentBytes * componentCount;
}

function validateAccessor(gltf, accessorIndex, binary, errors) {
  const accessor = gltf.accessors?.[accessorIndex];
  if (!accessor) {
    errors.push(`missing_accessor_${accessorIndex}`);
    return null;
  }
  if (accessor.sparse) {
    errors.push(`sparse_accessor_not_supported_${accessorIndex}`);
  }
  const byteSize = accessorByteSize(accessor);
  if (!byteSize) {
    errors.push(`unsupported_accessor_type_${accessorIndex}`);
    return null;
  }
  const bufferView = accessor.bufferView == null ? null : gltf.bufferViews?.[accessor.bufferView];
  if (!bufferView) {
    errors.push(`missing_buffer_view_for_accessor_${accessorIndex}`);
    return null;
  }
  const buffer = gltf.buffers?.[bufferView.buffer ?? 0];
  if (!buffer) {
    errors.push(`missing_buffer_for_accessor_${accessorIndex}`);
    return null;
  }
  if (!binary && !buffer.uri) {
    errors.push(`missing_binary_chunk_for_accessor_${accessorIndex}`);
    return null;
  }
  if (bufferView.buffer !== 0 && !buffer.uri) {
    errors.push(`unsupported_nonzero_binary_buffer_${bufferView.buffer}_for_accessor_${accessorIndex}`);
    return null;
  }
  const stride = bufferView.byteStride ?? byteSize;
  if (stride < byteSize) {
    errors.push(`invalid_stride_for_accessor_${accessorIndex}`);
    return null;
  }
  const start = (bufferView.byteOffset ?? 0) + (accessor.byteOffset ?? 0);
  const lastByte = start + stride * Math.max(0, accessor.count - 1) + byteSize;
  if (binary && lastByte > binary.byteLength) {
    errors.push(`accessor_${accessorIndex}_out_of_binary_range`);
    return null;
  }
  if (!Number.isFinite(accessor.count) || accessor.count <= 0) {
    errors.push(`accessor_${accessorIndex}_has_invalid_count`);
    return null;
  }
  return { accessor, bufferView, byteSize, stride, start };
}

function accessorMinMax(gltf, accessorIndex, binary, errors) {
  const validated = validateAccessor(gltf, accessorIndex, binary, errors);
  if (!validated) return null;
  const { accessor, stride, start } = validated;
  if (
    Array.isArray(accessor.min) &&
    Array.isArray(accessor.max) &&
    accessor.min.length >= 3 &&
    accessor.max.length >= 3
  ) {
    const min = accessor.min.slice(0, 3).map(Number);
    const max = accessor.max.slice(0, 3).map(Number);
    if (min.every(Number.isFinite) && max.every(Number.isFinite)) return { min, max };
  }
  if (accessor.componentType !== 5126 || accessor.type !== "VEC3" || !binary) {
    errors.push(`accessor_${accessorIndex}_missing_position_bounds`);
    return null;
  }
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < accessor.count; i += 1) {
    const base = start + i * stride;
    for (let c = 0; c < 3; c += 1) {
      const n = binary.readFloatLE(base + c * 4);
      if (!Number.isFinite(n)) {
        errors.push(`accessor_${accessorIndex}_has_nonfinite_position`);
        return null;
      }
      min[c] = Math.min(min[c], n);
      max[c] = Math.max(max[c], n);
    }
  }
  return { min, max };
}

function estimateTriangles(gltf, primitive, errors, binary) {
  const positionAccessor = primitive.attributes?.POSITION;
  if (positionAccessor == null) {
    errors.push("mesh_primitive_missing_POSITION_accessor");
    return 0;
  }
  validateAccessor(gltf, positionAccessor, binary, errors);
  const mode = primitive.mode ?? 4;
  const indexAccessor = primitive.indices == null ? null : gltf.accessors?.[primitive.indices];
  if (primitive.indices != null) validateAccessor(gltf, primitive.indices, binary, errors);
  const count = indexAccessor?.count ?? gltf.accessors?.[positionAccessor]?.count ?? 0;
  if (mode === 4) return Math.floor(count / 3);
  if (mode === 5 || mode === 6) return Math.max(0, count - 2);
  return 0;
}

function combineBounds(bounds, next) {
  if (!next) return bounds;
  if (!bounds) return { min: [...next.min], max: [...next.max] };
  for (let i = 0; i < 3; i += 1) {
    bounds.min[i] = Math.min(bounds.min[i], next.min[i]);
    bounds.max[i] = Math.max(bounds.max[i], next.max[i]);
  }
  return bounds;
}

function detectHumanoidBones(gltf) {
  const nodeNames = (gltf.nodes ?? []).map((node) => node?.name).filter(Boolean);
  const matchedNames = nodeNames.filter((name) =>
    HUMANOID_PATTERNS.some((pattern) => pattern.test(name)),
  );
  const lower = matchedNames.join(" ").toLowerCase();
  const likelyRigProfile =
    lower.includes("mixamo") || lower.includes("mixamorig")
      ? "mixamo"
      : lower.includes("vrm") || lower.includes("j_bip")
        ? "vrm"
        : lower.includes("rpm") || lower.includes("wolf3d")
          ? "readyplayerme"
          : matchedNames.length >= 8
            ? "custom"
            : "unknown";
  return { matchedNames, likelyRigProfile };
}

function audit(filePath) {
  const absolute = path.resolve(filePath);
  const errors = [];
  const warnings = [];
  const { fileSize, json: gltf, binary } = readGlb(absolute);
  if (gltf.asset?.version !== "2.0") errors.push(`invalid_gltf_version_${gltf.asset?.version ?? "missing"}`);
  if (!binary) warnings.push("missing_binary_chunk_external_buffers_not_loaded_by_this_audit");

  let meshCount = 0;
  let primitiveCount = 0;
  let triangleEstimate = 0;
  let bounds = null;
  for (const mesh of gltf.meshes ?? []) {
    meshCount += 1;
    for (const primitive of mesh.primitives ?? []) {
      primitiveCount += 1;
      triangleEstimate += estimateTriangles(gltf, primitive, errors, binary);
      const positionAccessor = primitive.attributes?.POSITION;
      if (positionAccessor != null) {
        bounds = combineBounds(bounds, accessorMinMax(gltf, positionAccessor, binary, errors));
      }
    }
  }

  for (let i = 0; i < (gltf.accessors ?? []).length; i += 1) {
    validateAccessor(gltf, i, binary, errors);
  }

  const size = bounds
    ? [
        bounds.max[0] - bounds.min[0],
        bounds.max[1] - bounds.min[1],
        bounds.max[2] - bounds.min[2],
      ]
    : null;
  if (!bounds || !size || !size.every(Number.isFinite) || !size.some((n) => Math.abs(n) > 1e-8)) {
    errors.push("non_finite_or_zero_bounds");
  }

  const skins = gltf.skins ?? [];
  const jointCount = skins.reduce((sum, skin) => sum + (skin.joints?.length ?? 0), 0);
  const { matchedNames, likelyRigProfile } = detectHumanoidBones(gltf);
  const materialCount = gltf.materials?.length ?? 0;
  const textureCount = gltf.textures?.length ?? 0;
  const imageCount = gltf.images?.length ?? 0;
  const animationCount = gltf.animations?.length ?? 0;
  const materialNames = (gltf.materials ?? []).map((material, index) => material.name ?? `material_${index}`);

  if (meshCount <= 0) errors.push("zero_meshes");
  if (primitiveCount <= 0) errors.push("zero_mesh_primitives");
  if (triangleEstimate <= 0) errors.push("zero_renderable_geometry");
  if (triangleEstimate > 70_000) warnings.push("triangle_estimate_exceeds_70000_mobile_budget");
  if (jointCount > 96) warnings.push("joint_count_exceeds_96_mobile_budget");
  if (materialCount > 12) warnings.push("material_count_exceeds_12_draw_call_budget");

  const report = {
    file: absolute,
    validGlb20: gltf.asset?.version === "2.0",
    fileSize,
    sceneCount: gltf.scenes?.length ?? 0,
    nodeCount: gltf.nodes?.length ?? 0,
    meshCount,
    primitiveCount,
    triangleEstimate,
    skinCount: skins.length,
    jointCount,
    animationCount,
    materialCount,
    materialNames,
    textureCount,
    imageCount,
    accessorCount: gltf.accessors?.length ?? 0,
    bufferCount: gltf.buffers?.length ?? 0,
    bufferViewCount: gltf.bufferViews?.length ?? 0,
    bounds: bounds
      ? {
          min: bounds.min,
          max: bounds.max,
          size,
        }
      : null,
    detectedHumanoidBoneNames: matchedNames,
    likelyRigProfile,
    mobileBudgetWarnings: warnings,
    fatalValidationErrors: [...new Set(errors)],
    valid: errors.length === 0,
  };

  return report;
}

try {
  const report = audit(input);
  console.log("Closy Avatar GLB Audit");
  console.log(`file: ${report.file}`);
  console.log(`valid: ${report.valid ? "yes" : "no"}`);
  console.log(
    `meshes=${report.meshCount} primitives=${report.primitiveCount} tris=${report.triangleEstimate} skins=${report.skinCount} joints=${report.jointCount} animations=${report.animationCount}`,
  );
  console.log(
    `materials=${report.materialCount} textures=${report.textureCount} images=${report.imageCount} rig=${report.likelyRigProfile}`,
  );
  if (report.bounds) console.log(`bounds.size=${report.bounds.size.map((n) => n.toFixed(4)).join(",")}`);
  if (report.mobileBudgetWarnings.length) console.log(`warnings=${report.mobileBudgetWarnings.join(",")}`);
  if (report.fatalValidationErrors.length) console.error(`errors=${report.fatalValidationErrors.join(",")}`);
  console.log(JSON.stringify(report, null, 2));
  process.exit(report.valid ? 0 : 1);
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  console.error(JSON.stringify({ valid: false, fatalValidationErrors: [message] }, null, 2));
  process.exit(1);
}
