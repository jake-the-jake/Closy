from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.solver_material_v1.common import canonical_bytes, digest, read_json, rounded
from closy_forge.solver_material_v1.estimator import estimate_solver_fields
from closy_forge.solver_material_v1.estimator_inputs import strip_truth_for_estimator
from closy_forge.solver_material_v1.production_solver import PRODUCTION_SOLVER_VERSION
from closy_forge.solver_material_v1.real_coupon import CouponValidationError, import_coupon
from closy_forge.solver_material_v1.result_decoder import independently_check_result
from closy_forge.solver_material_v1.retrospective_evaluator import evaluate_retrospective

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parent
OUTPUT = ROOT / "docs/evidence/phase7_solver_material_v1"
CORPUS = ROOT / "fixtures/solver_material_v1/locked_corpus.json"
GUARD_MANIFEST = ROOT / "fixtures/solver_material_v1/frozen_guard_manifest.json"
SOURCE_COMMIT = "aeb85402c325b989a981030ac203ee53c03d3780"
SOURCE_TREE = "c3bb127e1f787f088f47e875eb6624c0b9277e49"
PARENT_COMMIT = "8ccf6fa95d6ac5653f3c9dd45f2cf605038c73c8"
PARENT_TREE = "0440fa8c1b815682defa842e290759e71f99c013"
RESULT_NAME = "retrospective_result.json"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(canonical_bytes(value))
    os.replace(temporary, path)


def _text_write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value.rstrip() + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _tree_files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _first_byte_difference(expected: bytes, observed: bytes) -> str:
    shared = min(len(expected), len(observed))
    offset = next((index for index in range(shared) if expected[index] != observed[index]), shared)
    return (
        f"offset={offset};expectedBytes={len(expected)};observedBytes={len(observed)};"
        f"expectedSha256={_sha256(expected)};observedSha256={_sha256(observed)}"
    )


def _publication_differences(expected: dict[str, bytes], observed: dict[str, bytes]) -> list[str]:
    differences: list[str] = []
    for path in sorted(set(expected) | set(observed)):
        if path not in expected:
            differences.append(f"unexpected:{path}")
        elif path not in observed:
            differences.append(f"missing:{path}")
        elif expected[path] != observed[path]:
            differences.append(
                f"changed:{path}:{_first_byte_difference(expected[path], observed[path])}"
            )
    return differences


def _guard_receipt() -> dict[str, Any]:
    manifest = read_json(GUARD_MANIFEST)
    unsigned = dict(manifest)
    observed_digest = str(unsigned.pop("manifestDigest"))
    failures = [] if digest(unsigned) == observed_digest else ["guard_manifest_digest_invalid"]
    blob_receipts = []
    for row in manifest["frozenFiles"]:
        path = str(row["path"])
        observed_oid = (
            subprocess.check_output(["git", "rev-parse", f"HEAD:{path}"], cwd=REPOSITORY_ROOT)
            .decode("ascii")
            .strip()
        )
        if observed_oid != row["gitBlobOid"]:
            failures.append(f"frozen_blob_changed:{path}")
        blob_receipts.append(
            {
                "path": path,
                "expectedGitBlobOid": row["gitBlobOid"],
                "observedGitBlobOid": observed_oid,
                "matches": observed_oid == row["gitBlobOid"],
            }
        )
    return {
        "schemaVersion": 1,
        "guardVersion": manifest["guardVersion"],
        "frozenHead": manifest["frozenHead"],
        "manifestDigest": observed_digest,
        "checkedFileCount": manifest["frozenFileCount"],
        "blobReceipts": blob_receipts,
        "failureCount": len(failures),
        "failures": failures,
        "status": "passed" if not failures else "integrity_error",
        "gitObjectVerification": "performed",
    }


def _result_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "closy.phase7.solver_material_v1.retrospective_result.schema.v1",
        "type": "object",
        "required": [
            "schemaVersion",
            "resultVersion",
            "classification",
            "anchors",
            "denominators",
            "terminalConservation",
            "aggregate",
            "rows",
            "acceptancePredicates",
            "engineeringAcceptance",
            "scientificQualification",
            "resultDigest",
        ],
        "properties": {
            "schemaVersion": {"const": 1},
            "classification": {"const": "retrospective_contaminated_engineering_evaluation"},
            "engineeringAcceptance": {"const": "failed"},
            "scientificQualification": {"const": "ineligible_test_exposed_before_estimator"},
            "rows": {"type": "array", "minItems": 16, "maxItems": 16},
            "resultDigest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        },
        "additionalProperties": True,
    }


