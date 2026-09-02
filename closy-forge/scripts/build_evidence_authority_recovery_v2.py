from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.recovery_foundation_v2.c3_audit import (
    audit_persisted_glb,
    build_historical_v5_scope,
    generic_c3_mutation_report,
)
from closy_forge.recovery_foundation_v2.container_boundary import build_container_capability
from closy_forge.recovery_foundation_v2.contracts import (
    build_budget_event_ledger,
    build_external_attestation,
    build_starting_manifest,
    validate_budget_event_ledger,
    validate_external_attestation,
    validate_starting_manifest,
)
from closy_forge.recovery_foundation_v2.evaluator_v3 import (
    evaluate,
    generic_rows,
    mutation_report,
    protocol,
)
from closy_forge.recovery_foundation_v2.pixel_routes import (
    build_pixel_causal_controls,
    build_public_training_inventory,
    fit_public_development_model,
)
from closy_forge.recovery_foundation_v2.portable_numeric import (
    boundary_fixtures,
    canonical_geometry_coordinate,
)
from closy_forge.recovery_foundation_v2.production_assembly import execute_public_fixture
from closy_forge.recovery_foundation_v2.topology_holdout import (
    PUBLIC_DEVELOPMENT_SEED,
    build_public_development_proof,
    generate,
    generator_lock,
)
from closy_forge.recovery_foundation_v2.topology_holdout_oracle import derive_invariants
from closy_forge.recovery_foundation_v2.typed_inventory import (
    build_recoverable_inventory,
    validate_inventory,
)

EVIDENCE_RELATIVE = Path("docs/evidence/evidence_authority_recovery_v2")
FIXTURE_RELATIVE = Path("fixtures/evidence_authority_recovery_v2")
MODEL_RELATIVE = Path("models/d0_v3/public_pixel_fitted_tshirt_v1.json")


def _code_lock(root: Path) -> dict[str, Any]:
    paths = [
        "src/closy_forge/recovery_foundation_v2/container_boundary.py",
        "src/closy_forge/recovery_foundation_v2/pixel_routes.py",
        "src/closy_forge/recovery_foundation_v2/evaluator_v3.py",
        "src/closy_forge/recovery_foundation_v2/typed_inventory.py",
        "src/closy_forge/recovery_foundation_v2/c3_audit.py",
        "src/closy_forge/recovery_foundation_v2/portable_numeric.py",
        "src/closy_forge/recovery_foundation_v2/topology_holdout.py",
        "src/closy_forge/recovery_foundation_v2/topology_holdout_oracle.py",
        "src/closy_forge/recovery_foundation_v2/production_assembly.py",
        "docker/d0_v3/Dockerfile",
        "docker/d0_v3/entrypoint.sh",
        "docker/d0_v3/runner.py",
    ]
    records = [
        {
            "path": path,
            "sha256": sha256_file(root / path),
            "byteLength": (root / path).stat().st_size,
        }
        for path in paths
    ]
    return {
        "schemaVersion": 1,
        "lockVersion": "closy.evidence_authority_recovery.code_lock.v2",
        "records": records,
        "lockDigest": sha256_bytes(canonical_dumps(records).encode("utf-8")),
    }


def _source_separation(root: Path) -> dict[str, Any]:
    learned_path = root / "src/closy_forge/recovery_foundation_v2/pixel_routes.py"
    oracle_path = root / "src/closy_forge/recovery_foundation_v2/topology_holdout_oracle.py"
    learned = learned_path.read_text(encoding="utf-8")
    oracle = oracle_path.read_text(encoding="utf-8")
    learned_forbidden = (
        "from closy_forge.recovery_foundation_v2.evaluator_v3",
        "import target_generator",
        "import private_target",
    )
    oracle_forbidden = ("production_assembly", "final_remesher", "candidate_output_pass")
    return {
        "schemaVersion": 1,
        "learnedRouteSource": str(learned_path.relative_to(root)).replace("\\", "/"),
        "learnedRouteSourceSha256": sha256_file(learned_path),
        "learnedRouteForbiddenDependenciesAbsent": all(
            token not in learned for token in learned_forbidden
        ),
        "oracleSource": str(oracle_path.relative_to(root)).replace("\\", "/"),
        "oracleSourceSha256": sha256_file(oracle_path),
        "oracleForbiddenDependenciesAbsent": all(
            token not in oracle for token in oracle_forbidden
        ),
        "forbiddenDependencies": {
            "learnedRoute": list(learned_forbidden),
            "topologyOracle": list(oracle_forbidden),
        },
    }


