import { type Href, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import {
  ActivityIndicator,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { AppButton } from "@/components/ui/app-button";
import { AppInput } from "@/components/ui/app-input";
import { ScreenContainer } from "@/components/ui/screen-container";
import { useAuth } from "@/features/auth";
import { theme } from "@/theme";

export default function SignInRoute() {
  const router = useRouter();
  const { signInWithPassword, initializing, supabaseConfigured } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = useCallback(async () => {
    setError(null);
    if (!email.trim() || !password) {
      setError("Enter your email and password.");
      return;
    }
    setSubmitting(true);
    try {
      const { error: err } = await signInWithPassword(email, password);
      if (err) {
        setError(err.message);
        return;
      }
      if (router.canGoBack()) router.back();
      else router.replace("/(tabs)/profile" as Href);
    } finally {
      setSubmitting(false);
    }
  }, [email, password, router, signInWithPassword]);

  if (initializing) {
    return (
      <ScreenContainer scroll={false} omitTopSafeArea style={styles.centered}>
        <ActivityIndicator size="large" color={theme.colors.primary} />
      </ScreenContainer>
    );
  }

  if (!supabaseConfigured) {
    return (
      <ScreenContainer scroll omitTopSafeArea style={styles.body}>
        <Text style={styles.wizard}>
          Add EXPO_PUBLIC_SUPABASE_URL and EXPO_PUBLIC_SUPABASE_ANON_KEY to your{" "}
          <Text style={styles.code}>.env</Text>, then restart Expo.
        </Text>
        <AppButton label="Go back" variant="secondary" onPress={() => router.back()} />
      </ScreenContainer>
    );
  }

  return (
    <ScreenContainer scroll omitTopSafeArea style={styles.body}>
      <View style={styles.stack}>
        <AppInput
          label="Email"
          value={email}
          onChangeText={(t) => {
            setEmail(t);
            if (error) setError(null);
          }}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="email-address"
          autoComplete="email"
        />
        <AppInput
          label="Password"
          value={password}
          onChangeText={(t) => {
            setPassword(t);
            if (error) setError(null);
          }}
          secureTextEntry
          autoComplete="password"
        />
        {error ? <Text style={styles.error}>{error}</Text> : null}
        <AppButton
          label="Sign in"
          onPress={() => void onSubmit()}
          loading={submitting}
          disabled={submitting}
          fullWidth
        />
        <Pressable
          onPress={() => router.push("/sign-up" as Href)}
          accessibilityRole="button"
          accessibilityLabel="Go to create account"
          style={({ pressed }) => [pressed && { opacity: 0.75 }]}
        >
          <Text style={styles.link}>No account? Create one</Text>
        </Pressable>
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
  error: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.danger,
  },
  link: {
    fontSize: theme.typography.fontSize.md,
    fontWeight: theme.typography.fontWeight.semibold,
    color: theme.colors.primary,
    textAlign: "center",
    marginTop: theme.spacing.sm,
  },
  wizard: {
    fontSize: theme.typography.fontSize.md,
    color: theme.colors.text,
    marginBottom: theme.spacing.lg,
    lineHeight: 22,
  },
  code: {
    ...Platform.select({
      web: { fontFamily: "monospace" },
      default: {},
    }),
    fontWeight: theme.typography.fontWeight.semibold,
  },
});
