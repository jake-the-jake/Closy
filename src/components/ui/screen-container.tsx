import type { ReactNode } from "react";
import {
  Platform,
  ScrollView,
  StyleSheet,
  View,
  type ScrollViewProps,
  type StyleProp,
  type ViewStyle,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { theme } from "@/theme";

export type ScreenContainerProps = {
  children: ReactNode;
  /** When true, wraps children in a vertical ScrollView (default). */
  scroll?: boolean;
  /**
   * Tab screens sit under a header that already respects the top safe area.
   * Set true to use only horizontal + bottom insets plus a small top padding.
   */
  omitTopSafeArea?: boolean;
  contentContainerStyle?: StyleProp<ViewStyle>;
  scrollViewProps?: Omit<ScrollViewProps, "contentContainerStyle" | "children">;
  style?: StyleProp<ViewStyle>;
  testID?: string;
};

/**
 * Consistent screen padding and background. Prefer scroll={false} for static screens.
 */
export function ScreenContainer({
  children,
  scroll = true,
  omitTopSafeArea = false,
  contentContainerStyle,
  scrollViewProps,
  style,
  testID,
}: ScreenContainerProps) {
  const insets = useSafeAreaInsets();

  const paddingTop = omitTopSafeArea
    ? theme.spacing.md
    : Math.max(insets.top, theme.spacing.md);
  const paddingBottom = Math.max(insets.bottom, theme.spacing.md);

  const paddingStyle: ViewStyle = {
    paddingTop,
    paddingBottom,
    paddingHorizontal: theme.spacing.md,
    flexGrow: scroll ? 1 : undefined,
  };

  if (!scroll) {
    return (
      <View testID={testID} style={[styles.root, paddingStyle, style]}>
        {children}
      </View>
    );
  }

  /**
   * RN Web: vertical `ScrollView` installs responder capture (`onStartShouldSetResponderCapture`).
   * That can swallow mouse/tap sequences so nested `Pressable`s never see `onPress`, while `TextInput`
   * still focuses. Use a plain overflow scroll `View` so the browser handles scrolling without the RN
   * scroll responder owning the gesture chain.
   */
  if (Platform.OS === "web") {
    return (
      <View
        testID={testID}
        style={[styles.root, styles.rootScroll, styles.rootScrollWeb, styles.rootWebScroll, style]}
      >
        <View style={[paddingStyle, contentContainerStyle, styles.webScrollInner]}>
          {children}
        </View>
      </View>
    );
  }

  return (
    <ScrollView
      testID={testID}
      style={[styles.root, styles.rootScroll, style]}
      keyboardShouldPersistTaps="handled"
      contentContainerStyle={[paddingStyle, contentContainerStyle]}
      showsVerticalScrollIndicator={false}
      {...scrollViewProps}
    >
      {children}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  /** Default ScrollView flex chain (edit/add screens rely on this inside stacks). */
  rootScroll: {
    minHeight: 0,
  },
  /**
   * RN Web: stack scenes + ScrollView often collapse to 0 viewport height without stretch +
   * explicit flex/minHeight. Keeps scroll bodies visible on routes like /add-item.
   */
  rootScrollWeb: {
    flexGrow: 1,
    alignSelf: "stretch",
    width: "100%",
  },
  rootWebScroll: {
    minHeight: 0,
    overflowX: "hidden",
    overflowY: "auto",
  },
  webScrollInner: {
    width: "100%",
    maxWidth: "100%",
    minWidth: 0,
  },
});
