from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from closy_forge.disjoint_benchmark_v1.metrics import paired_bootstrap
from closy_forge.disjoint_confirmation_v2.evaluator import execute_evaluator as execute_v2
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

from .protocol import OUTCOMES, PRIMARY_ROUTE, ROUTES

TO_LEGACY = {
    ROUTES[0]: "metadata_only_control",
    ROUTES[1]: "no_pixel_template_prior",
    ROUTES[2]: "image_conditioned_iterative",
    ROUTES[3]: "deterministic_masks_landmarks",
}
FROM_LEGACY = {value: key for key, value in TO_LEGACY.items()}


def execute_evaluator(
    root: Any,
    *,
    protocol: Mapping[str, Any],
    predictions: Mapping[str, Any],
    targets: Mapping[str, Any],
    isolation_summary: Mapping[str, Any],
    contestant_repeats: Sequence[Mapping[str, Any]],
    integrity_pass: bool,
) -> dict[str, Any]:
    translated = {
        "schemaVersion": 1,
        "predictions": [
            _translate_prediction(row) for row in _records(predictions.get("predictions"))
        ],
    }
    legacy_protocol = {"thresholds": dict(_mapping(protocol.get("thresholds")))}
    legacy = execute_v2(
        root,
        protocol=legacy_protocol,
        predictions=translated,
        targets=targets,
        isolation_summary={
            "qualifiesD0Rp04": isolation_summary.get("qualifiesD0Rp04") is True,
        },
    )
    result = _translate_result(legacy)
    thresholds = _mapping(protocol.get("thresholds"))
    summaries = {str(row["routeId"]): row for row in _records(result.get("routeSummaries"))}
    primary = _mapping(summaries.get(PRIMARY_ROUTE))
    mask = _mapping(summaries.get(ROUTES[2]))
    learned_parameter = _relative_reduction(
        float(primary.get("meanMacroNormalizedError", 1.0)),
        float(mask.get("meanMacroNormalizedError", 1.0)),
    )
    learned_silhouette = float(primary.get("meanSilhouetteIoU", 0.0)) - float(
        mask.get("meanSilhouetteIoU", 0.0)
    )
    records = _records(result.get("records"))
    primary_rows = sorted(
        (row for row in records if row.get("routeId") == PRIMARY_ROUTE),
        key=lambda row: int(row["ordinal"]),
    )
    mask_rows = sorted(
        (row for row in records if row.get("routeId") == ROUTES[2]),
        key=lambda row: int(row["ordinal"]),
    )
    parameter_bootstrap = paired_bootstrap(
        [
            float(_mapping(row.get("parameterMetrics")).get("macroNormalizedError", 1.0))
            for row in primary_rows
        ],
        [
            float(_mapping(row.get("parameterMetrics")).get("macroNormalizedError", 1.0))
            for row in mask_rows
        ],
        lower_is_better=True,
        seed=int(thresholds["bootstrapSeed"]) + 2,
        resamples=int(thresholds["bootstrapResamples"]),
    )
    silhouette_bootstrap = paired_bootstrap(
        [
            float(_mapping(row.get("rasterMetrics")).get("silhouetteIoU", 0.0))
            for row in primary_rows
        ],
        [float(_mapping(row.get("rasterMetrics")).get("silhouetteIoU", 0.0)) for row in mask_rows],
        lower_is_better=False,
        seed=int(thresholds["bootstrapSeed"]) + 3,
        resamples=int(thresholds["bootstrapResamples"]),
    )
    learned_winner = (
        len(primary_rows) == 16
        and len(mask_rows) == 16
        and learned_parameter
        >= float(thresholds["learnedWinnerParameterRelativeImprovementMinimum"])
        and learned_silhouette
        >= float(thresholds["learnedWinnerSilhouetteAbsoluteImprovementMinimum"])
        and float(parameter_bootstrap["lower95"]) > 0.0
        and float(silhouette_bootstrap["lower95"]) > 0.0
    )
    repeat_pass = _contestant_repeat_pass(predictions, contestant_repeats)
    row_results = _mapping(result.get("rowDecisions"))
    row_results["D0-RP-04"] = (
        "pass"
        if isolation_summary.get("qualifiesD0Rp04") is True
        and result.get("deterministicFreshProcessRepeat") is True
        and repeat_pass
        else "fail"
    )
    absolute_pass = row_results.get("D0-RP-03") == "pass" and row_results.get("D0-RP-07") == "pass"
    comparative_pass = row_results.get("D0-RP-06") == "pass" and learned_winner
    all_rows_pass = all(
        row_results.get(row) == "pass" for row in ("D0-RP-03", "D0-RP-04", "D0-RP-06", "D0-RP-07")
    )
    promoted = all_rows_pass and comparative_pass and integrity_pass
    if promoted:
        outcome = OUTCOMES[0]
    elif not absolute_pass:
        outcome = OUTCOMES[1]
    elif not comparative_pass:
        outcome = OUTCOMES[2]
    else:
        outcome = OUTCOMES[3]
    result.update(
        {
            "schemaVersion": 1,
            "resultVersion": "closy.d0_disjoint_tshirt_confirmation.result.v3",
            "outcome": outcome,
            "attemptState": "completed",
            "rowDecisions": row_results,
            "rowAttemptStates": {row: "completed" for row in row_results},
            "learnedWinnerComparative": {
                "parameterRelativeImprovement": learned_parameter,
                "silhouetteAbsoluteImprovement": learned_silhouette,
                "parameterBootstrap": parameter_bootstrap,
                "silhouetteBootstrap": silhouette_bootstrap,
                "pass": learned_winner,
            },
            "contestantRepeatPass": repeat_pass,
            "integrityPass": integrity_pass,
            "routePromotion": {
                "promoted": promoted,
                "routeId": PRIMARY_ROUTE if promoted else None,
                "perIdentityMosaicUsed": False,
                "tieRule": "simpler_lower_evidence_route",
                "requiresAllFourRows": True,
                "reason": (
                    "all_locked_absolute_comparative_isolation_appearance_determinism_and_integrity_predicates_passed"
                    if promoted
                    else "one_or_more_locked_promotion_predicates_failed"
                ),
            },
            "successfulPredictionArtifactCount": sum(
                row.get("status") == "pass" for row in _records(predictions.get("attemptRows"))
            ),
            "authorityClaim": "procedural_freeze_and_container_isolation_not_cryptographic_secrecy",
            "disjointnessScope": "recoverable_inventory_only_lost_v2_relation_unverified",
            "physicalPbrAccuracyClaimed": False,
            "visibleAppearanceRecoverySeparatedFromPbrPresetValidity": True,
            "resultHash": "",
        }
    )
    result["resultHash"] = _hash({**result, "resultHash": ""})
    return result


