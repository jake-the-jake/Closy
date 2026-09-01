from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from closy_forge.core_runtime_c3_v4.sentinel import build_sentinel
from closy_forge.package_io.canonical_json import read_json
from closy_forge.package_io.hashing import sha256_file

UNIT_F_PACKAGE = Path(
    "docs/evidence/d0_texture_rerender_correction_v3/predictions/candidate_package"
)
PR43_LOCK = Path("fixtures/phy1_seam_support_v3/experiment_lock.json")
UNIT_G_INELIGIBLE_PREFIX = "d0_disjoint_tshirt_benchmark_v1"
REQUIRED_PATHS = (
    "pattern/pattern.json",
    "simulation/constraints.json",
    "simulation/seam_audit.json",
    "simulation/topology_manifest.json",
    "simulation/rest_mesh.glb",
    "simulation/settled_mesh.glb",
    "render/render_mesh.glb",
    "binding/sim_to_render.bin",
    "binding/binding_manifest.json",
)


def resolve_sentinel(root: Path, *, force_unit_f_failure: bool = False) -> dict[str, Any]:
    unit_f_error: str | None = None
    try:
        if force_unit_f_failure:
            raise ValueError("forced_unit_f_failure_for_fallback_fixture")
        unit_f = build_sentinel(root)
        package = root / UNIT_F_PACKAGE
        identities = _reopen_required(package)
        return {
            "schemaVersion": 1,
            "resolverVersion": "closy.d0_strict_c3.sentinel_resolver.v5",
            "resolutionRule": "unit_f_else_pr43",
            "resolutionOutcome": "unit_f_exact_candidate",
            "candidateId": unit_f["candidateId"],
            "candidatePackageDigest": unit_f["candidatePackageDigest"],
            "runtimePackageDigest": unit_f["runtimePackageDigest"],
            "fallbackIdentity": unit_f["identities"]["fallback"],
            "requiredAncestorBlobs": identities,
            "unitGCandidatesEligible": False,
            "trustedCommittedAncestryBoolean": False,
            "unitFError": None,
        }
    except (ValueError, FileNotFoundError, KeyError) as error:
        unit_f_error = f"{type(error).__name__}:{error}"
    lock = _mapping(read_json(root / PR43_LOCK))
    candidate_manifest_path = Path(str(_mapping(lock.get("candidate"))["candidateManifestPath"]))
    package = root / candidate_manifest_path.parent
    manifest = _mapping(read_json(root / candidate_manifest_path))
    identities = _reopen_required(package)
    return {
        "schemaVersion": 1,
        "resolverVersion": "closy.d0_strict_c3.sentinel_resolver.v5",
        "resolutionRule": "unit_f_else_pr43",
        "resolutionOutcome": "pr43_exact_candidate_fallback",
        "candidateId": manifest.get("candidateId"),
        "candidatePackageDigest": manifest.get("packageDigest"),
        "runtimePackageDigest": None,
        "fallbackIdentity": None,
        "requiredAncestorBlobs": identities,
        "unitGCandidatesEligible": False,
        "trustedCommittedAncestryBoolean": False,
        "unitFError": unit_f_error,
    }


def validate_sentinel_resolution(document: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if document.get("resolutionOutcome") not in {
        "unit_f_exact_candidate",
        "pr43_exact_candidate_fallback",
    }:
        issues.append("sentinel_resolution_outcome_invalid")
    if document.get("unitGCandidatesEligible") is not False:
        issues.append("unit_g_candidate_not_excluded")
    if document.get("trustedCommittedAncestryBoolean") is not False:
        issues.append("sentinel_trusts_committed_ancestry_boolean")
    paths = {row.get("path") for row in _records(document.get("requiredAncestorBlobs"))}
    if paths != set(REQUIRED_PATHS):
        issues.append("sentinel_required_blob_inventory_invalid")
    if not document.get("candidateId") or not document.get("candidatePackageDigest"):
        issues.append("sentinel_identity_incomplete")
    return issues


def _reopen_required(package: Path) -> list[dict[str, Any]]:
    records = []
    for relative in REQUIRED_PATHS:
        path = package / relative
        records.append(
            {"path": relative, "sha256": sha256_file(path), "byteLength": path.stat().st_size}
        )
    return records


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _records(value: object) -> list[dict[str, Any]]:
    return [_mapping(row) for row in value] if isinstance(value, list) else []
