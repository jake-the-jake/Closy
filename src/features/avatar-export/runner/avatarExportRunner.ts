/**
 * Stable interface for “run native avatar export”. The default implementation
 * lives in `run-avatar-export.ts` (poll filesystem under EXPO_PUBLIC_CLOSY_REPO_ROOT).
 */

export {
  buildNpmCliCommand,
  runAvatarExport,
  type RunAvatarExportOptions,
} from "../run-avatar-export";
