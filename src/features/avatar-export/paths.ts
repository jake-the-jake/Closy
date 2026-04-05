import {
  joinPathSegments,
  renderRelativePathForRenderId,
} from "./contract";
import { getClosyRepoRoot } from "./repo-root";

export function toExpoFileUri(absoluteNativePath: string): string {
  const p = absoluteNativePath.replace(/\\/g, "/");
  if (p.startsWith("file:")) return p;
  if (/^[A-Za-z]:/.test(p)) {
    return `file:///${p}`;
  }
  const withLeading = p.startsWith("/") ? p : `/${p}`;
  return `file://${withLeading}`;
}

export function absoluteRenderPathForId(renderId: string): {
  repoRoot: string;
  absolutePath: string;
  fileUri: string;
} | null {
  const repoRoot = getClosyRepoRoot();
  if (!repoRoot) return null;
  const rel = renderRelativePathForRenderId(renderId);
  const absolutePath = joinPathSegments(repoRoot, rel);
  return { repoRoot, absolutePath, fileUri: toExpoFileUri(absolutePath) };
}
