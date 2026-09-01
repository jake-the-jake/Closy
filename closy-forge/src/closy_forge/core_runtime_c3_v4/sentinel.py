from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.appearance_correction_v3.prediction import validate_frozen_candidate
from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file

SENTINEL_VERSION = "closy.d0_core_runtime_c3.sentinel.v4"
PREDICTION_ROOT = Path("docs/evidence/d0_texture_rerender_correction_v3/predictions")
CANDIDATE_RELATIVE = PREDICTION_ROOT / "candidate_package"
RUNTIME_RELATIVE = PREDICTION_ROOT / "candidate_runtime.closyruntime"
EXPECTED_CANDIDATE_ID = "candidate.d0_texture_rerender_v3.49161d8adafb514e5a04b1a9"
EXPECTED_PACKAGE_DIGEST = "c338762915d390a22e879f588e0f01a4b6ed586b9ff045eb0a039888ace8223b"
UNIT_F_EXACT_HEAD = "ba54b17a0aef7518d9acac30c6b7ec6564a38d87"
UNIT_G_EXACT_HEAD = "069707bbd0bfc95eabbc5a3b3045e349d4c0b121"


def build_sentinel(root: Path) -> dict[str, Any]:
    candidate = root / CANDIDATE_RELATIVE
    validation = validate_frozen_candidate(candidate)
    manifest = _object(read_json(candidate / "candidate_manifest.json"))
    invalidation = _object(read_json(root / PREDICTION_ROOT / "identity_invalidation.json"))
    runtime = _object(read_json(root / RUNTIME_RELATIVE / "manifest.json"))
    qualification = _object(read_json(root / PREDICTION_ROOT / "runtime_qualification.json"))
    if validation.get("status") != "pass":
        raise ValueError("h0_unit_f_candidate_not_structurally_valid")
    if manifest.get("candidateId") != EXPECTED_CANDIDATE_ID:
        raise ValueError("h0_unit_f_candidate_identity_mismatch")
    if manifest.get("packageDigest") != EXPECTED_PACKAGE_DIGEST:
        raise ValueError("h0_unit_f_package_digest_mismatch")
    if invalidation.get("allRetainedGeometryPhysicsByteIdentical") is not True:
        raise ValueError("h0_pr43_descendant_bytes_not_proven")
    retained = {
        str(record["path"]): record
        for record in invalidation.get("retainedGeometryPhysics", [])
        if isinstance(record, dict) and isinstance(record.get("path"), str)
    }
    required_retained = {
        "pattern/pattern.json",
        "simulation/topology_manifest.json",
        "simulation/seam_audit.json",
        "simulation/rest_mesh.glb",
        "simulation/settled_mesh.glb",
        "render/render_mesh.glb",
        "binding/sim_to_render.bin",
        "binding/binding_manifest.json",
    }
    if not required_retained.issubset(retained) or not all(
        retained[path].get("byteIdentical") is True for path in required_retained
    ):
        raise ValueError("h0_pr43_required_descendant_proof_incomplete")
    inventory = manifest.get("inventory")
    if not isinstance(inventory, list):
        raise ValueError("h0_candidate_inventory_missing")
    inventory_by_path = {
        str(record["path"]): record for record in inventory if isinstance(record, dict)
    }
    identities = {
        "sourceRoles": _many(
            root,
            CANDIDATE_RELATIVE,
            inventory_by_path,
            ("source/public_fixture/front.png", "source/public_fixture/back.png"),
        ),
        "prediction": _one(root, PREDICTION_ROOT / "prediction_summary.json"),
        "pattern": _candidate_one(root, inventory_by_path, "pattern/pattern.json"),
        "seamGraph": _candidate_one(root, inventory_by_path, "simulation/constraints.json"),
        "seamAudit": _candidate_one(root, inventory_by_path, "simulation/seam_audit.json"),
        "simulationTopology": _candidate_one(
            root, inventory_by_path, "simulation/topology_manifest.json"
        ),
        "simulationRest": _candidate_one(root, inventory_by_path, "simulation/rest_mesh.glb"),
        "simulationSettled": _candidate_one(root, inventory_by_path, "simulation/settled_mesh.glb"),
        "renderTopology": _candidate_one(root, inventory_by_path, "render/render_mesh.glb"),
        "binding": _candidate_one(root, inventory_by_path, "binding/sim_to_render.bin"),
        "bindingManifest": _candidate_one(root, inventory_by_path, "binding/binding_manifest.json"),
        "appearance": _candidate_one(root, inventory_by_path, "textures/bitmap_pbr_report.json"),
        "candidateManifest": _one(root, CANDIDATE_RELATIVE / "candidate_manifest.json"),
        "fallback": _one(root, RUNTIME_RELATIVE / "assets/conventional_fallback.glb"),
        "runtimeDescriptor": _one(root, RUNTIME_RELATIVE / "manifest.json"),
    }
    sentinel: dict[str, Any] = {
        "schemaVersion": 1,
        "sentinelVersion": SENTINEL_VERSION,
        "resolutionRule": (
            "unit_f_if_structurally_valid_and_pr43_geometry_topology_binding_"
            "descendant_else_pr43"
        ),
        "resolutionOutcome": "unit_f_exact_fixture_candidate",
        "unitGCohortEligible": False,
        "unitFExactHead": UNIT_F_EXACT_HEAD,
        "unitGParentHead": UNIT_G_EXACT_HEAD,
        "candidateId": manifest["candidateId"],
        "candidatePackageDigest": manifest["packageDigest"],
        "candidateManifestHash": _object(manifest.get("integrity")).get("manifestHash"),
        "runtimePackageDigest": runtime.get("packageDigest"),
        "runtimeQualificationDigest": qualification.get("runtimePackageDigest"),
        "runtimeV1RemainsSelected": qualification.get("runtimeV1SelectionChanged") is False,
        "pr43DescendantProof": {
            "allRetainedGeometryPhysicsByteIdentical": True,
            "invalidationReport": _one(root, PREDICTION_ROOT / "identity_invalidation.json"),
            "requiredRetainedPaths": sorted(required_retained),
        },
        "identities": identities,
        "integrity": {"sentinelManifestDigest": ""},
    }
    _rehash(sentinel, "sentinelManifestDigest")
    return sentinel


