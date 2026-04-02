import type { CSSProperties, MouseEvent } from "react";

import type { WebHtmlButtonProps } from "@/components/web/web-html-button.types";

export type { WebHtmlButtonProps };

/** Real `<button type="button">` — bypasses RN `Pressable` / responder chain on web. */
export function WebHtmlButton({
  onPress,
  disabled = false,
  testID,
  accessibilityLabel,
  title,
  style,
  className,
  children,
}: WebHtmlButtonProps) {
  const onClick = (e: MouseEvent<HTMLButtonElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (!disabled) onPress();
  };

  return (
    <button
      type="button"
      disabled={disabled}
      data-testid={testID}
      title={title}
      aria-label={accessibilityLabel}
      className={className}
      onClick={onClick}
      style={style as CSSProperties}
    >
      {children}
    </button>
  );
}
