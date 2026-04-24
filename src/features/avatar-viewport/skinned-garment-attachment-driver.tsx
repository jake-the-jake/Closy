import { useFrame } from "@react-three/fiber/native";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import type { RefObject } from "react";

import type { BodySceneAnchors } from "@/features/avatar-export";
import type { GarmentFitState } from "@/features/avatar-export";
import type { GarmentAttachmentSnapshot } from "./live-viewport-debug-types";
import {
  computeSkinnedGarmentAttachmentPoints,
  rigFallbackAttachmentPoints,
  type SkinnedGarmentAttachmentPoints,
} from "./skinned-garment-attachment";

/** Sit sleeves / torso / bottoms on posed bones (parent = `avatar_torso_region_fit`). */
const SLEEVE_Y_LOWER = -0.112;
const SLEEVE_Z_FORWARD = 0.008;
const TOP_CHEST_Y_LOWER = -0.17;
const TOP_CHEST_X_BLEND = 0.78;
const TOP_CHEST_Z_BLEND = 0.68;
const BOTTOM_PELVIS_Y_ADD = -0.064;
const BOTTOM_HIP_X_BLEND = 0.42;
const BOTTOM_WAIST_Z_BLEND = 0.56;

const SNAP_THROTTLE_MS = 240;

function v3a(v: THREE.Vector3): [number, number, number] {
  return [v.x, v.y, v.z];
}

function snapshotKey(s: GarmentAttachmentSnapshot): string {
  const f = (n: number) => (Math.round(n * 500) / 500).toFixed(3);
  const t = (p: [number, number, number]) => p.map(f).join(",");
  return [
    s.source,
    t(s.shoulderL),
    t(s.shoulderR),
    t(s.chest),
    t(s.pelvisTop),
    t(s.hipMid),
    t(s.topAnchor),
    t(s.bottomAnchor),
    t(s.leftSleevePivot),
    t(s.rightSleevePivot),
  ].join("|");
}

type Props = {
  enabled: boolean;
  rig: BodySceneAnchors;
  /** Torso region Z offset (same as `tz` in scene). */
  torsoOffsetZ: number;
  garmentFit: GarmentFitState;
  waistOffsetZVis: number;
  bodyRootRef: RefObject<THREE.Group | null>;
  torsoRegionFitRef: RefObject<THREE.Group | null>;
  leftSleevePivotRef: RefObject<THREE.Group | null>;
  rightSleevePivotRef: RefObject<THREE.Group | null>;
  leftSleeveBoneFollowRef?: RefObject<THREE.Group | null>;
  rightSleeveBoneFollowRef?: RefObject<THREE.Group | null>;
  topAnchorRef: RefObject<THREE.Group | null>;
  bottomAnchorRef: RefObject<THREE.Group | null>;
  showMarkers: boolean;
  markersGroupRef: RefObject<THREE.Group | null>;
  onAttachmentSnapshot?: (s: GarmentAttachmentSnapshot) => void;
};

