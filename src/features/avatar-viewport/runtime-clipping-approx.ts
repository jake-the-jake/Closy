/**
 * Lightweight runtime clipping **approximation** for the live viewport.
 * Uses analytic sphere/sphere penetration in world space, with transforms that mirror
 * `avatar-procedural-scene.tsx` (same anchors + FIT_VIS). Not physical collision.
 *
 * When a runtime body GLB is used, body proxies are inflated slightly — mesh poses differ
 * but the signal stays directionally useful.
 *
 * Keep numeric rig constants in sync with `avatar-procedural-scene.tsx`.
 */

import * as THREE from "three";

import type { GarmentFitState } from "@/features/avatar-export";
import type { DevAvatarPoseKey } from "@/features/avatar-export/dev-avatar-shared";

/** Same as `AVATAR_RIG_ANCHORS` in `avatar-procedural-scene.tsx` — keep in sync. */
const RIG = {
  pelvisY: 0.98,
  chestY: 1.15,
  shoulderY: 1.34,
  shoulderHalf: 0.188,
  headY: 1.52,
  pantsProxyHemY: 0.56,
  gltfTopMountY: 1.12,
} as const;

export type RuntimeClipSeverity = "clear" | "near" | "clip";

export type RuntimeClipRegion = {
  severity: RuntimeClipSeverity;
  /** Sphere-sphere style penetration (positive ≈ overlap depth, meters). */
  penetration: number;
};

export type RuntimeClippingReport = {
  torso: RuntimeClipRegion;
  sleeves: RuntimeClipRegion;
  waist: RuntimeClipRegion;
  hem: RuntimeClipRegion;
};

export type RuntimeClippingAnalyzeInput = {
  garmentFit: GarmentFitState;
  pose: DevAvatarPoseKey;
  hasRuntimeBodyGltf: boolean;
  hasRuntimeTopGltf: boolean;
  hasRuntimeBottomGltf: boolean;
};

/** Mirror `avatar-procedural-scene` FIT_VIS — update together. */
const FIT_VIS = {
  torsoOffsetZ: 3.4,
  torsoOffsetY: 0.42,
  torsoInflateMul: 3.2,
  torsoInflateYMul: 1.35,
  waistOffsetZ: 2.6,
  sleevePosMul: 1.75,
  globalGarmentInflate: 1.85,
} as const;

function poseAngles(pose: DevAvatarPoseKey) {
  switch (pose) {
    case "relaxed":
      return {
        laz: 0.12,
        raz: -0.12,
        lax: 0.48,
        rax: 0.48,
        laxz: 0.02,
        llx: 0.04,
        rlx: -0.06,
      };
    case "walk":
      return {
        laz: 0.38,
        raz: -0.38,
        lax: 0.36,
        rax: 0.36,
        laxz: 0.1,
        llx: 0.28,
        rlx: -0.32,
      };
    case "tpose":
      return {
        laz: 1.38,
        raz: -1.38,
        lax: 0,
        rax: 0,
        laxz: 0,
        llx: 0,
        rlx: 0,
      };
    case "apose":
      return {
        laz: 0.55,
        raz: -0.55,
        lax: 0,
        rax: 0,
        laxz: 0,
        llx: 0,
        rlx: 0,
      };
    default:
      return { laz: 0, raz: 0, lax: 0, rax: 0, laxz: 0, llx: 0, rlx: 0 };
  }
}

const _v = new THREE.Vector3();
const _e = new THREE.Euler();
const _q = new THREE.Quaternion();
const _s = new THREE.Vector3();

function matComp(
  pos: [number, number, number],
  scale: [number, number, number],
): THREE.Matrix4 {
  _v.set(...pos);
  _q.identity();
  _s.set(...scale);
  return new THREE.Matrix4().compose(_v, _q, _s);
}

function matT(x: number, y: number, z: number): THREE.Matrix4 {
  return new THREE.Matrix4().makeTranslation(x, y, z);
}

function matRx(rx: number): THREE.Matrix4 {
  return new THREE.Matrix4().makeRotationX(rx);
}

function matRz(rz: number): THREE.Matrix4 {
  return new THREE.Matrix4().makeRotationZ(rz);
}

function transformPoint(m: THREE.Matrix4, x: number, y: number, z: number): THREE.Vector3 {
  return _v.set(x, y, z).applyMatrix4(m);
}

function spherePenetration(
  ax: number,
  ay: number,
  az: number,
  ar: number,
  bx: number,
  by: number,
  bz: number,
  br: number,
): number {
  const dx = ax - bx;
  const dy = ay - by;
  const dz = az - bz;
  const d = Math.sqrt(dx * dx + dy * dy + dz * dz);
  return ar + br - d;
}

function severity(pen: number): RuntimeClipSeverity {
  if (pen > 0.017) return "clip";
  if (pen > -0.014) return "near";
  return "clear";
}

/**
 * Analyze likely body↔garment interference using proxy spheres (world space).
 */
