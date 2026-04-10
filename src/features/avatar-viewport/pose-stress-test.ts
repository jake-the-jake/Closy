/**
 * Multi-pose stress test + bounded auto-stabilization for live garment fit.
 * Uses the same runtime clipping proxy as `runtime-clipping-approx.ts` (no physics).
 */

import {
  cloneGarmentFitState,
  type GarmentFitState,
} from "@/features/avatar-export";
import type { DevAvatarPoseKey } from "@/features/avatar-export/dev-avatar-shared";

import {
  analyzeRuntimeClipping,
  type RuntimeClippingReport,
  type RuntimeClipSeverity,
} from "./runtime-clipping-approx";

/** Minimum set required by product spec. */
export const STRESS_TEST_POSES: readonly DevAvatarPoseKey[] = [
  "relaxed",
  "walk",
  "tpose",
  "apose",
] as const;

export type StressRegionKey = "torso" | "sleeves" | "waist" | "hem";

/** Coarse failure bucket for UI and aggregation. */
export type StressFailLevel = "ok" | "low" | "medium" | "high";

export type RuntimeClippingFlags = {
  hasRuntimeBodyGltf: boolean;
  hasRuntimeTopGltf: boolean;
  hasRuntimeBottomGltf: boolean;
};

const REGION_KEYS: StressRegionKey[] = ["torso", "sleeves", "waist", "hem"];

function severityToLevel(
  sev: RuntimeClipSeverity,
  penetration: number,
): StressFailLevel {
  if (sev === "clear") return "ok";
  if (sev === "near") return "low";
  return penetration > 0.028 ? "high" : "medium";
}

function regionScorePenalty(level: StressFailLevel): number {
  switch (level) {
    case "ok":
      return 0;
    case "low":
      return 8;
    case "medium":
      return 18;
    case "high":
      return 28;
    default:
      return 0;
  }
}

/** Single pose evaluation. */
export type PoseStressPoseResult = {
  pose: DevAvatarPoseKey;
  clipping: RuntimeClippingReport;
  /** 0–100, higher is better (derived from proxy severities). */
  stabilityScore: number;
  /** True when no region is clip-level failure for stress purposes. */
  pass: boolean;
  regions: Record<
    StressRegionKey,
    { severity: RuntimeClipSeverity; penetration: number; level: StressFailLevel }
  >;
  failingRegions: StressRegionKey[];
  notes: string;
};

export type PoseStressTestReport = {
  poses: PoseStressPoseResult[];
  /** Mean of per-pose stability scores. */
  overallStabilityScore: number;
  allPosesPass: boolean;
  worstPose: DevAvatarPoseKey | null;
  worstRegion: StressRegionKey | null;
  /** How many poses flagged each region at medium+ . */
  regionFailCounts: Record<StressRegionKey, number>;
  mostFrequentFailure: { region: StressRegionKey; count: number } | null;
};

export type AggregatedStressAnalysis = {
  summaryLines: string[];
  worstPose: DevAvatarPoseKey | null;
  worstRegion: StressRegionKey | null;
  regionFailCounts: Record<StressRegionKey, number>;
};

function evaluatePose(
  garmentFit: GarmentFitState,
  pose: DevAvatarPoseKey,
  flags: RuntimeClippingFlags,
): PoseStressPoseResult {
  const clipping = analyzeRuntimeClipping({
    garmentFit,
    pose,
    ...flags,
  });

  const regions = {
    torso: {
      severity: clipping.torso.severity,
      penetration: clipping.torso.penetration,
      level: severityToLevel(clipping.torso.severity, clipping.torso.penetration),
    },
    sleeves: {
      severity: clipping.sleeves.severity,
      penetration: clipping.sleeves.penetration,
      level: severityToLevel(
        clipping.sleeves.severity,
        clipping.sleeves.penetration,
      ),
    },
    waist: {
      severity: clipping.waist.severity,
      penetration: clipping.waist.penetration,
      level: severityToLevel(clipping.waist.severity, clipping.waist.penetration),
    },
    hem: {
      severity: clipping.hem.severity,
      penetration: clipping.hem.penetration,
      level: severityToLevel(clipping.hem.severity, clipping.hem.penetration),
    },
  } satisfies PoseStressPoseResult["regions"];

  let penalty = 0;
  for (const k of REGION_KEYS) {
    penalty += regionScorePenalty(regions[k].level);
  }
  const stabilityScore = Math.max(0, Math.min(100, Math.round(100 - penalty)));

  const failingRegions: StressRegionKey[] = [];
  for (const k of REGION_KEYS) {
    if (regions[k].severity === "clip" || regions[k].level === "high") {
      failingRegions.push(k);
    }
  }
  /** Pass if no clip-level proxy overlap and no region scored "high". */
  const pass = failingRegions.length === 0;

  const notes = pass
    ? "No clip-level regions."
    : `Issues: ${failingRegions.join(", ")}`;

  return {
    pose,
    clipping,
    stabilityScore,
    pass,
    regions,
    failingRegions,
    notes,
  };
}

