import { useLocalSearchParams } from "expo-router";
import { useMemo } from "react";

import { OutfitBuilderScreen } from "@/features/outfits/components/outfit-builder-screen";

function parseItemIdsParam(
  raw: string | string[] | undefined,
): readonly string[] | undefined {
  if (raw == null) return undefined;
  const s = Array.isArray(raw) ? raw[0] : raw;
  if (s === undefined || s === "") return undefined;
  const ids = s
    .split(",")
    .map((x) => x.trim())
    .filter((x) => x.length > 0);
  return ids.length > 0 ? ids : undefined;
}

export function CreateOutfitScreen() {
  const { itemIds } = useLocalSearchParams<{ itemIds?: string | string[] }>();
  const initialItemIds = useMemo(() => parseItemIdsParam(itemIds), [itemIds]);

  return (
    <OutfitBuilderScreen mode="create" initialItemIds={initialItemIds} />
  );
}
