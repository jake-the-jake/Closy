import { Image } from "expo-image";
import { type Href, useRouter } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { AppButton } from "@/components/ui/app-button";
import { AppInput } from "@/components/ui/app-input";
import { EmptyState } from "@/components/ui/empty-state";
import { ScreenContainer } from "@/components/ui/screen-container";
import { findClothingItemById } from "@/features/wardrobe/data/find-clothing-item";
import { clothingItemThumbnailUri } from "@/features/wardrobe/lib/clothing-item-images";
import { formatCategoryLabel } from "@/features/wardrobe/lib/format-category";
import type { ClothingItem } from "@/features/wardrobe/types/clothing-item";
import { useWardrobeItems } from "@/features/wardrobe/wardrobe-service";
import {
  OUTFIT_OCCASION_LABELS,
  OUTFIT_OCCASIONS_UI_ORDER,
  type OutfitOccasion,
} from "@/features/outfit-generation/occasion-presets";
import { generateRankedOutfitSuggestions } from "@/features/outfit-generation/rule-based-generator";
import { outfitSuggestionFeedbackService } from "@/features/outfit-generation/suggestion-feedback-service";
import type { GeneratedOutfitSuggestion } from "@/features/outfit-generation/types";
import type { OutfitSuggestionFeedbackPayload } from "@/features/outfit-generation/types/suggestion-feedback";
import { outfitsService } from "@/features/outfits/outfits-service";
import { useOutfitsStore } from "@/features/outfits/state/outfits-store";
import { media } from "@/lib/constants";
import { theme } from "@/theme";

const THUMB_W = 72;

function toFeedbackPayload(
  row: GeneratedOutfitSuggestion,
  feedbackType: OutfitSuggestionFeedbackPayload["feedbackType"],
): OutfitSuggestionFeedbackPayload {
  return {
    occasion: row.occasion,
    feedbackType,
    clothingItemIds: row.clothingItemIds,
    suggestionKey: row.id,
    scoreSnapshot: row.score,
  };
}

function PieceRow({ item }: { item: ClothingItem }) {
  const thumb = clothingItemThumbnailUri(item).trim();
  return (
    <View style={styles.pieceRow}>
      <View style={styles.thumbBox}>
        {thumb.length > 0 ? (
          <Image
            source={{ uri: thumb }}
            style={styles.thumb}
            contentFit="cover"
            transition={media.imageTransitionMs.card}
          />
        ) : (
          <View style={[styles.thumb, styles.thumbPh]}>
            <Text style={styles.thumbPhText}>—</Text>
          </View>
        )}
      </View>
      <View style={styles.pieceMeta}>
        <Text style={styles.pieceName} numberOfLines={2}>
          {item.name.trim() || "Untitled"}
        </Text>
        <Text style={styles.pieceSub} numberOfLines={1}>
          {formatCategoryLabel(item.category)}
          {item.colour.trim() ? ` · ${item.colour.trim()}` : ""}
        </Text>
      </View>
    </View>
  );
}

