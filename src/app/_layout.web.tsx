import { AppNavigationShell } from "@/navigation/AppNavigationShell";

/**
 * Web-only root: no `import "react-native-gesture-handler"` and no GestureHandlerRootView.
 * Metro resolves this file instead of `_layout.tsx` for web builds.
 */
export default function RootLayout() {
  return <AppNavigationShell />;
}
