import { useLocalSearchParams } from "expo-router";

import { OutfitDetailScreen } from "@/features/outfits";
import { resolveOutfitRouteId } from "@/features/outfits/lib/resolve-outfit-route-id";
import { useOutfitsStore } from "@/features/outfits/state/outfits-store";

export default function OutfitDetailRoute() {
  const { id } = useLocalSearchParams<{ id: string | string[] }>();
  const resolved = resolveOutfitRouteId(id);
  const outfit = useOutfitsStore((s) =>
    resolved == null ? undefined : s.outfits.find((o) => o.id === resolved),
  );

  return <OutfitDetailScreen outfit={outfit} />;
}