/**
 * Run the stress test: same fit, multiple poses, proxy clipping only.
 */
export function runPoseStressTest(
  garmentFit: GarmentFitState,
  flags: RuntimeClippingFlags,
  poses: readonly DevAvatarPoseKey[] = STRESS_TEST_POSES,
): PoseStressTestReport {
  const poseResults = poses.map((pose) =>
    evaluatePose(garmentFit, pose, flags),
  );

  const overallStabilityScore =
    poseResults.length === 0
      ? 100
      : Math.round(
          poseResults.reduce((a, p) => a + p.stabilityScore, 0) /
            poseResults.length,
        );

  const allPosesPass = poseResults.every((p) => p.pass);

  let worstPose: DevAvatarPoseKey | null = null;
  let worstScore = 101;
  for (const p of poseResults) {
    if (p.stabilityScore < worstScore) {
      worstScore = p.stabilityScore;
      worstPose = p.pose;
    }
  }

  const regionFailCounts: Record<StressRegionKey, number> = {
    torso: 0,
    sleeves: 0,
    waist: 0,
    hem: 0,
  };
  for (const pr of poseResults) {
    for (const k of REGION_KEYS) {
      const L = pr.regions[k].level;
      if (L === "medium" || L === "high") regionFailCounts[k] += 1;
    }
  }

  let worstRegion: StressRegionKey | null = null;
  let maxC = -1;
  for (const k of REGION_KEYS) {
    if (regionFailCounts[k] > maxC) {
      maxC = regionFailCounts[k];
      worstRegion = k;
    }
  }
  if (maxC === 0) worstRegion = null;

  const freq = Object.entries(regionFailCounts) as [StressRegionKey, number][];
  freq.sort((a, b) => b[1] - a[1]);
  const mostFrequentFailure =
    freq[0][1] > 0
      ? { region: freq[0][0], count: freq[0][1] }
      : null;

  return {
    poses: poseResults,
    overallStabilityScore,
    allPosesPass,
    worstPose,
    worstRegion,
    regionFailCounts,
    mostFrequentFailure,
  };
}

export function aggregateStressResults(
  report: PoseStressTestReport,
): AggregatedStressAnalysis {
  const summaryLines: string[] = [];
  for (const pr of report.poses) {
    const bad = REGION_KEYS.filter(
      (k) =>
        pr.regions[k].severity === "clip" ||
        pr.regions[k].level === "high" ||
        pr.regions[k].level === "medium",
    );
    summaryLines.push(
      `${pr.pose}: score ${pr.stabilityScore}${pr.pass ? " ✓" : " ✗"}${bad.length ? ` — watch ${bad.join(",")}` : ""}`,
    );
  }
  if (report.worstPose) {
    summaryLines.push(`Worst pose (lowest score): ${report.worstPose}`);
  }
  if (report.worstRegion && report.mostFrequentFailure) {
    summaryLines.push(
      `Most stressed region: ${report.worstRegion} (medium+ in ${report.mostFrequentFailure.count} poses)`,
    );
  }
  return {
    summaryLines,
    worstPose: report.worstPose,
    worstRegion: report.worstRegion,
    regionFailCounts: { ...report.regionFailCounts },
  };
}

// --- Stabilization (bounded, rule-based) ---

const STEP_TZ = 0.012;
const STEP_TORSO_INFL = 0.006;
const STEP_SLEEVE = 0.01;
const STEP_WAIST = 0.04;
const STEP_HEM = 0.008;
const MAX_TORSO_Z = 0.12;
const MAX_ITER = 5;
const TARGET_SCORE = 78;

