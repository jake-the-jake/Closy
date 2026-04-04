import type { SupabaseClient } from "@supabase/supabase-js";

import type { OutfitSuggestionFeedbackPayload } from "@/features/outfit-generation/types/suggestion-feedback";

export const OUTFIT_SUGGESTION_FEEDBACK_TABLE = "outfit_suggestion_feedback";

export async function insertOutfitSuggestionFeedbackRow(
  client: SupabaseClient,
  userId: string,
  payload: OutfitSuggestionFeedbackPayload,
): Promise<void> {
  const row = {
    user_id: userId,
    occasion: payload.occasion,
    feedback_type: payload.feedbackType,
    clothing_item_ids: [...payload.clothingItemIds],
    suggestion_key: payload.suggestionKey,
    score_snapshot:
      payload.scoreSnapshot != null && Number.isFinite(payload.scoreSnapshot)
        ? payload.scoreSnapshot
        : null,
  };
  const { error } = await client
    .from(OUTFIT_SUGGESTION_FEEDBACK_TABLE)
    .insert(row);
  if (error) {
    console.warn("[Closy] Outfit suggestion feedback insert failed:", error.message);
  }
}
