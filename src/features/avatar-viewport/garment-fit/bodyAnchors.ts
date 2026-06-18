import { THREE } from "../three";

export const BODY_ANCHOR_NAMES = [
  "head",
  "neck",
  "chest",
  "waist",
  "hips",
  "shoulderL",
  "shoulderR",
  "elbowL",
  "elbowR",
  "wristL",
  "wristR",
  "hipL",
  "hipR",
  "kneeL",
  "kneeR",
  "ankleL",
  "ankleR",
  "footL",
  "footR",
] as const;

export type BodyAnchorName = (typeof BODY_ANCHOR_NAMES)[number];
export type BodyAnchorMap = Partial<Record<BodyAnchorName, THREE.Vector3>>;

export function hasCoreGarmentAnchors(anchors: BodyAnchorMap): boolean {
  return Boolean(
    anchors.chest &&
      anchors.waist &&
      anchors.hips &&
      anchors.shoulderL &&
      anchors.shoulderR,
  );
}
