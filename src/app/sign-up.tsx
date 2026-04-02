import { type Href, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import {
  ActivityIndicator,
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

export default function SignUpRoute() {
  const router = useRouter();
  const { signUpWithPassword, initializing, supabaseConfigured } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const onSubmit = useCallback(async () => {
    setError(null);
    setNotice(null);
    if (!email.trim() || !password) {
      setError("Enter your email and password.");
      return;
    }
    if (password.length < 6) {
      setError("Use at least 6 characters for the password.");
      return;
    }
    setSubmitting(true);
    try {
      const { error: err } = await signUpWithPassword(email, password);
      if (err) {
        setError(err.message);
        return;
      }
      setNotice(
        "Check your email to confirm your account if required by your project settings. You can then sign in.",
      );
    } finally {
      setSubmitting(false);
    }
  }, [email, password, signUpWithPassword]);

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
        <Text style={styles.wizard}>
          Configure Supabase env vars (see .env.example), then restart Expo.
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
          autoComplete="new-password"
        />
        {error ? <Text style={styles.error}>{error}</Text> : null}
        {notice ? <Text style={styles.notice}>{notice}</Text> : null}
        <AppButton
          label="Create account"
          onPress={() => void onSubmit()}
          loading={submitting}
          disabled={submitting}
          fullWidth
        />
        <Pressable
          onPress={() => router.push("/sign-in" as Href)}
          accessibilityRole="button"
          accessibilityLabel="Go to sign in"
          style={({ pressed }) => [pressed && { opacity: 0.75 }]}
        >
          <Text style={styles.link}>Already have an account? Sign in</Text>
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
    gap: theme.spacing.md,
    paddingHorizontal: theme.spacing.lg,
  },
  bootCaption: {
    fontSize: theme.typography.fontSize.sm,
    color: theme.colors.textMuted,
    textAlign: "center",
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
  notice: {
    fontSize: theme.typography.fontSize.caption,
    color: theme.colors.textMuted,
    lineHeight: 18,
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
});
