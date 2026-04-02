import type { WebHtmlButtonProps } from "@/components/web/web-html-button.types";

export type { WebHtmlButtonProps };

/** Native / SSR: no DOM — use `Pressable` call sites instead. */
export function WebHtmlButton(_props: WebHtmlButtonProps): null {
  return null;
}
