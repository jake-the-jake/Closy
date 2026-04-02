import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { ActivityIndicator, StyleSheet, View } from "react-native";

import { useOutfitsStore } from "@/features/outfits/state/outfits-store";
import { useWardrobeStore } from "@/features/wardrobe/state/wardrobe-store";
import { theme } from "@/theme";

type AppPersistGateProps = {
  children: ReactNode;
};

function bothHydrated(): boolean {
  return (
    useWardrobeStore.persist.hasHydrated() && useOutfitsStore.persist.hasHydrated()
  );
}

/**
 * Blocks the tree until wardrobe + outfits Zustand stores finish rehydrating from AsyncStorage.
 */
export function AppPersistGate({ children }: AppPersistGateProps) {
  const [ready, setReady] = useState(() => {
    if (typeof window === "undefined") return true;
    return bothHydrated();
  });

  useEffect(() => {
    if (typeof window === "undefined") return;

    const check = () => {
      if (bothHydrated()) setReady(true);
    };

    check();
    const unsubW = useWardrobeStore.persist.onFinishHydration(check);
    const unsubO = useOutfitsStore.persist.onFinishHydration(check);
    return () => {
      unsubW();
      unsubO();
    };
  }, []);

  if (!ready) {
    return (
      <View style={styles.fill} accessibilityLabel="Loading">
        <ActivityIndicator size="large" color={theme.colors.primary} />
      </View>
    );
  }

  return <>{children}</>;
}

const styles = StyleSheet.create({
  fill: {
    flex: 1,
    backgroundColor: theme.colors.background,
    alignItems: "center",
    justifyContent: "center",
  },
});
