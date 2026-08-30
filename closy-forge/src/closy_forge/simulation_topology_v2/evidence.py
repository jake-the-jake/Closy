from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file

from .phy1_experiment import (
    PHY1_STATE_IDS,
    PHY1_TOPOLOGY_V2_PROFILE_VERSION,
    Phy1TopologyV2Inputs,
)

PHY1_TOPOLOGY_V2_PROFILE_PATH = Path("docs/capability-profiles/phy1-single-layer-d0-v2.json")
PHY1_TOPOLOGY_V2_EVIDENCE_DIRECTORY = Path("docs/evidence/phy1_topology_v2")
PHY1_TOPOLOGY_V2_PUBLICATION_VERSION = "closy.phy1.topology_v2.publication.v1"
FINAL_D0_MATRIX_VERSION = "closy.final_d0_research_prototype_matrix.v1"
INTEGRATED_D_LEDGER_PATH = Path("docs/evidence/integrated_runtime_invalidation_ledger_d0_v1.json")

_EXECUTABLE_SOURCE_PATHS = (
    Path("src/closy_forge/simulation_topology_v2/triangulator.py"),
    Path("src/closy_forge/simulation_topology_v2/seam_junctions.py"),
    Path("src/closy_forge/simulation_topology_v2/binding.py"),
    Path("src/closy_forge/simulation_topology_v2/temporal_quality.py"),
    Path("src/closy_forge/simulation_topology_v2/phy1_experiment.py"),
    Path("src/closy_forge/simulation_topology_v2/evidence.py"),
    Path("scripts/generate_phy1_topology_v2_evidence.py"),
)


def attach_performance_measurement(
    report: dict[str, Any],
    *,
    measured_wall_seconds: float,
    peak_memory_bytes: int | None,
    environment: dict[str, Any],
) -> dict[str, Any]:
    if measured_wall_seconds <= 0.0:
        raise ValueError("phy1_v2_wall_seconds_must_be_positive")
    updated = deepcopy(report)
    ceiling = float(updated["performance"]["runtimeCeilingSeconds"])
    performance_passed = measured_wall_seconds <= ceiling
    updated["performance"] = {
        **updated["performance"],
        "measurementAuthority": "external_full_profile_wall_clock_observation",
        "scope": (
            "one cold in-process build, settle, ten motion states, binding reconstruction, "
            "and all recorded CPU oracles"
        ),
        "sampleCount": 1,
        "medianWallClockSeconds": measured_wall_seconds,
        "p95WallClockSeconds": measured_wall_seconds,
        "worstWallClockSeconds": measured_wall_seconds,
        "peakMemoryBytes": peak_memory_bytes,
        "peakMemoryMeasurement": (
            "not_measured" if peak_memory_bytes is None else "process_peak_working_set"
        ),
        "cacheState": "cold_python_process_warm_os_file_cache_unknown",
        "buildMode": "CPython_source_CPU",
        "timeoutSeconds": ceiling,
        "environment": environment,
        "status": "pass" if performance_passed else "failed",
        "exclusions": [
            "first superseded exact-GLB signed-distance trial exceeded 210 seconds and was stopped",
            "CI queue time",
            "package publication I/O",
        ],
    }
    updated["acceptance"]["checks"]["performance"] = performance_passed
    updated["acceptance"]["failedChecks"] = [
        name for name, passed in updated["acceptance"]["checks"].items() if not passed
    ]
    updated["acceptance"]["status"] = (
        "pass" if not updated["acceptance"]["failedChecks"] else "failed"
    )
    updated["integrity"]["evidenceHash"] = ""
    updated["integrity"]["evidenceHash"] = _document_hash(updated, "evidenceHash")
    return updated


