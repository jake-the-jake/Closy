from __future__ import annotations

from dataclasses import replace
from typing import Any

from .contracts import (
    CAPABILITY_VERSION,
    LayerCollisionError,
    LayerSpec,
    OutfitSpec,
    canonical_hash,
)
from .solver import run_simultaneous_layer_solve, summarize_trajectory

ACCEPTANCE_THRESHOLDS = {
    "maximumResidualDepthMeters": 1e-7,
    "maximumResidualContactCount": 0,
    "minimumBodyClearanceMeters": 0.0025,
    "minimumInterLayerSeparationMeters": 0.0018,
    "maximumRadialStrain": 0.08,
    "maximumSeamCrackMeters": 0.005,
    "minimumOpeningRetention": 0.94,
    "maximumLayerOrderViolations": 0,
    "maximumBridgeConstraints": 0,
}


def build_layer_collision_capability_manifest() -> dict[str, Any]:
    cases = [
        _case("top_over_lower_garment", "waist", 0.285, 0.48, 2),
        _case("jacket_over_shirt", "torso", 0.31, 0.75, 2),
        _case("dress_with_outer_layer", "torso_hip", 0.325, 0.62, 2),
        _case("layered_asymmetric_fixture", "torso", 0.30, 0.58, 2),
        _case("lower_body_stress", "lower_body", 0.255, 0.92, 2),
        _case("sleeve_underlying_interaction", "upper_arm", 0.105, 0.88, 2),
        _case("extreme_supported_body", "torso", 0.39, 1.0, 2),
        _case("three_layer_material_mix", "torso", 0.315, 0.82, 3),
        _case("identical_coincident_layers", "torso", 0.30, 0.35, 2, coincident=True),
    ]
    rejection_cases = [
        {"caseId": "cyclic_layer_order", "expectedError": "cyclic_layer_order"},
        {"caseId": "missing_layer_id", "expectedError": "missing_layer_id"},
        {
            "caseId": "reversed_layer_order",
            "expectedError": "layer_order_reversed_or_ambiguous",
        },
        {"caseId": "incompatible_openings", "expectedError": "incompatible_layer_openings"},
    ]
    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "capabilityVersion": CAPABILITY_VERSION,
        "profile": "LayerCollision-D0-source-only-cpu",
        "acceptedCases": [_spec_record(spec) for spec in cases],
        "rejectionCases": rejection_cases,
        "thresholds": ACCEPTANCE_THRESHOLDS,
        "strategyBudget": {
            "maximumStrategies": 2,
            "executedStrategies": 2,
            "maximumTuningTrialsPerStrategy": 4,
            "executedTuningTrials": 2,
        },
        "unsupported": [
            "integrated Phase 13 outfit acceptance",
            "production cloth or visual quality",
            "mobile, GPU, battery, thermal, private-user, licensed-body, and human-review tiers",
        ],
        "integrity": {"manifestHash": ""},
    }
    manifest["integrity"]["manifestHash"] = canonical_hash(
        {**manifest, "integrity": {"manifestHash": ""}}
    )
    return manifest


def run_layer_collision_suite() -> dict[str, Any]:
    manifest = build_layer_collision_capability_manifest()
    specs = {spec.case_id: spec for spec in _accepted_specs()}
    accepted_reports: list[dict[str, Any]] = []
    for declared in manifest["acceptedCases"]:
        spec = specs[str(declared["caseId"])]
        report = run_simultaneous_layer_solve(spec)
        issues = validate_layer_report(report, manifest["thresholds"])
        accepted_reports.append(
            {
                "caseId": spec.case_id,
                "status": "pass" if not issues else "fail",
                "issues": issues,
                "report": report,
                "trajectorySummary": summarize_trajectory(report),
            }
        )
    rejection_reports = [_run_rejection(case["caseId"]) for case in manifest["rejectionCases"]]
    executed_ids = [item["caseId"] for item in accepted_reports]
    declared_ids = [item["caseId"] for item in manifest["acceptedCases"]]
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "capabilityVersion": manifest["capabilityVersion"],
        "capabilityManifestHash": manifest["integrity"]["manifestHash"],
        "inventoryExact": executed_ids == declared_ids,
        "acceptedCases": accepted_reports,
        "rejectionCases": rejection_reports,
        "summary": {
            "acceptedPassCount": sum(item["status"] == "pass" for item in accepted_reports),
            "acceptedCaseCount": len(accepted_reports),
            "rejectionPassCount": sum(item["status"] == "pass" for item in rejection_reports),
            "rejectionCaseCount": len(rejection_reports),
            "allSimultaneousSolvesExecuted": all(
                item["report"]["solverExecuted"] for item in accepted_reports
            ),
            "allDifferentMaterialsExecuted": all(
                item["report"]["differentMaterialsExecuted"] for item in accepted_reports
            ),
            "globalPhase13Accepted": False,
        },
        "integrity": {"suiteHash": ""},
    }
    result["integrity"]["suiteHash"] = canonical_hash({**result, "integrity": {"suiteHash": ""}})
    return result


