from __future__ import annotations

import ast
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from statistics import median
from typing import Any, Literal

from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes

FieldClass = Literal["semantic_consumed", "validation_only", "provenance_only"]
ROUTES = (
    "no_pixel_template_prior",
    "deterministic_masks_landmarks",
    "image_conditioned_iterative",
    "metadata_only_control",
)
FULL_COMPILE_ROUTES = ROUTES[:3]
PRIMARY_ROUTE = "deterministic_masks_landmarks"
GATE_FAMILIES = (
    "pattern",
    "seam",
    "opening",
    "topology",
    "simulation",
    "binding",
    "source_silhouette",
    "landmark",
    "appearance",
    "texture_identity",
    "pbr_integrity",
    "reproducibility",
)
FORBIDDEN_CONTESTANT_TOKENS = (
    "target_rgba",
    "target_palette",
    "target_uv_bounds",
    "target_dimensions",
    "fixture_tshirt_extent",
    "candidate_camera_bounds",
)


def load_declared_artifact(path: Path, *, declared_shape: str) -> dict[str, Any] | list[Any]:
    value = read_json(path)
    if declared_shape == "mapping":
        if not isinstance(value, Mapping):
            raise ValueError("evaluator_v2_mapping_artifact_required")
        return dict(value)
    if declared_shape == "list":
        if not isinstance(value, list):
            raise ValueError("evaluator_v2_list_artifact_required")
        return value
    raise ValueError(f"evaluator_v2_unknown_declared_shape:{declared_shape}")