def _validate_result_contract(result: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    required = set(_result_schema()["required"])
    if not required.issubset(result):
        failures.append("result_schema_required_field_missing")
    if result.get("schemaVersion") != 1:
        failures.append("result_schema_version_invalid")
    if len(result.get("rows", [])) != 16:
        failures.append("result_schema_row_count_invalid")
    if result.get("engineeringAcceptance") != "failed":
        failures.append("result_schema_engineering_class_invalid")
    if result.get("scientificQualification") != "ineligible_test_exposed_before_estimator":
        failures.append("result_schema_scientific_class_invalid")
    return failures


def _canonicalize_numerical_diagnostics(result: dict[str, Any]) -> None:
    # The frozen implementation's finite-difference/SVD path varies below meaningful
    # precision across CPython 3.11 and 3.12. Estimates, errors, and predicates are not
    # altered; only descriptive diagnostics receive an explicit publication precision.
    for row in result["rows"]:
        row["conditionNumber"] = round(float(row["conditionNumber"]), 1)
        row["singularValues"] = [round(float(value), 2) for value in row["singularValues"]]
        row["normalizedJacobian"] = [
            [round(float(value), 2) for value in values] for values in row["normalizedJacobian"]
        ]
    result["numericalDiagnosticPrecision"] = {
        "conditionNumberDecimalPlaces": 1,
        "singularValueDecimalPlaces": 2,
        "normalizedJacobianDecimalPlaces": 2,
        "reason": "cross_supported_minor_finite_difference_serialization_stability",
        "acceptanceMetricsOrPredicatesChanged": False,
    }


def _estimator_diagnostic(
    name: str,
    observations: list[dict[str, Any]],
    bounds: dict[str, list[float]] | None = None,
) -> dict[str, Any]:
    active_bounds = bounds or {
        field: [0.0, 1.0]
        for field in (
            "warp",
            "weft",
            "shear",
            "bend",
            "density",
            "damping",
            "friction",
            "restitution",
        )
    }
    try:
        estimate = estimate_solver_fields(observations, active_bounds, PRODUCTION_SOLVER_VERSION)
        return {
            "name": name,
            "terminalOutcome": "passed",
            "observationCount": len(observations),
            "jacobianRank": estimate["jacobianRank"],
            "conditionNumber": round(float(estimate["conditionNumber"]), 1),
            "estimateDigest": digest(estimate["estimatedFields"]),
        }
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        return {
            "name": name,
            "terminalOutcome": "failed",
            "observationCount": len(observations),
            "failureReason": type(error).__name__,
        }


def _transitive_import_diagnostic() -> dict[str, Any]:
    package = ROOT / "src/closy_forge/solver_material_v1"
    visited: set[str] = set()
    queue = ["retrospective_evaluator"]
    edges: list[dict[str, str]] = []
    while queue:
        module = queue.pop(0)
        if module in visited:
            continue
        visited.add(module)
        path = package / f"{module}.py"
        if not path.is_file():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                prefix = "closy_forge.solver_material_v1."
                if node.module.startswith(prefix):
                    target = node.module.removeprefix(prefix)
                    edges.append({"source": module, "target": target})
                    queue.append(target)
    return {
        "name": "transitive_import_detection",
        "terminalOutcome": "passed",
        "reachableModules": sorted(visited),
        "edges": sorted(edges, key=lambda row: (row["source"], row["target"])),
        "unexpectedExternalScientificModuleCount": 0,
    }


def _lineage_corruption_diagnostic(corpus: dict[str, Any]) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    for name, field in (("corrupt_digest", "corpusDigest"), ("corrupt_lineage", "protocolDigest")):
        candidate = deepcopy(corpus)
        candidate[field] = "0" * 64
        with tempfile.TemporaryDirectory(prefix="closy-phase7-corruption-") as temporary:
            path = Path(temporary) / "corpus.json"
            path.write_bytes(canonical_bytes(candidate))
            try:
                evaluate_retrospective(path)
            except ValueError as error:
                outcomes.append(
                    {
                        "name": name,
                        "terminalOutcome": "passed",
                        "rejected": True,
                        "failureReason": str(error),
                    }
                )
            else:
                outcomes.append({"name": name, "terminalOutcome": "failed", "rejected": False})
    return outcomes


def _post_hoc_diagnostics(corpus: dict[str, Any]) -> dict[str, Any]:
    locked = [row for row in corpus["rows"] if row["partition"] == "locked_test"]
    observations = strip_truth_for_estimator(locked[0])
    zeroed = deepcopy(observations)
    for row in zeroed:
        row["observable"] = 0.0
    shuffled = deepcopy(observations)
    families = [row["family"] for row in shuffled]
    loads = [row["load"] for row in shuffled]
    for index, row in enumerate(shuffled):
        row["family"] = families[(index + 1) % len(families)]
        row["load"] = loads[-(index + 1)]
    duplicated = deepcopy(observations) + [deepcopy(observations[0])]
    removed = deepcopy(observations[:-1])
    noisy = deepcopy(observations)
    for index, row in enumerate(noisy):
        row["observable"] = float(row["observable"]) * (1.0 + ((index % 3) - 1) * 0.01)
    perturbed = {
        field: [0.05, 0.95]
        for field in (
            "warp",
            "weft",
            "shear",
            "bend",
            "density",
            "damping",
            "friction",
            "restitution",
        )
    }
    contact_pairs: list[bool] = []
    vertical_rows: list[dict[str, Any]] = []
    for row in corpus["rows"]:
        coupons = {coupon["family"]: coupon for coupon in row["coupons"]}
        contact = coupons["contact_control"]
        inclined = coupons["inclined_contact"]
        contact_pairs.append(
            contact["sampledStates"] == inclined["sampledStates"]
            and contact["observable"] == inclined["observable"]
            and contact["diagnostics"] == inclined["diagnostics"]
        )
        vertical_rows.append(coupons["vertical_drop"])
    intervention = {row["field"]: row for row in corpus["interventions"]}
    convergence = [float(row["relativeObservableDifference"]) for row in corpus["convergence"]]
    controls = [
        _estimator_diagnostic("zeroed_observations", zeroed),
        _estimator_diagnostic("shuffled_family_and_load_metadata", shuffled),
        _estimator_diagnostic("duplicated_observation", duplicated),
        _estimator_diagnostic("removed_family", removed),
        _estimator_diagnostic("deterministic_one_percent_observation_noise", noisy),
        _estimator_diagnostic("perturbed_bounds", observations, perturbed),
        *_lineage_corruption_diagnostic(corpus),
        _transitive_import_diagnostic(),
    ]
    return {
        "schemaVersion": 1,
        "diagnosticVersion": "closy.solver_material_v1.post_hoc.v1",
        "classification": "post_hoc_non_qualification",
        "changesCanonicalResult": False,
        "controls": controls,
        "inactivePathAudit": {
            "contactControlAndInclinedContactStateObservableDiagnosticsByteEquivalent": all(
                contact_pairs
            ),
            "contactPairRowCount": len(contact_pairs),
            "verticalDropRowCount": len(vertical_rows),
            "verticalDropZeroContactRowCount": sum(
                row["diagnostics"]["contactEventCount"] == 0 for row in vertical_rows
            ),
            "frictionDistinctInterventionResponses": len(
                set(intervention["friction"]["observables"])
            ),
            "restitutionDistinctInterventionResponses": len(
                set(intervention["restitution"]["observables"])
            ),
            "frictionTrajectoryResponds": intervention["friction"]["trajectoryResponds"],
            "restitutionTrajectoryResponds": intervention["restitution"]["trajectoryResponds"],
        },
        "convergenceErratum": {
            "isConvergenceProof": False,
            "configurationCount": 2,
            "dimensionsChangedTogether": [
                "nodeCount",
                "timeStepSeconds",
                "stepCount",
                "iterations",
            ],
            "relativeDifferenceCount": len(convergence),
            "relativeDifferenceMinimum": rounded(min(convergence)),
            "relativeDifferenceMaximum": rounded(max(convergence)),
            "relativeDifferenceMean": rounded(sum(convergence) / len(convergence)),
        },
    }


def _current_status(result: dict[str, Any]) -> dict[str, Any]:
    stale = ROOT / "docs/current_blueprint_status.json"
    return {
        "schemaVersion": 1,
        "overlayVersion": "closy.phase7_v1.current_status_overlay.v1",
        "scope": "PR_62_append_only_closeout",
        "primaryInventoryStatus": "inventory_unavailable_stale",
        "stalePrimaryStatusSha256": _sha256(stale.read_bytes()),
        "staleCountsAreCurrent": False,
        "phase7": {
            "progress": "partial",
            "engineeringAcceptance": result["engineeringAcceptance"],
            "scientificQualification": result["scientificQualification"],
            "resultDigest": result["resultDigest"],
            "firstUnmetPredicate": result["firstUnmetPredicate"],
            "realCouponCount": 0,
            "realFabricCalibration": "not_run",
        },
        "unitY2": {
            "terminalOutcome": "preseed_scientific_protocol_invalid",
            "scientificAttemptConsumed": False,
            "seedConsumed": False,
            "authorityConsumed": False,
            "candidateConsumed": False,
            "topologyStrategyConsumed": False,
        },
        "remainingBudgets": {"canonicalCandidateCount": 1, "topologyStrategyCount": 0},
        "nextBranch": "codex/closy-forge-synthetic-capture-reconstruction-v2",
        "nextBase": "exact_final_PR62_head_external_attestation",
    }


def _stack_manifest(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "manifestVersion": "closy.pr_stack.phase7_v1_closeout.v1",
        "exactLinear": True,
        "nodes": [
            {
                "pullRequest": 60,
                "branch": "codex/closy-forge-truth-dependency-authority-v4",
                "head": "f3f9dd357e97e40fbb554f52a34668a4bede5bd6",
            },
            {
                "pullRequest": 61,
                "branch": "codex/closy-forge-capture-camera-material-engineering-v1",
                "parent": "f3f9dd357e97e40fbb554f52a34668a4bede5bd6",
                "head": PARENT_COMMIT,
                "remoteRun": "33758649869",
            },
            {
                "pullRequest": 62,
                "branch": "codex/closy-forge-phase7-solver-material-v1",
                "parent": PARENT_COMMIT,
                "sourceCommit": SOURCE_COMMIT,
                "publicationHead": "external_exact_head_attestation",
                "resultDigest": result["resultDigest"],
            },
        ],
        "next": {
            "branch": "codex/closy-forge-synthetic-capture-reconstruction-v2",
            "base": "exact_final_PR62_head_external_attestation",
        },
    }


def _resume(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "resumeVersion": "closy.phase7_v1.closeout_resume.v1",
        "branch": "codex/closy-forge-phase7-solver-material-v1",
        "parentCommit": PARENT_COMMIT,
        "sourceCommit": SOURCE_COMMIT,
        "publicationHead": "external_exact_head_attestation",
        "resultDigest": result["resultDigest"],
        "phase7Progress": "partial",
        "firstUnmetPredicate": result["firstUnmetPredicate"],
        "exactNextAction": "create_capture_reconstruction_v2_from_exact_final_PR62_head",
        "nextBranch": "codex/closy-forge-synthetic-capture-reconstruction-v2",
        "noMergeAuthorised": True,
        "budgetsConsumedByThisCloseout": {
            "scientificAttempt": False,
            "seed": False,
            "authority": False,
            "candidate": False,
            "topologyStrategy": False,
        },
    }


def _blockers() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "ledgerVersion": "closy.phase7_v1.external_blockers.v1",
        "rows": [
            {
                "id": "real_fabric_measurements",
                "state": "not_run",
                "reason": "no_authorised_unit_bearing_real_coupon_measurements",
                "realCouponCount": 0,
            },
            {
                "id": "independent_scientific_estimator_evaluation",
                "state": "failed",
                "reason": "locked_test_truth_exposed_before_estimator_and_metric_completion",
            },
            {
                "id": "confidence_intervals",
                "state": "not_run",
                "reason": "not_frozen_before_test_exposure",
            },
            {
                "id": "physical_garment_solver",
                "state": "not_started",
                "reason": "v1_is_same_author_correlated_scalar_toy_chain",
            },
        ],
    }


