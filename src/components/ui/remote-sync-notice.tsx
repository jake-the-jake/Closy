import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";

import type { RemoteDomainSnapshot } from "@/lib/sync";
import { theme } from "@/theme";

export type RemoteSyncNoticeDomain = "wardrobe" | "outfits";

type RemoteSyncNoticeProps = {
  snapshot: RemoteDomainSnapshot;
  domain: RemoteSyncNoticeDomain;
  onDismissError: () => void;
};

const DOMAIN_LABEL: Record<RemoteSyncNoticeDomain, string> = {
  wardrobe: "wardrobe",
  outfits: "outfits",
};

/**
 * Inline status for cloud hydration: non-blocking, keeps lists usable.
 */
export function RemoteSyncNotice({
  snapshot,
  domain,
  onDismissError,
}: RemoteSyncNoticeProps) {
  if (snapshot.phase === "idle" || snapshot.phase === "success") {
    return null;
  }

  if (snapshot.phase === "syncing") {
    return (
      <View
        style={styles.syncingRow}
        accessibilityRole="text"
        accessibilityLabel={`Syncing ${DOMAIN_LABEL[domain]} with your account`}
        accessibilityLiveRegion="polite"
      >
        <ActivityIndicator size="small" color={theme.colors.primary} />
        <Text style={styles.syncingText}>
          Syncing {DOMAIN_LABEL[domain]}…
        </Text>
      </View>
    );
  }

  if (snapshot.phase === "error" && snapshot.errorMessage != null) {
    return (
      <View style={styles.errorBox} accessibilityRole="alert">
        <Text style={styles.errorTitle}>Couldn’t refresh from the cloud</Text>
        <Text style={styles.errorBody}>{snapshot.errorMessage}</Text>
        <Text style={styles.errorHint}>
          You can still use Closy — this screen shows data on your device.
        </Text>
        <Pressable
          onPress={onDismissError}
          accessibilityRole="button"
          accessibilityLabel="Dismiss sync error message"
          style={({ pressed }) => [
            styles.dismissHit,
            pressed && { opacity: 0.8 },
          ]}
        >
          <Text style={styles.dismissText}>Dismiss</Text>
        </Pressable>
      </View>
    );
  }

  return null;
}


const styles = StyleSheet.create({
  syncingRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.sm,
    marginBottom: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    paddingHorizontal: theme.spacing.sm,
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.sm,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  syncingText: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
    flex: 1,
  },
  errorBox: {
    marginBottom: theme.spacing.md,
    padding: theme.spacing.md,
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.md,
    borderWidth: 1,
    borderColor: theme.colors.danger,
    gap: theme.spacing.sm,
  },
  errorTitle: {
    fontSize: theme.typography.fontSize.sm,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  errorBody: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.text,
    lineHeight: 18,
  },
  errorHint: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    lineHeight: 18,
  },
  dismissHit: {
    alignSelf: "flex-start",
    paddingVertical: theme.spacing.xs,
  },
  dismissText: {
    fontSize: theme.typography.fontSize.sm,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.primary,
  },
});
