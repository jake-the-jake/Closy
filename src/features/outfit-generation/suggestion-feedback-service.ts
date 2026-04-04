import {
  insertOutfitSuggestionFeedbackRow,
} from "@/features/outfit-generation/lib/cloud-outfit-suggestion-feedback";
import { useSuggestionFeedbackStore } from "@/features/outfit-generation/state/suggestion-feedback-store";
import type { OutfitSuggestionFeedbackPayload } from "@/features/outfit-generation/types/suggestion-feedback";
import { getAuthedUserId } from "@/lib/supabase/get-authed-user-id";
import { supabase } from "@/lib/supabase/client";

/**
 * Records outfit-suggestion feedback: always to the local append-only log;
 * also inserts a Supabase row when the user is signed in and Supabase is configured.
 */
export const outfitSuggestionFeedbackService = {
  async record(payload: OutfitSuggestionFeedbackPayload): Promise<void> {
    useSuggestionFeedbackStore.getState().append(payload);

    const client = supabase;
    const userId = await getAuthedUserId();
    if (client && userId) {
      await insertOutfitSuggestionFeedbackRow(client, userId, payload);
    }
  },
} as const;
