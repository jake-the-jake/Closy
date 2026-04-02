import { useLocalSearchParams } from "expo-router";

import { ScreenContainer } from "@/components/ui/screen-container";
import { EmptyState } from "@/components/ui/empty-state";
import { OutfitBuilderScreen } from "@/features/outfits/components/outfit-builder-screen";
import { resolveOutfitRouteId } from "@/features/outfits/lib/resolve-outfit-route-id";

export default function EditOutfitRoute() {
  const { id } = useLocalSearchParams<{ id: string | string[] }>();
  const resolved = resolveOutfitRouteId(id);

  if (resolved == null) {
    return (
      <ScreenContainer scroll={false} omitTopSafeArea>
        <EmptyState
          title="Invalid link"
          description="This outfit link is missing an id. Go back to Outfits."
        />
      </ScreenContainer>
    );
  }

  return <OutfitBuilderScreen mode="edit" outfitId={resolved} />;
}
