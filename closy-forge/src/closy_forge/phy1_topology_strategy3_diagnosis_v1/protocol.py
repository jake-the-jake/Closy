from __future__ import annotations

import hashlib
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file

LOCK_VERSION = "closy.phy1.topology_strategy3.diagnosis_lock.v1"
FIXTURE_ROOT = Path("fixtures/phy1_topology_strategy3_diagnosis_v1")
EVIDENCE_ROOT = Path("docs/evidence/phy1_topology_strategy3_diagnosis_v1")
LOCK_PATH = FIXTURE_ROOT / "diagnosis_lock.json"
AUTHORITY_PATH = EVIDENCE_ROOT / "starting_authority.json"
CONFIRMATION_GENERATOR_PATH = FIXTURE_ROOT / "confirmation_generator_lock.json"
LOCK_REPORT_PATH = EVIDENCE_ROOT / "lock_report.json"
OUTCOME_PATH = EVIDENCE_ROOT / "unit_o_outcome.json"

PR43_PACKAGE = Path("docs/evidence/d0_fitting_pbr_fidelity_v2/predictions/candidate_package")
RUNTIME_V1 = Path("docs/evidence/integrated_runtime_avatar_outfit_v2.json")

AUTHORITY_FILES = (
    "fixtures/phy1_seam_support_v3/experiment_lock.json",
    "docs/evidence/phy1_seam_support_v3/neutral_preflight.json",
    "docs/evidence/phy1_seam_support_v3/outcome.json",
    "docs/evidence/phy1_seam_support_v3/evidence_manifest.json",
    "docs/evidence/d0_fitting_pbr_fidelity_v2/predictions/candidate_package/candidate_manifest.json",
    "docs/evidence/d0_fitting_pbr_fidelity_v2/predictions/candidate_package/simulation/rest_mesh.glb",
    "docs/evidence/d0_fitting_pbr_fidelity_v2/predictions/candidate_package/simulation/constraints.json",
    "docs/evidence/d0_fitting_pbr_fidelity_v2/predictions/candidate_package/render/render_mesh.glb",
    "docs/evidence/d0_fitting_pbr_fidelity_v2/predictions/candidate_package/binding/sim_to_render.bin",
    "fixtures/phy1_topology_strategy2_v4/strategy_lock.json",
    "docs/evidence/phy1_topology_strategy2_v4/strategy_microfixtures.json",
    "docs/evidence/phy1_topology_strategy2_v4/unit_i_outcome.json",
    "docs/evidence/phy1_topology_strategy2_v4/physical_attempt_registry.json",
    "docs/evidence/d0_recovery_foundation_v1/physical_budget_authority.json",
    "docs/evidence/integrated_runtime_avatar_outfit_v2.json",
)

IMPLEMENTATION_FILES = (
    "src/closy_forge/phy1_topology_strategy3_diagnosis_v1/protocol.py",
    "src/closy_forge/phy1_topology_strategy3_diagnosis_v1/production_kernels.py",
    "src/closy_forge/phy1_topology_strategy3_diagnosis_v1/transfer.py",
    "src/closy_forge/phy1_topology_strategy3_diagnosis_v1/fixtures.py",
    "src/closy_forge/phy1_topology_strategy3_diagnosis_v1/diagnosis.py",
    "src/closy_forge/phy1_topology_strategy3_diagnosis_v1/repeat_worker.py",
)

FIXTURE_IDS = (
    "duplicated_seam_normal_separation",
    "curved_seam_tangential_loading",
    "unequal_discretisation_ease",
    "three_way_seam_junction",
    "opening_adjacent_to_seam",
    "seam_near_body_contact",
    "constrained_remesh_attribute_transfer",
    "deterministic_repeat_cross_process",
)