function applyStabilizationStep(
  fit: GarmentFitState,
  report: PoseStressTestReport,
): GarmentFitState {
  let s = cloneGarmentFitState(fit);
  const r = s.regions;
  const g = s.global;

  const torsoStress = report.regionFailCounts.torso;
  const sleeveStress = report.regionFailCounts.sleeves;
  const waistStress = report.regionFailCounts.waist;
  const hemStress = report.regionFailCounts.hem;

  if (torsoStress >= 2) {
    r.torso.offsetZ = Math.round((r.torso.offsetZ - STEP_TZ) * 1000) / 1000;
    r.torso.inflate = Math.min(
      0.18,
      Math.round((r.torso.inflate + STEP_TORSO_INFL) * 1000) / 1000,
    );
  } else if (torsoStress === 1) {
    r.torso.offsetZ = Math.round((r.torso.offsetZ - STEP_TZ * 0.65) * 1000) / 1000;
  }

  if (sleeveStress >= 1) {
    r.sleeves.inflate = Math.min(
      0.22,
      Math.round((r.sleeves.inflate + STEP_SLEEVE) * 1000) / 1000,
    );
  }

  if (waistStress >= 1) {
    r.waist.tighten = Math.max(
      0,
      Math.round((r.waist.tighten - STEP_WAIST * 0.55) * 1000) / 1000,
    );
    r.waist.offsetZ = Math.round((r.waist.offsetZ + STEP_TZ * 0.8) * 1000) / 1000;
  }

  if (hemStress >= 1) {
    r.hem.offsetY = Math.min(
      0.1,
      Math.round((r.hem.offsetY + STEP_HEM) * 1000) / 1000,
    );
  }

  if (report.overallStabilityScore < 65 && torsoStress + sleeveStress >= 2) {
    g.inflate = Math.round((g.inflate + 0.006) * 1000) / 1000;
  }

  r.torso.offsetZ = Math.max(
    -MAX_TORSO_Z,
    Math.min(MAX_TORSO_Z, r.torso.offsetZ),
  );

  return s;
}

export type StabilizeFitResult = {
  fit: GarmentFitState;
  finalReport: PoseStressTestReport;
  iterations: number;
  log: string[];
  aggregate: AggregatedStressAnalysis;
};

/**
 * Few iterations of small adjustments; re-evaluates stress test each round.
 */
export function stabilizeFitAcrossPoses(
  garmentFit: GarmentFitState,
  flags: RuntimeClippingFlags,
  options?: {
    maxIterations?: number;
    targetStability?: number;
    poses?: readonly DevAvatarPoseKey[];
  },
): StabilizeFitResult {
  const maxIterations = options?.maxIterations ?? MAX_ITER;
  const targetStability = options?.targetStability ?? TARGET_SCORE;
  const poses = options?.poses ?? STRESS_TEST_POSES;

  let current = cloneGarmentFitState(garmentFit);
  const log: string[] = [];
  let lastReport = runPoseStressTest(current, flags, poses);
  let applyCount = 0;

  if (
    lastReport.allPosesPass &&
    lastReport.overallStabilityScore >= targetStability
  ) {
    log.push(
      `Already stable: score ${lastReport.overallStabilityScore}, all poses pass.`,
    );
    return {
      fit: current,
      finalReport: lastReport,
      iterations: 0,
      log,
      aggregate: aggregateStressResults(lastReport),
    };
  }

  for (let i = 0; i < maxIterations; i++) {
    const beforeScore = lastReport.overallStabilityScore;
    current = applyStabilizationStep(current, lastReport);
    applyCount += 1;
    lastReport = runPoseStressTest(current, flags, poses);
    log.push(
      `Iteration ${i + 1}: overall ${beforeScore} → ${lastReport.overallStabilityScore}`,
    );

    if (
      lastReport.allPosesPass &&
      lastReport.overallStabilityScore >= targetStability
    ) {
      log.push("Target reached: all poses pass and score ≥ target.");
      break;
    }
    if (lastReport.overallStabilityScore <= beforeScore) {
      log.push("No score improvement — stopping.");
      break;
    }
  }

  return {
    fit: current,
    finalReport: lastReport,
    iterations: applyCount,
    log,
    aggregate: aggregateStressResults(lastReport),
  };
}

/** Serializable subset for `LiveFitSessionSnapshot` (history / compare). */
export type LiveFitStressSnapshotMeta = {
  overallStabilityScore: number;
  allPosesPass: boolean;
  worstPose: DevAvatarPoseKey | null;
  worstRegion: StressRegionKey | null;
  perPose: Array<{
    pose: DevAvatarPoseKey;
    stabilityScore: number;
    pass: boolean;
  }>;
};

export function stressReportToSnapshotMeta(
  r: PoseStressTestReport,
): LiveFitStressSnapshotMeta {
  return {
    overallStabilityScore: r.overallStabilityScore,
    allPosesPass: r.allPosesPass,
    worstPose: r.worstPose,
    worstRegion: r.worstRegion,
    perPose: r.poses.map((p) => ({
      pose: p.pose,
      stabilityScore: p.stabilityScore,
      pass: p.pass,
    })),
  };
}
