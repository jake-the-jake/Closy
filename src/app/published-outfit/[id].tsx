import { useLocalSearchParams } from "expo-router";

import { PublishedOutfitDetailScreen } from "@/features/discover";
import { resolvePublishedOutfitRouteId } from "@/features/discover/lib/resolve-published-outfit-route-id";

export default function PublishedOutfitRoute() {
  const { id } = useLocalSearchParams<{ id: string | string[] }>();
  const resolvedId = resolvePublishedOutfitRouteId(id);

  return <PublishedOutfitDetailScreen publishedId={resolvedId} />;
}