def build_starting_authority(root: Path) -> dict[str, Any]:
    files = [_identity(root, Path(path)) for path in AUTHORITY_FILES]
    seam_lock = _mapping(read_json(root / AUTHORITY_FILES[0]))
    constraints = _mapping(read_json(root / PR43_PACKAGE / "simulation/constraints.json"))
    strategy2 = _mapping(
        read_json(root / "docs/evidence/phy1_topology_strategy2_v4/unit_i_outcome.json")
    )
    budget = _mapping(
        read_json(root / "docs/evidence/d0_recovery_foundation_v1/physical_budget_authority.json")
    )
    neutral = _mapping(
        read_json(root / "docs/evidence/phy1_seam_support_v3/neutral_preflight.json")
    )
    physical_outcome = _mapping(read_json(root / "docs/evidence/phy1_seam_support_v3/outcome.json"))
    runtime = _mapping(read_json(root / RUNTIME_V1))
    runtime_decision = _mapping(runtime["runtimeDecision"])
    runtime_authority = _mapping(runtime_decision["authority"])
    configuration = _mapping(seam_lock["configuration"])
    semantic_inventory = {
        "semanticSeamPairCount": len(constraints.get("seams", [])),
        "semanticConstraintCount": len(constraints.get("constraints", [])),
        "openingCount": len(constraints.get("openings", [])),
    }
    if semantic_inventory != {
        "semanticSeamPairCount": 12,
        "semanticConstraintCount": 92,
        "openingCount": 4,
    }:
        raise ValueError("unit_o_pr43_semantic_inventory_mismatch")
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "authorityVersion": "closy.phy1.topology_strategy3.starting_authority.v1",
        "repository": "jake-the-jake/Closy",
        "branch": "codex/closy-forge-phy1-topology-strategy3-diagnosis-v1",
        "pullRequest": "pending",
        "baseBranch": "codex/closy-forge-d0-strict-c3-confirmation-v5",
        "baseSha": "e062a30ba295ed27334622916ddb449fd76e2166",
        "mergeBase": "e062a30ba295ed27334622916ddb449fd76e2166",
        "sourceEvidenceAnchorSha": "6aee5ed3b2753ee99c95abdef6f5a24be39b3a7e",
        "actualBlobIdentities": files,
        "candidatePackageTreeDigest": _tree_digest(root / PR43_PACKAGE),
        "semanticInventory": semantic_inventory,
        "finiteComplianceAuthority": _mapping(configuration["seams"]),
        "solverAuthority": _mapping(configuration["solver"]),
        "supportAuthority": _mapping(configuration["supports"]),
        "collisionAuthority": _mapping(configuration["collision"]),
        "conditionalCcdAuthority": _mapping(seam_lock["conditionalPhy1"]),
        "constraintOrder": configuration["constraintOrder"],
        "priorPhysicalOutcome": {
            "neutralStatus": neutral.get("status"),
            "outcome": physical_outcome.get("outcome"),
            "neutralExecuted": physical_outcome.get("neutralExecuted"),
            "fullPhy1Executed": physical_outcome.get("fullPhy1Executed"),
            "integratedCcdExecuted": physical_outcome.get("ccdExecuted"),
        },
        "strategy2Outcome": {
            "outcomeClass": strategy2["outcomeClass"],
            "reasonCode": strategy2["reasonCode"],
            "remainingBudgets": strategy2["remainingBudgets"],
            "outcomeDigest": _mapping(strategy2["integrity"])["outcomeDigest"],
        },
        "globalPhysicalChainHead": budget.get("headHash"),
        "physicalBudgets": _mapping(budget["budgets"]),
        "runtimeV1ManifestIdentity": {
            "runtimeId": runtime_decision.get("runtimeVersion"),
            "packageDigest": runtime_authority.get("packageDigest"),
            "conventionalFallbackSha256": runtime_authority.get("conventionalFallbackSha256"),
            "authoritySha256": sha256_file(root / RUNTIME_V1),
        },
        "runtimeV1Selected": True,
        "candidateCreated": False,
        "candidateAttemptConsumed": False,
        "finalStrategyConsumed": False,
        "integrity": {"authorityDigest": ""},
    }
    document["integrity"]["authorityDigest"] = document_digest(document, "authorityDigest")
    return document


