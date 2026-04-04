export type {
  GeneratedOutfitExplanation,
  GeneratedOutfitSuggestion,
  GenerateOutfitsOptions,
  OutfitSuggestionScoreBand,
} from "./types";
export {
  SCORE_BAND_OKAY_MIN,
  SCORE_BAND_SOLID_MIN,
  SCORE_BAND_STRONG_MIN,
  SUGGESTION_SCORING_VERSION,
  computeSuggestionScoring,
  rawScoreToBand,
} from "./suggestion-scoring";
export {
  OUTFIT_OCCASIONS,
  OUTFIT_OCCASION_LABELS,
  OUTFIT_OCCASIONS_UI_ORDER,
} from "./occasion-presets";
export type { OutfitOccasion } from "./occasion-presets";
export { aggregateColourHarmony, colourFamilyFromLabel } from "./colour-heuristic";
export { generateRankedOutfitSuggestions } from "./rule-based-generator";
export { SuggestOutfitScreen } from "./components/suggest-outfit-screen";
export { outfitSuggestionFeedbackService } from "./suggestion-feedback-service";
export {
  OUTFIT_SUGGESTION_FEEDBACK_TYPES,
} from "./types/suggestion-feedback";
export type {
  LocalOutfitSuggestionFeedbackEntry,
  OutfitSuggestionFeedbackPayload,
  OutfitSuggestionFeedbackType,
} from "./types/suggestion-feedback";
