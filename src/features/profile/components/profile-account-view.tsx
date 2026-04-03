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
  fetchPublicProfileByUserId,
  upsertMyProfile,
} from "@/features/profile/lib/cloud-profiles";
import {
  buildAccountProfile,
  displayInitials,
} from "../types/account-profile";
import { media } from "@/lib/constants";
import { supabase } from "@/lib/supabase/client";
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

  const account = useMemo(
    () => (user ? buildAccountProfile(user) : null),
    [user],
  );

  const [remoteProfile, setRemoteProfile] = useState<Awaited<
    ReturnType<typeof fetchPublicProfileByUserId>
  > | null>(null);
  const [profileLoading, setProfileLoading] = useState(true);

  const [draftDisplayName, setDraftDisplayName] = useState("");
  const [draftAvatarUrl, setDraftAvatarUrl] = useState("");
  const [saving, setSaving] = useState(false);
  const [nameNotice, setNameNotice] = useState<string | null>(null);
  const [nameError, setNameError] = useState<string | null>(null);
  const [signingOut, setSigningOut] = useState(false);

  useEffect(() => {
    if (!user?.id || !isAuthenticated) {
      setRemoteProfile(null);
      setProfileLoading(false);
      return;
    }
    const uid = user.id;
    const userSnapshot = user;
    let cancelled = false;
    setProfileLoading(true);
    void fetchPublicProfileByUserId(uid).then((row) => {
      if (cancelled) return;
      setRemoteProfile(row);
      setProfileLoading(false);
      const acct = buildAccountProfile(userSnapshot);
      const name =
        row?.displayName != null && row.displayName.trim().length > 0
          ? row.displayName.trim()
          : acct.displayName;
      const av =
        (row?.avatarUrl != null && row.avatarUrl.trim().length > 0
          ? row.avatarUrl.trim()
          : "") ||
        acct.avatarUrl?.trim() ||
        "";
      setDraftDisplayName(name);
      setDraftAvatarUrl(av);
      setNameNotice(null);
      setNameError(null);
    });
    return () => {
      cancelled = true;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps -- reload when account identity changes, not every session refresh
  }, [user?.id, isAuthenticated]);

  const baselineDisplayName = useMemo(() => {
    if (!account) return "";
    const fromDb = remoteProfile?.displayName?.trim() ?? "";
    return fromDb.length > 0 ? fromDb : account.displayName;
  }, [account, remoteProfile?.displayName]);

  const baselineAvatarUrl = useMemo(() => {
    if (!account) return "";
    const fromDb = remoteProfile?.avatarUrl?.trim() ?? "";
    if (fromDb.length > 0) return fromDb;
    return account.avatarUrl?.trim() ?? "";
  }, [account, remoteProfile?.avatarUrl]);

  const nameDirty =
    account != null &&
    draftDisplayName.trim() !== baselineDisplayName.trim();

  const avatarDirty =
    account != null &&
    draftAvatarUrl.trim() !== baselineAvatarUrl.trim();

  const onSaveProfile = useCallback(async () => {
    setNameError(null);
    setNameNotice(null);
    if (!user?.id || !account || !supabase) return;
    if (!nameDirty && !avatarDirty) return;
    setSaving(true);
    try {
      if (nameDirty) {
        const { error } = await updateProfileDisplayName(draftDisplayName);
        if (error) {
          setNameError(error.message);
          return;
        }
      }
      if (avatarDirty) {
        const trimmed = draftAvatarUrl.trim();
        const pe = await upsertMyProfile(supabase, user.id, {
          avatarUrl: trimmed.length > 0 ? trimmed : null,
        });
        if (pe.error) {
          setNameError(pe.error.message);
          return;
        }
      }
      setNameNotice("Profile saved.");
      const row = await fetchPublicProfileByUserId(user.id);
      setRemoteProfile(row);
    } finally {
      setSaving(false);
    }
  }, [
    account,
    avatarDirty,
    draftAvatarUrl,
    draftDisplayName,
    nameDirty,
    updateProfileDisplayName,
    user?.id,
  ]);

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

  if (!isAuthenticated || !user || !account) {
    return (
      <ScreenContainer scroll={false} omitTopSafeArea style={styles.centered}>
        <ActivityIndicator size="large" color={theme.colors.primary} />
        <Text style={styles.muted}>Loading account…</Text>
      </ScreenContainer>
    );
  }

  if (profileLoading) {
    return (
      <ScreenContainer scroll={false} omitTopSafeArea style={styles.centered}>
        <ActivityIndicator size="large" color={theme.colors.primary} />
        <Text style={styles.muted}>Loading your profile…</Text>
      </ScreenContainer>
    );
  }

  const heroAvatarUri = draftAvatarUrl.trim();
  const showAvatar = heroAvatarUri.length > 0;
  const initials = displayInitials(draftDisplayName || baselineDisplayName);

  return (
    <ScreenContainer scroll omitTopSafeArea style={styles.body}>
      <View style={styles.stack}>
        <Text style={styles.screenTitle}>Profile</Text>

        <View style={styles.hero}>
          {showAvatar ? (
            <Image
              source={{ uri: heroAvatarUri }}
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
            {draftDisplayName.trim() || baselineDisplayName}
          </Text>
          <Text style={styles.heroEmail}>{account.email ?? "No email on file"}</Text>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Public profile</Text>
          <Text style={styles.cardHint}>
            Your display name and photo appear on Discover when you publish
            outfits. Stored in your Closy profile (synced with your account
            name).
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
            editable={!saving}
          />
          <Text style={styles.inputLabel}>Avatar image URL (optional)</Text>
          <TextInput
            value={draftAvatarUrl}
            onChangeText={(t) => {
              setDraftAvatarUrl(t);
              if (nameError) setNameError(null);
              if (nameNotice) setNameNotice(null);
            }}
            placeholder="https://…"
            placeholderTextColor={theme.colors.textMuted}
            style={styles.textField}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            accessibilityLabel="Avatar image URL"
            editable={!saving}
          />
          {nameError ? <Text style={styles.error}>{nameError}</Text> : null}
          {nameNotice ? <Text style={styles.notice}>{nameNotice}</Text> : null}
          <AppButton
            label="Save profile"
            variant="secondary"
            fullWidth
            onPress={() => void onSaveProfile()}
            loading={saving}
            disabled={saving || (!nameDirty && !avatarDirty)}
            accessibilityHint={
              nameDirty || avatarDirty
                ? "Saves your public name and avatar"
                : "Change the fields above to enable saving"
            }
          />
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Account status</Text>
          <View style={styles.kvRow}>
            <Text style={styles.kvLabel}>Email</Text>
            <Text style={styles.kvValue} selectable>
              {account.email ?? "—"}
            </Text>
          </View>
          <View style={styles.kvRow}>
            <Text style={styles.kvLabel}>Verification</Text>
            <Text
              style={[
                styles.kvValue,
                account.emailConfirmed
                  ? styles.statusOk
                  : styles.statusPending,
              ]}
            >
              {account.emailConfirmed ? "Verified" : "Pending"}
            </Text>
          </View>
          <View style={styles.kvRow}>
            <Text style={styles.kvLabel}>User id</Text>
            <Text style={styles.kvMono} selectable numberOfLines={1}>
              {account.userId}
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
