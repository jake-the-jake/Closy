import { Image } from "expo-image";
import * as FileSystem from "expo-file-system/legacy";
import { useRouter } from "expo-router";
import { useCallback, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Platform,
  ScrollView,
  Share,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { AppButton } from "@/components/ui/app-button";
import { ScreenContainer } from "@/components/ui/screen-container";

import {
  buildAvatarExportRequest,
  buildNpmCliCommand,
  canUseCacheDirectoryForExport,
  getClosyRepoRoot,
  requestRelativePathForRenderId,
  runAvatarExport,
  saveAvatarExportRequest,
  type AvatarOutfitLike,
} from "@/features/avatar-export";
import { runAvatarExportMock } from "@/features/avatar-export/runner/avatarExportRunner.mock";
import { theme } from "@/theme";

type PoseKey = "relaxed" | "walk" | "tpose" | "apose";

type PresetKey = "default" | "navy" | "casual";

const PRESETS: Record<PresetKey, AvatarOutfitLike> = {
  default: {
    top: { kind: "jumper" },
    bottom: { kind: "trousers" },
  },
  navy: {
    top: { kind: "jumper", color: [0.12, 0.18, 0.42] },
    bottom: { kind: "trousers", color: [0.15, 0.16, 0.2] },
  },
  casual: {
    top: { kind: "shirt", color: [0.85, 0.35, 0.32] },
    bottom: { kind: "trousers", color: [0.28, 0.32, 0.38] },
    shoes: { kind: "shoes", color: [0.65, 0.64, 0.62] },
  },
};

export function AvatarPreviewDevScreen() {
  const router = useRouter();
  const [pose, setPose] = useState<PoseKey>("relaxed");
  const [preset, setPreset] = useState<PresetKey>("default");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [cliHint, setCliHint] = useState<string | null>(null);
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [lastJsonPreview, setLastJsonPreview] = useState<string | null>(null);

  const repoRoot = useMemo(() => getClosyRepoRoot(), []);
  const mockOn = process.env.EXPO_PUBLIC_AVATAR_EXPORT_MOCK === "1";
  const canPollPng = Platform.OS !== "web" && repoRoot != null;
  const canUseCache = canUseCacheDirectoryForExport();
  const envRawLen =
    typeof process.env.EXPO_PUBLIC_CLOSY_REPO_ROOT === "string"
      ? process.env.EXPO_PUBLIC_CLOSY_REPO_ROOT.length
      : 0;

  const onShareCommand = useCallback(async (cmd: string) => {
    try {
      await Share.share({ message: cmd, title: "Closy avatar export" });
      setStatus((s) => s ?? "Share sheet dismissed.");
    } catch {
      /* user cancelled */
    }
  }, []);

  const onShareJson = useCallback(async (json: string) => {
    try {
      await Share.share({ message: json, title: "Closy outfit JSON" });
    } catch {
      /* user cancelled */
    }
  }, []);

  const onGenerate = useCallback(async () => {
    setBusy(true);
    setError(null);
    setStatus(null);
    setWarnings([]);
    setImageUri(null);
    setLastJsonPreview(null);
    try {
      const outfit = PRESETS[preset];
      const request = buildAvatarExportRequest(outfit, {
        pose,
        width: 1024,
        height: 1024,
        camera: "three_quarter",
        renderId: `dev_${preset}_${pose}_${Date.now()}`,
      });
      const saved = await saveAvatarExportRequest(request);
      setLastJsonPreview(saved.jsonForEngine);
      const cmd = buildNpmCliCommand(saved.renderId);
      setCliHint(cmd);

      const persisted =
        saved.repoWriteSucceeded || saved.cacheWriteSucceeded;
      setWarnings(saved.warnings);

      if (!persisted) {
        setError(
          saved.warnings.length > 0
            ? saved.warnings.join("\n\n")
            : "Could not save the request JSON to disk.",
        );
        if (repoRoot == null) {
          setStatus(
            "Repo root env not loaded. Set EXPO_PUBLIC_CLOSY_REPO_ROOT in .env and restart Expo (`npx expo start --clear`). You can still share the JSON below.",
          );
        }
        setBusy(false);
        return;
      }

      setError(null);

      const exportResult = await runAvatarExport(saved, {
        poll: Platform.OS !== "web",
        pollTimeoutMs: 120_000,
      });

      if (exportResult.ok && exportResult.variant === "manual_cli") {
        const reqRel = requestRelativePathForRenderId(saved.renderId);
        const head = saved.repoWriteSucceeded
          ? `Request saved to ${reqRel}.`
          : "Request stored in app cache.";
        setStatus(
          `${head}\n\n${exportResult.message}\n\nOutput: ${exportResult.outputPathForDisplay}\nCLI: ${exportResult.cliCommand}`,
        );
      } else if (exportResult.ok && exportResult.variant === "image") {
        setImageUri(exportResult.imageUri);
        const prefix =
          Platform.OS === "web"
            ? ""
            : "PNG found.\n\n";
        setStatus(
          `${prefix}Loaded render (${exportResult.mode}).`,
        );
      } else if (!exportResult.ok) {
        const prefix =
          saved.cacheWriteSucceeded && !saved.repoWriteSucceeded
            ? "Request is in app cache only; poll/repo path may be unavailable.\n\n"
            : "";
        setError(
          `${prefix}${exportResult.message}${exportResult.cliCommand ? `\n\n${exportResult.cliCommand}` : ""}`,
        );
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setBusy(false);
    }
  }, [pose, preset, repoRoot]);

  const onMock = useCallback(async () => {
    setBusy(true);
    setError(null);
    setWarnings([]);
    setImageUri(null);
    try {
      const request = buildAvatarExportRequest(PRESETS.casual, {
        pose: "relaxed",
        renderId: `mock_${Date.now()}`,
      });
      const saved = await saveAvatarExportRequest(request);
      if (!saved.repoWriteSucceeded && !saved.cacheWriteSucceeded) {
        setWarnings(saved.warnings);
        setError(
          saved.warnings.join("\n\n") ||
            "Save failed; mock preview can still run.",
        );
      } else {
        setWarnings(saved.warnings);
      }
      const result = await runAvatarExportMock(saved);
      if (result.ok && result.variant === "image") {
        setImageUri(result.imageUri);
        setStatus("Mock image (no native binary).");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setBusy(false);
    }
  }, []);

  const primaryLabel =
    Platform.OS === "web"
      ? "Save request & show CLI (web)"
      : "Save request & poll for PNG";

  return (
    <ScreenContainer scroll={false} omitTopSafeArea style={styles.root}>
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        <Text style={styles.title}>Avatar preview (dev)</Text>

        <Text style={styles.hint}>
          <Text style={styles.hintStrong}>Web: </Text>
          writes JSON into{" "}
          <Text style={styles.mono}>generated/avatar_requests/</Text> when repo
          root is set; you run{" "}
          <Text style={styles.mono}>npm run closy:avatar-export -- &lt;id&gt;</Text>{" "}
          locally and open the PNG from disk (no in-browser PNG poll).
          {"\n\n"}
          <Text style={styles.hintStrong}>Native: </Text>
          same JSON handoff; the app can poll{" "}
          <Text style={styles.mono}>generated/avatar_renders/</Text> after you run
          the CLI (or if the file already exists).
        </Text>

        <View style={styles.diagnostics}>
          <Text style={styles.diagnosticsTitle}>Diagnostics</Text>
          <Text style={styles.diagnosticsLine}>
            Platform: {Platform.OS}
          </Text>
          <Text style={styles.diagnosticsLine}>
            Repo root (resolved):{" "}
            {repoRoot ?? "— not set —"}
          </Text>
          <Text style={styles.diagnosticsLine}>
            EXPO_PUBLIC_CLOSY_REPO_ROOT raw length: {envRawLen} (0 means unset at
            bundle time)
          </Text>
          <Text style={styles.diagnosticsLine}>
            Mock mode: {mockOn ? "on" : "off"}
          </Text>
          <Text style={styles.diagnosticsLine}>
            Can poll local PNG: {canPollPng ? "yes" : "no"}
          </Text>
          <Text style={styles.diagnosticsLine}>
            Can use FileSystem cache dir: {canUseCache ? "yes" : "no"}
            {Platform.OS === "web" ? " (skipped on web)" : ""}
            {FileSystem.cacheDirectory == null && Platform.OS !== "web"
              ? " — null"
              : ""}
          </Text>
          {repoRoot == null ? (
            <Text style={styles.diagnosticsHint}>
              If you added EXPO_PUBLIC_CLOSY_REPO_ROOT to `.env`, restart Metro
              with `npx expo start --clear` so it inlines into the bundle.
            </Text>
          ) : null}
        </View>

        <Text style={styles.section}>Pose</Text>
        <View style={styles.row}>
          {(["relaxed", "walk", "tpose", "apose"] as const).map((p) => (
            <AppButton
              key={p}
              label={p}
              variant={pose === p ? "primary" : "secondary"}
              onPress={() => setPose(p)}
              disabled={busy}
            />
          ))}
        </View>

        <Text style={styles.section}>Outfit preset</Text>
        <View style={styles.row}>
          {(["default", "navy", "casual"] as const).map((p) => (
            <AppButton
              key={p}
              label={p}
              variant={preset === p ? "primary" : "secondary"}
              onPress={() => setPreset(p)}
              disabled={busy}
            />
          ))}
        </View>

        <AppButton
          label={primaryLabel}
          onPress={() => void onGenerate()}
          loading={busy}
          disabled={busy}
          fullWidth
        />

        {repoRoot == null ? (
          <Text style={styles.callout}>
            Repo root is missing: the button above still builds the request and
            you can share the JSON, but the CLI handoff needs{" "}
            <Text style={styles.mono}>EXPO_PUBLIC_CLOSY_REPO_ROOT</Text> set and
            Expo restarted so the file is written into{" "}
            <Text style={styles.mono}>generated/avatar_requests/</Text>.
          </Text>
        ) : null}

        {cliHint ? (
          <View style={styles.cliBox}>
            <Text style={styles.cliText} selectable>
              {cliHint}
            </Text>
            <AppButton
              label="Share command"
              variant="secondary"
              onPress={() => void onShareCommand(cliHint)}
              disabled={busy}
              fullWidth
            />
          </View>
        ) : null}

        <AppButton
          label="Mock image (no native binary)"
          variant="secondary"
          onPress={() => void onMock()}
          disabled={busy}
          fullWidth
        />

        {lastJsonPreview ? (
          <View style={styles.jsonBox}>
            <Text style={styles.section}>Last request JSON</Text>
            <Text style={styles.jsonPreview} selectable numberOfLines={8}>
              {lastJsonPreview}
            </Text>
            <AppButton
              label="Share JSON"
              variant="secondary"
              onPress={() => void onShareJson(lastJsonPreview)}
              disabled={busy}
              fullWidth
            />
          </View>
        ) : null}

        {warnings.length > 0 ? (
          <View style={styles.warningsBox}>
            {warnings.map((w) => (
              <Text key={w} style={styles.warningText}>
                {w}
              </Text>
            ))}
          </View>
        ) : null}

        {status ? <Text style={styles.status}>{status}</Text> : null}
        {error ? <Text style={styles.error}>{error}</Text> : null}

        {busy ? <ActivityIndicator color={theme.colors.primary} /> : null}

        {imageUri ? (
          <Image
            source={{ uri: imageUri }}
            style={styles.preview}
            contentFit="contain"
            accessibilityLabel="Exported avatar preview"
          />
        ) : null}

        <AppButton
          label="Back"
          variant="secondary"
          onPress={() => router.back()}
          fullWidth
        />
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
  },
  scroll: {
    padding: theme.spacing.md,
    paddingBottom: theme.spacing.xl,
    gap: theme.spacing.md,
    maxWidth: 520,
    alignSelf: "center",
    width: "100%",
  },
  title: {
    fontSize: theme.typography.fontSize.lg,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  hint: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
    lineHeight: 20,
  },
  hintStrong: {
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  mono: {
    fontFamily: Platform.select({ web: "monospace", default: "monospace" }),
    fontSize: theme.typography.fontSize.caption,
  },
  diagnostics: {
    padding: theme.spacing.sm,
    borderRadius: theme.radii.sm,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
    gap: 6,
  },
  diagnosticsTitle: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
    textTransform: "uppercase",
  },
  diagnosticsLine: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.text,
    fontFamily: Platform.select({ web: "monospace", default: "monospace" }),
  },
  diagnosticsHint: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    lineHeight: 18,
    marginTop: 4,
  },
  callout: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
    lineHeight: 20,
    padding: theme.spacing.sm,
    borderRadius: theme.radii.sm,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  section: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
    textTransform: "uppercase",
  },
  row: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: theme.spacing.sm,
  },
  cliBox: {
    gap: theme.spacing.sm,
    padding: theme.spacing.sm,
    borderRadius: theme.radii.sm,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  cliText: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.text,
    fontFamily: Platform.select({ web: "monospace", default: "monospace" }),
  },
  jsonBox: {
    gap: theme.spacing.sm,
  },
  jsonPreview: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    fontFamily: Platform.select({ web: "monospace", default: "monospace" }),
  },
  warningsBox: {
    gap: 8,
    padding: theme.spacing.sm,
    borderRadius: theme.radii.sm,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  warningText: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
    lineHeight: 20,
  },
  status: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.text,
    lineHeight: 20,
  },
  error: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.danger,
    lineHeight: 20,
  },
  preview: {
    width: "100%",
    aspectRatio: 1,
    backgroundColor: theme.colors.border,
    borderRadius: theme.radii.md,
  },
});
