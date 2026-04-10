import {
  cloneGarmentFitState,
  DEFAULT_GARMENT_FIT_STATE,
  type GarmentFitState,
} from "@/features/avatar-export";

import type { GarmentFitRegionKey } from "./avatar-scene-types";

/** Reset only the given region (and sleeve/waist legacy fields when sleeves/waist). */
export function resetGarmentFitRegion(
  s: GarmentFitState,
  region: GarmentFitRegionKey,
): GarmentFitState {
  const c = cloneGarmentFitState(s);
  const d = DEFAULT_GARMENT_FIT_STATE;
  switch (region) {
    case "global":
      c.global = {
        offset: [...d.global.offset] as [number, number, number],
        scale: [...d.global.scale] as [number, number, number],
        inflate: d.global.inflate,
      };
      break;
    case "torso":
      c.regions.torso = { ...d.regions.torso };
      break;
    case "sleeves":
      c.regions.sleeves = {
        offset: [...d.regions.sleeves.offset] as [number, number, number],
        inflate: d.regions.sleeves.inflate,
      };
      c.legacy.sleeveOffsetY = d.legacy.sleeveOffsetY;
      break;
    case "waist":
      c.regions.waist = { ...d.regions.waist };
      c.legacy.waistAdjustY = d.legacy.waistAdjustY;
      break;
    case "hem":
      c.regions.hem = { ...d.regions.hem };
      break;
    default:
      break;
  }
  return c;
}
