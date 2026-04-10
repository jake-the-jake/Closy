/**
 * Live garment pipeline (reads shared `GarmentFitState` only):
 *
 * 1. **Base placement** — Anchor groups (`garment_top_anchor`, `garment_bottom_anchor`, arm binds),
 *    canonical procedural layout, GLTF height normalization on load.
 * 2. **Global fit transform** — Parent `avatar_world_fit` translation + scale
 *    (`global.offset`, `global.scale`, `global.inflate` amplification).
 * 3. **Region-aware deformation** — This module: per-vertex displacement from smooth masks
 *    (torso / sleeves / waist / hem) in **mesh local space** after 1–2, so shape adapts without
 *    only sliding the whole mesh.
 * 4. **Live shading** — `applyLiveShadingToGltfMaterials` (opacity/tint), separate from geometry.
 *
 * No cloth physics; CPU vertex push with rest-pose caching. Suitable for dev/mobile first pass.
 */

import * as THREE from "three";

import type { GarmentFitState } from "@/features/avatar-export";

const _v = new THREE.Vector3();
const _box = new THREE.Box3();

export type GarmentDeformProfile = "top" | "bottom" | "sleeve";

type GeoRest = {
  positions: Float32Array;
  min: THREE.Vector3;
  max: THREE.Vector3;
  size: THREE.Vector3;
};

const restCache = new WeakMap<THREE.BufferGeometry, GeoRest>();

function smoothstep(edge0: number, edge1: number, x: number): number {
  const t = Math.max(0, Math.min(1, (x - edge0) / (edge1 - edge0 + 1e-8)));
  return t * t * (3 - 2 * t);
}

export function getOrCaptureGarmentRest(geometry: THREE.BufferGeometry): GeoRest {
  let cached = restCache.get(geometry);
  if (cached) return cached;

  const attr = geometry.attributes.position;
  const src = attr.array as Float32Array;
  const positions = new Float32Array(src.length);
  positions.set(src);

  _box.makeEmpty();
  for (let i = 0; i < positions.length; i += 3) {
    _v.set(positions[i], positions[i + 1], positions[i + 2]);
    _box.expandByPoint(_v);
  }

  const min = _box.min.clone();
  const max = _box.max.clone();
  const size = new THREE.Vector3().subVectors(max, min);
  cached = { positions, min, max, size };
  restCache.set(geometry, cached);
  return cached;
}

/** Clear rest cache if geometry is replaced (e.g. hot reload). Rare. */
export function forgetGarmentRest(geometry: THREE.BufferGeometry) {
  restCache.delete(geometry);
}

/**
 * Apply regional displacement for shirts / tops in local space.
 * Torso band: center column, mid–upper height. Sleeves: high + wide. Hem: low. Waist-ish: transition.
 */
