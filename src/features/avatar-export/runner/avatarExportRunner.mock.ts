import type { ExportResult, SaveAvatarRequestResult } from "../types";

/** Test/dev stub: always succeeds with a remote placeholder. */
export async function runAvatarExportMock(
  saved: SaveAvatarRequestResult,
): Promise<ExportResult> {
  const uri =
    process.env.EXPO_PUBLIC_AVATAR_EXPORT_MOCK_URI?.trim() ||
    "https://picsum.photos/seed/closy-mock-runner/512/512";
  return {
    ok: true,
    variant: "image",
    imageUri: uri,
    outputPathForDisplay: `(mock:${saved.renderId})`,
    mode: "mock",
  };
}