export function SuggestOutfitScreen() {
  const router = useRouter();
  const items = useWardrobeItems();
  const outfits = useOutfitsStore((s) => s.outfits);
  const [occasion, setOccasion] = useState<OutfitOccasion>("casual");

  const ranked = useMemo(
    () =>
      generateRankedOutfitSuggestions(items, outfits, { occasion }),
    [items, outfits, occasion],
  );

  const [skippedSuggestionKeys, setSkippedSuggestionKeys] = useState<
    Set<string>
  >(() => new Set());
  const [pickIndex, setPickIndex] = useState(0);
  const [outfitName, setOutfitName] = useState("");
  const [saving, setSaving] = useState(false);

  const visibleRanked = useMemo(
    () => ranked.filter((s) => !skippedSuggestionKeys.has(s.id)),
    [ranked, skippedSuggestionKeys],
  );

  useEffect(() => {
    setSkippedSuggestionKeys(new Set());
    setPickIndex(0);
  }, [occasion]);

  useEffect(() => {
    setPickIndex((i) => {
      const n = visibleRanked.length;
      if (n === 0) return 0;
      return i % n;
    });
  }, [visibleRanked]);

  const current: GeneratedOutfitSuggestion | null =
    visibleRanked.length > 0
      ? visibleRanked[pickIndex % visibleRanked.length]!
      : null;

  useEffect(() => {
    if (current == null) return;
    setOutfitName(current.suggestedName);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only reseed name when switching ranked pick
  }, [current?.id]);

  const resolvedPieces: ClothingItem[] = useMemo(() => {
    if (current == null) return [];
    return current.clothingItemIds
      .map((id) => findClothingItemById(items, id))
      .filter((x): x is ClothingItem => x != null);
  }, [current, items]);

  const regenerate = useCallback(() => {
    setPickIndex((i) => {
      const n = visibleRanked.length;
      if (n === 0) return 0;
      return (i + 1) % n;
    });
  }, [visibleRanked.length]);

  const openInBuilder = useCallback(() => {
    if (current == null) return;
    router.push({
      pathname: "/create-outfit",
      params: { itemIds: [...current.clothingItemIds].join(",") },
    } as Href);
  }, [current, router]);

  const likeThisLook = useCallback(() => {
    if (current == null) return;
    void outfitSuggestionFeedbackService.record(
      toFeedbackPayload(current, "positive_like"),
    );
  }, [current]);

  const recordNotForMe = useCallback(() => {
    if (current == null) return;
    void outfitSuggestionFeedbackService.record(
      toFeedbackPayload(current, "negative_not_my_style"),
    );
    setSkippedSuggestionKeys((prev) => new Set(prev).add(current.id));
    setPickIndex(0);
  }, [current]);

  const recordAnotherIdea = useCallback(() => {
    if (current == null) return;
    void outfitSuggestionFeedbackService.record(
      toFeedbackPayload(current, "regenerate"),
    );
    setSkippedSuggestionKeys((prev) => new Set(prev).add(current.id));
    setPickIndex(0);
  }, [current]);

  const saveOutfit = useCallback(async () => {
    if (current == null) return;
    const trimmed =
      outfitName.trim() || current.suggestedName.trim() || "Outfit";
    setSaving(true);
    try {
      const created = await outfitsService.addOutfit({
        name: trimmed,
        clothingItemIds: [...current.clothingItemIds],
      });
      void outfitSuggestionFeedbackService.record(
        toFeedbackPayload(current, "saved"),
      );
      router.replace({
        pathname: "/outfit/[id]",
        params: { id: created.id },
      } as Href);
    } finally {
      setSaving(false);
    }
  }, [current, outfitName, router]);

  const occasionPicker = (
    <View style={styles.occasionBlock}>
      <Text style={styles.sectionLabel}>Occasion</Text>
      <Text style={styles.occasionSub}>
        Picks and ordering use your tags, names, colours, and categories — still only
        items you own.
      </Text>
      <View style={styles.chipWrap}>
        {OUTFIT_OCCASIONS_UI_ORDER.map((key) => (
          <Pressable
            key={key}
            onPress={() => setOccasion(key)}
            accessibilityRole="button"
            accessibilityState={{ selected: occasion === key }}
            accessibilityLabel={`Occasion ${OUTFIT_OCCASION_LABELS[key]}`}
            style={({ pressed }) => [
              styles.chip,
              occasion === key && styles.chipOn,
              pressed && styles.chipPressed,
            ]}
          >
            <Text
              style={[
                styles.chipText,
                occasion === key && styles.chipTextOn,
              ]}
              numberOfLines={1}
            >
              {OUTFIT_OCCASION_LABELS[key]}
            </Text>
          </Pressable>
        ))}
      </View>
    </View>
  );

  if (items.length === 0) {
    return (
      <ScreenContainer scroll omitTopSafeArea contentContainerStyle={styles.emptyWrap}>
        <EmptyState
          title="Add wardrobe pieces first"
          description="Smart suggestions mix your own tops, bottoms, dresses, shoes, and layers. Add items under Wardrobe, then come back here."
        />
      </ScreenContainer>
    );
  }

  if (ranked.length === 0) {
    return (
      <ScreenContainer scroll={false} omitTopSafeArea style={styles.screen}>
        <ScrollView
          contentContainerStyle={[styles.scrollEmpty, styles.emptyWrap]}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {occasionPicker}
          <EmptyState
            title="Not enough to compose yet"
            description="You need at least a dress and shoes, or a top and bottom. If everything is already saved as outfits, try new pieces—or remove duplicates from your closet."
          />
          <AppButton
            label="Go to Wardrobe"
            onPress={() => router.push("/(tabs)" as Href)}
            variant="secondary"
            fullWidth
            style={styles.emptyCta}
          />
        </ScrollView>
      </ScreenContainer>
    );
  }

  if (ranked.length > 0 && visibleRanked.length === 0) {
    return (
      <ScreenContainer scroll={false} omitTopSafeArea style={styles.screen}>
        <ScrollView
          contentContainerStyle={[styles.scrollEmpty, styles.emptyWrap]}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {occasionPicker}
          <EmptyState
            title="No suggestions left in this round"
            description="You skipped or dismissed every combo for this occasion. Show them again, or pick another occasion."
          />
          <AppButton
            label="Show suggestions again"
            onPress={() => {
              setSkippedSuggestionKeys(new Set());
              setPickIndex(0);
            }}
            fullWidth
            style={styles.emptyCta}
          />
        </ScrollView>
      </ScreenContainer>
    );
  }

  if (current == null) return null;

  return (
    <ScreenContainer scroll omitTopSafeArea style={styles.screen}>
      <ScrollView
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {occasionPicker}

        <Text style={styles.lede}>
          Rule-based mixer on your device. Quick reactions below are saved to improve
          future ranking (locally always; to your Supabase project when signed in).
        </Text>

        <View style={styles.occasionPill} accessibilityRole="text">
          <Text style={styles.occasionPillLabel}>Chosen occasion</Text>
          <Text style={styles.occasionPillValue}>
            {OUTFIT_OCCASION_LABELS[current.occasion]}
          </Text>
        </View>

        <View style={styles.draftBanner} accessibilityRole="summary">
          <Text style={styles.draftBannerTitle}>Suggested look (not saved)</Text>
          <Text style={styles.draftBannerSub}>
            This preview is not in your Outfits tab yet. Save once to store it as
            a normal outfit with the same pieces — the name below includes your
            occasion when you use the suggested title.
          </Text>
        </View>

        <View style={styles.explainCard}>
          <Text style={styles.explainBand}>{current.explanation.bandLabel}</Text>
          <Text style={styles.explainSummary}>{current.explanation.summaryLine}</Text>
          <Text style={styles.explainDisclaimer}>
            {current.explanation.pointsDisclaimer}
          </Text>
          {current.explanation.sections.map((sec) => (
            <View key={sec.heading} style={styles.explainSection}>
              <Text style={styles.explainSectionTitle}>{sec.heading}</Text>
              {sec.bullets.map((b, bi) => (
                <Text
                  key={`${sec.heading}-${bi}`}
                  style={styles.explainBullet}
                >
                  • {b}
                </Text>
              ))}
            </View>
          ))}
          <Text style={styles.explainFormula}>{current.explanation.formulaNote}</Text>
          <Text style={styles.explainVersion}>
            {`Rule recipe v${current.explanation.scoringVersion} — see suggestion-scoring.ts`}
          </Text>
        </View>

        {visibleRanked.length > 1 ? (
          <Text style={styles.regenHint}>
            {`Suggestion ${(pickIndex % visibleRanked.length) + 1} of ${visibleRanked.length} in this set — Regenerate cycles; Another skips this combo.`}
          </Text>
        ) : null}

        <Text style={styles.feedbackCaption}>Quick reaction (optional)</Text>
        <View style={styles.feedbackRow}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Like this suggestion"
            onPress={likeThisLook}
            disabled={saving}
            style={({ pressed }) => [
              styles.feedbackBtn,
              pressed && styles.feedbackBtnPressed,
            ]}
          >
            <Text style={styles.feedbackBtnText}>Like</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Not my style, show a different combo"
            onPress={recordNotForMe}
            disabled={saving}
            style={({ pressed }) => [
              styles.feedbackBtn,
              pressed && styles.feedbackBtnPressed,
            ]}
          >
            <Text style={styles.feedbackBtnText}>Not my style</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Another idea"
            onPress={recordAnotherIdea}
            disabled={saving}
            style={({ pressed }) => [
              styles.feedbackBtn,
              pressed && styles.feedbackBtnPressed,
            ]}
          >
            <Text style={styles.feedbackBtnText}>Another</Text>
          </Pressable>
        </View>

        <Text style={styles.sectionLabel}>Pieces</Text>
        <View style={styles.card}>
          {resolvedPieces.map((item) => (
            <PieceRow key={item.id} item={item} />
          ))}
        </View>

        <Text style={styles.saveCaption}>
          One tap saves using the suggested name (with occasion). Optionally edit
          the name first.
        </Text>
        <AppButton
          label={saving ? "Saving…" : "Save outfit"}
          onPress={() => void saveOutfit()}
          fullWidth
          loading={saving}
          disabled={saving}
          accessibilityHint="Creates this outfit in your saved list and opens it"
        />

        <AppInput
          label="Custom name (optional)"
          value={outfitName}
          onChangeText={setOutfitName}
          placeholder={current.suggestedName}
          autoCapitalize="words"
        />

        <View style={styles.actions}>
          {visibleRanked.length > 1 ? (
            <AppButton
              label="Regenerate suggestion"
              onPress={regenerate}
              variant="secondary"
              fullWidth
              disabled={saving}
            />
          ) : null}
          <AppButton
            label="Open in builder"
            onPress={openInBuilder}
            variant="secondary"
            fullWidth
            disabled={saving}
            accessibilityHint="Adjust selection on the new-outfit screen without saving yet"
          />
        </View>

        {saving ? (
          <View style={styles.savingRow}>
            <ActivityIndicator color={theme.colors.primary} />
          </View>
        ) : null}
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
  },
  scroll: {
    paddingBottom: theme.spacing.xl,
    maxWidth: 560,
    width: "100%",
    alignSelf: "center",
    ...(Platform.OS === "web" ? { boxSizing: "border-box" as const } : {}),
  },
  scrollEmpty: {
    paddingBottom: theme.spacing.xl,
    flexGrow: 1,
    maxWidth: 560,
    width: "100%",
    alignSelf: "center",
  },
  occasionBlock: {
    marginBottom: theme.spacing.md,
  },
  occasionSub: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    lineHeight: 18,
    marginBottom: theme.spacing.sm,
  },
  chipWrap: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: theme.spacing.sm,
  },
  chip: {
    paddingVertical: theme.spacing.sm,
    paddingHorizontal: theme.spacing.md,
    borderRadius: theme.radii.full,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
    maxWidth: "100%",
  },
  chipOn: {
    borderColor: theme.colors.primary,
    backgroundColor: "rgba(32, 138, 239, 0.08)",
  },
  chipPressed: {
    opacity: 0.9,
  },
  chipText: {
    fontSize: theme.typography.fontSize.sm,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
  },
  chipTextOn: {
    color: theme.colors.primary,
  },
  occasionPill: {
    borderRadius: theme.radii.md,
    borderWidth: 1,
    borderColor: theme.colors.primary,
    backgroundColor: "rgba(32, 138, 239, 0.06)",
    padding: theme.spacing.md,
    marginBottom: theme.spacing.md,
    gap: theme.spacing.xxs,
  },
  occasionPillLabel: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  occasionPillValue: {
    fontSize: theme.typography.fontSize.lg,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  draftBanner: {
    borderRadius: theme.radii.md,
    borderWidth: 1,
    borderStyle: "dashed",
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.background,
    padding: theme.spacing.md,
    marginBottom: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  draftBannerTitle: {
    fontSize: theme.typography.fontSize.sm,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  draftBannerSub: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    lineHeight: 18,
  },
  saveCaption: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    lineHeight: 18,
    marginTop: theme.spacing.md,
    marginBottom: theme.spacing.sm,
  },
  emptyWrap: {
    paddingTop: theme.spacing.xl,
    paddingHorizontal: theme.spacing.md,
    flexGrow: 1,
  },
  emptyCta: {
    marginTop: theme.spacing.lg,
  },
  lede: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    lineHeight: 20,
    marginBottom: theme.spacing.md,
  },
  explainCard: {
    borderRadius: theme.radii.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
    padding: theme.spacing.md,
    marginBottom: theme.spacing.md,
    gap: theme.spacing.sm,
  },
  explainBand: {
    fontSize: theme.typography.fontSize.panel,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.primary,
  },
  explainSummary: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.text,
    lineHeight: 20,
  },
  explainDisclaimer: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    lineHeight: 18,
  },
  explainSection: {
    marginTop: theme.spacing.xs,
    gap: theme.spacing.xxs,
  },
  explainSectionTitle: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.5,
    marginTop: theme.spacing.xs,
  },
  explainBullet: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.text,
    lineHeight: 20,
    paddingLeft: theme.spacing.xs,
  },
  explainFormula: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    lineHeight: 18,
    marginTop: theme.spacing.sm,
    ...Platform.select({
      ios: { fontFamily: "Menlo" },
      android: { fontFamily: "monospace" },
      default: { fontFamily: "monospace" },
    }),
  },
  explainVersion: {
    fontSize: theme.typography.fontSize.xs,
    color: theme.colors.textMuted,
  },
  regenHint: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    marginBottom: theme.spacing.md,
    lineHeight: 18,
  },
  feedbackCaption: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.5,
    marginBottom: theme.spacing.sm,
  },
  feedbackRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: theme.spacing.sm,
    marginBottom: theme.spacing.md,
  },
  feedbackBtn: {
    paddingVertical: theme.spacing.sm,
    paddingHorizontal: theme.spacing.md,
    borderRadius: theme.radii.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
  },
  feedbackBtnPressed: {
    opacity: 0.88,
  },
  feedbackBtnText: {
    fontSize: theme.typography.fontSize.sm,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  sectionLabel: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.6,
    marginBottom: theme.spacing.sm,
    marginTop: theme.spacing.sm,
  },
  card: {
    borderRadius: theme.radii.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
    overflow: "hidden",
  },
  pieceRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
    paddingHorizontal: theme.spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: theme.colors.border,
  },
  thumbBox: {
    borderRadius: theme.radii.sm,
    overflow: "hidden",
  },
  thumb: {
    width: THUMB_W,
    height: Math.round((THUMB_W * 4) / 3),
    backgroundColor: theme.colors.border,
  },
  thumbPh: {
    alignItems: "center",
    justifyContent: "center",
  },
  thumbPhText: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.fontSize.sm,
  },
  pieceMeta: {
    flex: 1,
    minWidth: 0,
  },
  pieceName: {
    fontSize: theme.typography.fontSize.md,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  pieceSub: {
    marginTop: 2,
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
  },
  actions: {
    marginTop: theme.spacing.lg,
    gap: theme.spacing.sm,
  },
  savingRow: {
    marginTop: theme.spacing.md,
    alignItems: "center",
  },
});