def validate_sentinel(root: Path, sentinel: dict[str, Any]) -> None:
    reopened = build_sentinel(root)
    if reopened != sentinel:
        raise ValueError("h0_sentinel_reopen_mismatch")


def _candidate_one(
    root: Path, inventory: dict[str, dict[str, Any]], relative: str
) -> dict[str, Any]:
    record = inventory.get(relative)
    if record is None:
        raise ValueError(f"h0_candidate_inventory_path_missing:{relative}")
    path = root / CANDIDATE_RELATIVE / relative
    actual = sha256_file(path)
    if actual != record.get("sha256"):
        raise ValueError(f"h0_candidate_inventory_hash_mismatch:{relative}")
    return {"path": (CANDIDATE_RELATIVE / relative).as_posix(), "sha256": actual}


def _one(root: Path, relative: Path) -> dict[str, Any]:
    return {"path": relative.as_posix(), "sha256": sha256_file(root / relative)}


def _many(
    root: Path,
    prefix: Path,
    inventory: dict[str, dict[str, Any]],
    paths: tuple[str, ...],
) -> list[dict[str, Any]]:
    return [_candidate_one(root, inventory, path) for path in paths]


def _rehash(payload: dict[str, Any], field: str) -> None:
    copied = deepcopy(payload)
    _object(copied["integrity"])[field] = ""
    _object(payload["integrity"])[field] = sha256_bytes(canonical_dumps(copied).encode("utf-8"))


def _object(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