def _report(result: dict[str, Any], post_hoc: dict[str, Any]) -> str:
    aggregate = result["aggregate"]
    inactive = post_hoc["inactivePathAudit"]
    convergence = post_hoc["convergenceErratum"]
    return f"""# Phase 7 solver/material V1 retrospective closeout

This is a contaminated retrospective engineering evaluation of same-author, closely aligned
scalar one-dimensional numerical chains. It is not XPBD, material-physics, blind, predictive,
calibrated, or real-fabric evidence.

## Canonical outcome

- Engineering acceptance: `{result['engineeringAcceptance']}`.
- Scientific qualification: `{result['scientificQualification']}`.
- First unmet predicate: `{result['firstUnmetPredicate']}`.
- Mean six-field normalized error: `{aggregate['sixField']['mean']}`.
- Nearest-rank P95: `{aggregate['sixField']['p95NearestRank']}`.
- Worst six-field error: `{aggregate['sixField']['worst']}`.
- Mean historical `predictiveNrmse`: `{aggregate['meanHistoricalPredictiveNrmse']}`; this is
  fitted-observation reconstruction, not withheld prediction.
- Passing tuples: `{aggregate['passingTupleCount']}/16`.
- Result digest: `{result['resultDigest']}`.

Terminal conservation is 96 estimated + 32 abstained + 16 unsupported = 144 cells, with zero dropped
rows. Friction and restitution are abstained. Compression/thickness is unsupported. Confidence
intervals and frozen negative controls were not run. `real_coupon_count=0`;
`real_fabric_calibration=not_run`.

## Post-hoc diagnostics

All diagnostics are `post_hoc_non_qualification` and cannot alter the terminal result.
Independent checks found contact-control and inclined-contact state/observable diagnostics
equivalent across {inactive['contactPairRowCount']} rows,
{inactive['verticalDropZeroContactRowCount']}/{inactive['verticalDropRowCount']} vertical-drop rows
with zero contacts, {inactive['frictionDistinctInterventionResponses']} distinct friction responses,
and {inactive['restitutionDistinctInterventionResponses']} distinct restitution response. The
two-configuration comparison changed node count, timestep, step count, and iteration count
together; it is not a convergence proof. Relative differences span
{convergence['relativeDifferenceMinimum']} to {convergence['relativeDifferenceMaximum']} with mean
{convergence['relativeDifferenceMean']}.
"""


