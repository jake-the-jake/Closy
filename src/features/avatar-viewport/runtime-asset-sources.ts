/**
 * Optional GLTF/GLB sources for the live viewport (Expo / Metro).
 *
 * Set in `.env` / `app.config` → `extra` or use `EXPO_PUBLIC_*`:
 * - EXPO_PUBLIC_AVATAR_RUNTIME_BODY_GLTF_URL
 * - EXPO_PUBLIC_AVATAR_RUNTIME_TOP_GLTF_URL
 * - EXPO_PUBLIC_AVATAR_RUNTIME_BOTTOM_GLTF_URL
 *
 * URLs must be reachable from the device (https) or `file://` where supported.
 * When unset, the viewport uses procedural proxies for that slot.
 */
export type AvatarRuntimeAssetUrls = {
  bodyGltfUrl: string | null;
  topGltfUrl: string | null;
  bottomGltfUrl: string | null;
};

export function getAvatarRuntimeAssetUrls(): AvatarRuntimeAssetUrls {
  const body =
    typeof process.env.EXPO_PUBLIC_AVATAR_RUNTIME_BODY_GLTF_URL === "string" &&
    process.env.EXPO_PUBLIC_AVATAR_RUNTIME_BODY_GLTF_URL.length > 0
      ? process.env.EXPO_PUBLIC_AVATAR_RUNTIME_BODY_GLTF_URL
      : null;
  const top =
    typeof process.env.EXPO_PUBLIC_AVATAR_RUNTIME_TOP_GLTF_URL === "string" &&
    process.env.EXPO_PUBLIC_AVATAR_RUNTIME_TOP_GLTF_URL.length > 0
      ? process.env.EXPO_PUBLIC_AVATAR_RUNTIME_TOP_GLTF_URL
      : null;
  const bottom =
    typeof process.env.EXPO_PUBLIC_AVATAR_RUNTIME_BOTTOM_GLTF_URL === "string" &&
    process.env.EXPO_PUBLIC_AVATAR_RUNTIME_BOTTOM_GLTF_URL.length > 0
      ? process.env.EXPO_PUBLIC_AVATAR_RUNTIME_BOTTOM_GLTF_URL
      : null;
  return { bodyGltfUrl: body, topGltfUrl: top, bottomGltfUrl: bottom };
}

export function runtimeAssetSummary(urls: AvatarRuntimeAssetUrls): string {
  const parts: string[] = [];
  parts.push(urls.bodyGltfUrl ? "body=GLTF" : "body=proxy");
  parts.push(urls.topGltfUrl ? "top=GLTF" : "top=proxy");
  parts.push(urls.bottomGltfUrl ? "bottom=GLTF" : "bottom=proxy");
  return parts.join(" · ");
}
