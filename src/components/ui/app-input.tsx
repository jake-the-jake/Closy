import { useState } from "react";
import {
  Platform,
  StyleSheet,
  Text,
  TextInput,
  View,
  type StyleProp,
  type TextInputProps,
  type TextStyle,
  type ViewStyle,
} from "react-native";

import { theme } from "@/theme";

type AppInputOwnProps = {
  label: string;
  containerStyle?: StyleProp<ViewStyle>;
  error?: string;
  testID?: string;
};

export type AppInputProps = AppInputOwnProps &
  Omit<TextInputProps, "style"> & {
    /** Merged after internal styles so you can extend the field. */
    style?: StyleProp<TextStyle>;
  };

/**
 * Single-line field with label and optional error text. Forwards TextInput props.
 */
export function AppInput({
  label,
  containerStyle,
  error,
  testID,
  style,
  onFocus,
  onBlur,
  ...textInputProps
}: AppInputProps) {
  const [focused, setFocused] = useState(false);

  return (
    <View style={[styles.wrap, containerStyle]}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        testID={testID}
        accessibilityLabel={label}
        placeholderTextColor={theme.colors.textMuted}
        style={[
          styles.input,
          Platform.OS === "web" && styles.inputWeb,
          focused && styles.inputFocused,
          error ? styles.inputError : null,
          style,
        ]}
        onFocus={(e) => {
          setFocused(true);
          onFocus?.(e);
        }}
        onBlur={(e) => {
          setFocused(false);
          onBlur?.(e);
        }}
        {...textInputProps}
      />
      {error ? (
        <Text style={styles.error} accessibilityLiveRegion="polite">
          {error}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    width: "100%",
    maxWidth: "100%",
    minWidth: 0,
    alignSelf: "stretch",
  },
  label: {
    fontSize: theme.typography.fontSize.sm,
    fontWeight: theme.typography.fontWeight.medium,
    color: theme.colors.text,
    marginBottom: theme.spacing.xs,
  },
  input: {
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radii.md,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm + theme.spacing.xxs,
    fontSize: theme.typography.fontSize.base,
    color: theme.colors.text,
    backgroundColor: theme.colors.surface,
  },
  /**
   * RN Web: unstyled inputs often collapse to 0 usable width inside flex columns.
   * outlineWidth tames the default browser focus ring (we keep border feedback).
   */
  inputWeb: {
    width: "100%",
    maxWidth: "100%",
    minWidth: 0,
    alignSelf: "stretch",
    minHeight: 44,
    outlineWidth: 0,
    boxSizing: "border-box",
  },
  inputFocused: {
    borderColor: theme.colors.primary,
  },
  inputError: {
    borderColor: theme.colors.danger,
  },
  error: {
    marginTop: theme.spacing.xs,
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.danger,
  },
});
