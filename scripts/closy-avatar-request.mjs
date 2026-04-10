#!/usr/bin/env node
/**
 * Write outfit JSON into the repo for `closy:avatar-export` (host PC only).
 *
 * After you Copy/Share JSON from the Android app, save it as a file (e.g. handoff.json), then:
 *   npm run closy:avatar-request -- --id <renderId> --file path\\to\\handoff.json
 *   npm run closy:avatar-export -- <renderId>
 *
 * Or pipe JSON:
 *   type handoff.json | node scripts/closy-avatar-request.mjs --id <renderId> --stdin
 */

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
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

const useStdin = process.argv.includes("--stdin");
const id = getArg("--id");
const file = getArg("--file");

if (!id || id.startsWith("--")) {
  console.error("Usage: node scripts/closy-avatar-request.mjs --id <renderId> --file <path-to.json>");
  console.error("   or: ... --id <renderId> --stdin   (pipe JSON on stdin)");
  process.exit(1);
}

let json;
if (useStdin) {
  json = readFileSync(0, "utf8");
} else if (file) {
  json = readFileSync(path.resolve(file), "utf8");
} else {
  console.error("Provide --file <path> or --stdin");
  process.exit(1);
}

try {
  JSON.parse(json);
} catch (e) {
  console.error("[closy] Invalid JSON:", e.message);
  process.exit(1);
}

const safeId = id.replace(/[/\\]/g, "_");
const outDir = path.join(repoRoot, "generated", "avatar_requests");
const outPath = path.join(outDir, `${safeId}.json`);

mkdirSync(outDir, { recursive: true });
writeFileSync(outPath, json.endsWith("\n") ? json : `${json}\n`, "utf8");
console.log("[closy] Wrote request:", outPath);