def build_diagnosis_lock(root: Path, authority: Mapping[str, Any]) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "lockVersion": LOCK_VERSION,
        "state": "frozen_before_bounded_revision_execution",
        "startingAuthorityDigest": _mapping(authority["integrity"])["authorityDigest"],
        "question": (
            "Can a constrained-remesh class preserve duplicated explicit finite-compliance seams, "
            "semantic openings, production-kernel mechanics, and every canonical transfer field?"
        ),
        "hypothesesNotCauses": [
            "representation_collapse",
            "collision_ordering",
            "timestep",
            "mesh_quality",
            "constraint_scheduling",
            "support_response",
            "transfer_error",
        ],
        "productionKernels": {
            "solver": "closy.reference_xpbd_cpu.v2.0_material_coupled_d0",
            "distanceConstraint": "reference_cloth_solver._solve_distance",
            "supportConstraint": "reference_cloth_solver._solve_support",
            "bodyCollision": "reference_cloth_solver._project_collisions",
            "finiteComplianceMetersPerNewton": 1e-9,
            "timeStepSeconds": 0.016666667,
            "constraintOrder": ["distance_xpbd", "support_projection", "body_collision"],
        },
        "developmentFixtures": [
            {"fixtureId": fixture_id, "candidateIndependent": True, "qualificationEligible": False}
            for fixture_id in FIXTURE_IDS
        ],
        "revisions": [
            {
                "revision": 1,
                "strategyClass": "local_longest_edge_bisection",
                "declaredRisk": "unclosed_shared_edge_creates_t_junction",
            },
            {
                "revision": 2,
                "strategyClass": "closure_longest_edge_bisection",
                "declaredRisk": "semantic_seam_sequence_requires_explicit_transfer",
            },
        ],
        "maximumPreCandidateRevisions": 2,
        "admissionThresholds": {
            "maximumResidualRatio": 0.1,
            "maximumEnergyBalanceErrorJoules": 1e-9,
            "maximumImpulseBalanceErrorNewtonSeconds": 1e-9,
            "maximumMassTransferErrorKg": 1e-12,
            "minimumTriangleAngleDegrees": 5.0,
            "maximumTopologyDefectCount": 0,
            "requiredOpeningCount": 1,
            "requiredNegativeMutationDetectionRate": 1.0,
            "requiredFixturePassCount": 8,
            "requiredFixtureCount": 8,
        },
        "numericalIntervalDerivation": {
            "xpbdImpulseAndEnergy": (
                "closed-form first XPBD update using frozen compliance, timestep, "
                "and inverse masses"
            ),
            "transferConservation": (
                "exact split accounting with 1e-12 SI tolerance above binary64 accumulation noise"
            ),
            "topology": "integer combinatorial invariants require zero defects",
            "triangleQuality": "five-degree lower bound fixed before revision execution",
            "strategy2ThresholdReused": False,
            "thresholdRelaxationAllowed": False,
        },
        "requiredTransferFields": [
            "mass",
            "uv",
            "material",
            "semanticSeamIds",
            "sourceCoordinates",
            "bindingCoordinates",
        ],
        "fieldClasses": {
            "semantic": ["compliance", "mass", "uv", "semanticSeamIds", "bindingCoordinates"],
            "validation": ["topologyHashes", "openingCount", "winding", "finiteValues"],
            "provenance": ["revision", "strategyClass", "implementationDigest"],
        },
        "confirmationGenerator": {
            "version": "closy.phy1.strategy3.confirmation_fixture_generator.v1",
            "seedAuthority": "first_external_unit_p_authority_after_final_strategy_lock",
            "seedBits": 256,
            "seedRealized": False,
            "instanceParametersRealized": False,
            "strata": list(FIXTURE_IDS),
            "instancesPerStratum": 1,
            "denominator": 8,
            "ranges": {
                "initialSeparationMeters": [0.008, 0.035],
                "tangentialOffsetMeters": [0.003, 0.02],
                "easeRatio": [0.2, 0.8],
                "contactPenetrationMeters": [0.001, 0.008],
                "triangleAspectRatio": [1.2, 8.0],
            },
            "invariants": [
                "finite_compliance_seam_law_preserved",
                "normal_and_tangential_residuals_separate",
                "energy_and_impulse_within_locked_intervals",
                "deterministic_constraint_order",
                "semantic_seams_and_openings_preserved",
                "topology_defect_count_zero",
                "all_transfer_fields_preserved",
                "negative_mutations_detected",
            ],
            "thresholds": {
                "maximumResidualRatio": 0.1,
                "maximumEnergyBalanceErrorJoules": 1e-9,
                "maximumImpulseBalanceErrorNewtonSeconds": 1e-9,
                "maximumMassTransferErrorKg": 1e-12,
                "minimumTriangleAngleDegrees": 5.0,
                "maximumTopologyDefectCount": 0,
            },
            "oneShot": True,
            "rerollAllowed": False,
            "qualificationInstances": [],
        },
        "outcomes": [
            "strategy3_class_admitted_pre_candidate",
            "no_strategy3_class_admitted_within_bounded_diagnosis",
            "diagnosis_integrity_error",
            "dependency_blocked",
        ],
        "candidateCreationAllowed": False,
        "finalStrategyConsumptionAllowed": False,
        "implementationHashMode": "utf8_canonical_lf_final_newline",
        "implementationFiles": [
            {"path": path, "sha256": canonical_source_sha256(root / path)}
            for path in IMPLEMENTATION_FILES
        ],
        "integrity": {"lockDigest": ""},
    }
    document["integrity"]["lockDigest"] = document_digest(document, "lockDigest")
    return document