def build_phy1_topology_v2_profile(
    root: Path,
    report: dict[str, Any],
    inputs: Phy1TopologyV2Inputs,
) -> dict[str, Any]:
    v1 = _object(root / "docs/capability-profiles/phy1-single-layer-d0-v1.json")
    inventory, executable_hash = executable_source_inventory(root)
    profile: dict[str, Any] = {
        "schemaVersion": 1,
        "profileVersion": PHY1_TOPOLOGY_V2_PROFILE_VERSION,
        "classification": "opt_in_physical_experiment_only_not_runtime_capability",
        "predecessorProfileVersion": v1["profileVersion"],
        "predecessorFailurePreserved": True,
        "authorityOutcome": "A_physical_experiment_only_v2",
        "identities": report["identities"],
        "frozenScenarioIds": PHY1_STATE_IDS,
        "frozenScenarioDefinitions": v1["scenarioDefinitions"],
        "solverProfile": v1["solverProfile"],
        "thresholds": report["thresholds"],
        "oracles": {
            "temporal": "closy.deformation_quality.temporal_swept_area.v1",
            "clearance": "closy.phy1.solver_primitive_signed_clearance.v1",
            "simulationAndRenderMeasuredSeparately": True,
            "rotationInvariantTemporalOracle": True,
        },
        "topology": {
            "simulationTopologyVersion": "closy.simulation_topology.v2",
            "triangulatorVersion": "closy.interior_constrained_triangulator.v2",
            "simulationVertexCount": inputs.rest_mesh.vertex_count,
            "simulationTriangleCount": inputs.rest_mesh.triangle_count,
            "runtimeExposed": False,
        },
        "determinism": {
            "seed": 0,
            "threadCount": 1,
            "canonicalPositionDigits": 9,
            "canonicalJson": True,
            "sourceInventory": inventory,
            "experimentExecutableSourceHash": executable_hash,
        },
        "claims": {
            "phy1Passed": False,
            "solverDrivenZ2Passed": False,
            "integratedCcd": False,
            "runtimeCapabilityExposed": False,
        },
        "integrity": {"profileHash": ""},
    }
    profile["integrity"]["profileHash"] = _document_hash(profile, "profileHash")
    return profile


def build_topology_manifest(report: dict[str, Any], inputs: Phy1TopologyV2Inputs) -> dict[str, Any]:
    manifest = deepcopy(inputs.topology_manifest)
    manifest.update(
        {
            "schemaVersion": 1,
            "publicationVersion": PHY1_TOPOLOGY_V2_PUBLICATION_VERSION,
            "sourceAnchorSha": report["sourceAnchorSha"],
            "simulationTopologyHash": report["identities"]["simulationTopologyHash"],
            "simulationRestContentHash": report["identities"]["simulationRestContentHash"],
            "outcome": "A_physical_experiment_only_v2",
            "runtimeExposed": False,
            "integrity": {"manifestHash": ""},
        }
    )
    manifest["integrity"]["manifestHash"] = _document_hash(manifest, "manifestHash")
    return manifest


def build_component_audit(
    report: dict[str, Any], audit: dict[str, Any], *, component: str
) -> dict[str, Any]:
    result = deepcopy(audit)
    result.update(
        {
            "schemaVersion": 1,
            "publicationVersion": PHY1_TOPOLOGY_V2_PUBLICATION_VERSION,
            "component": component,
            "sourceAnchorSha": report["sourceAnchorSha"],
            "runtimeExposed": False,
            "integrity": {"auditHash": ""},
        }
    )
    result["integrity"]["auditHash"] = _document_hash(result, "auditHash")
    return result