export function applyTopGarmentDeformation(
  geometry: THREE.BufferGeometry,
  fit: GarmentFitState,
) {
  const rest = getOrCaptureGarmentRest(geometry);
  const pos = geometry.attributes.position.array as Float32Array;
  const { positions: bases, min, max, size } = rest;

  const cx = (min.x + max.x) * 0.5;
  const cz = (min.z + max.z) * 0.5;
  const sy = Math.max(size.y, 1e-6);
  const sx = Math.max(size.x, 1e-6);

  const r = fit.regions;
  const g = fit.global;

  for (let i = 0; i < pos.length; i += 3) {
    const ox = bases[i];
    const oy = bases[i + 1];
    const oz = bases[i + 2];

    const ny = (oy - min.y) / sy;
    const ax = Math.abs(ox - cx) / (sx * 0.5 + 1e-6);

    const wTorsoCore =
      (1 - smoothstep(0.22, 0.55, ax)) *
      smoothstep(0.18, 0.42, ny) *
      (1 - smoothstep(0.72, 0.96, ny));

    const wSleeve =
      smoothstep(0.28, 0.55, ax) * smoothstep(0.38, 0.62, ny) * (1 - smoothstep(0.78, 0.98, ny));

    const wHem = (1 - smoothstep(0.1, 0.32, ny)) * (0.55 + 0.45 * (1 - smoothstep(0.2, 0.45, ax)));

    const wUpperChest = wTorsoCore * smoothstep(0.45, 0.75, ny);

    let dx = 0;
    let dy = 0;
    let dz = 0;

    const torsoPushZ = r.torso.offsetZ * sy * 1.15;
    const torsoBulge = r.torso.inflate * Math.max(size.x, size.z) * 0.55;
    const torsoStretchY = (r.torso.scaleY - 1) * sy * 0.35 * wTorsoCore;

    dz += torsoPushZ * wTorsoCore * 0.85;
    dz += torsoPushZ * 0.35 * wUpperChest;

    const radXZ = Math.hypot(ox - cx, oz - cz);
    if (radXZ > 1e-6) {
      const k = torsoBulge / radXZ;
      dx += (ox - cx) * k * wTorsoCore;
      dz += (oz - cz) * k * wTorsoCore;
    }

    dy += torsoStretchY * (ny - 0.5) * 2 * wTorsoCore;

    const sleeveInf = r.sleeves.inflate * sy * 0.75;
    if (radXZ > 1e-6) {
      const sk = sleeveInf / radXZ;
      dx += (ox - cx) * sk * wSleeve;
      dz += (oz - cz) * sk * wSleeve;
    }
    dx += r.sleeves.offset[0] * sy * 1.1 * wSleeve;
    dy += (r.sleeves.offset[1] + fit.legacy.sleeveOffsetY * 0.5) * sy * 1.1 * wSleeve;
    dz += r.sleeves.offset[2] * sy * 1.1 * wSleeve;

    dy += r.hem.offsetY * sy * 1.2 * wHem;

    const gInfl = g.inflate * Math.max(size.x, size.z, sy) * 0.22;
    if (radXZ > 1e-6) {
      const gk = gInfl / radXZ;
      dx += (ox - cx) * gk;
      dz += (oz - cz) * gk;
    }
    dy += g.inflate * sy * 0.12 * (ny - 0.5) * 2;

    pos[i] = ox + dx;
    pos[i + 1] = oy + dy;
    pos[i + 2] = oz + dz;
  }

  geometry.attributes.position.needsUpdate = true;
  geometry.computeVertexNormals();
}

/** Pants / shorts: waist band (mid height), legs (low), hem at very bottom. */
export function applyBottomGarmentDeformation(
  geometry: THREE.BufferGeometry,
  fit: GarmentFitState,
) {
  const rest = getOrCaptureGarmentRest(geometry);
  const pos = geometry.attributes.position.array as Float32Array;
  const { positions: bases, min, max, size } = rest;

  const cx = (min.x + max.x) * 0.5;
  const cz = (min.z + max.z) * 0.5;
  const sy = Math.max(size.y, 1e-6);

  const r = fit.regions;
  const g = fit.global;

  for (let i = 0; i < pos.length; i += 3) {
    const ox = bases[i];
    const oy = bases[i + 1];
    const oz = bases[i + 2];

    const ny = (oy - min.y) / sy;
    const radXZ = Math.hypot(ox - cx, oz - cz);

    const wWaist =
      smoothstep(0.45, 0.58, ny) * (1 - smoothstep(0.58, 0.72, ny));

    const wLeg = smoothstep(0.15, 0.45, ny) * (1 - smoothstep(0.65, 0.92, ny));

    const wHem = 1 - smoothstep(0.05, 0.22, ny);

    let dx = 0;
    let dy = 0;
    let dz = 0;

    const tighten = r.waist.tighten;
    if (radXZ > 1e-6) {
      const pinch = tighten * 0.55 * wWaist;
      dx -= ((ox - cx) / radXZ) * pinch * Math.max(size.x, size.z) * 0.35;
      dz -= ((oz - cz) / radXZ) * pinch * Math.max(size.z, size.x) * 0.35;
    }

    dz += r.waist.offsetZ * sy * 0.9 * (wWaist * 0.7 + wLeg * 0.35);

    dy += (fit.legacy.waistAdjustY * sy * 0.8 + r.hem.offsetY * sy * 1.25) * wLeg;
    dy += r.hem.offsetY * sy * 1.4 * wHem;

    const gInfl = g.inflate * Math.max(size.x, size.z, sy) * 0.18;
    if (radXZ > 1e-6) {
      const gk = gInfl / radXZ;
      dx += (ox - cx) * gk * (wLeg + wWaist * 0.5);
      dz += (oz - cz) * gk * (wLeg + wWaist * 0.5);
    }

    pos[i] = ox + dx;
    pos[i + 1] = oy + dy;
    pos[i + 2] = oz + dz;
  }

  geometry.attributes.position.needsUpdate = true;
  geometry.computeVertexNormals();
}

