import { Image } from "expo-image";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { AppButton } from "@/components/ui/app-button";
import { ScreenContainer } from "@/components/ui/screen-container";
import { useAuth } from "@/features/auth";
import {
  buildAccountProfile,
  displayInitials,
} from "../types/account-profile";
import { media } from "@/lib/constants";
import { theme } from "@/theme";

export function ProfileAccountView() {
  const {
    user,
    isAuthenticated,
    initializing,
    supabaseConfigured,
    signOut,
    updateProfileDisplayName,
  } = useAuth();

  const profile = useMemo(
    () => (user ? buildAccountProfile(user) : null),
    [user],
  );

  const [draftDisplayName, setDraftDisplayName] = useState("");
  const [savingName, setSavingName] = useState(false);
  const [nameNotice, setNameNotice] = useState<string | null>(null);
  const [nameError, setNameError] = useState<string | null>(null);
  const [signingOut, setSigningOut] = useState(false);

  useEffect(() => {
    if (!profile) return;
    setDraftDisplayName(profile.displayName);
    setNameNotice(null);
    setNameError(null);
  }, [profile]);

  const nameDirty =
    profile != null && draftDisplayName.trim() !== profile.displayName.trim();

  const onSaveDisplayName = useCallback(async () => {
    setNameError(null);
    setNameNotice(null);
    if (!profile) return;
    setSavingName(true);
    try {
      const { error } = await updateProfileDisplayName(draftDisplayName);
      if (error) {
        setNameError(error.message);
        return;
      }
      setNameNotice("Display name saved.");
    } finally {
      setSavingName(false);
    }
  }, [draftDisplayName, profile, updateProfileDisplayName]);

  const onSignOut = useCallback(async () => {
    setSigningOut(true);
    try {
      await signOut();
    } finally {
      setSigningOut(false);
    }
  }, [signOut]);

  if (initializing) {
    return (
      <ScreenContainer scroll={false} omitTopSafeArea style={styles.centered}>
        <ActivityIndicator size="large" color={theme.colors.primary} />
        <Text style={styles.bootCaption}>Checking your session…</Text>
      </ScreenContainer>
    );
  }

  if (!supabaseConfigured) {
    return (
      <ScreenContainer scroll omitTopSafeArea style={styles.body}>
        <View style={styles.stack}>
          <Text style={styles.screenTitle}>Profile</Text>
          <Text style={styles.muted}>
            Supabase is not configured. Add project URL and anon key to use
            accounts; this device still keeps wardrobe and outfits locally.
          </Text>
        </View>
      </ScreenContainer>
    );
  }

  if (!isAuthenticated || !user || !profile) {
    return (
      <ScreenContainer scroll={false} omitTopSafeArea style={styles.centered}>
        <ActivityIndicator size="large" color={theme.colors.primary} />
        <Text style={styles.muted}>Loading account…</Text>
      </ScreenContainer>
    );
  }

  const initials = displayInitials(draftDisplayName || profile.displayName);
  const showAvatar = profile.avatarUrl != null && profile.avatarUrl.length > 0;

  return (
    <ScreenContainer scroll omitTopSafeArea style={styles.body}>
      <View style={styles.stack}>
        <Text style={styles.screenTitle}>Profile</Text>

        <View style={styles.hero}>
          {showAvatar ? (
            <Image
              source={{ uri: profile.avatarUrl! }}
              style={styles.avatarImage}
              contentFit="cover"
              transition={media.imageTransitionMs.card}
              accessibilityLabel="Profile photo"
            />
          ) : (
            <View style={styles.avatarFallback}>
              <Text style={styles.avatarInitials}>{initials}</Text>
            </View>
          )}
          <Text style={styles.heroName}>
            {draftDisplayName.trim() || profile.displayName}
          </Text>
          <Text style={styles.heroEmail}>{profile.email ?? "No email on file"}</Text>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Your name</Text>
          <Text style={styles.cardHint}>
            Shown in the app as you personalize Closy. Stored in your account
            metadata (avatar coming later).
          </Text>
          <Text style={styles.inputLabel}>Display name</Text>
          <TextInput
            value={draftDisplayName}
            onChangeText={(t) => {
              setDraftDisplayName(t);
              if (nameError) setNameError(null);
              if (nameNotice) setNameNotice(null);
            }}
            placeholder="How should we greet you?"
            placeholderTextColor={theme.colors.textMuted}
            style={styles.textField}
            autoCapitalize="words"
            autoCorrect
            accessibilityLabel="Display name"
            editable={!savingName}
          />
          {nameError ? <Text style={styles.error}>{nameError}</Text> : null}
          {nameNotice ? <Text style={styles.notice}>{nameNotice}</Text> : null}
          <AppButton
            label="Save display name"
            variant="secondary"
            fullWidth
            onPress={() => void onSaveDisplayName()}
            loading={savingName}
            disabled={savingName || !nameDirty}
            accessibilityHint={
              nameDirty
                ? "Updates the name on your account"
                : "Change the name above to enable saving"
            }
          />
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Account status</Text>
          <View style={styles.kvRow}>
            <Text style={styles.kvLabel}>Email</Text>
            <Text style={styles.kvValue} selectable>
              {profile.email ?? "—"}
            </Text>
          </View>
          <View style={styles.kvRow}>
            <Text style={styles.kvLabel}>Verification</Text>
            <Text
              style={[
                styles.kvValue,
                profile.emailConfirmed
                  ? styles.statusOk
                  : styles.statusPending,
              ]}
            >
              {profile.emailConfirmed ? "Verified" : "Pending"}
            </Text>
          </View>
          <View style={styles.kvRow}>
            <Text style={styles.kvLabel}>User id</Text>
            <Text style={styles.kvMono} selectable numberOfLines={1}>
              {profile.userId}
            </Text>
          </View>
        </View>

        <AppButton
          label="Sign out"
          variant="secondary"
          fullWidth
          onPress={() => void onSignOut()}
          loading={signingOut}
          disabled={signingOut}
          accessibilityHint="Ends this session on this device"
        />
      </View>
    </ScreenContainer>
  );
}