export function analyzeRuntimeClipping(input: RuntimeClippingAnalyzeInput): RuntimeClippingReport {
  const { garmentFit: fit, pose } = input;
  const g = fit.global;
  const r = fit.regions;
  const ang = poseAngles(pose);
  const { pelvisY, chestY, shoulderY, shoulderHalf, pantsProxyHemY, gltfTopMountY } =
    RIG;

  const inf = g.inflate;
  const inflVis = inf * FIT_VIS.globalGarmentInflate;
  const gsx = g.scale[0] + inflVis;
  const gsy = g.scale[1] + inflVis;
  const gsz = g.scale[2] + inflVis;

  const tz = r.torso.offsetZ;
  const worldOff: [number, number, number] = [
    g.offset[0],
    g.offset[1] + fit.legacy.bodyOffsetBias,
    g.offset[2],
  ];
  const bodyAnchorPos: [number, number, number] = [
    0,
    tz * FIT_VIS.torsoOffsetY,
    tz * FIT_VIS.torsoOffsetZ,
  ];
  const bodyAnchorScale: [number, number, number] = [
    1 + r.torso.inflate * FIT_VIS.torsoInflateMul,
    r.torso.scaleY * (1 + r.torso.inflate * FIT_VIS.torsoInflateYMul),
    1 + r.torso.inflate * FIT_VIS.torsoInflateMul,
  ];

  const shirtInfl = 1 + r.torso.inflate * 2.2;
  const topAnchorPos: [number, number, number] = [0, tz * 0.18, tz * 0.35];
  const topAnchorScale: [number, number, number] = [
    shirtInfl,
    1 + r.torso.inflate * 1.2,
    shirtInfl,
  ];

  const mWorld = matComp(worldOff, [gsx, gsy, gsz]);
  const mTorsoFit = matComp(bodyAnchorPos, bodyAnchorScale);
  const mBody = new THREE.Matrix4().multiplyMatrices(mWorld, mTorsoFit);

  const bodyBias = input.hasRuntimeBodyGltf ? 1.07 : 1;

  const mTopAnchor = matComp(topAnchorPos, topAnchorScale);

  /** Shirt / top garment sphere center (in top-anchor space, then world). */
  let mShirtLocal: THREE.Matrix4;
  let shirtR: number;
  if (input.hasRuntimeTopGltf) {
    const mMount = matT(0, gltfTopMountY, 0);
    mShirtLocal = new THREE.Matrix4().multiplyMatrices(mMount, matT(0, 0.21, 0));
    shirtR = 0.26;
  } else {
    const inflateK = 1.02 + r.torso.inflate;
    mShirtLocal = matT(0, chestY, 0);
    const hx = 0.24 * inflateK;
    const hy = 0.18 * inflateK;
    const hz = 0.15 * inflateK;
    shirtR = 0.45 * Math.sqrt(hx * hx + hy * hy + hz * hz);
  }

  const mGarmentTopChain = new THREE.Matrix4()
    .multiplyMatrices(mBody, mTopAnchor)
    .multiply(mShirtLocal);
  const torsoBody = transformPoint(mBody, 0, chestY, 0);
  const torsoBodyR = 0.162 * bodyBias;
  const shirtC = transformPoint(mGarmentTopChain, 0, 0, 0);
  const penTorso = spherePenetration(
    torsoBody.x,
    torsoBody.y,
    torsoBody.z,
    torsoBodyR,
    shirtC.x,
    shirtC.y,
    shirtC.z,
    shirtR,
  );

  const sleeveS = 1 + r.sleeves.inflate * 2.8;
  const sleevePos = [
    r.sleeves.offset[0],
    r.sleeves.offset[1] + fit.legacy.sleeveOffsetY,
    r.sleeves.offset[2],
  ] as const;
  const spx = sleevePos[0] * FIT_VIS.sleevePosMul;
  const spy = sleevePos[1] * FIT_VIS.sleevePosMul;
  const spz = sleevePos[2] * FIT_VIS.sleevePosMul;

  function armBindMatrix(side: 1 | -1): THREE.Matrix4 {
    const laxz = side * ang.laxz;
    const laz = side === 1 ? ang.laz : ang.raz;
    const lax = side === 1 ? ang.lax : -ang.rax;
    const mShoulder = matComp([shoulderHalf * side, shoulderY, 0], [1, 1, 1]);
    const mA = new THREE.Matrix4().multiplyMatrices(matRz(laxz), matRz(laz));
    const mUpper = matRz(lax);
    const mSp = matComp([spx * side, spy, spz], [sleeveS, sleeveS, sleeveS]);
    return new THREE.Matrix4()
      .multiplyMatrices(mShoulder, mA)
      .multiply(mUpper)
      .multiply(mSp);
  }

  const mArmL = new THREE.Matrix4().multiplyMatrices(mBody, armBindMatrix(1));
  const mArmR = new THREE.Matrix4().multiplyMatrices(mBody, armBindMatrix(-1));

  const gSleeveR = 0.075 * sleeveS + 0.11;
  const sleeveOffY = -0.04 + spy * 0.25;
  const sleeveOffZ = spz * 0.3;

  const slCentL = transformPoint(mArmL, 0.15, sleeveOffY, sleeveOffZ);
  const slCentR = transformPoint(mArmR, -0.15, sleeveOffY, sleeveOffZ);

  const armBodyL = transformPoint(mArmL, 0.14, -0.14, 0);
  const armBodyR = transformPoint(mArmR, -0.14, -0.14, 0);
  const armBodyRrad = 0.098 * bodyBias;

  let penSleeve =
    input.hasRuntimeTopGltf
      ? Math.max(
          spherePenetration(
            armBodyL.x,
            armBodyL.y,
            armBodyL.z,
            armBodyRrad,
            shirtC.x,
            shirtC.y,
            shirtC.z,
            shirtR * 0.92,
          ),
          spherePenetration(
            armBodyR.x,
            armBodyR.y,
            armBodyR.z,
            armBodyRrad,
            shirtC.x,
            shirtC.y,
            shirtC.z,
            shirtR * 0.92,
          ),
        )
      : Math.max(
          spherePenetration(
            armBodyL.x,
            armBodyL.y,
            armBodyL.z,
            armBodyRrad,
            slCentL.x,
            slCentL.y,
            slCentL.z,
            gSleeveR,
          ),
          spherePenetration(
            armBodyR.x,
            armBodyR.y,
            armBodyR.z,
            armBodyRrad,
            slCentR.x,
            slCentR.y,
            slCentR.z,
            gSleeveR,
          ),
        );

  const waistAdjY = fit.legacy.waistAdjustY;
  const waistZ = r.waist.offsetZ * FIT_VIS.waistOffsetZ;
  const waistScale: [number, number, number] = [
    1 - r.waist.tighten * 0.48,
    1 - r.waist.tighten * 0.32,
    1 - r.waist.tighten * 0.26,
  ];
  const mBottomAnchor = matComp([0, waistAdjY, waistZ], waistScale);
  const mBottom = new THREE.Matrix4().multiplyMatrices(mBody, mBottomAnchor);

  const hemY = r.hem.offsetY;
  const pelvisC = transformPoint(mBody, 0, pelvisY, 0);
  const pelvisR = 0.154 * bodyBias;

  const pantsHipC = transformPoint(mBottom, 0, pantsProxyHemY + hemY, 0);
  const pantsHipR = 0.198;
  const penWaist = spherePenetration(
    pelvisC.x,
    pelvisC.y,
    pelvisC.z,
    pelvisR,
    pantsHipC.x,
    pantsHipC.y,
    pantsHipC.z,
    pantsHipR,
  );

  const legGy = pantsProxyHemY - 0.34 + hemY;
  const legGarR = 0.118;
  const mPelvis = matT(0, pelvisY, 0);
  const mLegBindL = new THREE.Matrix4()
    .multiplyMatrices(matT(0.075, -0.06, 0), matRx(ang.llx))
    .multiply(matT(0.02, -0.2, 0));
  const mLegBindR = new THREE.Matrix4()
    .multiplyMatrices(matT(-0.075, -0.06, 0), matRx(ang.rlx))
    .multiply(matT(-0.02, -0.2, 0));
  const mLegLW = new THREE.Matrix4().multiplyMatrices(mBody, mPelvis).multiply(mLegBindL);
  const mLegRW = new THREE.Matrix4().multiplyMatrices(mBody, mPelvis).multiply(mLegBindR);
  const legBodyLy = transformPoint(mLegLW, 0, 0, 0);
  const legBodyRy = transformPoint(mLegRW, 0, 0, 0);
  const legBodyRrad = 0.104 * bodyBias;
  const gLegL = transformPoint(mBottom, 0.09, legGy, 0);
  const gLegR = transformPoint(mBottom, -0.09, legGy, 0);

  const penHemL = spherePenetration(
    legBodyLy.x,
    legBodyLy.y,
    legBodyLy.z,
    legBodyRrad,
    gLegL.x,
    gLegL.y,
    gLegL.z,
    legGarR,
  );
  const penHemR = spherePenetration(
    legBodyRy.x,
    legBodyRy.y,
    legBodyRy.z,
    legBodyRrad,
    gLegR.x,
    gLegR.y,
    gLegR.z,
    legGarR,
  );
  const penHem = Math.max(penHemL, penHemR);

  return {
    torso: { severity: severity(penTorso), penetration: penTorso },
    sleeves: { severity: severity(penSleeve), penetration: penSleeve },
    waist: { severity: severity(penWaist), penetration: penWaist },
    hem: { severity: severity(penHem), penetration: penHem },
  };
}

export function worstGarmentClipSeverity(
  a: RuntimeClipSeverity,
  b: RuntimeClipSeverity,
): RuntimeClipSeverity {
  const order: Record<RuntimeClipSeverity, number> = { clear: 0, near: 1, clip: 2 };
  return order[a] >= order[b] ? a : b;
}

export function clipSeverityToEmissive(
  severity: RuntimeClipSeverity,
): THREE.Color {
  switch (severity) {
    case "clip":
      return new THREE.Color(0.38, 0.1, 0.04);
    case "near":
      return new THREE.Color(0.18, 0.14, 0.02);
    default:
      return new THREE.Color(0, 0, 0);
  }
}
