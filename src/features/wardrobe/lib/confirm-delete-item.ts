import { Alert, Platform } from "react-native";

export type ConfirmDeleteWardrobeItemOptions = {
  title: string;
  message: string;
  onConfirm: () => void;
};

/**
 * Native: two-step `Alert`. Web: `window.confirm` so deletion is never a single unconfirmed tap.
 */
export function confirmDeleteWardrobeItem(
  options: ConfirmDeleteWardrobeItemOptions,
): void {
  const { title, message, onConfirm } = options;

  if (Platform.OS === "web") {
    if (
      typeof window !== "undefined" &&
      window.confirm(`${title}\n\n${message}`)
    ) {
      onConfirm();
    }
    return;
  }

  Alert.alert(title, message, [
    { text: "Cancel", style: "cancel" },
    { text: "Delete", style: "destructive", onPress: onConfirm },
  ]);
}