def validate_lock(root: Path, document: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if document.get("lockVersion") != LOCK_VERSION:
        issues.append("lock_version_mismatch")
    if _mapping(document.get("integrity")).get("lockDigest") != document_digest(
        dict(document), "lockDigest"
    ):
        issues.append("lock_digest_mismatch")
    for record in document.get("implementationFiles", []):
        row = _mapping(record)
        path = root / str(row.get("path"))
        if not path.is_file() or canonical_source_sha256(path) != row.get("sha256"):
            issues.append(f"implementation_hash_mismatch:{row.get('path')}")
    generator = _mapping(document.get("confirmationGenerator"))
    if (
        generator.get("seedRealized") is not False
        or generator.get("instanceParametersRealized") is not False
        or generator.get("qualificationInstances") != []
        or "seed" in generator
    ):
        issues.append("confirmation_instances_realized_before_unit_p_lock")
    if document.get("candidateCreationAllowed") is not False:
        issues.append("candidate_creation_allowed_in_unit_o")
    if document.get("finalStrategyConsumptionAllowed") is not False:
        issues.append("final_strategy_consumption_allowed_in_unit_o")
    return sorted(set(issues))


def canonical_source_sha256(path: Path) -> str:
    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return sha256_bytes((text.rstrip("\n") + "\n").encode("utf-8"))


def document_digest(document: dict[str, Any], field: str) -> str:
    payload = deepcopy(document)
    if field in payload:
        payload[field] = ""
    elif isinstance(payload.get("integrity"), dict):
        payload["integrity"][field] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _identity(root: Path, relative: Path) -> dict[str, Any]:
    path = root / relative
    if not path.is_file():
        raise ValueError(f"unit_o_authority_file_missing:{relative.as_posix()}")
    content = path.read_bytes()
    git_payload = f"blob {len(content)}\0".encode() + content
    return {
        "path": relative.as_posix(),
        "sha256": sha256_file(path),
        "gitBlobOidSha1": hashlib.sha1(git_payload, usedforsecurity=False).hexdigest(),
        "byteLength": path.stat().st_size,
    }


def _tree_digest(path: Path) -> str:
    records = [
        [item.relative_to(path).as_posix(), sha256_file(item), item.stat().st_size]
        for item in sorted(path.rglob("*"))
        if item.is_file()
    ]
    return sha256_bytes(canonical_dumps(records).encode("utf-8"))


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
