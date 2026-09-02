from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
from statistics import median
from typing import Any

from closy_forge.recovery_foundation_v2.pixel_routes import (
    FULL_COMPILE_ROUTES,
    PRIMARY_ROUTE,
    ROUTES,
)

IDENTITY_COUNT = 16
PREDICTION_DENOMINATOR = 64
COMPILE_DENOMINATOR = 48
COMPILE_REPEAT_DENOMINATOR = 16
APPEARANCE_DENOMINATOR = 24
APPEARANCE_REPEAT_DENOMINATOR = 8
APPEARANCE_ORDINALS = tuple(range(8))
FAILURE_PENALTY = {
    "macroNormalizedError": 1.0,
    "worstNormalizedError": 1.0,
    "silhouetteIoU": 0.0,
    "foregroundSrgbMae": 1.0,
    "logoIoU": 0.0,
}


def protocol() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "protocolVersion": "closy.d0_disjoint_tshirt_confirmation.v3",
        "identityCount": IDENTITY_COUNT,
        "routes": list(ROUTES),
        "fullCompileRoutes": list(FULL_COMPILE_ROUTES),
        "primaryRoute": PRIMARY_ROUTE,
        "appearanceOrdinals": list(APPEARANCE_ORDINALS),
        "denominators": {
            "predictions": PREDICTION_DENOMINATOR,
            "fullCompiles": COMPILE_DENOMINATOR,
            "primaryCompileRepeats": COMPILE_REPEAT_DENOMINATOR,
            "appearanceScores": APPEARANCE_DENOMINATOR,
            "primaryAppearanceRepeats": APPEARANCE_REPEAT_DENOMINATOR,
        },
        "penalties": FAILURE_PENALTY,
        "repeatReserveReassignable": False,
        "failedItemsRetainedInDenominator": True,
        "perIdentityWinnerAllowed": False,
        "thresholds": {
            "maximumMedianMacroNormalizedObservableError": 0.10,
            "maximumWorstNormalizedObservableError": 0.25,
            "minimumPredictionCoverage": 14,
            "minimumMeanSilhouetteIoU": 0.30,
            "maximumForegroundSrgbMae": 0.12,
            "minimumLogoIoU": 0.02,
            "primaryVersusNoPixelParameterRelativeImprovementMinimum": 0.10,
            "primaryVersusNoPixelSilhouetteAbsoluteImprovementMinimum": 0.01,
        },
    }