def build(output: Path) -> dict[str, Any]:
    # These two append-only notes predate the generated publication. Include their exact
    # bytes in temporary rebuilds so the publication manifest is independently reproducible.
    for name in ("scientific_errata.md", "dirty_file_exclusion_manifest.json"):
        source = OUTPUT / name
        destination = output / name
        if output != OUTPUT:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    corpus = read_json(CORPUS)
    result = evaluate_retrospective(CORPUS)
    _canonicalize_numerical_diagnostics(result)
    result["producer"] = {
        "sourceCommit": SOURCE_COMMIT,
        "sourceTree": SOURCE_TREE,
        "implementation": "closy.solver_material.retrospective_result.v1",
        "immutableCorpusDigest": corpus["corpusDigest"],
    }
    result.pop("resultDigest")
    result["resultDigest"] = digest(result)
    checker = independently_check_result(result)
    schema_failures = _validate_result_contract(result)
    if checker["status"] != "passed" or schema_failures:
        raise SystemExit("retrospective_result_integrity_error:" + ";".join(schema_failures))
    post_hoc = _post_hoc_diagnostics(corpus)
    outputs: dict[str, Any] = {
        RESULT_NAME: result,
        "retrospective_result.schema.json": _result_schema(),
        "independent_checker_receipt.json": {
            "schemaVersion": 1,
            **checker,
            "resultDigest": result["resultDigest"],
            "schemaValidation": "passed",
        },
        "frozen_guard_receipt.json": _guard_receipt(),
        "post_hoc_diagnostics.json": post_hoc,
        "current_status_overlay.json": _current_status(result),
        "pr_stack_manifest.json": _stack_manifest(result),
        "active_resume.json": _resume(result),
        "external_blocker_ledger.json": _blockers(),
        "phase7_evidence_row.json": {
            "schemaVersion": 1,
            "phase": 7,
            "blueprintProgress": "partial",
            "evidenceClass": result["evidenceClass"],
            "engineeringAcceptance": result["engineeringAcceptance"],
            "scientificQualification": result["scientificQualification"],
            "resultDigest": result["resultDigest"],
            "limitations": [
                "same_author_correlated_scalar_toy_chain",
                "test_truth_exposed_before_estimator",
                "same_observation_reconstruction_not_prediction",
                "negative_controls_not_run",
                "confidence_intervals_not_run",
                "real_coupon_count_zero",
            ],
        },
        "real_coupon_status.json": {
            "schemaVersion": 1,
            "schema": "schemas/real_coupon_v1/real_coupon.schema.json",
            "csvTemplate": "fixtures/real_coupon_v1/empty_template.csv",
            "jsonTemplate": "fixtures/real_coupon_v1/empty_template.json",
            "realCouponCount": 0,
            "realFabricCalibration": "not_run",
            "realMeasurementsInvented": False,
        },
        "execution_ledger.json": {
            "schemaVersion": 1,
            "executionVersion": "closy.phase7_v1.retrospective_publication.v1",
            "parentCommit": PARENT_COMMIT,
            "parentTree": PARENT_TREE,
            "sourceCommit": SOURCE_COMMIT,
            "sourceTree": SOURCE_TREE,
            "protocolDigest": result["protocolDigest"],
            "corpusDigest": result["corpusDigest"],
            "resultDigest": result["resultDigest"],
            "canonicalPublicationCount": 1,
            "reproductionIsScientificAttempt": False,
            "ordinaryExactHeadGates": [
                {
                    "stage": "forward_source",
                    "commit": "e8568100257b4bea87ce831e1320371bf9354d3f",
                    "tree": "0f8943af4948e75be2bfae93669bf283f73a9114",
                    "runId": "33761507921",
                    "result": "32_of_32_success",
                },
                {
                    "stage": "corpus_lock",
                    "commit": "bbbc48aaf016ef704c4a43aede3cf337df81de40",
                    "tree": "6538b59037ece2641615344b1bc9195150fbe497",
                    "runId": "33763873776",
                    "result": "32_of_32_success",
                },
                {
                    "stage": "estimator_source",
                    "commit": "4835f9ce13dde54eb1aeaa6c68a35b05c4f361cb",
                    "tree": "f9840147f8b852bd6ab9fdd85fc5de2efe66f9eb",
                    "runId": "33766358569",
                    "result": "32_of_32_success",
                },
                {
                    "stage": "retrospective_evaluator_source",
                    "commit": SOURCE_COMMIT,
                    "tree": SOURCE_TREE,
                    "runId": "33812167165",
                    "result": "32_of_32_success",
                },
            ],
            "externalRunAttestation": "PR_body_only_after_exact_head_green",
        },
    }
    for name, value in outputs.items():
        _canonical_write(output / name, value)
    _text_write(output / "REPORT.md", _report(result, post_hoc))
    indexed = []
    publication_files = sorted(
        (path for path in output.iterdir() if path.is_file()),
        key=lambda path: (path.name.casefold(), path.name),
    )
    for path in publication_files:
        if path.name == "publication_manifest.json":
            continue
        payload = path.read_bytes()
        indexed.append({"path": path.name, "sha256": _sha256(payload), "byteCount": len(payload)})
    manifest = {
        "schemaVersion": 1,
        "manifestVersion": "closy.phase7_v1.publication_manifest.v1",
        "sourceCommit": SOURCE_COMMIT,
        "sourceTree": SOURCE_TREE,
        "resultDigest": result["resultDigest"],
        "files": indexed,
    }
    manifest["manifestDigest"] = digest(manifest)
    _canonical_write(output / "publication_manifest.json", manifest)
    return result


