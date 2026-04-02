import { StyleSheet, Text, View } from "react-native";

import { theme } from "@/theme";

import { AppButton } from "./app-button";

type EmptyStateBase = {
  title: string;
  description?: string;
  testID?: string;
};

type EmptyStateWithAction = EmptyStateBase & {
  actionLabel: string;
  onActionPress: () => void;
};

type EmptyStateWithoutAction = EmptyStateBase & {
  actionLabel?: undefined;
  onActionPress?: undefined;
};

export type EmptyStateProps = EmptyStateWithAction | EmptyStateWithoutAction;

function hasAction(props: EmptyStateProps): props is EmptyStateWithAction {
  return props.actionLabel !== undefined && props.onActionPress !== undefined;
}

/**
 * Centered message for lists or tabs. Optional primary action (both label + handler required).
 */
export function EmptyState(props: EmptyStateProps) {
  const { title, description, testID } = props;

  return (
    <View
      testID={testID}
      style={styles.root}
      accessibilityRole="text"
      accessibilityLabel={[title, description].filter(Boolean).join(". ")}
    >
      <Text style={styles.title}>{title}</Text>
      {description ? (
        <Text style={styles.description}>{description}</Text>
      ) : null}
      {hasAction(props) ? (
        <View style={styles.action}>
          <AppButton
            label={props.actionLabel}
            onPress={props.onActionPress}
            variant="primary"
            fullWidth
          />
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    paddingVertical: theme.spacing.xl * 2,
    paddingHorizontal: theme.spacing.lg,
    gap: theme.spacing.sm,
  },
  title: {
    fontSize: theme.typography.fontSize.panel,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
    textAlign: "center",
  },
  description: {
    fontSize: theme.typography.fontSize.md,
    lineHeight: theme.typography.lineHeight.lede,
    color: theme.colors.textMuted,
    textAlign: "center",
    maxWidth: 320,
  },
  action: {
    marginTop: theme.spacing.md,
    alignSelf: "stretch",
    maxWidth: 280,
  },
});
