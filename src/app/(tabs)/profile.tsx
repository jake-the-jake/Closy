import { type Href, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import {
  ActivityIndicator,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { AppButton } from "@/components/ui/app-button";
import { ScreenContainer } from "@/components/ui/screen-container";
import { useAuth } from "@/features/auth";
import { theme } from "@/theme";

export default function ProfileTab() {
  const router = useRouter();
  const {
    user,
    initializing,
    supabaseConfigured,
    signOut,
  } = useAuth();
  const [signingOut, setSigningOut] = useState(false);

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
      </ScreenContainer>
    );
  }

  return (
    <ScreenContainer scroll omitTopSafeArea style={styles.body}>
      <View style={styles.stack}>
        <Text style={styles.title}>Account</Text>
        {!supabaseConfigured ? (
          <Text style={styles.muted}>
            Cloud sign-in is not configured. Add Supabase env vars to use an
            account; your wardrobe and outfits stay on this device.
          </Text>
        ) : user ? (
          <>
            <Text style={styles.label}>Signed in as</Text>
            <Text style={styles.email}>
              {user.email ?? user.id}
            </Text>
            <AppButton
              label="Sign out"
              variant="secondary"
              fullWidth
              onPress={() => void onSignOut()}
              loading={signingOut}
              disabled={signingOut}
            />
          </>
        ) : (
          <>
            <Text style={styles.muted}>
              Sign in to sync your wardrobe to the cloud. Outfits stay on this
              device for now.
            </Text>
            <AppButton
              label="Sign in"
              fullWidth
              onPress={() => router.push("/sign-in" as Href)}
            />
            <AppButton
              label="Create account"
              variant="secondary"
              fullWidth
              onPress={() => router.push("/sign-up" as Href)}
            />
          </>
        )}
      </View>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  body: {
    paddingHorizontal: theme.spacing.md,
    paddingTop: theme.spacing.lg,
  },
  centered: {
    flexGrow: 1,
    justifyContent: "center",
    alignItems: "center",
  },
  stack: {
    gap: theme.spacing.md,
    width: "100%",
    maxWidth: 420,
    alignSelf: "center",
    paddingBottom: theme.spacing.xl,
  },
  title: {
    fontSize: theme.typography.fontSize.lg,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.text,
  },
  label: {
    fontSize: theme.typography.fontSize.xs,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  email: {
    fontSize: theme.typography.fontSize.md,
    color: theme.colors.text,
  },
  muted: {
    fontSize: theme.typography.fontSize.md,
    color: theme.colors.textMuted,
    lineHeight: 22,
  },
});
