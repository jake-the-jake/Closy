import * as FileSystem from "expo-file-system/legacy";
import { Platform } from "react-native";

/** Whether `saveAvatarExportRequest` will attempt a cache copy (native + cacheDirectory set). */
export function canUseCacheDirectoryForExport(): boolean {
  return Platform.OS !== "web" && FileSystem.cacheDirectory != null;
}
