import { useLocalSearchParams } from "expo-router";

import { ClothingItemDetailScreen } from "@/features/wardrobe/components/clothing-item-detail-screen";
import { findClothingItemById } from "@/features/wardrobe/data/find-clothing-item";
import { resolveClothingItemRouteId } from "@/features/wardrobe/lib/resolve-item-route-id";
import { useWardrobeItems } from "@/features/wardrobe/wardrobe-service";

export default function ItemDetailRoute() {
  const { id } = useLocalSearchParams<{ id: string | string[] }>();
  const items = useWardrobeItems();
  const item = findClothingItemById(items, resolveClothingItemRouteId(id));

  return <ClothingItemDetailScreen item={item} />;
}
