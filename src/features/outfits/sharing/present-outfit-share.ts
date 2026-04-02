import { Share } from "react-native";

import type { OutfitSharePayload } from "@/features/outfits/sharing/outfit-share-payload";
import { outfitSharePlainText } from "@/features/outfits/sharing/outfit-share-payload";

export type ShareOutfitResult =
  | { status: "shared" }
  | { status: "dismissed" }
  | { status: "unavailable"; message: string };

/**
 * Opens the native share sheet with a plain-text outfit summary.
 * Web: falls back when `Share` is unavailable; extend with `navigator.share` later if needed.
 */
export async function presentOutfitShareSheet(
  payload: OutfitSharePayload,
): Promise<ShareOutfitResult> {
  const message = outfitSharePlainText(payload);
  const title = `Closy: ${payload.outfitName}`;

  try {
    const out = await Share.share({
      title,
      message,
    });

    if (out.action === Share.sharedAction) {
      return { status: "shared" };
    }
    return { status: "dismissed" };
  } catch {
    return {
      status: "unavailable",
      message: "Sharing is not available on this device right now.",
    };
  }
}