def build(root: Path, authority: Mapping[str, Any] | None) -> dict[Path, Any]:
    model = fit_public_development_model()
    inventory = build_recoverable_inventory(root)
    evaluator_protocol = protocol()
    evaluator_result = evaluate(evaluator_protocol, *generic_rows())
    fixtures = generate(PUBLIC_DEVELOPMENT_SEED, qualification_eligible=False)
    topology_oracles = [derive_invariants(fixture) for fixture in fixtures]
    production_reports = [execute_public_fixture(fixture) for fixture in fixtures]
    container = build_container_capability()
    preflight_pass = bool(authority and authority.get("pass") is True)
    portable_pass = bool(authority and authority.get("portableMatrixPass") is True)
    if authority:
        container["replicationRule"] = {
            "required": 3,
            "passed": int(authority.get("replicationsPassed", 0)),
            "officialPreflightRun": authority.get("runId"),
            "workflowHeadSha": authority.get("headSha"),
            "externalAttestation": True,
        }
    subgates = {
        "S-core-truth": {
            "result": "pass",
            "reason": "starting_truth_replay_ledger_schema_and_budget_derivation_valid",
        },
        "S-D0-authority": {
            "result": "pass" if preflight_pass else "dependency_blocked",
            "reason": (
                "exact_head_pinned_image_preflight_3_of_3"
                if preflight_pass
                else "local_docker_unavailable_external_exact_head_preflight_pending"
            ),
        },
        "S-PHY-authority": {
            "result": "pass" if portable_pass else "dependency_blocked",
            "reason": (
                "exact_head_cross_platform_numeric_matrix_green"
                if portable_pass
                else "external_exact_head_cross_platform_matrix_pending"
            ),
        },
    }
    documents: dict[Path, Any] = {
        EVIDENCE_RELATIVE / "starting_manifest.json": build_starting_manifest(),
        EVIDENCE_RELATIVE / "external_pr52_attestation.json": build_external_attestation(),
        EVIDENCE_RELATIVE / "physical_budget_event_ledger.json": build_budget_event_ledger(),
        EVIDENCE_RELATIVE / "code_lock.json": _code_lock(root),
        EVIDENCE_RELATIVE / "container_boundary.json": container,
        EVIDENCE_RELATIVE / "pixel_causal_controls.json": build_pixel_causal_controls(model),
        EVIDENCE_RELATIVE / "typed_prior_inventory.json": inventory,
        EVIDENCE_RELATIVE / "evaluator_generic_result.json": evaluator_result,
        EVIDENCE_RELATIVE / "evaluator_mutation_report.json": mutation_report(),
        EVIDENCE_RELATIVE / "strict_c3_historical_scope.json": build_historical_v5_scope(root),
        EVIDENCE_RELATIVE / "strict_c3_mutation_report.json": generic_c3_mutation_report(),
        EVIDENCE_RELATIVE / "persisted_glb_attribute_audit.json": {
            "simulation": audit_persisted_glb(
                root
                / "docs/evidence/d0_fitting_pbr_fidelity_v2/predictions/"
                "candidate_package/simulation/rest_mesh.glb"
            ),
            "render": audit_persisted_glb(
                root
                / "docs/evidence/d0_fitting_pbr_fidelity_v2/predictions/"
                "candidate_package/render/render_mesh.glb"
            ),
        },
        EVIDENCE_RELATIVE / "portable_numeric_boundary_fixtures.json": boundary_fixtures(),
        EVIDENCE_RELATIVE / "canonical_geometry_boundary.json": {
            "policyVersion": "closy.canonical_geometry.nanometer_half_even.v1",
            "examples": [
                canonical_geometry_coordinate(value)
                for value in (-0.1234567894, 0.0, 0.1234567894)
            ],
        },
        EVIDENCE_RELATIVE / "source_separation.json": _source_separation(root),
        EVIDENCE_RELATIVE / "topology_public_development_proof.json": (
            build_public_development_proof()
        ),
        EVIDENCE_RELATIVE / "topology_public_fixtures.json": fixtures,
        EVIDENCE_RELATIVE / "topology_public_oracles.json": topology_oracles,
        EVIDENCE_RELATIVE / "topology_production_path_coverage.json": production_reports,
        EVIDENCE_RELATIVE / "subgate_report.json": {
            "schemaVersion": 1,
            "unit": "S",
            "subgates": subgates,
            "officialD0SeedCreated": False,
            "officialD0CohortCreated": False,
            "officialTopologySeedCreated": False,
            "officialTopologyFixturesCreated": False,
            "canonicalCandidateCreated": False,
            "physicalAttemptConsumed": False,
        },
        EVIDENCE_RELATIVE / "unit_s_outcome.json": {
            "schemaVersion": 1,
            "unit": "S",
            "result": (
                "pass"
                if all(row["result"] == "pass" for row in subgates.values())
                else "partial"
            ),
            "subgates": subgates,
            "remainingBudgets": {
                "seamModels": 0,
                "topologyStrategies": 1,
                "canonicalCandidateAttempts": 1,
            },
            "runtimeUnchanged": True,
            "runtimePackageDigest": (
                "836abc564a79c0f38ae8bdad3d4a418b0fb05a550193059c1cece8130203c20a"
            ),
            "conventionalFallbackDigest": (
                "8eccea814251f8974f5349548038be73a4d00cec73df7a7bfb787aede58385c6"
            ),
        },
        FIXTURE_RELATIVE / "evaluator_protocol_v3.json": evaluator_protocol,
        FIXTURE_RELATIVE / "topology_generator_lock_v2.json": generator_lock(),
        FIXTURE_RELATIVE / "public_pixel_training_inventory.json": (
            build_public_training_inventory()
        ),
        MODEL_RELATIVE: model,
    }
    if authority:
        documents[EVIDENCE_RELATIVE / "external_unit_s_preflight_attestation.json"] = dict(
            authority
        )
    return documents


