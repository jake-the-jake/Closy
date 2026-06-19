import { useMemo, useState } from "react";
import {
  Pressable,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";

import { AppButton } from "@/components/ui/app-button";
import { ScreenContainer } from "@/components/ui/screen-container";
import {
  cloneFitState,
  DEFAULT_BODY_SHAPE,
  DEFAULT_GARMENT_FIT_STATE,
} from "@/features/avatar-export";
import {
  DEV_AVATAR_PRESETS,
  type DevAvatarPoseKey,
  type DevAvatarPresetKey,
} from "@/features/avatar-export/dev-avatar-shared";
import { theme } from "@/theme";

import {
  getAvatarSourceOptionsForRoute,
  type AvatarSourcePreference,
  type AvatarSourceRouteOption,
} from "./avatarSourceResolver";
import { AvatarViewportLive } from "./avatar-viewport-live";
import type { LiveViewportPoseFitDebug } from "./live-viewport-debug-types";

const POSES: DevAvatarPoseKey[] = ["relaxed", "walk", "tpose", "apose"];
const USER_AVATAR_SOURCE_OPTIONS = getAvatarSourceOptionsForRoute("user");

export function AvatarExperienceScreen() {
  const { height } = useWindowDimensions();
  const [pose, setPose] = useState<DevAvatarPoseKey>("relaxed");
  const [preset, setPreset] = useState<DevAvatarPresetKey>("default");
  const [avatarSourcePreference, setAvatarSourcePreference] = useState<AvatarSourcePreference>(
    USER_AVATAR_SOURCE_OPTIONS.defaultPreference,
  );
  const [cameraResetNonce, setCameraResetNonce] = useState(0);
  const [debugOpen, setDebugOpen] = useState(false);
  const [debug, setDebug] = useState<LiveViewportPoseFitDebug | null>(null);

  const viewportHeight = Math.min(520, Math.max(360, height * 0.52));
  const garmentFit = useMemo(() => cloneFitState(DEFAULT_GARMENT_FIT_STATE), []);
  const userAvatarSourceOptions = USER_AVATAR_SOURCE_OPTIONS.options.filter(
    (sourceOption) => !sourceOption.disabled,
  );
  const selectedAvatarSource =
    userAvatarSourceOptions.find(
      (sourceOption) => sourceOption.preference === avatarSourcePreference,
    ) ?? userAvatarSourceOptions[0];
  const resolvedAvatarSourcePreference =
    selectedAvatarSource?.preference ?? USER_AVATAR_SOURCE_OPTIONS.defaultPreference;

  return (
    <ScreenContainer scroll omitTopSafeArea style={styles.screen}>
      <View style={styles.shell}>
        <View style={styles.heroCopy}>
          <Text style={styles.eyebrow}>Avatar try-on</Text>
          <Text style={styles.title}>Preview your outfit on a clean mannequin</Text>
          <Text style={styles.subtitle}>
            A stable v1 fitting preview for checking outfit shape, pose, and proportion before
            the full avatar pipeline lands.
          </Text>
        </View>

        <View style={styles.viewportCard}>
          <AvatarViewportLive
            pose={pose}
            preset={preset}
            garmentFit={garmentFit}
            liveShading="normal"
            bodyShape={DEFAULT_BODY_SHAPE}
            height={viewportHeight}
            avatarSourcePreference={resolvedAvatarSourcePreference}
            avatarRouteMode="user"
            layout="workbench"
            cameraResetNonce={cameraResetNonce}
            activeTab="view"
            cleanMode
            onLiveViewportPoseFitDebug={__DEV__ ? setDebug : undefined}
          />
        </View>

        <View style={styles.controlCard}>
          <Text style={styles.sectionTitle}>Outfit</Text>
          <View style={styles.chipRow}>
            {(Object.keys(DEV_AVATAR_PRESETS) as DevAvatarPresetKey[]).map((key) => (
              <Chip
                key={key}
                label={key}
                selected={preset === key}
                onPress={() => setPreset(key)}
              />
            ))}
          </View>

          <Text style={styles.sectionTitle}>Pose</Text>
          <View style={styles.chipRow}>
            {POSES.map((key) => (
              <Chip
                key={key}
                label={key}
                selected={pose === key}
                onPress={() => setPose(key)}
              />
            ))}
          </View>

          {userAvatarSourceOptions.length > 1 ? (
            <>
              <Text style={styles.sectionTitle}>Avatar style</Text>
              <View style={styles.styleGrid}>
                {userAvatarSourceOptions.map((style) => (
                  <StyleCard
                    key={style.id}
                    styleOption={style}
                    selected={avatarSourcePreference === style.preference}
                    onPress={() => setAvatarSourcePreference(style.preference)}
                  />
                ))}
              </View>
            </>
          ) : null}

          <View style={styles.actions}>
            <AppButton
              label="Reset view"
              variant="secondary"
              onPress={() => setCameraResetNonce((n) => n + 1)}
            />
            <Text style={styles.hint}>Drag to rotate. Pinch or wheel to zoom.</Text>
          </View>
        </View>

        {__DEV__ ? (
          <View style={styles.devCard}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Toggle avatar diagnostics"
              onPress={() => setDebugOpen((open) => !open)}
              style={({ pressed }) => [styles.devHeader, pressed && styles.pressed]}
            >
              <Text style={styles.devTitle}>Developer diagnostics</Text>
              <Text style={styles.devToggle}>{debugOpen ? "Hide" : "Show"}</Text>
            </Pressable>
            {debugOpen ? (
              <View style={styles.devLines}>
                <Text style={styles.devLine}>
                  route={debug?.bodySource?.routeMode ?? "user"} source=
                  {debug?.bodySource?.resolvedLabel ?? debug?.avatar?.avatarSource ?? "n/a"} load=
                  {debug?.avatar?.loadStatus ?? "n/a"}
                </Text>
                <Text style={styles.devLine}>
                  lifecycle requested={debug?.sourceLifecycle?.requestedPreference ?? "n/a"} candidate=
                  {debug?.sourceLifecycle?.candidateAssetId ?? "n/a"} visible=
                  {debug?.sourceLifecycle?.activeVisibleAssetId ?? "n/a"} phase=
                  {debug?.sourceLifecycle?.phase ?? "n/a"}
                </Text>
                <Text style={styles.devLine}>
                  startup={debug?.startup?.phase ?? "n/a"} meshes=
                  {debug?.renderAudit?.visibleMeshCount ?? debug?.startup?.visibleMeshCount ?? "n/a"}
                </Text>
                <Text style={styles.devLine}>
                  canvasH={Math.round(viewportHeight)} intent=
                  {debug?.bodySource?.loadIntent ?? "n/a"} visibleDefault=
                  {debug?.bodySource?.visibleByDefault ? "yes" : "no"}
                </Text>
                <Text style={styles.devLine}>
                  asset={debug?.bodySource?.assetManifestId ?? "n/a"} availability=
                  {debug?.bodySource?.assetAvailability ?? "n/a"}
                </Text>
                <Text style={styles.devLine}>
                  audit meshes={debug?.avatar?.meshCount ?? "n/a"} visible=
                  {debug?.avatar?.visibleMeshCount ?? "n/a"} skinned=
                  {debug?.avatar?.skinnedMeshCount ?? "n/a"} materialSafety=
                  {debug?.avatar?.materialSafetyStatus ?? "n/a"}
                </Text>
                <Text style={styles.devLine}>
                  child valid={debug?.renderableReport?.valid == null
                    ? "n/a"
                    : debug.renderableReport.valid
                      ? "yes"
                      : "no"} reason={debug?.renderableReport?.reason ?? "n/a"} childMeshes=
                  {debug?.renderableReport
                    ? `${debug.renderableReport.visibleMeshCount}/${debug.renderableReport.meshCount}`
                    : "n/a"}
                </Text>
                <Text style={styles.devLine}>
                  branch={debug?.renderAudit?.activeRenderBranchName ?? "n/a"} fallback=
                  {debug?.renderAudit?.safetyFallbackReason ??
                    debug?.sourceLifecycle?.failureReason ??
                    debug?.bodySource?.errorReason ??
                    debug?.avatar?.fallbackReason ??
                    "none"}
                </Text>
                <Text style={styles.devLine}>
                  camera r={debug?.renderAudit?.cameraRadius?.toFixed(2) ?? "n/a"} target=[
                  {debug?.renderAudit?.cameraTarget?.map((n) => n.toFixed(2)).join(", ") ?? "n/a"}]
                </Text>
              </View>
            ) : null}
          </View>
        ) : null}
      </View>
    </ScreenContainer>
  );
}

function StyleCard({
  styleOption,
  selected,
  onPress,
}: {
  styleOption: AvatarSourceRouteOption;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={({ pressed }) => [
        styles.styleCard,
        selected && styles.styleCardSelected,
        pressed && styles.pressed,
      ]}
    >
      <View style={styles.styleSwatch} />
      <View style={styles.styleCopy}>
        <Text style={[styles.styleTitle, selected && styles.styleTitleSelected]}>
          {styleOption.label}
        </Text>
        <Text style={styles.styleDescription}>{styleOption.description}</Text>
      </View>
    </Pressable>
  );
}

function Chip({
  label,
  selected,
  onPress,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={({ pressed }) => [
        styles.chip,
        selected && styles.chipSelected,
        pressed && styles.pressed,
      ]}
    >
      <Text style={[styles.chipLabel, selected && styles.chipLabelSelected]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: {
    paddingHorizontal: theme.spacing.md,
  },
  shell: {
    width: "100%",
    maxWidth: 560,
    alignSelf: "center",
    gap: theme.spacing.md,
    paddingBottom: theme.spacing.xl,
  },
  heroCopy: {
    gap: theme.spacing.xs,
  },
  eyebrow: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.primary,
    textTransform: "uppercase",
    letterSpacing: 0.7,
  },
  title: {
    fontSize: theme.typography.fontSize.xl,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  subtitle: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
    lineHeight: 20,
  },
  viewportCard: {
    borderRadius: theme.radii.lg,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
    padding: theme.spacing.sm,
  },
  controlCard: {
    borderRadius: theme.radii.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
    padding: theme.spacing.md,
    gap: theme.spacing.sm,
  },
  sectionTitle: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  chipRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: theme.spacing.sm,
    marginBottom: theme.spacing.xs,
  },
  styleGrid: {
    gap: theme.spacing.sm,
    marginBottom: theme.spacing.xs,
  },
  styleCard: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.sm,
    borderRadius: theme.radii.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.background,
    padding: theme.spacing.sm,
  },
  styleCardSelected: {
    borderColor: theme.colors.primary,
    backgroundColor: theme.colors.surface,
  },
  styleSwatch: {
    width: 42,
    height: 42,
    borderRadius: theme.radii.md,
    backgroundColor: "#d9b48f",
  },
  styleCopy: {
    flex: 1,
    minWidth: 0,
  },
  styleTitle: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.text,
    fontWeight: theme.typography.fontWeight.semibold,
  },
  styleTitleSelected: {
    color: theme.colors.primary,
  },
  styleDescription: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    lineHeight: 16,
  },
  chip: {
    borderRadius: theme.radii.full,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.background,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
  },
  chipSelected: {
    borderColor: theme.colors.primary,
    backgroundColor: theme.colors.primary,
  },
  chipLabel: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.text,
    fontWeight: theme.typography.fontWeight.semibold,
  },
  chipLabelSelected: {
    color: theme.colors.surface,
  },
  actions: {
    gap: theme.spacing.sm,
    marginTop: theme.spacing.xs,
  },
  hint: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    textAlign: "center",
  },
  pressed: {
    opacity: 0.86,
  },
  devCard: {
    borderRadius: theme.radii.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
    overflow: "hidden",
  },
  devHeader: {
    padding: theme.spacing.md,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: theme.spacing.md,
  },
  devTitle: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.text,
    fontWeight: theme.typography.fontWeight.semibold,
  },
  devToggle: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.primary,
    fontWeight: theme.typography.fontWeight.semibold,
  },
  devLines: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: theme.colors.border,
    padding: theme.spacing.md,
    gap: 4,
  },
  devLine: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    fontFamily: "monospace",
  },
});