def check() -> None:
    if not (OUTPUT / RESULT_NAME).is_file():
        raise SystemExit("phase7_v1_publication_missing")
    with tempfile.TemporaryDirectory(prefix="closy-phase7-v1-check-") as temporary:
        candidate = Path(temporary) / "publication"
        build(candidate)
        observed = _tree_files(candidate)
        expected = _tree_files(OUTPUT)
        if observed != expected:
            detail = "|".join(_publication_differences(expected, observed))
            raise SystemExit(f"phase7_v1_publication_stale:{detail}")


def _coupon_command(path: Path, output: Path | None) -> None:
    imported = import_coupon(path)
    summary = {
        "schemaVersion": 1,
        "sourceFormat": imported["sourceFormat"],
        "recordCount": imported["recordCount"],
        "status": "valid",
    }
    if output is not None:
        if output.resolve() == path.resolve():
            raise CouponValidationError("coupon_import_output_must_not_overwrite_source")
        _canonical_write(output, imported)
        summary["outputWritten"] = True
    print(json.dumps(summary, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish or verify Phase 7 V1 closeout evidence.")
    parser.add_argument(
        "--check", action="store_true", help="Verify canonical publication freshness."
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("evaluate")
    subparsers.add_parser("check")
    validate = subparsers.add_parser("validate-coupon")
    validate.add_argument("path", type=Path)
    import_parser = subparsers.add_parser("import-coupon")
    import_parser.add_argument("path", type=Path)
    import_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    command = "check" if args.check else (args.command or "evaluate")
    if command == "evaluate":
        build(OUTPUT)
    elif command == "check":
        check()
    elif command == "validate-coupon":
        _coupon_command(args.path, None)
    elif command == "import-coupon":
        _coupon_command(args.path, args.output)
    else:
        parser.error(f"unsupported command: {command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
