#!/usr/bin/env node
/**
 * Closy native avatar export CLI bridge (repo root).
 * Usage (from repo root):
 *   npm run closy:avatar-export -- --id outfit_123
 *
 * Reads:  generated/avatar_requests/{id}.json
 * Writes: generated/avatar_renders/{id}.png
 */

import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = process.env.CLOSY_REPO_ROOT
  ? path.resolve(process.env.CLOSY_REPO_ROOT)
  : path.resolve(__dirname, "..");

function getArg(name) {
  const i = process.argv.indexOf(name);
  if (i === -1 || i + 1 >= process.argv.length) return null;
  return process.argv[i + 1];
}

const id =
  getArg("--id") ??
  process.argv.slice(2).find((a) => !a.startsWith("--")) ??
  null;
if (!id || id.startsWith("--")) {
  console.error(
    "Usage: node scripts/closy-avatar-export.mjs --id <renderId>\n   or: npm run closy:avatar-export -- <renderId>",
  );
  process.exit(1);
}

const safeId = id.replace(/[/\\]/g, "_");
const requestPath = path.join(
  repoRoot,
  "generated",
  "avatar_requests",
  `${safeId}.json`,
);
const outPath = path.join(
  repoRoot,
  "generated",
  "avatar_renders",
  `${safeId}.png`,
);

if (!existsSync(requestPath)) {
  console.error(`[closy] Request not found: ${requestPath}`);
  process.exit(1);
}

mkdirSync(path.dirname(outPath), { recursive: true });

function resolveExportBinary() {
  if (process.env.CLOSY_AVATAR_EXPORT_EXE) {
    return process.env.CLOSY_AVATAR_EXPORT_EXE;
  }
  const candidates = [
    path.join(repoRoot, "engine", "build", "Release", "avatar_export.exe"),
    path.join(repoRoot, "engine", "build", "Release", "avatar_export"),
    path.join(repoRoot, "engine", "build", "avatar_export"),
    path.join(repoRoot, "engine", "build", "avatar_export.exe"),
  ];
  for (const c of candidates) {
    if (existsSync(c)) return c;
  }
  return candidates[0];
}

const exe = resolveExportBinary();
if (!existsSync(exe)) {
  console.error(
    `[closy] avatar_export not found at ${exe}. Build the engine (cmake --build engine/build --config Release).`,
  );
  process.exit(1);
}

const res = spawnSync(
  exe,
  ["--out", outPath, "--outfit", requestPath],
  {
    cwd: repoRoot,
    stdio: "inherit",
    shell: false,
  },
);

if (res.error) {
  console.error(res.error);
  process.exit(1);
}
process.exit(res.status === 0 ? 0 : 1);