const AVATAR = 72;

const styles = StyleSheet.create({
  body: {
    paddingHorizontal: theme.spacing.md,
    paddingTop: theme.spacing.lg,
  },
  centered: {
    flexGrow: 1,
    justifyContent: "center",
    alignItems: "center",
    gap: theme.spacing.md,
    paddingHorizontal: theme.spacing.lg,
  },
  bootCaption: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
    textAlign: "center",
  },
  stack: {
    gap: theme.spacing.lg,
    width: "100%",
    maxWidth: 420,
    alignSelf: "center",
    paddingBottom: theme.spacing.xl,
  },
  screenTitle: {
    fontSize: theme.typography.fontSize.lg,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  hero: {
    alignItems: "center",
    gap: theme.spacing.sm,
  },
  avatarImage: {
    width: AVATAR,
    height: AVATAR,
    borderRadius: AVATAR / 2,
    backgroundColor: theme.colors.border,
  },
  avatarFallback: {
    width: AVATAR,
    height: AVATAR,
    borderRadius: AVATAR / 2,
    backgroundColor: theme.colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarInitials: {
    fontSize: theme.typography.fontSize.xl,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.surface,
  },
  heroName: {
    fontSize: theme.typography.fontSize.panel,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
    textAlign: "center",
  },
  heroEmail: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
    textAlign: "center",
  },
  card: {
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radii.md,
    backgroundColor: theme.colors.surface,
    padding: theme.spacing.md,
    gap: theme.spacing.sm,
  },
  cardTitle: {
    fontSize: theme.typography.fontSize.sm,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  cardHint: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    lineHeight: 18,
    marginBottom: theme.spacing.xs,
  },
  inputLabel: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  textField: {
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radii.sm,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    fontSize: theme.typography.fontSize.md,
    color: theme.colors.text,
    backgroundColor: theme.colors.background,
  },
  error: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.danger,
  },
  notice: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
  },
  kvRow: {
    gap: 4,
    paddingVertical: theme.spacing.xs,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: theme.colors.border,
  },
  kvLabel: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  kvValue: {
    fontSize: theme.typography.fontSize.md,
    color: theme.colors.text,
  },
  kvMono: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    fontFamily: Platform.select({ web: "monospace", default: "monospace" }),
  },
  statusOk: {
    color: theme.colors.text,
  },
  statusPending: {
    color: theme.colors.textMuted,
  },
  muted: {
    fontSize: theme.typography.fontSize.md,
    color: theme.colors.textMuted,
    lineHeight: 22,
    textAlign: "center",
    paddingHorizontal: theme.spacing.md,
  },
});
