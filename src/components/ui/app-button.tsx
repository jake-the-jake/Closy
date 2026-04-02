import type { CSSProperties, ReactNode } from "react";
import {
  ActivityIndicator,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
  type PressableProps,
  type StyleProp,
  type TextStyle,
  type ViewStyle,
} from "react-native";

import { WebHtmlButton } from "@/components/web/web-html-button";
import { theme } from "@/theme";

export type AppButtonVariant = "primary" | "secondary" | "ghost";

export type AppButtonProps = {
  label: string;
  onPress: () => void;
  variant?: AppButtonVariant;
  disabled?: boolean;
  loading?: boolean;
  icon?: ReactNode;
  /** Full-width tap target (common for forms). */
  fullWidth?: boolean;
  testID?: string;
  accessibilityHint?: string;
  style?: StyleProp<ViewStyle>;
} & Pick<PressableProps, "accessibilityLabel">;

function appButtonWebStyle({
  variant,
  fullWidth,
  isDisabled,
}: {
  variant: AppButtonVariant;
  fullWidth: boolean;
  isDisabled: boolean;
}): CSSProperties {
  const padY = theme.spacing.sm + theme.spacing.xxs;
  const base: CSSProperties = {
    borderRadius: theme.radii.md,
    paddingTop: padY,
    paddingBottom: padY,
    paddingLeft: theme.spacing.md,
    paddingRight: theme.spacing.md,
    minHeight: 48,
    display: "flex",
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: theme.spacing.sm,
    boxSizing: "border-box",
    fontSize: theme.typography.fontSize.base,
    fontWeight: theme.typography.fontWeight.semibold,
    fontFamily: "system-ui, sans-serif",
    cursor: isDisabled ? "not-allowed" : "pointer",
    opacity: isDisabled ? 0.5 : 1,
    width: fullWidth ? "100%" : "auto",
    maxWidth: fullWidth ? "100%" : undefined,
    alignSelf: fullWidth ? "stretch" : undefined,
    userSelect: "none",
    WebkitUserSelect: "none",
  };

  if (variant === "primary") {
    return {
      ...base,
      border: "none",
      backgroundColor: theme.colors.primary,
      color: theme.colors.surface,
    };
  }
  if (variant === "secondary") {
    return {
      ...base,
      border: `1px solid ${theme.colors.border}`,
      backgroundColor: theme.colors.surface,
      color: theme.colors.text,
    };
  }
  return {
    ...base,
    border: "1px solid transparent",
    backgroundColor: "transparent",
    color: theme.colors.primary,
  };
}

export function AppButton({
  label,
  onPress,
  variant = "primary",
  disabled = false,
  loading = false,
  icon,
  fullWidth = false,
  testID,
  accessibilityLabel,
  accessibilityHint,
  style,
}: AppButtonProps) {
  const isDisabled = disabled || loading;

  if (Platform.OS === "web") {
    const webStyle = appButtonWebStyle({ variant, fullWidth, isDisabled });
    return (
      <WebHtmlButton
        testID={testID}
        accessibilityLabel={accessibilityLabel ?? label}
        title={accessibilityHint}
        disabled={isDisabled}
        onPress={onPress}
        style={webStyle as Record<string, unknown>}
      >
        {loading ? "…" : (
          <>
            {icon}
            {label}
          </>
        )}
      </WebHtmlButton>
    );
  }

  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled: isDisabled }}
      disabled={isDisabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.base,
        fullWidth && styles.fullWidth,
        variant === "primary" && styles.primary,
        variant === "secondary" && styles.secondary,
        variant === "ghost" && styles.ghost,
        pressed && !isDisabled && styles.pressed,
        isDisabled && styles.disabled,
        style,
      ]}
    >
      <View style={[styles.inner, styles.innerPassthrough]}>
        {loading ? (
          <ActivityIndicator
            color={variant === "primary" ? theme.colors.surface : theme.colors.primary}
            style={styles.spinnerPassthrough}
          />
        ) : (
          <>
            {icon}
            <Text
              style={[
                styles.label,
                styles.labelPassthrough,
                variant === "primary" && styles.labelPrimary,
                variant === "secondary" && styles.labelSecondary,
                variant === "ghost" && styles.labelGhost,
              ]}
            >
              {label}
            </Text>
          </>
        )}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    borderRadius: theme.radii.md,
    paddingVertical: theme.spacing.sm + theme.spacing.xxs,
    paddingHorizontal: theme.spacing.md,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 48,
  },
  fullWidth: {
    alignSelf: "stretch",
    width: "100%",
    maxWidth: "100%",
  },
  inner: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.sm,
  },
  innerPassthrough: {
    pointerEvents: "none",
  },
  spinnerPassthrough: {
    pointerEvents: "none",
  } as ViewStyle,
  labelPassthrough: {
    pointerEvents: "none",
  } as TextStyle,
  primary: {
    backgroundColor: theme.colors.primary,
  },
  secondary: {
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  ghost: {
    backgroundColor: "transparent",
  },
  pressed: {
    opacity: 0.9,
  },
  disabled: {
    opacity: 0.5,
  },
  label: {
    fontSize: theme.typography.fontSize.base,
    fontWeight: theme.typography.fontWeight.semibold,
  },
  labelPrimary: {
    color: theme.colors.surface,
  },
  labelSecondary: {
    color: theme.colors.text,
  },
  labelGhost: {
    color: theme.colors.primary,
  },
});
