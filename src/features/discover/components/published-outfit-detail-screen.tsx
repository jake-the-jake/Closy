import { Image } from "expo-image";
import { useCallback, useEffect, useLayoutEffect, useState } from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { useNavigation } from "@react-navigation/native";

import { EmptyState } from "@/components/ui/empty-state";
import { ScreenContainer } from "@/components/ui/screen-container";
import { discoverService } from "@/features/discover/discover-service";
import type { PublishedOutfit } from "@/features/discover/types/published-outfit";
import { media } from "@/lib/constants";
import { theme } from "@/theme";

export type PublishedOutfitDetailScreenProps = {
  publishedId: string | null;
};

function formatPublishedLabel(publishedAt: number): string {
  try {
    const d = new Date(publishedAt);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

export function PublishedOutfitDetailScreen({ publishedId }: PublishedOutfitDetailScreenProps) {
  const navigation = useNavigation();
  const [row, setRow] = useState<PublishedOutfit | null | undefined>(undefined);

  const load = useCallback(async () => {
    if (!publishedId) {
      setRow(null);
      return;
    }
    setRow(undefined);
    const next = await discoverService.fetchPublishedById(publishedId);
    setRow(next);
  }, [publishedId]);

  useEffect(() => {
    void load();
  }, [load]);

  useLayoutEffect(() => {
    if (row === undefined) {
      navigation.setOptions({ title: "Published outfit" });
      return;
    }
    if (row === null) {
      navigation.setOptions({ title: "Post" });
      return;
    }
    navigation.setOptions({ title: row.name.trim() || "Published outfit" });
  }, [navigation, row]);

  if (!publishedId || row === null) {
    return (
      <ScreenContainer scroll={false} omitTopSafeArea>
        <EmptyState
          title="Post not found"
          description="It may have been removed or the link is invalid."
        />
      </ScreenContainer>
    );
  }

  if (row === undefined) {
    return (
      <ScreenContainer scroll={false} omitTopSafeArea style={styles.centered}>
        <ActivityIndicator color={theme.colors.primary} />
        <Text style={styles.loadingText}>Loading…</Text>
      </ScreenContainer>
    );
  }

  const { snapshot } = row;

  return (
    <ScreenContainer scroll omitTopSafeArea contentContainerStyle={styles.body}>
      <Text style={styles.lede}>
        {row.pieceCount} piece{row.pieceCount === 1 ? "" : "s"} · Published{" "}
        {formatPublishedLabel(row.publishedAt)}
      </Text>
      <Text style={styles.snapshotHint}>
        Snapshot from {new Date(snapshot.generatedAtIso).toLocaleDateString()} — edits to
        the original outfit won’t change this post.
      </Text>

      <Text style={styles.sectionLabel}>Pieces</Text>
      <View style={styles.list}>
        {snapshot.lines.map((line) => {
          const uri = line.imageUrl.trim();
          return (
            <View key={line.clothingItemId} style={styles.row}>
              {uri ? (
                <Image
                  source={{ uri }}
                  style={styles.thumb}
                  contentFit="cover"
                  transition={media.imageTransitionMs.card}
                />
              ) : (
                <View style={[styles.thumb, styles.thumbPlaceholder]}>
                  <Text style={styles.thumbPhText}>No photo</Text>
                </View>
              )}
              <View style={styles.rowText}>
                <Text style={styles.rowTitle} numberOfLines={2}>
                  {line.label}
                </Text>
                <Text style={styles.rowSub} numberOfLines={1}>
                  {line.categoryLabel}
                  {line.missingFromWardrobe ? " · removed at publish time" : ""}
                </Text>
              </View>
            </View>
          );
        })}
      </View>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  centered: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: theme.spacing.md,
  },
  loadingText: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
  },
  body: {
    paddingBottom: theme.spacing.xl,
    gap: theme.spacing.lg,
  },
  lede: {
    fontSize: theme.typography.fontSize.md,
    color: theme.colors.textMuted,
  },
  snapshotHint: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
    lineHeight: 20,
  },
  sectionLabel: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  list: {
    borderRadius: theme.radii.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    overflow: "hidden",
    backgroundColor: theme.colors.surface,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: theme.spacing.sm,
    paddingHorizontal: theme.spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: theme.colors.border,
    gap: theme.spacing.md,
  },
  thumb: {
    width: 56,
    height: 56,
    borderRadius: theme.radii.sm,
    backgroundColor: theme.colors.border,
  },
  thumbPlaceholder: {
    alignItems: "center",
    justifyContent: "center",
  },
  thumbPhText: {
    fontSize: 10,
    color: theme.colors.textMuted,
  },
  rowText: {
    flex: 1,
    minWidth: 0,
  },
  rowTitle: {
    fontSize: theme.typography.fontSize.md,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  rowSub: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    marginTop: 2,
  },
});
