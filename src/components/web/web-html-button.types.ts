import type { ReactNode } from "react";

/**
 * Shared props for {@link WebHtmlButton}. On native, the component renders `null`.
 */
export type WebHtmlButtonProps = {
  onPress: () => void;
  disabled?: boolean;
  testID?: string;
  accessibilityLabel?: string;
  title?: string;
  /** Web only: `React.CSSProperties` for the DOM `<button>`. */
  style?: Record<string, unknown>;
  className?: string;
  children?: ReactNode;
};
