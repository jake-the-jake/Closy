import { Platform, Share } from "react-native";

import type { OutfitSharePayload } from "@/features/outfits/sharing/outfit-share-payload";
import { outfitSharePlainText } from "@/features/outfits/sharing/outfit-share-payload";

export type ShareOutfitResult =
  | { status: "shared" }
  | { status: "dismissed" }
  /** Web: text was copied because Web Share API was unavailable or failed. */
  | { status: "copied"; message: string }
  | { status: "unavailable"; message: string };

async function shareOnWeb(message: string, title: string): Promise<ShareOutfitResult> {
  if (typeof navigator === "undefined") {
    return {
      status: "unavailable",
      message: "Sharing is not available in this environment.",
    };
  }

  if (typeof navigator.share === "function") {
    try {
      await navigator.share({ title, text: message });
      console.log("[Closy][Share] Web Share API completed");
      return { status: "shared" };
    } catch (e) {
      const name = e instanceof Error ? e.name : "";
      if (name === "AbortError") {
        console.log("[Closy][Share] Web Share API dismissed by user");
        return { status: "dismissed" };
      }
      console.warn("[Closy][Share] Web Share API failed, trying clipboard", e);
    }
  }

  try {
    await navigator.clipboard.writeText(message);
    console.log("[Closy][Share] Copied outfit summary to clipboard (web fallback)");
    return {
      status: "copied",
      message: "Summary copied to your clipboard. Paste somewhere to share.",
    };
  } catch (e) {
    console.error("[Closy][Share] Clipboard write failed", e);
    return {
      status: "unavailable",
      message:
        "Could not share or copy. Try a browser that supports the Web Share API or clipboard access.",
    };
  }
}

/**
 * Native: `Share.share`. Web: `navigator.share` when supported, else clipboard copy.
 */
export async function presentOutfitShareSheet(
  payload: OutfitSharePayload,
): Promise<ShareOutfitResult> {
  const message = outfitSharePlainText(payload);
  const title = `Closy: ${payload.outfitName}`;

  if (Platform.OS === "web") {
    return shareOnWeb(message, title);
  }

  try {
    const out = await Share.share({
      title,
      message,
    });

    if (out.action === Share.sharedAction) {
      console.log("[Closy][Share] Native share completed");
      return { status: "shared" };
    }
    console.log("[Closy][OutfitDetail] Native share dismissed");
    return { status: "dismissed" };
  } catch (e) {
    console.error("[Closy][Share] Native Share.share failed", e);
    return {
      status: "unavailable",
      message: "Sharing is not available on this device right now.",
    };
  }
}