def build_v2_invalidation_ledger(root: Path, report: dict[str, Any]) -> dict[str, Any]:
    integrated = _object(root / INTEGRATED_D_LEDGER_PATH)
    if integrated["baselineIdentities"] != integrated["currentIdentities"]:
        raise ValueError("integrated_d_identity_drift_before_phy1_v2")
    ledger: dict[str, Any] = {
        "schemaVersion": 1,
        "ledgerVersion": "closy.phy1.topology_v2.invalidation_ledger.v1",
        "sourceAnchorSha": report["sourceAnchorSha"],
        "authorityOutcome": "A_physical_experiment_only_v2",
        "integratedRuntimeLedgerPath": INTEGRATED_D_LEDGER_PATH.as_posix(),
        "integratedRuntimeLedgerSha256": sha256_file(root / INTEGRATED_D_LEDGER_PATH),
        "baselineRuntimeIdentities": integrated["baselineIdentities"],
        "currentRuntimeIdentities": integrated["currentIdentities"],
        "runtimeIdentityChanges": [],
        "retainedRuntimeCapabilities": integrated["calculatedInvalidation"][
            "retainedByExactIdentity"
        ],
        "invalidatedRuntimeCapabilities": [],
        "mandatoryRuntimeReruns": [],
        "experimentIdentities": report["identities"],
        "separationProof": {
            "v2PackagePublished": False,
            "v2BindingPublishedToRuntime": False,
            "v2DerivativePublished": False,
            "v2RuntimeCapabilityPublished": False,
            "dRuntimeStillPinnedToV1": True,
            "historicalC3Mt1RuntimeEvidenceChanged": False,
        },
        "integrity": {"ledgerHash": ""},
    }
    ledger["integrity"]["ledgerHash"] = _document_hash(ledger, "ledgerHash")
    return ledger


