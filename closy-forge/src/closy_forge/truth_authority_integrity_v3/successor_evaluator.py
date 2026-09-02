from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes, sha256_file

from .common import load_mapping, mapping

ROUTES = (
    "metadata_category_control_v3",
    "no_pixel_template_prior_v3",
    "pixel_mask_landmark_optimizer_v3",
    "pixel_learned_structured_tshirt_v3",
)
COMPILE_ROUTES = ROUTES[1:]
PRIMARY_ROUTE = ROUTES[3]
PROTOCOL_PATH = Path("fixtures/d0_disjoint_tshirt_confirmation_v3/protocol_lock.json")
PBR_FIELDS = ("baseColor", "roughness", "metalness", "ao")


def build_successor_protocol(forge_root: Path) -> dict[str, Any]:
    frozen = load_mapping(forge_root / PROTOCOL_PATH)
    return {
        "schemaVersion": 1,
        "protocolVersion": "closy.unit_s_integrity_successor.v1",
        "thresholdSourcePath": PROTOCOL_PATH.as_posix(),
        "thresholdSourceDigest": sha256_file(forge_root / PROTOCOL_PATH),
        "thresholds": mapping(frozen.get("thresholds")),
        "routes": list(ROUTES),
        "compileRoutes": list(COMPILE_ROUTES),
        "primaryRoute": PRIMARY_ROUTE,
        "appearanceOrdinals": list(range(8)),
        "denominators": {
            "attemptsScheduled": 64,
            "compileRowsScheduled": 48,
            "appearanceRowsScheduled": 24,
            "primaryCompileRepeatsScheduled": 16,
            "primaryAppearanceRepeatsScheduled": 8,
        },
        "lineage": (
            "attempt_to_returned_or_abstained_to_candidate_to_compiler_to_appearance_to_final"
        ),
        "candidateOracleTopologyMetric": "candidateOracleTopologyDeltaMeters",
        "physicalSeamCrackMetricReserved": "absolutePhysicalSeamCrackMeters",
    }


