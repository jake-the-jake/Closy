import "react-native-gesture-handler";

import { GestureHandlerRootView } from "react-native-gesture-handler";
import { StyleSheet } from "react-native";

import { AppNavigationShell } from "@/navigation/AppNavigationShell";

/**
 * Native entry (iOS / Android / windows): RNGH is imported and the tree is wrapped.
 * Web uses `app/_layout.web.tsx` instead — this file is omitted from the web bundle.
 */
export default function RootLayout() {
  return (
    <GestureHandlerRootView style={styles.gestureRoot}>
      <AppNavigationShell />
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  gestureRoot: {
    flex: 1,
  },
});