def _manifest(root: Path, paths: list[Path]) -> dict[str, Any]:
    records = [
        {
            "path": path.as_posix(),
            "sha256": sha256_file(root / path),
            "byteLength": (root / path).stat().st_size,
        }
        for path in sorted(paths)
    ]
    return {
        "schemaVersion": 1,
        "manifestVersion": "closy.evidence_authority_recovery.manifest.v2",
        "records": records,
        "manifestDigest": sha256_bytes(canonical_dumps(records).encode("utf-8")),
    }


def _report(documents: Mapping[Path, Any]) -> str:
    outcome = documents[EVIDENCE_RELATIVE / "unit_s_outcome.json"]
    gates = outcome["subgates"]
    return "\n".join(
        [
            "# Evidence and Authority Recovery Foundation v2",
            "",
            "Unit S repairs evidence authority using only public/generic development fixtures.",
            "It creates no official D0 cohort, untouched topology fixture, canonical candidate,",
            "or physical attempt.",
            "",
            "## Sub-gates",
            "",
            *[
                f"- `{name}`: `{row['result']}` - `{row['reason']}`"
                for name, row in gates.items()
            ],
            "",
            "## Literal scope",
            "",
            "- Historical strict-C3 v5 remains a pre-topology positional binding result.",
            "- The v2 opaque D0 cohort remains unrecoverable and disjointness is unverified.",
            "- The learned T-shirt route is fitted only on public pre-v3 development renders.",
            "- Unit O raw outcome and superseding integrity attestation remain byte-immutable.",
            "- Runtime v1 and all package/fallback identities remain unchanged.",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--authority-attestation", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    authority: Mapping[str, Any] | None = None
    if args.authority_attestation:
        loaded = json.loads(args.authority_attestation.read_text(encoding="utf-8"))
        if not isinstance(loaded, Mapping):
            raise ValueError("unit_s_authority_attestation_mapping_required")
        authority = loaded
    documents = build(root, authority)
    if validate_starting_manifest(documents[EVIDENCE_RELATIVE / "starting_manifest.json"]):
        raise ValueError("unit_s_starting_manifest_invalid")
    if validate_external_attestation(
        documents[EVIDENCE_RELATIVE / "external_pr52_attestation.json"]
    ):
        raise ValueError("unit_s_external_attestation_invalid")
    if validate_budget_event_ledger(
        documents[EVIDENCE_RELATIVE / "physical_budget_event_ledger.json"]
    ):
        raise ValueError("unit_s_budget_ledger_invalid")
    if validate_inventory(documents[EVIDENCE_RELATIVE / "typed_prior_inventory.json"]):
        raise ValueError("unit_s_typed_inventory_invalid")
    expected_paths = list(documents)
    report_path = EVIDENCE_RELATIVE / "REPORT.md"
    if args.check:
        for path, value in documents.items():
            expected = canonical_dumps(value)
            if (root / path).read_text(encoding="utf-8") != expected:
                raise ValueError(f"unit_s_document_stale:{path.as_posix()}")
        if (root / report_path).read_text(encoding="utf-8") != _report(documents):
            raise ValueError("unit_s_report_stale")
        manifest_path = EVIDENCE_RELATIVE / "evidence_manifest.json"
        expected_manifest = canonical_dumps(_manifest(root, [*expected_paths, report_path]))
        if (root / manifest_path).read_text(encoding="utf-8") != expected_manifest:
            raise ValueError("unit_s_evidence_manifest_stale")
        return 0
    for path, value in documents.items():
        write_canonical_json(root / path, value)
    (root / report_path).parent.mkdir(parents=True, exist_ok=True)
    (root / report_path).write_text(_report(documents), encoding="utf-8", newline="\n")
    expected_paths.append(report_path)
    write_canonical_json(
        root / EVIDENCE_RELATIVE / "evidence_manifest.json",
        _manifest(root, expected_paths),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
