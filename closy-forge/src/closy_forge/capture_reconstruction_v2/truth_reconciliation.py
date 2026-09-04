from __future__ import annotations

from collections import Counter
from typing import Any

from .common import canonical_digest


def build_truth_reconciliation(pr62_final_head: str, pr62_final_run: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = [
        {
            "id": "PR60_UNIT_Y2",
            "state": "integrity_error",
            "terminalOutcome": "preseed_scientific_protocol_invalid",
            "reason": "scientific_protocol_incomplete_before_seed_or_attempt",
            "authorityIdReusable": False,
            "consumed": {
                "authorityTag": False,
                "seed": False,
                "scientificAttempt": False,
                "topologyStrategy": False,
                "candidate": False,
            },
            "evidence": ["PR60", "Forge run 33741178274"],
        },
        {
            "id": "PR61_CAPTURE_ENGINEERING_V1",
            "state": "superseded",
            "terminalOutcome": "development_acceptance_partial",
            "evidenceClass": "project_authored_decoded_raster_synthetic_engineering",
            "denominators": {
                "sessions": 80,
                "stillImages": 136,
                "aviClips": 12,
                "decodedVideoFrames": 288,
                "packageValid": 8,
                "packageAttempted": 20,
                "tshirtValid": 4,
                "tshirtAttempted": 4,
                "sleevelessValid": 4,
                "sleevelessAttempted": 8,
                "skirtValid": 0,
                "skirtAttempted": 8,
            },
            "limitations": [
                "synthetic_only_32x44_pixels",
                "mode_b_d_avatar_pose_semantics_metadata_only",
                "flat_hung_distinction_metadata_only",
                "camera_from_view_role_and_self_comparison",
                "fitter_first_observation_and_own_renderer",
                "uv_exact_target_bounds_to_foreground_box",
                "correction_journal_no_op",
                "all_validation_identities_development_exposed",
            ],
            "downgradedClaims": [
                "BP-CAMERA-OBSERVATION",
                "BP-SOURCE-PANEL-UV",
                "Mode-B",
                "Mode-D",
                "fitting",
                "correction",
                "D0-prerequisite",
            ],
            "evidence": ["PR61", "Forge run 33758649869"],
        },
        {
            "id": "PR62_SOLVER_MATERIAL_V1",
            "state": "failed",
            "terminalOutcome": "retrospective_contaminated_engineering_evaluation",
            "evidenceClass": "project_authored_same_author_correlated_scalar_solver_engineering",
            "engineeringAcceptance": "failed",
            "scientificQualification": "ineligible_test_exposed_before_estimator",
            "firstUnmetPredicate": "meanSixFieldNormalizedError",
            "resultDigest": "2e54ee3eaa80bc686c86d44c844cb6b63ac3ff24500999dca937d48d1d1c6e4d",
            "resultHead": pr62_final_head,
            "resultRun": pr62_final_run,
            "limitations": [
                "scalar_toy_coupon_chains_not_garment_physics",
                "no_real_coupon_evidence",
                "no_withheld_prediction",
            ],
            "evidence": ["PR62", f"Forge run {pr62_final_run}"],
        },
        {
            "id": "HISTORICAL_BLUEPRINT_TOTALS",
            "state": "superseded",
            "reason": "stale_until_current_source_derived_recount",
            "historicalCounts": {
                "complete": 20,
                "partial": 63,
                "notStarted": 7,
                "discoveryPending": 11,
                "total": 101,
            },
            "countsAreCurrent": False,
            "evidence": ["PR60 starting status snapshot"],
        },
    ]
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "reconciliationVersion": "closy.truth_reconciliation.capture_v2.v1",
        "repository": "jake-the-jake/Closy",
        "mainAtUnitStart": "859d4ee9a8a3386e95ec8c29043aa9ecc246769a",
        "mainUnprotectedObserved": True,
        "stackState": "all_implementation_prs_draft_open_unmerged",
        "rows": rows,
        "statusCounts": dict(sorted(Counter(str(row["state"]) for row in rows).items())),
        "remainingBudgets": {"canonicalCandidateCount": 1, "topologyStrategyCount": 0},
        "strategy3Consumed": True,
    }
    result["reconciliationDigest"] = canonical_digest(result)
    return result


def render_truth_markdown(document: dict[str, Any]) -> str:
    rows = {row["id"]: row for row in document["rows"]}
    pr61 = rows["PR61_CAPTURE_ENGINEERING_V1"]
    pr62 = rows["PR62_SOLVER_MATERIAL_V1"]
    return f"""# Capture V2 truth reconciliation

This append-only update is generated from `truth_reconciliation.json`. It preserves prior bytes and
records corrections without rewriting historical results.

## Unit Y2 / PR #60

`preseed_scientific_protocol_invalid`: the protocol was incomplete before arming. No
authority tag, seed, scientific attempt, topology strategy, or candidate was consumed.
The authorization identity is terminal and may never be reused. Candidate budget remains
one; topology-strategy budget remains zero; Strategy 3 remains consumed.

## Capture engineering V1 / PR #61

Evidence is project-authored decoded-raster synthetic engineering, not capture/reconstruction
qualification. It retained {pr61['denominators']['sessions']} sessions,
{pr61['denominators']['stillImages']} stills, {pr61['denominators']['aviClips']} AVI clips, and
{pr61['denominators']['decodedVideoFrames']} decoded video frames. Intrinsic packages were
{pr61['denominators']['packageValid']}/{pr61['denominators']['packageAttempted']}: T-shirt 4/4,
sleeveless 4/8, and skirt 0/8.

The 32x44 pixels were synthetic only. Mode B/D avatar/pose semantics and flat/hung
distinction were metadata-only; camera used the view role and self-compared geometry;
fitting used the first observation and its source renderer; UV mapped target bounds into a
foreground box; corrections were no-ops. Camera, source-panel UV, Mode B/D, fitting,
correction, and D0-prerequisite claims are therefore `partial`. All V1 validation identities
are exposed development identities and cannot qualify a future locked result.

## Solver/material V1 / PR #62

Result `{pr62['resultDigest']}` at `{pr62['resultHead']}` / run `{pr62['resultRun']}` is
`retrospective_contaminated_engineering_evaluation`; engineering acceptance is `failed`, scientific
qualification is `ineligible_test_exposed_before_estimator`, and the first unmet predicate
is `meanSixFieldNormalizedError`. It is toy-chain estimator evidence, not material physics
or real-coupon evidence.

## Status boundary

The historical 20 complete / 63 partial / 7 not started / 11 discovery pending summary is
superseded and stale until the source-derived V2 inventory is published. `main` was
unchanged and unprotected at unit start. Every stacked implementation PR remained draft
and unmerged.
"""