/** Sleeve capsule: emphasize radial inflate and Z offset along arm-ish X axis. */
export function applySleeveGarmentDeformation(
  geometry: THREE.BufferGeometry,
  fit: GarmentFitState,
) {
  const rest = getOrCaptureGarmentRest(geometry);
  const pos = geometry.attributes.position.array as Float32Array;
  const { positions: bases, min, max, size } = rest;

  const cy = (min.y + max.y) * 0.5;
  const cz = (min.z + max.z) * 0.5;
  const sx = Math.max(size.x, 1e-6);
  const sy = Math.max(size.y, 1e-6);

  const r = fit.regions;

  for (let i = 0; i < pos.length; i += 3) {
    const ox = bases[i];
    const oy = bases[i + 1];
    const oz = bases[i + 2];

    const tArm = Math.abs(ox - (min.x + max.x) * 0.5) / (sx * 0.5 + 1e-6);
    const ny = (oy - min.y) / sy;

    const w = smoothstep(0.15, 0.85, tArm) * smoothstep(0.1, 0.9, ny);

    const radYZ = Math.hypot(oy - cy, oz - cz);
    let dx = 0;
    let dy = 0;
    let dz = 0;

    const inf = r.sleeves.inflate * Math.max(size.y, size.z) * 0.65;
    if (radYZ > 1e-6) {
      const k = (inf / radYZ) * w;
      dy += (oy - cy) * k;
      dz += (oz - cz) * k;
    }

    dx +=
      (Math.sign(ox - (min.x + max.x) * 0.5) || 1) *
      r.sleeves.offset[0] *
      sy *
      0.9 *
      w;
    dy += r.sleeves.offset[1] * sy * 0.9 * w;
    dz += r.sleeves.offset[2] * sy * 0.9 * w;

    pos[i] = ox + dx;
    pos[i + 1] = oy + dy;
    pos[i + 2] = oz + dz;
  }

  geometry.attributes.position.needsUpdate = true;
  geometry.computeVertexNormals();
}

export function applyGarmentDeformationForProfile(
  geometry: THREE.BufferGeometry,
  fit: GarmentFitState,
  profile: GarmentDeformProfile,
) {
  switch (profile) {
    case "top":
      applyTopGarmentDeformation(geometry, fit);
      break;
    case "bottom":
      applyBottomGarmentDeformation(geometry, fit);
      break;
    case "sleeve":
      applySleeveGarmentDeformation(geometry, fit);
      break;
    default:
      break;
  }
}

/** Traverse and deform every mesh under `root` with the same profile (typical GLB). */
export function deformGarmentObject3D(
  root: THREE.Object3D,
  fit: GarmentFitState,
  profile: GarmentDeformProfile,
) {
  root.updateMatrixWorld(true);
  root.traverse((o) => {
    if (!(o instanceof THREE.Mesh) || !o.geometry) return;
    const g = o.geometry;
    if (!g.attributes?.position) return;
    applyGarmentDeformationForProfile(g, fit, profile);
  });
}

export function deformationSummary(profile: GarmentDeformProfile): string {
  switch (profile) {
    case "top":
      return "torso+sleeve+hem masks (local)";
    case "bottom":
      return "waist+leg+hem masks (local)";
    case "sleeve":
      return "sleeve radial+offset (local)";
    default:
      return "off";
  }
}
