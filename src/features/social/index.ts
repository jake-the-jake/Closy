/**
 * Social / sharing extension surface. Outfit share contracts live in
 * `features/outfits/sharing`; keep imports here when building feeds or remote share.
 */
export type {
  OutfitShareLineItem,
  OutfitSharePayload,
} from "@/features/outfits/sharing/outfit-share-payload";
export {
  OUTFIT_SHARE_SCHEMA_VERSION,
  buildOutfitSharePayload,
  outfitSharePlainText,
  outfitShareToJson,
} from "@/features/outfits/sharing/outfit-share-payload";
export {
  presentOutfitShareSheet,
  type ShareOutfitResult,
} from "@/features/outfits/sharing/present-outfit-share";