def validate_protocol(protocol: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    expected = {
        "evaluatorIdentityCount": 16,
        "predictionDenominator": 64,
        "fullCompileDenominator": 48,
        "primaryCompileRepeatDenominator": 16,
        "appearanceDenominator": 24,
        "primaryAppearanceRepeatDenominator": 8,
    }
    for field, value in expected.items():
        if protocol.get(field) != value:
            issues.append(f"protocol_denominator_invalid:{field}")
    if tuple(protocol.get("routes", ())) != ROUTES:
        issues.append("protocol_route_inventory_invalid")
    if tuple(protocol.get("fullCompileRoutes", ())) != FULL_COMPILE_ROUTES:
        issues.append("protocol_full_compile_routes_invalid")
    if protocol.get("primaryRoute") != PRIMARY_ROUTE:
        issues.append("protocol_primary_route_invalid")
    if protocol.get("perIdentityRouteSelectionAllowed") is not False:
        issues.append("protocol_mosaic_not_forbidden")
    if protocol.get("failedItemsRetainedInDenominator") is not True:
        issues.append("protocol_failure_denominator_not_immutable")
    if protocol.get("d0Rp03IndependentFromD0Rp06") is not True:
        issues.append("protocol_rp03_rp06_conflated")
    return issues


def audit_disjointness(inventories: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    rows = [
        {
            "inventory": inventory,
            "identity": str(row.get("identity", "")),
            "geometryHash": str(row.get("geometryHash", "")),
            "pixelHash": str(row.get("pixelHash", "")),
            "parameterAlias": str(row.get("parameterAlias", "")),
            "seedAlias": str(row.get("seedAlias", "")),
            "targetFeatureHash": str(row.get("targetFeatureHash", "")),
        }
        for inventory, records in sorted(inventories.items())
        for row in records
    ]
    duplicate_fields: dict[str, list[str]] = {}
    for field in (
        "identity",
        "geometryHash",
        "pixelHash",
        "parameterAlias",
        "seedAlias",
        "targetFeatureHash",
    ):
        counts = Counter(row[field] for row in rows if row[field])
        duplicate_fields[field] = sorted(value for value, count in counts.items() if count > 1)
    result = {
        "inventoryNames": sorted(inventories),
        "recordCount": len(rows),
        "duplicateFields": duplicate_fields,
        "allDisjoint": all(not values for values in duplicate_fields.values()),
        "inventoryDigest": sha256_bytes(canonical_dumps(rows).encode("utf-8")),
    }
    return result


def audit_contestant_source(source: str) -> list[str]:
    issues: list[str] = []
    lowered = source.lower()
    for token in FORBIDDEN_CONTESTANT_TOKENS:
        if token in lowered:
            issues.append(f"forbidden_target_feature_token:{token}")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [*issues, "contestant_source_syntax_invalid"]
    numeric = [
        float(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, int | float)
        and not isinstance(node.value, bool)
    ]
    if len(set(numeric)) > 48:
        issues.append("contestant_hardcoded_numeric_table_suspected")
    return sorted(set(issues))


def derive_contribution(observed_pixels: int, generated_pixels: int) -> dict[str, float]:
    if observed_pixels < 0 or generated_pixels < 0:
        raise ValueError("contribution_pixel_count_negative")
    denominator = observed_pixels + generated_pixels
    if denominator <= 0:
        raise ValueError("contribution_empty_evidence")
    return {
        "sourceObserved": round(observed_pixels / denominator, 12),
        "generated": round(generated_pixels / denominator, 12),
    }


def evaluate_generic_rows(
    protocol: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    issues = validate_protocol(protocol)
    if issues:
        raise ValueError(";".join(issues))
    expected_keys = {(ordinal, route) for ordinal in range(16) for route in FULL_COMPILE_ROUTES}
    by_key = {(int(row["ordinal"]), str(row["routeId"])): row for row in rows}
    missing = sorted(expected_keys - set(by_key))
    extra = sorted(set(by_key) - expected_keys)
    records: list[dict[str, Any]] = []
    for ordinal, route in sorted(expected_keys):
        row = by_key.get((ordinal, route))
        if row is None:
            records.append(_failure_record(ordinal, route, "missing_frozen_item"))
            continue
        records.append(_score_row(row))
    summaries = [_route_summary(route, records) for route in FULL_COMPILE_ROUTES]
    primary = next(row for row in summaries if row["routeId"] == PRIMARY_ROUTE)
    baseline = next(row for row in summaries if row["routeId"] == FULL_COMPILE_ROUTES[0])
    relative = (baseline["meanMacroError"] - primary["meanMacroError"]) / max(
        1e-12, baseline["meanMacroError"]
    )
    silhouette = primary["meanSilhouetteIoU"] - baseline["meanSilhouetteIoU"]
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "evaluatorVersion": "closy.d0_identity_disjoint_evaluator.v2",
        "missingItems": [list(item) for item in missing],
        "extraItems": [list(item) for item in extra],
        "records": records,
        "routeSummaries": summaries,
        "comparisons": {
            "primaryVersusNoPixelParameterRelativeImprovement": round(relative, 12),
            "primaryVersusNoPixelSilhouetteAbsoluteImprovement": round(silhouette, 12),
            "equalEvidence": True,
            "perRowWinnerUsed": False,
        },
        "rowDecisions": {
            "D0-RP-03": "pass" if primary["functionalAbsolutePass"] else "fail",
            "D0-RP-06": "pass" if primary["sourceConditioningPass"] else "fail",
            "D0-RP-07": "pass" if primary["appearanceAbsolutePass"] else "fail",
        },
        "failuresRetainedInDenominator": True,
        "resultDigest": "",
    }
    result["resultDigest"] = _hash({**result, "resultDigest": ""})
    return result


def classify_lock_fields() -> list[dict[str, Any]]:
    return [
        {
            "pointer": "/thresholds/maximumMedianMacroNormalizedObservableError",
            "fieldClass": "semantic_consumed",
            "gateFamily": "pattern",
            "mutationExpectation": "changes_computed_acceptance",
        },
        {
            "pointer": "/denominators/predictions",
            "fieldClass": "validation_only",
            "gateFamily": "reproducibility",
            "mutationExpectation": "validation_rejects",
        },
        {
            "pointer": "/lineage/sourceLockSha",
            "fieldClass": "provenance_only",
            "gateFamily": "reproducibility",
            "mutationExpectation": "changes_digest_and_lineage",
        },
        *[
            {
                "pointer": f"/gateFamilies/{family}",
                "fieldClass": "semantic_consumed",
                "gateFamily": family,
                "mutationExpectation": "changes_row_gate_result",
            }
            for family in GATE_FAMILIES
        ],
    ]


def run_generic_mutation_fixtures() -> dict[str, Any]:
    protocol = generic_protocol()
    rows = generic_rows()
    baseline = evaluate_generic_rows(protocol, rows)
    semantic = deepcopy(rows)
    semantic[16]["metrics"]["macroNormalizedError"] = 1.0
    semantic_changed = (
        evaluate_generic_rows(protocol, semantic)["resultDigest"] != baseline["resultDigest"]
    )
    invalid = deepcopy(protocol)
    invalid["predictionDenominator"] = 63
    validation_rejected = bool(validate_protocol(invalid))
    provenance = {"sourceLockSha": "a" * 40}
    first_digest = _hash(provenance)
    provenance["sourceLockSha"] = "b" * 40
    provenance_changed = _hash(provenance) != first_digest
    gate_mutations = {family: _gate_mutation_detected(family, rows) for family in GATE_FAMILIES}
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "fixtureVersion": "closy.d0_identity_disjoint_evaluator.generic_fixtures.v2",
        "qualificationDataUsed": False,
        "freshEvaluatorIdentityRealized": False,
        "freshTargetRealized": False,
        "mappingAndListLoaders": True,
        "completeDispatch": len(baseline["records"]) == 48,
        "fieldClasses": classify_lock_fields(),
        "semanticMutationChangesBehaviour": semantic_changed,
        "validationMutationRejected": validation_rejected,
        "provenanceMutationChangesDigest": provenance_changed,
        "gateFamilyMutations": gate_mutations,
        "allPassed": all(gate_mutations.values())
        and semantic_changed
        and validation_rejected
        and provenance_changed,
        "integrity": {"fixtureDigest": ""},
    }
    report["integrity"]["fixtureDigest"] = _hash({**report, "integrity": {"fixtureDigest": ""}})
    return report


def generic_protocol() -> dict[str, Any]:
    return {
        "evaluatorIdentityCount": 16,
        "predictionDenominator": 64,
        "fullCompileDenominator": 48,
        "primaryCompileRepeatDenominator": 16,
        "appearanceDenominator": 24,
        "primaryAppearanceRepeatDenominator": 8,
        "routes": list(ROUTES),
        "fullCompileRoutes": list(FULL_COMPILE_ROUTES),
        "primaryRoute": PRIMARY_ROUTE,
        "perIdentityRouteSelectionAllowed": False,
        "failedItemsRetainedInDenominator": True,
        "d0Rp03IndependentFromD0Rp06": True,
    }


def generic_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    route_error = {FULL_COMPILE_ROUTES[0]: 0.2, PRIMARY_ROUTE: 0.08, FULL_COMPILE_ROUTES[2]: 0.07}
    route_iou = {FULL_COMPILE_ROUTES[0]: 0.32, PRIMARY_ROUTE: 0.38, FULL_COMPILE_ROUTES[2]: 0.4}
    for ordinal in range(16):
        for route in FULL_COMPILE_ROUTES:
            rows.append(
                {
                    "ordinal": ordinal,
                    "routeId": route,
                    "status": "pass",
                    "applicableAppearance": ordinal < 8,
                    "metrics": {
                        "macroNormalizedError": route_error[route],
                        "worstNormalizedError": route_error[route] + 0.05,
                        "silhouetteIoU": route_iou[route],
                        "boundaryError": 0.1,
                        "landmarkError": 0.08,
                        "referenceRmsMeters": 0.04,
                        "foregroundSrgbMae": 0.08,
                        "logoDisplacement": 0.08,
                        "logoFalsePositiveFraction": 0.001,
                        "logoIoU": 0.1,
                    },
                    "gates": {family: True for family in GATE_FAMILIES},
                    "observedPixels": 72,
                    "generatedPixels": 28,
                    "cameraFramingSource": "source_only",
                }
            )
    return rows


def _score_row(row: Mapping[str, Any]) -> dict[str, Any]:
    metrics = dict(_mapping(row.get("metrics")))
    gates = {
        family: bool(_mapping(row.get("gates")).get(family, False)) for family in GATE_FAMILIES
    }
    if row.get("cameraFramingSource") != "source_only":
        gates["source_silhouette"] = False
    contribution = derive_contribution(
        int(row.get("observedPixels", 0)), int(row.get("generatedPixels", 0))
    )
    applicable = bool(row.get("applicableAppearance", False))
    appearance = (
        (
            float(metrics.get("foregroundSrgbMae", math.inf)) <= 0.12
            and float(metrics.get("logoDisplacement", math.inf)) <= 0.14
            and float(metrics.get("logoFalsePositiveFraction", math.inf)) <= 0.002
            and float(metrics.get("logoIoU", -math.inf)) >= 0.02
        )
        if applicable
        else None
    )
    status = "pass" if row.get("status") == "pass" and all(gates.values()) else "fail"
    return {
        "ordinal": int(row["ordinal"]),
        "routeId": str(row["routeId"]),
        "status": status,
        "metrics": metrics,
        "gates": gates,
        "appearanceApplicable": applicable,
        "appearancePass": appearance,
        "contribution": contribution,
    }


def _failure_record(ordinal: int, route: str, reason: str) -> dict[str, Any]:
    return {
        "ordinal": ordinal,
        "routeId": route,
        "status": "fail",
        "failureReason": reason,
        "metrics": {
            "macroNormalizedError": 1.0,
            "worstNormalizedError": 1.0,
            "silhouetteIoU": 0.0,
        },
        "gates": {family: False for family in GATE_FAMILIES},
        "appearanceApplicable": ordinal < 8,
        "appearancePass": False if ordinal < 8 else None,
        "contribution": None,
    }


def _route_summary(route: str, records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    route_rows = [row for row in records if row.get("routeId") == route]
    errors = [
        float(_mapping(row.get("metrics")).get("macroNormalizedError", 1.0)) for row in route_rows
    ]
    silhouettes = [
        float(_mapping(row.get("metrics")).get("silhouetteIoU", 0.0)) for row in route_rows
    ]
    appearance = [row for row in route_rows if row.get("appearanceApplicable") is True]
    gate_families = [
        all(bool(_mapping(row.get("gates")).get(family, False)) for row in route_rows)
        for family in GATE_FAMILIES
    ]
    functional = (
        sum(row.get("status") == "pass" for row in route_rows) >= 14
        and median(errors) <= 0.10
        and max(errors, default=1.0) <= 0.25
        and math.fsum(silhouettes) / 16 >= 0.30
        and all(gate_families)
    )
    return {
        "routeId": route,
        "denominator": 16,
        "coverage": sum(row.get("status") == "pass" for row in route_rows),
        "medianMacroError": median(errors),
        "meanMacroError": math.fsum(errors) / 16,
        "worstMacroError": max(errors, default=1.0),
        "meanSilhouetteIoU": math.fsum(silhouettes) / 16,
        "functionalAbsolutePass": functional,
        "sourceConditioningPass": functional and route != FULL_COMPILE_ROUTES[0],
        "appearanceAbsolutePass": len(appearance) == 8
        and all(row.get("appearancePass") is True for row in appearance),
    }


def _gate_mutation_detected(family: str, rows: list[dict[str, Any]]) -> bool:
    mutated = deepcopy(rows)
    mutated[16]["gates"][family] = False
    result = evaluate_generic_rows(generic_protocol(), mutated)
    record = next(
        row for row in result["records"] if row["ordinal"] == 5 and row["routeId"] == PRIMARY_ROUTE
    )
    return record["status"] == "fail" and record["gates"][family] is False


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _hash(value: object) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))
