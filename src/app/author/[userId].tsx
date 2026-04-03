import { useLocalSearchParams } from "expo-router";

import { AuthorProfileScreen } from "@/features/discover/components/author-profile-screen";
import { resolveAuthorRouteUserId } from "@/features/discover/lib/resolve-author-route-user-id";

function resolveDisplayNameParam(
  param: string | string[] | undefined,
): string | null {
  if (param === undefined) return null;
  const raw = Array.isArray(param) ? param[0] : param;
  if (raw == null || raw === "") return null;
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

export default function AuthorProfileRoute() {
  const { userId, displayName } = useLocalSearchParams<{
    userId: string | string[];
    displayName?: string | string[];
  }>();
  const resolvedUserId = resolveAuthorRouteUserId(userId);
  const initialDisplayName = resolveDisplayNameParam(displayName);

  return (
    <AuthorProfileScreen
      authorUserId={resolvedUserId}
      initialDisplayName={initialDisplayName}
    />
  );
}
