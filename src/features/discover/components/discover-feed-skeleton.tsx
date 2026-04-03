import { StyleSheet, View } from "react-native";

import { theme } from "@/theme";

const THUMB = 108;

function SkeletonCard() {
  return (
    <View style={styles.card}>
      <View style={styles.main}>
        <View style={styles.thumb} />
        <View style={styles.body}>
          <View style={styles.lineLg} />
          <View style={styles.lineSm} />
        </View>
      </View>
      <View style={styles.likeCol} />
    </View>
  );
}

export function DiscoverFeedSkeleton() {
  return (
    <View style={styles.stack} accessibilityLabel="Loading feed">
      <SkeletonCard />
      <SkeletonCard />
      <SkeletonCard />
    </View>
  );
}

const styles = StyleSheet.create({
  stack: {
    gap: theme.spacing.md,
    paddingHorizontal: theme.spacing.md,
    paddingTop: theme.spacing.md,
  },
  card: {
    flexDirection: "row",
    borderRadius: theme.radii.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
    overflow: "hidden",
    minHeight: THUMB + theme.spacing.md * 2,
  },
  main: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    padding: theme.spacing.md,
    gap: theme.spacing.sm,
  },
  thumb: {
    width: THUMB,
    height: THUMB,
    borderRadius: theme.radii.sm,
    backgroundColor: theme.colors.border,
    opacity: 0.55,
  },
  body: {
    flex: 1,
    gap: theme.spacing.sm,
    justifyContent: "center",
  },
  lineLg: {
    height: 16,
    borderRadius: theme.radii.sm,
    backgroundColor: theme.colors.border,
    opacity: 0.65,
    width: "88%",
  },
  lineSm: {
    height: 12,
    borderRadius: theme.radii.sm,
    backgroundColor: theme.colors.border,
    opacity: 0.5,
    width: "55%",
  },
  likeCol: {
    width: 56,
    borderLeftWidth: StyleSheet.hairlineWidth,
    borderLeftColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
  },
});
