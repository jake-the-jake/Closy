import type { OutfitOccasion } from "@/features/outfit-generation/occasion-presets";

export const OUTFIT_SUGGESTION_FEEDBACK_TYPES = [
  "positive_like",
  "negative_not_my_style",
  "regenerate",
  "saved",
] as const;

export type OutfitSuggestionFeedbackType =
  (typeof OUTFIT_SUGGESTION_FEEDBACK_TYPES)[number];

/** Payload recorded locally and (when authed) in Supabase. */
export type OutfitSuggestionFeedbackPayload = {
  occasion: OutfitOccasion;
  feedbackType: OutfitSuggestionFeedbackType;
  clothingItemIds: readonly string[];
  /** Generator composite id (`occasion` + item-set key). */
  suggestionKey: string;
  /** Optional ranking score at feedback time for future models. */
  scoreSnapshot?: number;
};

export type LocalOutfitSuggestionFeedbackEntry = OutfitSuggestionFeedbackPayload & {
  localId: string;
  createdAt: number;
};