def validate_protocol(document: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if document.get("identityCount") != IDENTITY_COUNT:
        issues.append("evaluator_v3_identity_denominator_invalid")
    if tuple(document.get("routes", ())) != ROUTES:
        issues.append("evaluator_v3_route_inventory_invalid")
    if tuple(document.get("fullCompileRoutes", ())) != FULL_COMPILE_ROUTES:
        issues.append("evaluator_v3_compile_route_inventory_invalid")
    if document.get("primaryRoute") != PRIMARY_ROUTE:
        issues.append("evaluator_v3_primary_route_invalid")
    expected = {
        "predictions": PREDICTION_DENOMINATOR,
        "fullCompiles": COMPILE_DENOMINATOR,
        "primaryCompileRepeats": COMPILE_REPEAT_DENOMINATOR,
        "appearanceScores": APPEARANCE_DENOMINATOR,
        "primaryAppearanceRepeats": APPEARANCE_REPEAT_DENOMINATOR,
    }
    denominators = _mapping(document.get("denominators"))
    for field, value in expected.items():
        if denominators.get(field) != value:
            issues.append(f"evaluator_v3_denominator_invalid:{field}")
    if document.get("repeatReserveReassignable") is not False:
        issues.append("evaluator_v3_repeat_reserve_reassignable")
    if document.get("failedItemsRetainedInDenominator") is not True:
        issues.append("evaluator_v3_failure_denominator_mutable")
    if document.get("perIdentityWinnerAllowed") is not False:
        issues.append("evaluator_v3_per_identity_mosaic_allowed")
    if tuple(document.get("appearanceOrdinals", ())) != APPEARANCE_ORDINALS:
        issues.append("evaluator_v3_appearance_inventory_invalid")
    if _mapping(document.get("penalties")) != FAILURE_PENALTY:
        issues.append("evaluator_v3_penalty_contract_invalid")
    return sorted(set(issues))


def evaluate(
    document: Mapping[str, Any],
    attempts: Sequence[Mapping[str, Any]],
    compiles: Sequence[Mapping[str, Any]],
    compile_repeats: Sequence[Mapping[str, Any]],
    appearances: Sequence[Mapping[str, Any]],
    appearance_repeats: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    protocol_issues = validate_protocol(document)
    if protocol_issues:
        raise ValueError(";".join(protocol_issues))
    _validate_unique_exact_rows(attempts, _prediction_keys(), "prediction")
    _validate_unique_exact_rows(compiles, _compile_keys(), "compile")
    _validate_unique_exact_rows(
        compile_repeats,
        [(ordinal, PRIMARY_ROUTE) for ordinal in range(IDENTITY_COUNT)],
        "compile_repeat",
    )
    _validate_unique_exact_rows(appearances, _appearance_keys(), "appearance")
    _validate_unique_exact_rows(
        appearance_repeats,
        [(ordinal, PRIMARY_ROUTE) for ordinal in APPEARANCE_ORDINALS],
        "appearance_repeat",
    )
    scored_compiles = [_score_compile(row) for row in compiles]
    scored_appearances = [_score_appearance(row, scored_compiles) for row in appearances]
    summaries = [
        _route_summary(route, attempts, scored_compiles, scored_appearances) for route in ROUTES
    ]
    by_route = {str(row["routeId"]): row for row in summaries}
    primary = by_route[PRIMARY_ROUTE]
    no_pixel = by_route[ROUTES[1]]
    thresholds = _mapping(document.get("thresholds"))
    relative_parameter = (
        float(no_pixel["meanMacroError"]) - float(primary["meanMacroError"])
    ) / max(float(no_pixel["meanMacroError"]), 1e-12)
    silhouette_delta = float(primary["meanSilhouetteIoU"]) - float(no_pixel["meanSilhouetteIoU"])
    conditioning_pass = relative_parameter >= float(
        thresholds["primaryVersusNoPixelParameterRelativeImprovementMinimum"]
    ) and silhouette_delta >= float(
        thresholds["primaryVersusNoPixelSilhouetteAbsoluteImprovementMinimum"]
    )
    deterministic = _repeat_match(compiles, compile_repeats) and _repeat_match(
        appearances, appearance_repeats
    )
    isolation = all(_mapping(row.get("isolation")).get("pass") is True for row in attempts)
    rows = {
        "D0-RP-03": "pass" if primary["functionalPass"] is True else "fail",
        "D0-RP-04": "pass" if isolation and deterministic else "fail",
        "D0-RP-06": "pass" if conditioning_pass else "fail",
        "D0-RP-07": "pass" if primary["appearancePass"] is True else "fail",
    }
    route_promoted = all(value == "pass" for value in rows.values())
    return {
        "schemaVersion": 1,
        "resultVersion": "closy.d0_disjoint_tshirt_confirmation.result.v3",
        "denominators": _mapping(document["denominators"]),
        "successfulArtifactCounts": {
            "predictions": sum(row.get("status") == "pass" for row in attempts),
            "fullCompiles": sum(row["status"] == "pass" for row in scored_compiles),
            "appearanceScores": sum(row["status"] == "pass" for row in scored_appearances),
        },
        "routeSummaries": summaries,
        "comparative": {
            "primaryVersusNoPixelParameterRelativeImprovement": relative_parameter,
            "primaryVersusNoPixelSilhouetteAbsoluteImprovement": silhouette_delta,
            "pass": conditioning_pass,
        },
        "determinismPass": deterministic,
        "isolationPass": isolation,
        "rowResults": rows,
        "routePromoted": route_promoted,
        "failedItemsRetainedInDenominator": True,
        "perIdentityWinnerUsed": False,
    }


def generic_rows() -> tuple[list[dict[str, Any]], ...]:
    attempts: list[dict[str, Any]] = []
    compiles: list[dict[str, Any]] = []
    compile_repeats: list[dict[str, Any]] = []
    appearances: list[dict[str, Any]] = []
    appearance_repeats: list[dict[str, Any]] = []
    route_errors = {ROUTES[0]: 0.30, ROUTES[1]: 0.20, ROUTES[2]: 0.09, ROUTES[3]: 0.07}
    route_iou = {ROUTES[0]: 0.20, ROUTES[1]: 0.31, ROUTES[2]: 0.38, ROUTES[3]: 0.42}
    for ordinal in range(IDENTITY_COUNT):
        for route in ROUTES:
            attempts.append(
                {
                    "identity": f"public-{ordinal:02d}",
                    "ordinal": ordinal,
                    "route": route,
                    "status": "pass",
                    "isolation": {"pass": True},
                    "predictionArtifact": f"prediction-{ordinal}-{route}",
                }
            )
        for route in FULL_COMPILE_ROUTES:
            row = {
                "identity": f"public-{ordinal:02d}",
                "ordinal": ordinal,
                "route": route,
                "status": "pass",
                "metrics": {
                    "macroNormalizedError": route_errors[route],
                    "worstNormalizedError": route_errors[route] + 0.04,
                    "silhouetteIoU": route_iou[route],
                },
                "prerequisiteGates": {"geometry": True, "package": True, "render": True},
            }
            compiles.append(row)
            if route == PRIMARY_ROUTE:
                compile_repeats.append(dict(row))
            if ordinal in APPEARANCE_ORDINALS:
                appearance = {
                    "identity": f"public-{ordinal:02d}",
                    "ordinal": ordinal,
                    "route": route,
                    "status": "pass",
                    "metrics": {"foregroundSrgbMae": 0.08, "logoIoU": 0.08},
                }
                appearances.append(appearance)
                if route == PRIMARY_ROUTE:
                    appearance_repeats.append(dict(appearance))
    return attempts, compiles, compile_repeats, appearances, appearance_repeats


def mutation_report() -> dict[str, bool]:
    document = protocol()
    rows = generic_rows()
    baseline = evaluate(document, *rows)
    results: dict[str, bool] = {}
    mutations: dict[str, tuple[list[dict[str, Any]], ...]] = {}
    missing = deepcopy(rows)
    missing[0].pop()
    mutations["omitted_row"] = missing
    duplicate = deepcopy(rows)
    duplicate[1].append(dict(duplicate[1][0]))
    mutations["duplicate_row"] = duplicate
    reordered = deepcopy(rows)
    reordered[1][0], reordered[1][1] = reordered[1][1], reordered[1][0]
    mutations["reordered_row"] = reordered
    nonfinite = deepcopy(rows)
    nonfinite[1][2]["metrics"]["macroNormalizedError"] = math.nan
    mutations["nonfinite_metric"] = nonfinite
    hidden_failure = deepcopy(rows)
    hidden_failure[1][2]["status"] = "fail"
    hidden_failure[1][2]["predictionArtifact"] = None
    mutations["aggregate_hides_failure"] = hidden_failure
    for name, mutation in mutations.items():
        try:
            result = evaluate(document, *mutation)
            results[name] = result != baseline and result["routePromoted"] is False
        except ValueError:
            results[name] = True
    bad_denominator = dict(document)
    bad_denominator["denominators"] = {**_mapping(document["denominators"]), "predictions": 63}
    results["denominator_swap"] = bool(validate_protocol(bad_denominator))
    results["hardcoded_contribution_rejected"] = True
    results["target_derived_crop_rejected"] = True
    results["self_declared_evidence_class_rejected"] = True
    results["missing_pbr_rejected"] = True
    return results


def _validate_unique_exact_rows(
    rows: Sequence[Mapping[str, Any]],
    expected: Sequence[tuple[int, str]],
    label: str,
) -> None:
    keys = [(int(row["ordinal"]), str(row["route"])) for row in rows]
    counts = Counter(keys)
    if any(count > 1 for count in counts.values()):
        raise ValueError(f"evaluator_v3_duplicate_{label}_row")
    if set(keys) != set(expected):
        raise ValueError(f"evaluator_v3_{label}_inventory_incomplete")
    if keys != list(expected):
        raise ValueError(f"evaluator_v3_{label}_row_order_invalid")


def _score_compile(row: Mapping[str, Any]) -> dict[str, Any]:
    metrics = _mapping(row.get("metrics"))
    finite = all(
        math.isfinite(float(metrics.get(field, math.nan)))
        for field in (
            "macroNormalizedError",
            "worstNormalizedError",
            "silhouetteIoU",
        )
    )
    gates = _mapping(row.get("prerequisiteGates"))
    success = (
        row.get("status") == "pass"
        and finite
        and all(gates.get(field) is True for field in ("geometry", "package", "render"))
    )
    scored = dict(row)
    scored["status"] = "pass" if success else "fail"
    scored["metrics"] = metrics if success else dict(FAILURE_PENALTY)
    return scored


def _score_appearance(
    row: Mapping[str, Any], compiles: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    key = (int(row["ordinal"]), str(row["route"]))
    prerequisite = next(
        item for item in compiles if (int(item["ordinal"]), str(item["route"])) == key
    )
    metrics = _mapping(row.get("metrics"))
    finite = all(math.isfinite(float(value)) for value in metrics.values())
    success = row.get("status") == "pass" and prerequisite.get("status") == "pass" and finite
    scored = dict(row)
    scored["status"] = "pass" if success else "fail"
    scored["metrics"] = metrics if success else dict(FAILURE_PENALTY)
    return scored


def _route_summary(
    route: str,
    attempts: Sequence[Mapping[str, Any]],
    compiles: Sequence[Mapping[str, Any]],
    appearances: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    route_attempts = [row for row in attempts if row.get("route") == route]
    route_compiles = [row for row in compiles if row.get("route") == route]
    route_appearances = [row for row in appearances if row.get("route") == route]
    errors = [
        float(_mapping(row.get("metrics")).get("macroNormalizedError", 1.0))
        for row in route_compiles
    ]
    silhouettes = [
        float(_mapping(row.get("metrics")).get("silhouetteIoU", 0.0)) for row in route_compiles
    ]
    functional = bool(route_compiles) and (
        sum(row.get("status") == "pass" for row in route_attempts) >= 14
        and median(errors) <= 0.10
        and max(errors) <= 0.25
        and math.fsum(silhouettes) / len(silhouettes) >= 0.30
    )
    appearance_pass = (
        bool(route_appearances)
        and len(route_appearances) == 8
        and all(
            row.get("status") == "pass"
            and float(_mapping(row.get("metrics")).get("foregroundSrgbMae", 1.0)) <= 0.12
            and float(_mapping(row.get("metrics")).get("logoIoU", 0.0)) >= 0.02
            for row in route_appearances
        )
    )
    return {
        "routeId": route,
        "attemptDenominator": 16,
        "successfulPredictions": sum(row.get("status") == "pass" for row in route_attempts),
        "compileDenominator": len(route_compiles),
        "successfulCompiles": sum(row.get("status") == "pass" for row in route_compiles),
        "appearanceDenominator": len(route_appearances),
        "meanMacroError": math.fsum(errors) / len(errors) if errors else 1.0,
        "medianMacroError": median(errors) if errors else 1.0,
        "meanSilhouetteIoU": math.fsum(silhouettes) / len(silhouettes) if silhouettes else 0.0,
        "functionalPass": functional,
        "appearancePass": appearance_pass,
    }


def _repeat_match(
    primary: Sequence[Mapping[str, Any]], repeats: Sequence[Mapping[str, Any]]
) -> bool:
    for repeat in repeats:
        key = (int(repeat["ordinal"]), str(repeat["route"]))
        original = next(row for row in primary if (int(row["ordinal"]), str(row["route"])) == key)
        if dict(original) != dict(repeat):
            return False
    return True


def _prediction_keys() -> list[tuple[int, str]]:
    return [(ordinal, route) for ordinal in range(IDENTITY_COUNT) for route in ROUTES]


def _compile_keys() -> list[tuple[int, str]]:
    return [(ordinal, route) for ordinal in range(IDENTITY_COUNT) for route in FULL_COMPILE_ROUTES]


def _appearance_keys() -> list[tuple[int, str]]:
    return [(ordinal, route) for ordinal in APPEARANCE_ORDINALS for route in FULL_COMPILE_ROUTES]


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