export function SkinnedGarmentAttachmentDriver({
  enabled,
  rig,
  torsoOffsetZ,
  garmentFit,
  waistOffsetZVis,
  bodyRootRef,
  torsoRegionFitRef,
  leftSleevePivotRef,
  rightSleevePivotRef,
  leftSleeveBoneFollowRef,
  rightSleeveBoneFollowRef,
  topAnchorRef,
  bottomAnchorRef,
  showMarkers,
  markersGroupRef,
  onAttachmentSnapshot,
}: Props) {
  const tmp = useMemo(
    () => ({
      topPos: new THREE.Vector3(),
      botPos: new THREE.Vector3(),
      lSleeve: new THREE.Vector3(),
      rSleeve: new THREE.Vector3(),
      qBone: new THREE.Quaternion(),
      qParent: new THREE.Quaternion(),
      qRel: new THREE.Quaternion(),
      eRel: new THREE.Euler(0, 0, 0, "XYZ"),
    }),
    [],
  );
  const lastSource = useRef<GarmentAttachmentSnapshot["source"] | null>(null);
  const lastSnapKey = useRef("");
  const lastSnapEmitMs = useRef(0);

  useFrame(() => {
    if (!enabled) return;
    const parent = torsoRegionFitRef.current;
    const bodyRoot = bodyRootRef.current;
    if (!parent || !bodyRoot) return;

    const computed = computeSkinnedGarmentAttachmentPoints(parent, bodyRoot, rig);
    const source: GarmentAttachmentSnapshot["source"] = computed ? "skinned_bones" : "rig_fallback";
    const pts: SkinnedGarmentAttachmentPoints = computed
      ? computed.points
      : rigFallbackAttachmentPoints(rig);
    const bones = computed?.bones;

    const tz = torsoOffsetZ;
    const rigTopZ = tz * 0.35;

    const left = leftSleevePivotRef.current;
    if (left) {
      tmp.lSleeve.copy(pts.shoulderL);
      tmp.lSleeve.y += SLEEVE_Y_LOWER;
      tmp.lSleeve.z += SLEEVE_Z_FORWARD;
      left.position.copy(tmp.lSleeve);
    }
    const right = rightSleevePivotRef.current;
    if (right) {
      tmp.rSleeve.copy(pts.shoulderR);
      tmp.rSleeve.y += SLEEVE_Y_LOWER;
      tmp.rSleeve.z += SLEEVE_Z_FORWARD;
      right.position.copy(tmp.rSleeve);
    }

    const lf = leftSleeveBoneFollowRef?.current;
    const rf = rightSleeveBoneFollowRef?.current;
    if (bones && parent) {
      parent.updateMatrixWorld(true);
      if (lf && bones.armL_shoulder) {
        bones.armL_shoulder.updateWorldMatrix(true, false);
        bones.armL_shoulder.getWorldQuaternion(tmp.qBone);
        parent.getWorldQuaternion(tmp.qParent);
        tmp.qRel.copy(tmp.qParent).invert().multiply(tmp.qBone);
        tmp.eRel.setFromQuaternion(tmp.qRel);
        lf.rotation.set(tmp.eRel.x * 0.24, tmp.eRel.y * 0.14, tmp.eRel.z * 0.11);
      } else if (lf) {
        lf.rotation.set(0, 0, 0);
      }
      if (rf && bones.armR_shoulder) {
        bones.armR_shoulder.updateWorldMatrix(true, false);
        bones.armR_shoulder.getWorldQuaternion(tmp.qBone);
        parent.getWorldQuaternion(tmp.qParent);
        tmp.qRel.copy(tmp.qParent).invert().multiply(tmp.qBone);
        tmp.eRel.setFromQuaternion(tmp.qRel);
        rf.rotation.set(tmp.eRel.x * 0.24, tmp.eRel.y * 0.14, tmp.eRel.z * 0.11);
      } else if (rf) {
        rf.rotation.set(0, 0, 0);
      }
    } else {
      lf?.rotation.set(0, 0, 0);
      rf?.rotation.set(0, 0, 0);
    }

    const top = topAnchorRef.current;
    if (top) {
      tmp.topPos.set(
        THREE.MathUtils.lerp(0, pts.chest.x, TOP_CHEST_X_BLEND),
        pts.chest.y + TOP_CHEST_Y_LOWER,
        THREE.MathUtils.lerp(rigTopZ, pts.chest.z, TOP_CHEST_Z_BLEND),
      );
      top.position.copy(tmp.topPos);
    }

    const bot = bottomAnchorRef.current;
    if (bot) {
      const legacyY = garmentFit.legacy.waistAdjustY * 0.52;
      tmp.botPos.set(
        THREE.MathUtils.lerp(0, pts.hipMid.x, BOTTOM_HIP_X_BLEND),
        pts.pelvisTop.y + legacyY + BOTTOM_PELVIS_Y_ADD,
        THREE.MathUtils.lerp(waistOffsetZVis, pts.hipMid.z, BOTTOM_WAIST_Z_BLEND),
      );
      bot.position.copy(tmp.botPos);
    }

    const mg = markersGroupRef.current;
    if (mg && showMarkers) {
      mg.visible = true;
      const ch = mg.children;
      if (ch[0]) ch[0].position.copy(pts.shoulderL);
      if (ch[1]) ch[1].position.copy(pts.shoulderR);
      if (ch[2]) ch[2].position.copy(pts.chest);
      if (ch[3]) ch[3].position.copy(pts.pelvisTop);
      if (ch[4]) ch[4].position.copy(pts.hipMid);
    } else if (mg) {
      mg.visible = false;
    }

    if (!onAttachmentSnapshot) return;

    const snap: GarmentAttachmentSnapshot = {
      shoulderL: v3a(pts.shoulderL),
      shoulderR: v3a(pts.shoulderR),
      chest: v3a(pts.chest),
      pelvisTop: v3a(pts.pelvisTop),
      hipMid: v3a(pts.hipMid),
      source,
      topAnchor: top ? [top.position.x, top.position.y, top.position.z] : [0, 0, 0],
      bottomAnchor: bot ? [bot.position.x, bot.position.y, bot.position.z] : [0, 0, 0],
      leftSleevePivot: left ? [left.position.x, left.position.y, left.position.z] : [0, 0, 0],
      rightSleevePivot: right ? [right.position.x, right.position.y, right.position.z] : [0, 0, 0],
    };

    const key = snapshotKey(snap);
    const now = typeof performance !== "undefined" ? performance.now() : Date.now();
    const sourceChanged = source !== lastSource.current;
    lastSource.current = source;

    if (key === lastSnapKey.current && !sourceChanged) return;
    if (!sourceChanged && now - lastSnapEmitMs.current < SNAP_THROTTLE_MS) return;

    lastSnapKey.current = key;
    lastSnapEmitMs.current = now;
    onAttachmentSnapshot(snap);
  }, 1);

  return null;
}