def evaluate_successor(
    protocol: Mapping[str, Any], attempt_rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    issues = validate_successor_rows(protocol, attempt_rows)
    if issues:
        raise ValueError(";".join(issues))
    rows = [dict(row) for row in attempt_rows]
    compiles = [row for row in rows if mapping(row.get("compiler")).get("entered") is True]
    appearances = [row for row in rows if row.get("appearance") is not None]
    returned = [row for row in rows if row.get("attemptState") == "returned"]
    compile_valid = [
        row for row in compiles if mapping(row.get("compiler")).get("status") == "valid"
    ]
    appearance_pass = [
        row for row in appearances if mapping(row.get("appearance")).get("status") == "pass"
    ]
    return {
        "schemaVersion": 1,
        "resultVersion": "closy.unit_s_integrity_successor.result.v1",
        "protocolVersion": protocol.get("protocolVersion"),
        "thresholdSourceDigest": protocol.get("thresholdSourceDigest"),
        "attemptsScheduledCount": len(rows),
        "attemptsExecutedCount": len(rows),
        "returnedAttemptCount": len(returned),
        "explicitAbstentionCount": len(rows) - len(returned),
        "predictionArtifactProducedCount": sum(
            isinstance(row.get("predictionArtifactSha256"), str) for row in rows
        ),
        "candidateCompleteCount": sum(row.get("candidate") is not None for row in rows),
        "compilerEnteredCount": len(compiles),
        "compileValidCount": len(compile_valid),
        "appearanceActuallyEvaluatedCount": len(appearances),
        "appearanceGatePassCount": len(appearance_pass),
        "lineageCompleteCount": len(rows),
        "finalGatePassCount": sum(row.get("finalGatePass") is True for row in rows),
        "allIntegrityPredicatesPass": True,
    }


def validate_successor_rows(
    protocol: Mapping[str, Any], attempt_rows: Sequence[Mapping[str, Any]]
) -> list[str]:
    issues: list[str] = []
    denominators = mapping(protocol.get("denominators"))
    expected = [(ordinal, route) for ordinal in range(16) for route in ROUTES]
    keys = [(int(row.get("ordinal", -1)), str(row.get("routeId", ""))) for row in attempt_rows]
    if denominators.get("attemptsScheduled") != 64:
        issues.append("successor_denominator_integrity_invalid")
    if keys != expected or Counter(keys) != Counter(expected):
        issues.append("successor_attempt_row_inventory_invalid")
    for row in attempt_rows:
        ordinal = int(row.get("ordinal", -1))
        route = str(row.get("routeId", ""))
        row_id = f"{ordinal:02d}:{route}"
        if row.get("rowId") != row_id:
            issues.append("successor_row_linkage_invalid")
        returned = row.get("attemptState") == "returned"
        if row.get("attemptState") not in {"returned", "abstained"}:
            issues.append("successor_attempt_state_invalid")
        artifact = row.get("predictionArtifactSha256")
        if returned != (isinstance(artifact, str) and len(artifact) == 64):
            issues.append("successor_prediction_artifact_lineage_invalid")
        expected_class = (
            "source_conditioned_pixels" if row.get("pixelsConsumed") is True else "metadata_only"
        )
        if row.get("trustedEvidenceClass") != expected_class:
            issues.append("successor_trusted_evidence_class_invalid")
        if row.get("declaredEvidenceClass") != expected_class:
            issues.append("successor_self_declared_evidence_class_invalid")
        issues.extend(_validate_contribution(row))
        issues.extend(_validate_crop(row))
        candidate = mapping(row.get("candidate"))
        compiler = mapping(row.get("compiler"))
        compile_expected = route in COMPILE_ROUTES and returned
        if compile_expected != bool(candidate):
            issues.append("successor_candidate_lineage_invalid")
        if compile_expected != (compiler.get("entered") is True):
            issues.append("successor_compiler_lineage_invalid")
        if candidate:
            if candidate.get("rowId") != row_id:
                issues.append("successor_candidate_row_linkage_invalid")
            if any(field not in mapping(candidate.get("pbr")) for field in PBR_FIELDS):
                issues.append("successor_missing_pbr_rejected")
            if compiler.get("candidateSha256") != candidate.get("candidateSha256"):
                issues.append("successor_compiler_candidate_linkage_invalid")
            issues.extend(_validate_metrics(compiler))
        appearance = mapping(row.get("appearance"))
        appearance_expected = compile_expected and ordinal < 8
        if appearance_expected != bool(appearance):
            issues.append("successor_appearance_lineage_invalid")
        if appearance and appearance.get("candidateSha256") != candidate.get("candidateSha256"):
            issues.append("successor_appearance_candidate_linkage_invalid")
        final_expected = bool(
            compiler.get("status") == "valid"
            and (not appearance_expected or appearance.get("status") == "pass")
        )
        if row.get("finalGatePass") is not final_expected:
            issues.append("successor_final_gate_lineage_invalid")
        if "semanticSeamCrackMeters" in row or "semanticSeamCrackMeters" in compiler:
            issues.append("candidate_oracle_delta_mislabeled_as_physical_crack")
    if not mapping(protocol.get("thresholds")):
        issues.append("successor_frozen_thresholds_missing")
    if protocol.get("candidateOracleTopologyMetric") != "candidateOracleTopologyDeltaMeters":
        issues.append("successor_topology_delta_metric_name_invalid")
    return sorted(set(issues))


def generic_successor_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ordinal in range(16):
        for route in ROUTES:
            row_id = f"{ordinal:02d}:{route}"
            pixel = route in ROUTES[2:]
            artifact = _hash({"rowId": row_id, "kind": "prediction"})
            observed = ["front_png", "rear_png"] if pixel else []
            generated = ["category"] if not pixel else ["pbr_roughness", "pbr_metalness"]
            candidate: dict[str, Any] | None = None
            compiler: dict[str, Any] = {"entered": False, "status": "not_entered"}
            appearance: dict[str, Any] | None = None
            if route in COMPILE_ROUTES:
                candidate_hash = _hash({"rowId": row_id, "kind": "candidate"})
                candidate = {
                    "rowId": row_id,
                    "candidateSha256": candidate_hash,
                    "pbr": {
                        "baseColor": "source" if pixel else "preset",
                        "roughness": 0.8,
                        "metalness": 0.0,
                        "ao": 1.0,
                    },
                }
                metrics = {"bodyLength": 0.08, "chestWidth": 0.06, "sleeveLength": 0.07}
                compiler = {
                    "entered": True,
                    "status": "valid",
                    "candidateSha256": candidate_hash,
                    "metricsByObservable": metrics,
                    "worstNormalizedObservableError": max(metrics.values()),
                    "candidateOracleTopologyDeltaMeters": 0.001,
                }
                if ordinal < 8:
                    appearance = {
                        "candidateSha256": candidate_hash,
                        "status": "pass",
                        "sourceBitmapSha256": _hash({"rowId": row_id, "kind": "source"}),
                        "uvTextureSha256": _hash({"rowId": row_id, "kind": "uv"}),
                    }
            rows.append(
                {
                    "rowId": row_id,
                    "ordinal": ordinal,
                    "routeId": route,
                    "attemptState": "returned",
                    "predictionArtifactSha256": artifact,
                    "pixelsConsumed": pixel,
                    "trustedEvidenceClass": (
                        "source_conditioned_pixels" if pixel else "metadata_only"
                    ),
                    "declaredEvidenceClass": (
                        "source_conditioned_pixels" if pixel else "metadata_only"
                    ),
                    "sourceContribution": {
                        "observedFields": observed,
                        "generatedFields": generated,
                        "observedFieldCount": len(observed),
                        "generatedFieldCount": len(generated),
                    },
                    "crop": {
                        "sourceRole": "front_png" if pixel else "none",
                        "cropFraction": 0.1 if pixel else 0.0,
                        "beforeSha256": _hash({"rowId": row_id, "crop": "before"}),
                        "afterSha256": (
                            _hash({"rowId": row_id, "crop": "after"})
                            if pixel
                            else _hash({"rowId": row_id, "crop": "before"})
                        ),
                    },
                    "candidate": candidate,
                    "compiler": compiler,
                    "appearance": appearance,
                    "finalGatePass": route in COMPILE_ROUTES,
                }
            )
    return rows


def executed_mutation_report(forge_root: Path) -> dict[str, bool]:
    protocol = build_successor_protocol(forge_root)
    baseline = generic_successor_rows()
    if validate_successor_rows(protocol, baseline):
        raise ValueError("successor_mutation_baseline_invalid")
    mutations: dict[str, tuple[dict[str, Any], list[dict[str, Any]]]] = {}
    hardcoded = deepcopy(baseline)
    hardcoded[10]["sourceContribution"]["observedFieldCount"] = 999
    mutations["hardcoded_contribution"] = (protocol, hardcoded)
    target_crop = deepcopy(baseline)
    target_crop[10]["crop"]["sourceRole"] = "private_target"
    mutations["target_derived_crop"] = (protocol, target_crop)
    declared = deepcopy(baseline)
    declared[0]["declaredEvidenceClass"] = "source_conditioned_pixels"
    mutations["self_declared_evidence_class"] = (protocol, declared)
    missing_pbr = deepcopy(baseline)
    del missing_pbr[1]["candidate"]["pbr"]["roughness"]
    mutations["missing_pbr"] = (protocol, missing_pbr)
    worst = deepcopy(baseline)
    worst[1]["compiler"]["worstNormalizedObservableError"] = 0.0
    mutations["worst_error"] = (protocol, worst)
    linkage = deepcopy(baseline)
    linkage[1]["compiler"]["candidateSha256"] = "0" * 64
    mutations["row_linkage"] = (protocol, linkage)
    denominator = deepcopy(protocol)
    denominator["denominators"]["attemptsScheduled"] = 63
    mutations["denominator_integrity"] = (denominator, deepcopy(baseline))
    report: dict[str, bool] = {}
    for name, (candidate_protocol, rows) in mutations.items():
        report[name] = bool(validate_successor_rows(candidate_protocol, rows))
    return report


def _validate_contribution(row: Mapping[str, Any]) -> list[str]:
    contribution = mapping(row.get("sourceContribution"))
    observed = contribution.get("observedFields")
    generated = contribution.get("generatedFields")
    if not isinstance(observed, list) or not isinstance(generated, list):
        return ["successor_source_contribution_lineage_missing"]
    if contribution.get("observedFieldCount") != len(observed):
        return ["successor_hardcoded_contribution_rejected"]
    if contribution.get("generatedFieldCount") != len(generated):
        return ["successor_hardcoded_contribution_rejected"]
    if set(observed) & set(generated):
        return ["successor_source_contribution_overlap"]
    return []


def _validate_crop(row: Mapping[str, Any]) -> list[str]:
    crop = mapping(row.get("crop"))
    source_role = str(crop.get("sourceRole", ""))
    if source_role not in {"none", "front_png", "rear_png"}:
        return ["successor_target_derived_crop_rejected"]
    fraction = float(crop.get("cropFraction", math.nan))
    if not math.isfinite(fraction) or not 0.0 <= fraction < 1.0:
        return ["successor_crop_fraction_invalid"]
    before = crop.get("beforeSha256")
    after = crop.get("afterSha256")
    if fraction > 0.0 and before == after:
        return ["successor_crop_claim_did_not_change_bytes"]
    if fraction == 0.0 and before != after:
        return ["successor_zero_crop_changed_bytes"]
    return []


def _validate_metrics(compiler: Mapping[str, Any]) -> list[str]:
    metrics = mapping(compiler.get("metricsByObservable"))
    values = [float(value) for value in metrics.values()]
    if not values or not all(math.isfinite(value) for value in values):
        return ["successor_metric_inventory_invalid"]
    worst = float(compiler.get("worstNormalizedObservableError", math.nan))
    if not math.isfinite(worst) or worst != max(values):
        return ["successor_worst_error_not_derived"]
    delta = float(compiler.get("candidateOracleTopologyDeltaMeters", math.nan))
    if not math.isfinite(delta) or delta < 0.0:
        return ["successor_candidate_oracle_topology_delta_invalid"]
    return []


def _hash(value: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))
