/**
 * User-selectable outfit contexts. Matching uses tags, names, categories, and colour text only.
 */

export const OUTFIT_OCCASIONS = [
  "casual",
  "smart_casual",
  "office",
  "date_night",
  "going_out",
  "gym",
  "warm_weather",
  "cold_weather",
] as const;

export type OutfitOccasion = (typeof OUTFIT_OCCASIONS)[number];

export const OUTFIT_OCCASION_LABELS: Record<OutfitOccasion, string> = {
  casual: "Casual",
  smart_casual: "Smart casual",
  office: "Office",
  date_night: "Date night",
  going_out: "Going out",
  gym: "Gym",
  warm_weather: "Warm weather",
  cold_weather: "Cold weather",
};

/** Display order in the picker UI. */
export const OUTFIT_OCCASIONS_UI_ORDER: readonly OutfitOccasion[] = [
  "casual",
  "smart_casual",
  "office",
  "date_night",
  "going_out",
  "gym",
  "warm_weather",
  "cold_weather",
];
