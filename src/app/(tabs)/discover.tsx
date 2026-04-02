import { StyleSheet, View } from "react-native";

import { DiscoverFeedScreen } from "@/features/discover";

export default function DiscoverTab() {
  return (
    <View style={styles.root}>
      <DiscoverFeedScreen />
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
  },
});
