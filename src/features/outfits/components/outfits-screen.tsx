import { type Href, useRouter } from "expo-router";
import { useCallback, useLayoutEffect, useMemo } from "react";
import {
  FlatList,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useNavigation } from "@react-navigation/native";

import { EmptyState } from "@/components/ui/empty-state";
import { RemoteSyncNotice } from "@/components/ui/remote-sync-notice";
import { ScreenContainer } from "@/components/ui/screen-container";
import { useAuth } from "@/features/auth";
import { useOutfits } from "@/features/outfits/outfits-service";
import { useRemoteSyncStore } from "@/lib/sync";
import { theme } from "@/theme";

const CREATE_OUTFIT_HREF = "/create-outfit" as Href;

export function OutfitsScreen() {
  const navigation = useNavigation();
  const router = useRouter();
  const outfits = useOutfits();
  const { supabaseConfigured, isAuthenticated } = useAuth();
  const outfitsSync = useRemoteSyncStore((s) => s.outfits);
  const dismissOutfitsError = useRemoteSyncStore((s) => s.dismissOutfitsError);

  const openCreate = useCallback(() => {
    router.push(CREATE_OUTFIT_HREF);
  }, [router]);

  useLayoutEffect(() => {
    navigation.setOptions({
      headerRight: () => (
        <Pressable
          onPress={openCreate}
          accessibilityRole="button"
          accessibilityLabel="Create outfit"
          style={({ pressed }) => [
            styles.headerActionHit,
            pressed && { opacity: 0.75 },
          ]}
        >
          <Text style={styles.headerActionText}>New</Text>
        </Pressable>
      ),
    });
  }, [navigation, openCreate]);

  const listHeader = useMemo(
    () =>
      supabaseConfigured && isAuthenticated ? (
        <RemoteSyncNotice
          snapshot={outfitsSync}
          domain="outfits"
          onDismissError={dismissOutfitsError}
        />
      ) : null,
    [
      dismissOutfitsError,
      isAuthenticated,
      outfitsSync,
      supabaseConfigured,
    ],
  );

  const listEmpty = useMemo(
    () => (
      <View style={styles.emptyWrap}>
        <EmptyState
          title="No outfits yet"
          description={
            supabaseConfigured && isAuthenticated
              ? "Tap New to build a look. Outfits sync to your account when the network is available."
              : "Tap New to combine pieces from your wardrobe into a look."
          }
        />
        <Pressable
          onPress={openCreate}
          accessibilityRole="button"
          accessibilityLabel="Create your first outfit"
          style={({ pressed }) => [
            styles.cta,
            pressed && styles.ctaPressed,
          ]}
        >
          <Text style={styles.ctaText}>Create outfit</Text>
        </Pressable>
      </View>
    ),
    [isAuthenticated, openCreate, supabaseConfigured],
  );

  return (
    <ScreenContainer scroll={false} omitTopSafeArea style={styles.shell}>
      <FlatList
        data={[...outfits]}
        extraData={outfits}
        keyExtractor={(item) => item.id}
        contentContainerStyle={[
          styles.listContent,
          outfits.length === 0 && styles.listContentEmpty,
        ]}
        ListHeaderComponent={listHeader}
        ListEmptyComponent={listEmpty}
        keyboardShouldPersistTaps={
          Platform.OS === "web" ? "always" : "handled"
        }
        renderItem={({ item }) => (
          <Pressable
            onPress={() =>
              router.push({
                pathname: "/outfit/[id]",
                params: { id: item.id },
              } as Href)
            }
            accessibilityRole="button"
            accessibilityLabel={`Open outfit ${item.name}`}
            style={({ pressed }) => [
              styles.card,
              pressed && styles.cardPressed,
            ]}
          >
            <Text style={styles.cardTitle} numberOfLines={2}>
              {item.name.trim() || "Untitled outfit"}
            </Text>
            <Text style={styles.cardMeta}>
              {item.clothingItemIds.length}{" "}
              {item.clothingItemIds.length === 1 ? "piece" : "pieces"}
            </Text>
          </Pressable>
        )}
      />
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  shell: {
    flex: 1,
  },
  listContent: {
    paddingTop: theme.spacing.xs,
    paddingBottom: theme.spacing.xl,
    flexGrow: 1,
  },
  listContentEmpty: {
    justifyContent: "center",
  },
  emptyWrap: {
    flex: 1,
    minHeight: 320,
    justifyContent: "center",
    gap: theme.spacing.lg,
  },
  cta: {
    alignSelf: "center",
    paddingVertical: theme.spacing.sm + theme.spacing.xxs,
    paddingHorizontal: theme.spacing.lg,
    borderRadius: theme.radii.md,
    backgroundColor: theme.colors.primary,
  },
  ctaPressed: {
    opacity: 0.92,
  },
  ctaText: {
    fontSize: theme.typography.fontSize.md,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.surface,
  },
  card: {
    marginHorizontal: theme.spacing.md,
    marginBottom: theme.spacing.sm,
    padding: theme.spacing.md,
    borderRadius: theme.radii.md,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  cardPressed: {
    opacity: 0.92,
  },
  cardTitle: {
    fontSize: theme.typography.fontSize.lg,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  cardMeta: {
    marginTop: theme.spacing.xs,
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
  },
  headerActionHit: {
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
  },
  headerActionText: {
    fontSize: theme.typography.fontSize.md,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.primary,
  },
});