def validate_layer_report(report: dict[str, Any], thresholds: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if report.get("solverExecuted") is not True:
        return ["simultaneous_solver_not_executed"]
    metrics = report.get("finalMetrics", {})
    if int(metrics.get("residualContactCount", 1)) > int(thresholds["maximumResidualContactCount"]):
        issues.append("residual_contacts")
    if float(metrics.get("maximumResidualDepthMeters", 1.0)) > float(
        thresholds["maximumResidualDepthMeters"]
    ):
        issues.append("residual_depth")
    for name, issue in (
        ("minimumBodyClearanceMeters", "body_clearance"),
        ("minimumInterLayerSeparationMeters", "inter_layer_separation"),
        ("minimumOpeningRetention", "opening_retention"),
    ):
        if float(metrics.get(name, -1.0)) < float(thresholds[name]):
            issues.append(issue)
    for name, issue in (
        ("maximumRadialStrain", "strain"),
        ("maximumSeamCrackMeters", "seam_crack"),
        ("layerOrderViolationCount", "layer_order"),
        ("bridgeConstraintCount", "bridge_constraint"),
    ):
        threshold_name = {
            "layerOrderViolationCount": "maximumLayerOrderViolations",
            "bridgeConstraintCount": "maximumBridgeConstraints",
        }.get(name, name)
        if float(metrics.get(name, 1.0)) > float(thresholds[threshold_name]):
            issues.append(issue)
    if report.get("response", {}).get("bothSidesMoved") is not True:
        issues.append("symmetric_response_missing")
    if report.get("broadPhase", {}).get("adjacentLayerOnly") is not True:
        issues.append("unrelated_layer_bridge")
    return sorted(issues)


def _accepted_specs() -> list[OutfitSpec]:
    return [
        _case("top_over_lower_garment", "waist", 0.285, 0.48, 2),
        _case("jacket_over_shirt", "torso", 0.31, 0.75, 2),
        _case("dress_with_outer_layer", "torso_hip", 0.325, 0.62, 2),
        _case("layered_asymmetric_fixture", "torso", 0.30, 0.58, 2),
        _case("lower_body_stress", "lower_body", 0.255, 0.92, 2),
        _case("sleeve_underlying_interaction", "upper_arm", 0.105, 0.88, 2),
        _case("extreme_supported_body", "torso", 0.39, 1.0, 2),
        _case("three_layer_material_mix", "torso", 0.315, 0.82, 3),
        _case("identical_coincident_layers", "torso", 0.30, 0.35, 2, coincident=True),
    ]


def _case(
    case_id: str,
    zone: str,
    body_radius: float,
    motion: float,
    layer_count: int,
    *,
    coincident: bool = False,
) -> OutfitSpec:
    materials = (
        ("material.cotton_jersey_d0_v1", 0.0016, 0.16, 0.42),
        ("material.lightweight_woven_d0_v1", 0.0009, 0.135, 0.68),
        ("material.heavy_jersey_d0_v1", 0.0022, 0.24, 0.55),
    )
    layers: list[LayerSpec] = []
    for index in range(layer_count):
        material_id, thickness, density, stiffness = materials[index]
        offset = 0.006 if coincident else 0.006 + index * 0.0012
        layers.append(
            LayerSpec(
                layer_id=f"layer.{case_id}.{index}",
                collision_order=10 + index * 10,
                parent_layer_id=None if index == 0 else f"layer.{case_id}.{index - 1}",
                material_id=material_id,
                thickness_meters=thickness,
                areal_density_kg_m2=density,
                radial_stiffness=stiffness,
                initial_center_offset_meters=offset,
            )
        )
    return OutfitSpec(
        case_id=case_id,
        zone=zone,
        body_radius_meters=body_radius,
        body_clearance_meters=0.0032,
        inter_layer_clearance_meters=0.002,
        motion_amplitude=motion,
        opening_compatible=True,
        layers=tuple(layers),
    )


def _spec_record(spec: OutfitSpec) -> dict[str, Any]:
    return {
        "caseId": spec.case_id,
        "zone": spec.zone,
        "layerIds": [layer.layer_id for layer in spec.layers],
        "collisionOrders": [layer.collision_order for layer in spec.layers],
        "materialIds": [layer.material_id for layer in spec.layers],
        "motionAmplitude": spec.motion_amplitude,
    }


def _run_rejection(case_id: str) -> dict[str, Any]:
    spec = _case(case_id, "adversarial", 0.3, 0.4, 2)
    expected = {
        "cyclic_layer_order": "cyclic_layer_order",
        "missing_layer_id": "missing_layer_id",
        "reversed_layer_order": "layer_order_reversed_or_ambiguous",
        "incompatible_openings": "incompatible_layer_openings",
    }[case_id]
    if case_id == "cyclic_layer_order":
        first, second = spec.layers
        spec = replace(
            spec,
            layers=(
                replace(first, parent_layer_id=second.layer_id),
                replace(second, parent_layer_id=first.layer_id),
            ),
        )
    elif case_id == "missing_layer_id":
        spec = replace(spec, layers=(replace(spec.layers[0], layer_id=""), spec.layers[1]))
    elif case_id == "reversed_layer_order":
        spec = replace(spec, layers=(spec.layers[1], spec.layers[0]))
    else:
        spec = replace(spec, opening_compatible=False)
    observed: str | None = None
    try:
        run_simultaneous_layer_solve(spec)
    except LayerCollisionError as error:
        observed = error.code
    return {
        "caseId": case_id,
        "expectedError": expected,
        "observedError": observed,
        "status": "pass" if observed == expected else "fail",
        "solverExecuted": False,
        "issues": [observed] if observed else ["adversarial_case_not_rejected"],
    }
