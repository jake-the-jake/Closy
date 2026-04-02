import { Platform, StyleSheet, Text, View } from "react-native";

import { theme } from "@/theme";

import { ScreenContainer } from "./screen-container";

type PlaceholderScreenProps = {
  title: string;
  subtitle?: string;
  /** Tab/stack layouts usually provide top inset via the navigator header. */
  omitTopSafeArea?: boolean;
};

/**
 * Simple tab or stack placeholder: shared typography + ScreenContainer.
 */
export function PlaceholderScreen({
  title,
  subtitle,
  omitTopSafeArea = true,
}: PlaceholderScreenProps) {
  return (
    <ScreenContainer scroll={false} omitTopSafeArea={omitTopSafeArea}>
      <View style={styles.block}>
        <Text style={styles.title}>{title}</Text>
        {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
      </View>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  block: {
    gap: theme.spacing.xs,
    flex: 1,
    justifyContent: "flex-start",
    paddingTop: theme.spacing.sm,
    ...Platform.select({
      web: {
        minHeight: 360,
        width: "100%" as const,
      },
      default: {},
    }),
  },
  title: {
    fontSize: theme.typography.fontSize.xxl,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  subtitle: {
    fontSize: theme.typography.fontSize.md,
    color: theme.colors.textMuted,
  },
});