def _translate_prediction(row: Mapping[str, Any]) -> dict[str, Any]:
    translated = deepcopy(dict(row))
    translated["routeId"] = TO_LEGACY[str(row["routeId"])]
    translated["predictionHash"] = _hash({**translated, "predictionHash": ""})
    return translated


def _translate_result(value: Mapping[str, Any]) -> dict[str, Any]:
    def visit(item: object) -> object:
        if isinstance(item, str):
            return FROM_LEGACY.get(item, item)
        if isinstance(item, list):
            return [visit(child) for child in item]
        if isinstance(item, Mapping):
            return {str(key): visit(child) for key, child in item.items()}
        return item

    translated = visit(value)
    if not isinstance(translated, dict):
        raise ValueError("d0_v3_translated_result_invalid")
    return translated


def _contestant_repeat_pass(
    predictions: Mapping[str, Any], repeats: Sequence[Mapping[str, Any]]
) -> bool:
    originals = {
        (int(row["ordinal"]), str(row["routeId"])): row
        for row in _records(predictions.get("predictions"))
        if row.get("routeId") == PRIMARY_ROUTE
    }
    if len(originals) != 16 or len(repeats) != 16:
        return False
    for repeat in repeats:
        key = (int(repeat["ordinal"]), str(repeat["routeId"]))
        original = originals.get(key)
        if original is None:
            return False
        fields = ("abstained", "appearance", "parameters", "evidenceClass")
        if any(original.get(field) != repeat.get(field) for field in fields):
            return False
    return True


def validate_result(result: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if result.get("outcome") not in OUTCOMES[:4]:
        issues.append("d0_v3_result_outcome_invalid")
    expected = {
        "predictionDenominator": 64,
        "predictionCount": 64,
        "fullCompileDenominator": 48,
        "fullCompileCount": 48,
        "primaryCompileRepeatDenominator": 16,
        "primaryCompileRepeatCount": 16,
        "appearanceDenominator": 24,
        "appearanceEvaluationCount": 24,
        "primaryAppearanceRepeatDenominator": 8,
        "primaryAppearanceRepeatCount": 8,
    }
    for field, value in expected.items():
        if result.get(field) != value:
            issues.append(f"d0_v3_result_denominator_invalid:{field}")
    rows = _mapping(result.get("rowDecisions"))
    if set(rows) != {"D0-RP-03", "D0-RP-04", "D0-RP-06", "D0-RP-07"}:
        issues.append("d0_v3_result_row_inventory_invalid")
    if any(value not in {"pass", "fail"} for value in rows.values()):
        issues.append("d0_v3_result_row_value_invalid")
    if result.get("failuresRetainedInDenominator") is not True:
        issues.append("d0_v3_result_failure_denominator_not_preserved")
    promotion = _mapping(result.get("routePromotion"))
    if promotion.get("perIdentityMosaicUsed") is not False:
        issues.append("d0_v3_result_per_identity_mosaic_used")
    if not math.isfinite(
        float(
            _mapping(result.get("learnedWinnerComparative")).get(
                "parameterRelativeImprovement", math.nan
            )
        )
    ):
        issues.append("d0_v3_result_nonfinite_comparative")
    if _hash({**dict(result), "resultHash": ""}) != result.get("resultHash"):
        issues.append("d0_v3_result_hash_invalid")
    return sorted(set(issues))


def _relative_reduction(primary: float, baseline: float) -> float:
    return (baseline - primary) / max(abs(baseline), 1e-12)


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _records(value: object) -> list[dict[str, Any]]:
    return [_mapping(row) for row in value] if isinstance(value, list | tuple) else []


def _hash(value: Any) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))
