import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { Platform, StyleSheet } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { ActivityUnreadProvider } from "@/features/activity/context/activity-unread-context";
import { AuthGate, AuthProvider } from "@/features/auth";
import { AppPersistGate } from "@/lib/app-persist-gate";
import { theme } from "@/theme";

/** `modal` stack presentation is unreliable for programmatic pushes on RN Web; use a normal stack screen. */
export const ADD_EDIT_PRESENTATION =
  Platform.OS === "web" ? ("card" as const) : ("modal" as const);

export function AppNavigationShell() {
  return (
    <AppPersistGate>
      <AuthProvider>
        <SafeAreaProvider style={styles.safeArea}>
          <AuthGate>
            <ActivityUnreadProvider>
              <StatusBar style="auto" />
              <Stack
                screenOptions={{
                  headerTintColor: theme.colors.text,
                  headerStyle: { backgroundColor: theme.colors.surface },
                  contentStyle: {
                    flex: 1,
                    backgroundColor: theme.colors.background,
                  },
                }}
              >
                <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
                <Stack.Screen name="sign-in" options={{ title: "Sign in" }} />
                <Stack.Screen
                  name="sign-up"
                  options={{ title: "Create account" }}
                />
                <Stack.Screen
                  name="add-item"
                  options={{
                    title: "Add item",
                    presentation: ADD_EDIT_PRESENTATION,
                    animation: Platform.OS === "web" ? "fade" : "default",
                  }}
                />
                <Stack.Screen
                  name="edit-item/[id]"
                  options={{
                    title: "Edit item",
                    presentation: ADD_EDIT_PRESENTATION,
                    animation: Platform.OS === "web" ? "fade" : "default",
                  }}
                />
                <Stack.Screen name="item/[id]" options={{ title: "Item" }} />
                <Stack.Screen
                  name="create-outfit"
                  options={{
                    title: "New outfit",
                    presentation: ADD_EDIT_PRESENTATION,
                    animation: Platform.OS === "web" ? "fade" : "default",
                  }}
                />
                <Stack.Screen
                  name="wardrobe-insights"
                  options={{ title: "Wardrobe insights" }}
                />
                <Stack.Screen
                  name="suggest-outfit"
                  options={{ title: "Suggest an outfit" }}
                />
                <Stack.Screen
                  name="edit-outfit/[id]"
                  options={{
                    title: "Edit outfit",
                    presentation: ADD_EDIT_PRESENTATION,
                    animation: Platform.OS === "web" ? "fade" : "default",
                  }}
                />
                <Stack.Screen name="outfit/[id]" options={{ title: "Outfit" }} />
                <Stack.Screen
                  name="published-outfit/[id]"
                  options={{ title: "Discover" }}
                />
                <Stack.Screen
                  name="author/[userId]"
                  options={{ title: "Profile" }}
                />
                <Stack.Screen name="activity" options={{ title: "Activity" }} />
              </Stack>
            </ActivityUnreadProvider>
          </AuthGate>
        </SafeAreaProvider>
      </AuthProvider>
    </AppPersistGate>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
  },
});