def build_final_d0_research_matrix(root: Path, report: dict[str, Any]) -> dict[str, Any]:
    c3_path = Path("docs/evidence/c3_phy1_candidate_1a500b1.json")
    integrated_path = Path("docs/evidence/integrated_runtime_avatar_outfit_v2.json")
    z1_path = Path("docs/evidence/phase10_zeroone_static/z1_representative_evidence.json")
    mt1_path = Path("docs/evidence/phase11_reference_motion_v2/execution_evidence.json")
    c3 = _object(root / c3_path)
    integrated = _object(root / integrated_path)
    z1 = _object(root / z1_path)
    mt1 = _object(root / mt1_path)
    rows = [
        _matrix_row(
            "D0-RP-01",
            "decoded front/rear raster ingestion and source identity",
            "not_run",
            "exact selected T-shirt identity has decoded front and rear raster source records",
            reason=(
                "historical synthetic raster evidence is not linked to the exact "
                "integrated D identity"
            ),
        ),
        _matrix_row(
            "D0-RP-02",
            "pixel-derived masks, landmarks, and correction provenance",
            "not_run",
            "all records derive from decoded pixels and retain correction provenance",
            reason="no exact-row decoded-pixel lineage was executed",
        ),
        _matrix_row(
            "D0-RP-03",
            "image-conditioned template ranking and continuous parameter fit",
            "not_run",
            "precommitted ranking and parameter thresholds pass on the exact row",
            reason=(
                "the losing structured E1 experiment was not selected into the "
                "integrated identity"
            ),
        ),
        _matrix_row(
            "D0-RP-04",
            "strongest equal-input no-pixel/template and deterministic fitting baselines",
            "not_run",
            "equal-input controls execute without source-pixel access",
            reason="no exact-row equal-input control manifest exists",
        ),
        _matrix_row(
            "D0-RP-05",
            "persisted pattern, seams, openings, simulation/render topology, and binding",
            "pass",
            "canonical package validates every required representation identity",
            evidence={
                "path": integrated_path.as_posix(),
                "sha256": sha256_file(root / integrated_path),
                "packageDigest": integrated["packageExecution"]["packageDigest"],
                "simulationTopologyHash": integrated["invalidationLedger"]["currentIdentities"][
                    "simulationTopologyHash"
                ],
                "renderTopologyHash": integrated["invalidationLedger"]["currentIdentities"][
                    "renderTopologyHash"
                ],
                "bindingHash": integrated["invalidationLedger"]["currentIdentities"]["bindingHash"],
            },
        ),
        _matrix_row(
            "D0-RP-06",
            "source-conditioned silhouette and landmark error after reference-3D compilation",
            "not_run",
            "precommitted source-conditioned silhouette and landmark errors pass",
            reason=(
                "no decoded-raster authority is linked through reference-3D compilation "
                "on this row"
            ),
        ),
        _matrix_row(
            "D0-RP-07",
            "decoded bitmap/PBR projection and independent rerender comparison",
            "not_run",
            "independent rerender compares against decoded source pixels not self-derived texture",
            reason="no independent exact-row decoded-bitmap/PBR rerender comparison exists",
        ),
        _matrix_row(
            "D0-RP-08",
            "C3 dense-shell and fallback following on exact selected identity",
            "pass",
            "11 of 11 states and persisted binding thresholds pass",
            evidence={
                "path": c3_path.as_posix(),
                "sha256": sha256_file(root / c3_path),
                "sourceSha": c3["source"]["gitSha"],
                "statePassCount": c3["C3-Binding-D0"]["bindingStatePassCount"],
                "stateCount": c3["C3-Binding-D0"]["stateCount"],
                "recordCount": c3["C3-Binding-D0"]["persistedBindingRecordCount"],
                "maximumReconstructionErrorMeters": c3["C3-Binding-D0"][
                    "maximumReconstructionErrorMeters"
                ],
            },
        ),
        _matrix_row(
            "D0-RP-09",
            "conventional fallback load without ZeroOne",
            "pass",
            "offline conventional fallback validates and loads independently",
            evidence={
                "path": integrated_path.as_posix(),
                "loaded": integrated["packageExecution"]["conventionalFallback"]["loaded"],
                "sha256": integrated["packageExecution"]["conventionalFallback"]["sha256"],
                "packageValidityDependsOnZeroOne": integrated["packageExecution"][
                    "packageValidityDependsOnZeroOne"
                ],
            },
        ),
        _matrix_row(
            "D0-RP-10",
            "candidate static ZeroOne capability",
            "pass",
            (
                "representative static candidate passes while global/current-master "
                "claims remain false"
            ),
            evidence={
                "path": z1_path.as_posix(),
                "sha256": sha256_file(root / z1_path),
                "status": z1["status"],
                "zeroOneSha": z1["zeroOneSha"],
                "executableSha256": z1["executableSha256"],
                "globalZ1Passed": z1["claims"]["globalZ1Passed"],
            },
        ),
        _matrix_row(
            "D0-RP-11",
            "MT1 lab/reference motion separately from solver-driven Gate Z2",
            "pass",
            "clean mechanical-reference profile passes with blueprint Z2 false",
            evidence={
                "path": mt1_path.as_posix(),
                "sha256": sha256_file(root / mt1_path),
                "outcome": mt1["outcome"],
                "requestIdentity": mt1["dynamic"]["requestSha256"],
                "outputIdentity": mt1["dynamic"]["outputSha256"],
                "blueprintZ2Passed": mt1["claims"]["blueprintZ2Passed"],
                "solverDrivenClothPassed": mt1["claims"]["solverDrivenClothPassed"],
            },
        ),
        _matrix_row(
            "D0-RP-12",
            "fresh build, cache, and delete/rebuild determinism",
            "pass",
            "all three deterministic paths preserve exact selected identities",
            evidence={
                "z1DeleteRebuildPassed": z1["deleteAndRebuild"]["passed"],
                "z1Before": z1["deleteAndRebuild"]["canonicalDerivativeHashBefore"],
                "z1After": z1["deleteAndRebuild"]["canonicalDerivativeHashAfter"],
                "mt1CacheHitValidated": mt1["dynamic"]["cacheHitValidated"],
                "mt1DeleteRebuild": mt1["dynamic"]["deterministicDeleteRebuild"],
            },
        ),
        _matrix_row(
            "D0-RP-13",
            "exact evidence, package, and executable hashes",
            "pass",
            "all selected executable and package authorities carry exact hashes",
            evidence={
                "integratedPackageDigest": integrated["packageExecution"]["packageDigest"],
                "z1ExecutableSha256": z1["executableSha256"],
                "mt1ExecutableSha256": integrated["invalidationLedger"]["currentIdentities"][
                    "zeroOneBinaryIdentity"
                ],
                "phy1V2EvidenceHash": report["integrity"]["evidenceHash"],
            },
        ),
        _matrix_row(
            "D0-RP-14",
            "unsupported human, private, device, and physical claims remain false",
            "pass",
            "no unsupported evidence class is promoted",
            evidence={
                "humanReview": integrated["truth"]["humanReview"],
                "privateUser": integrated["truth"]["privateUser"],
                "mobileDevice": integrated["truth"]["mobileDevice"],
                "gpu": integrated["truth"]["gpu"],
                "phy1V2Passed": report["acceptance"]["globalPhy1Complete"],
                "productionPhysicalAnimation": report["claims"]["productionPhysicalAnimation"],
            },
        ),
    ]
    counts = {
        status: sum(row["status"] == status for row in rows)
        for status in ("pass", "fail", "not_run")
    }
    matrix: dict[str, Any] = {
        "schemaVersion": 1,
        "matrixVersion": FINAL_D0_MATRIX_VERSION,
        "sourceAnchorSha": report["sourceAnchorSha"],
        "scope": "fixed_reference_avatar_project_authored_tshirt_D0",
        "rowCount": len(rows),
        "rows": rows,
        "statusCounts": counts,
        "researchPrototypeStatus": "partial",
        "firstUnmetRequirement": {
            "rowId": "D0-RP-01",
            "reason": rows[0]["reason"],
        },
        "separateGates": {
            "phy1V2": report["acceptance"]["status"],
            "solverDrivenZ2": "failed_not_admitted",
            "mt1MechanicalReference": "pass",
        },
        "claims": {
            "globalResearchPrototypePassed": False,
            "alphaReady": False,
            "humanEvidence": False,
            "privateUserEvidence": False,
            "deviceEvidence": False,
            "physicalClothEvidence": False,
        },
        "integrity": {"matrixHash": ""},
    }
    matrix["integrity"]["matrixHash"] = _document_hash(matrix, "matrixHash")
    return matrix


