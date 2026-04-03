/**
 * Design tokens — keep screens on shared spacing, type scale, radii, and colour.
 * Extend gradually; avoid a heavy “design system” layer until the product stabilises.
 */
const colors = {
  background: "#F7F7F8",
  surface: "#FFFFFF",
  text: "#111113",
  textMuted: "#6B6B70",
  border: "#E4E4E7",
  primary: "#208AEF",
  primaryPressed: "#1A6FCC",
  danger: "#DC2626",
  shadow: "#000000",
} as const;

export const theme = {
  colors,
  radii: {
    sm: 8,
    md: 12,
    lg: 16,
    full: 9999,
  },
  spacing: {
    xxs: 2,
    xs: 4,
    sm: 8,
    md: 16,
    lg: 24,
    xl: 32,
  },
  typography: {
    fontSize: {
      xs: 12,
      sm: 14,
      /** Helper / error lines */
      caption: 13,
      md: 15,
      base: 16,
      lg: 17,
      /** Empty states, secondary headings */
      panel: 18,
      xl: 20,
      xxl: 22,
    },
    lineHeight: {
      title: 28,
      lede: 21,
    },
    fontWeight: {
      medium: "500",
      semibold: "600",
    },
  },
  /** iOS / Android only — on web use `boxShadow` to avoid RN Web `shadow*` deprecation warnings. */
  shadows: {
    fab: {
      shadowColor: colors.shadow,
      shadowOffset: { width: 0, height: 2 },
      shadowOpacity: 0.2,
      shadowRadius: 4,
      elevation: 4,
    },
  },
} as const;

export type Theme = typeof theme;
