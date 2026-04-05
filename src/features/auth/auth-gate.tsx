import type { ReactNode } from "react";
import { useEffect } from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { type Href, useRootNavigationState, useRouter, useSegments } from "expo-router";

import { theme } from "@/theme";

import { useAuth } from "./auth-context";

const AUTH_ROUTE_SEGMENTS = new Set(["sign-in", "sign-up"]);

function routeAllowsSignedOutOnly(segments: readonly string[]): boolean {
  return segments.some((s) => AUTH_ROUTE_SEGMENTS.has(s));
}

function routeBypassesAuthInDev(segments: readonly string[]): boolean {
  return __DEV__ && segments.some((s) => s === "dev-avatar-preview");
}

type AuthGateProps = {
  children: ReactNode;
};

/**
 * When Supabase env is present: blocks UI until the first session resolution, then
 * keeps navigation aligned with auth — main stack routes require a signed-in user;
 * `sign-in` / `sign-up` are only for signed-out users.
 *
 * When Supabase is not configured, children are always shown (local-only dev mode).
 */
export function AuthGate({ children }: AuthGateProps) {
  const { user, initializing, supabaseConfigured } = useAuth();
  const segments = useSegments();
  const router = useRouter();
  const rootNavigation = useRootNavigationState();

  useEffect(() => {
    if (initializing) return;
    if (!supabaseConfigured) return;
    if (!rootNavigation?.key) return;

    const onAuthFlowOnly = routeAllowsSignedOutOnly(segments);
    const devBypass = routeBypassesAuthInDev(segments);

    if (!user && !onAuthFlowOnly && !devBypass) {
      router.replace("/sign-in" as Href);
      return;
    }
    if (user && onAuthFlowOnly) {
      router.replace("/(tabs)" as Href);
    }
  }, [
    initializing,
    rootNavigation?.key,
    router,
    segments,
    supabaseConfigured,
    user,
  ]);

  if (supabaseConfigured && initializing) {
    return (
      <View style={styles.boot} accessibilityLabel="Loading account">
        <ActivityIndicator size="large" color={theme.colors.primary} />
        <Text style={styles.bootCaption}>Checking your session…</Text>
      </View>
    );
  }

  return <>{children}</>;
}

const styles = StyleSheet.create({
  boot: {
    flex: 1,
    backgroundColor: theme.colors.background,
    alignItems: "center",
    justifyContent: "center",
    gap: theme.spacing.md,
    paddingHorizontal: theme.spacing.lg,
  },
  bootCaption: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
    textAlign: "center",
  },
});