def validate_publication(
    root: Path,
    *,
    profile: dict[str, Any],
    report: dict[str, Any],
    ledger: dict[str, Any],
    matrix: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    if _document_hash(profile, "profileHash") != profile["integrity"]["profileHash"]:
        issues.append("phy1_v2_profile_hash_mismatch")
    if _document_hash(report, "evidenceHash") != report["integrity"]["evidenceHash"]:
        issues.append("phy1_v2_evidence_hash_mismatch")
    if _document_hash(ledger, "ledgerHash") != ledger["integrity"]["ledgerHash"]:
        issues.append("phy1_v2_ledger_hash_mismatch")
    if _document_hash(matrix, "matrixHash") != matrix["integrity"]["matrixHash"]:
        issues.append("phy1_v2_matrix_hash_mismatch")
    if report["acceptance"]["status"] != "failed":
        issues.append("phy1_v2_unexpected_acceptance")
    if report["authority"]["outcome"] != "A_physical_experiment_only_v2":
        issues.append("phy1_v2_authority_outcome_invalid")
    if ledger["baselineRuntimeIdentities"] != ledger["currentRuntimeIdentities"]:
        issues.append("phy1_v2_runtime_identity_drift")
    if not ledger["separationProof"]["dRuntimeStillPinnedToV1"]:
        issues.append("phy1_v2_runtime_not_pinned_to_v1")
    if matrix["researchPrototypeStatus"] != "partial":
        issues.append("phy1_v2_research_matrix_overclaimed")
    integrated = _object(root / INTEGRATED_D_LEDGER_PATH)
    if ledger["currentRuntimeIdentities"] != integrated["currentIdentities"]:
        issues.append("phy1_v2_integrated_identity_mismatch")
    return issues


def executable_source_inventory(root: Path) -> tuple[list[dict[str, str]], str]:
    rows = [
        {"path": path.as_posix(), "sha256": sha256_file(root / path)}
        for path in _EXECUTABLE_SOURCE_PATHS
    ]
    return rows, sha256_bytes(canonical_dumps(rows).encode("utf-8"))


def _matrix_row(
    row_id: str,
    requirement: str,
    status: str,
    threshold: str,
    *,
    evidence: dict[str, Any] | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    row = {
        "rowId": row_id,
        "requirement": requirement,
        "status": status,
        "precommittedThreshold": threshold,
        "evidence": evidence,
        "reason": reason,
    }
    return row


def _object(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"object_required:{path.as_posix()}")
    return value


def _document_hash(document: dict[str, Any], field: str) -> str:
    payload = deepcopy(document)
    payload["integrity"][field] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
