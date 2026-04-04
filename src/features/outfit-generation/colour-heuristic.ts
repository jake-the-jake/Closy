/**
 * Lightweight colour harmony for outfit scoring — lexical heuristics only (no CV).
 * Pairs map to a 0–3 score; multi-piece outfits use the average pairwise score.
 */

export type ColourFamily =
  | "neutral"
  | "cool"
  | "warm"
  | "earth"
  | "pastel"
  | "bright"
  | "unknown";

const NEUTRAL_RE =
  /\b(black|white|off-white|offwhite|grey|gray|charcoal|ivory|cream|beige|tan|taupe|nude|khaki|camel|cocoa|oat|sand|stone|silver|gold|bronze)\b/i;

const COOL_RE =
  /\b(navy|blue|teal|turquoise|aqua|cyan|green|emerald|olive|sage|mint|indigo|denim)\b/i;

const WARM_RE =
  /\b(red|crimson|scarlet|burgundy|wine|maroon|orange|peach|coral|yellow|mustard|pink|magenta|rust|terracotta)\b/i;

const EARTH_RE = /\b(brown|chocolate|espresso|umber|khaki|camel)\b/i;

const PASTEL_RE =
  /\b(pastel|blush|lavender|sky|powder|mint|butter|ice)\b/i;

const BRIGHT_RE =
  /\b(neon|fluoro|electric|vivid|highlighter|lime)\b/i;

export function colourFamilyFromLabel(label: string): ColourFamily {
  const c = label.trim().toLowerCase();
  if (c.length === 0) return "unknown";
  if (NEUTRAL_RE.test(c)) return "neutral";
  if (PASTEL_RE.test(c)) return "pastel";
  if (BRIGHT_RE.test(c)) return "bright";
  if (EARTH_RE.test(c)) return "earth";
  if (COOL_RE.test(c)) return "cool";
  if (WARM_RE.test(c)) return "warm";
  return "unknown";
}

/** Single pair: 0 = clash risk, 3 = strong harmony. */
export function pairHarmonyScore(
  colourA: string,
  colourB: string,
): 0 | 1 | 2 | 3 {
  const fa = colourFamilyFromLabel(colourA);
  const fb = colourFamilyFromLabel(colourB);
  if (fa === "unknown" || fb === "unknown") return 2;
  if (fa === "neutral" || fb === "neutral") return 3;
  if (fa === fb) return fa === "bright" ? 1 : 3;
  if (
    (fa === "cool" && fb === "warm") ||
    (fa === "warm" && fb === "cool")
  ) {
    return 2;
  }
  if (fa === "pastel" || fb === "pastel") return 2;
  if (fa === "earth" || fb === "earth") return 2;
  if (fa === "bright" || fb === "bright") return 1;
  return 2;
}

/** Average pairwise harmony for N pieces (0–3 scale). */
export function aggregateColourHarmony(colours: readonly string[]): number {
  const trimmed = colours
    .map((c) => c.trim())
    .filter((c) => c.length > 0);
  if (trimmed.length < 2) return 2.5;
  let sum = 0;
  let n = 0;
  for (let i = 0; i < trimmed.length; i++) {
    for (let j = i + 1; j < trimmed.length; j++) {
      sum += pairHarmonyScore(trimmed[i]!, trimmed[j]!);
      n++;
    }
  }
  return n === 0 ? 2.5 : sum / n;
}
