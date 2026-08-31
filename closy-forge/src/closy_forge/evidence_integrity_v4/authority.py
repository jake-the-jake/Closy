from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from closy_forge.binding.binary_format import read_binding
from closy_forge.fitting.exact_d0_candidate import inventory_digest
from closy_forge.geometry.glb_io import audit_glb, read_glb_meshset
from closy_forge.package_io.canonical_json import read_json
from closy_forge.package_io.hashing import geometry_content_hash, sha256_file, topology_hash
from closy_forge.package_io.paths import validate_package_relpath


class AuthorityAuditError(ValueError):
    pass


def audit_candidate_package(package: Path) -> dict[str, Any]:
    """Reopen and semantically authenticate the exact D0 candidate package."""

    root = package.resolve(strict=True)
    manifest = _object(root / "candidate_manifest.json")
    inventory = manifest.get("inventory")
    if not isinstance(inventory, list) or not inventory:
        raise AuthorityAuditError("candidate_inventory_invalid")
    opened: list[dict[str, Any]] = []
    declared_paths: list[str] = []
    for raw in inventory:
        if not isinstance(raw, dict):
            raise AuthorityAuditError("candidate_inventory_invalid")
        relative = raw.get("path")
        if not isinstance(relative, str):
            raise AuthorityAuditError("candidate_inventory_path_invalid")
        try:
            validate_package_relpath(relative)
        except ValueError as error:
            raise AuthorityAuditError("candidate_inventory_path_invalid") from error
        if relative in declared_paths:
            raise AuthorityAuditError("candidate_inventory_duplicate")
        path = root / relative
        if not path.is_file():
            raise AuthorityAuditError(f"candidate_inventory_file_missing:{relative}")
        observed_hash = sha256_file(path)
        observed_size = path.stat().st_size
        if raw.get("sha256") != observed_hash:
            raise AuthorityAuditError(f"candidate_inventory_hash_mismatch:{relative}")
        if raw.get("byteLength") != observed_size:
            raise AuthorityAuditError(f"candidate_inventory_size_mismatch:{relative}")
        declared_paths.append(relative)
        opened.append({"path": relative, "byteLength": observed_size, "sha256": observed_hash})
    if declared_paths != sorted(declared_paths):
        raise AuthorityAuditError("candidate_inventory_order_invalid")
    if inventory_digest(opened) != manifest.get("packageDigest"):
        raise AuthorityAuditError("candidate_package_digest_mismatch")
    actual_files = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "candidate_manifest.json"
    )
    if actual_files != declared_paths:
        raise AuthorityAuditError("candidate_inventory_exact_set_mismatch")

    pattern = _object(root / "pattern/pattern.json")
    constraints = _object(root / "simulation/constraints.json")
    topology = _object(root / "simulation/topology_manifest.json")
    binding_manifest = _object(root / "binding/binding_manifest.json")
    binding = read_binding(root / "binding/sim_to_render.bin")
    material = _object(root / "textures/bitmap_pbr_report.json")
    rest = read_glb_meshset(root / "simulation/rest_mesh.glb")
    settled = read_glb_meshset(root / "simulation/settled_mesh.glb")
    fallback_path = root / str(manifest.get("fallbackPath"))
    fallback = read_glb_meshset(fallback_path)
    fallback_audit = audit_glb(fallback_path)

    identity = _mapping(manifest.get("identityGraph"), "candidate_identity_graph_invalid")
    if sha256_file(root / "pattern/pattern.json") != identity.get("patternHash"):
        raise AuthorityAuditError("candidate_pattern_authority_mismatch")
    if topology_hash(rest) != identity.get("simulationTopologyHash"):
        raise AuthorityAuditError("candidate_simulation_topology_mismatch")
    if geometry_content_hash(settled) != identity.get("simulationContentHash"):
        raise AuthorityAuditError("candidate_simulation_content_mismatch")
    if topology_hash(fallback) != identity.get("renderTopologyHash"):
        raise AuthorityAuditError("candidate_render_topology_mismatch")
    if geometry_content_hash(fallback) != identity.get("renderContentHash"):
        raise AuthorityAuditError("candidate_render_content_mismatch")
    if binding.simulation_topology_hash != identity.get("simulationTopologyHash"):
        raise AuthorityAuditError("candidate_binding_simulation_topology_mismatch")
    if binding.render_topology_hash != identity.get("renderTopologyHash"):
        raise AuthorityAuditError("candidate_binding_render_topology_mismatch")
    if binding_manifest.get("recordCount") != len(binding.records):
        raise AuthorityAuditError("candidate_binding_record_count_mismatch")
    if constraints.get("auditSummary", {}).get("status") != "pass":
        raise AuthorityAuditError("candidate_seam_opening_graph_invalid")
    if not constraints.get("seams") or not constraints.get("openings"):
        raise AuthorityAuditError("candidate_seam_opening_graph_empty")
    if not pattern.get("panels") or topology.get("panelCount") != len(pattern["panels"]):
        raise AuthorityAuditError("candidate_pattern_topology_semantics_mismatch")
    _audit_material_maps(root, material)
    bounds = _fallback_bounds(fallback)
    panel_ids = sorted({mesh.panel_id for mesh in fallback.meshes})
    material_ids = sorted({mesh.material_id for mesh in fallback.meshes})
    if not panel_ids or any(not panel_id.startswith("panel.") for panel_id in panel_ids):
        raise AuthorityAuditError("candidate_fallback_not_garment")
    if any("avatar" in panel_id or "body" in panel_id for panel_id in panel_ids):
        raise AuthorityAuditError("candidate_fallback_is_avatar_body")
    if material_ids != ["material.cotton_jersey_reference_v1"]:
        raise AuthorityAuditError("candidate_fallback_material_slot_invalid")
    if bounds["heightMeters"] <= 0.2 or bounds["heightMeters"] > 2.5:
        raise AuthorityAuditError("candidate_fallback_bounds_invalid")
    depth = float(bounds["maximum"][2]) - float(bounds["minimum"][2])
    if (
        float(bounds["minimum"][1]) < 0.0
        or float(bounds["maximum"][1]) > 2.5
        or bounds["heightMeters"] <= depth * 1.5
    ):
        raise AuthorityAuditError("candidate_fallback_coordinate_convention_invalid")
    if abs(bounds["center"][0]) > 1.5 or abs(bounds["center"][2]) > 1.5:
        raise AuthorityAuditError("candidate_fallback_out_of_frame")
    if fallback_audit["meshCount"] != len(fallback.meshes):
        raise AuthorityAuditError("candidate_fallback_mesh_inventory_mismatch")

    return {
        "auditVersion": "closy.d0_candidate.package_authority.v4",
        "status": "pass",
        "candidateId": manifest.get("candidateId"),
        "packageDigest": manifest.get("packageDigest"),
        "inventory": opened,
        "inventoryDigestRecomputedFromOpenedBytes": True,
        "semanticAuthorities": {
            "patternOpened": True,
            "seamOpeningGraphOpened": True,
            "simulationTopologyOpened": True,
            "renderTopologyOpened": True,
            "bindingOpened": True,
            "materialsOpened": True,
            "fallbackGlbParsed": True,
            "fallbackIsGarmentNotBody": True,
            "coordinateConvention": {"up": "+Y", "front": "+Z"},
        },
        "fallback": {
            "path": manifest.get("fallbackPath"),
            "sha256": sha256_file(fallback_path),
            "panelIds": panel_ids,
            "materialIds": material_ids,
            "bounds": bounds,
            "glbAudit": fallback_audit,
        },
        "identities": {
            "patternHash": identity.get("patternHash"),
            "simulationTopologyHash": topology_hash(rest),
            "simulationContentHash": geometry_content_hash(settled),
            "renderTopologyHash": topology_hash(fallback),
            "renderContentHash": geometry_content_hash(fallback),
            "bindingHash": sha256_file(root / "binding/sim_to_render.bin"),
            "materialPayloadHash": sha256_file(root / "textures/bitmap_pbr_report.json"),
        },
        "runtimePolicy": {
            "runtimeV1RemainsSelected": True,
            "zeroOneRequiredForCoreAuthority": False,
            "executionAdmission": "conditional_when_authenticated_payload_supplied",
        },
    }


def validate_execution_authority(
    supplied: Mapping[str, Any] | None,
    *,
    trusted: Mapping[str, Any],
    candidate: Mapping[str, Any],
    seen_attestation_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Validate optional execution without making it a core package dependency."""

    if supplied is None:
        return {
            "status": "not_run",
            "attemptState": "dependency_blocked",
            "reason": "authenticated_execution_not_supplied",
            "corePackageAuthorityValid": True,
        }
    fields = (
        "platform",
        "architecture",
        "zeroOneCommit",
        "processorContractSha256",
        "executableSha256",
        "requestInventorySha256",
        "outputInventorySha256",
        "executionAttestationSha256",
        "candidatePackageDigest",
    )
    if any(field not in supplied for field in fields):
        raise AuthorityAuditError("execution_authority_field_missing")
    for field in (
        "platform",
        "architecture",
        "zeroOneCommit",
        "processorContractSha256",
        "executableSha256",
    ):
        if supplied[field] != trusted.get(field):
            raise AuthorityAuditError(f"execution_authority_mismatch:{field}")
    if supplied["candidatePackageDigest"] != candidate.get("packageDigest"):
        raise AuthorityAuditError("execution_authority_candidate_mismatch")
    for field in (
        "processorContractSha256",
        "executableSha256",
        "requestInventorySha256",
        "outputInventorySha256",
        "executionAttestationSha256",
        "candidatePackageDigest",
    ):
        if not _sha(supplied[field]):
            raise AuthorityAuditError(f"execution_authority_digest_invalid:{field}")
    commit = supplied["zeroOneCommit"]
    if not isinstance(commit, str) or len(commit) != 40 or not _hex(commit):
        raise AuthorityAuditError("execution_authority_commit_invalid")
    attestation = str(supplied["executionAttestationSha256"])
    if seen_attestation_ids is not None:
        if attestation in seen_attestation_ids:
            raise AuthorityAuditError("execution_authority_duplicate")
        seen_attestation_ids.add(attestation)
    return {
        "status": "pass",
        "attemptState": "attempted_pass",
        "authenticatedExternalAuthority": True,
        "platform": supplied["platform"],
        "architecture": supplied["architecture"],
        "zeroOneCommit": commit,
        "processorContractSha256": supplied["processorContractSha256"],
        "executableSha256": supplied["executableSha256"],
        "requestInventorySha256": supplied["requestInventorySha256"],
        "outputInventorySha256": supplied["outputInventorySha256"],
        "executionAttestationSha256": attestation,
        "candidatePackageDigest": supplied["candidatePackageDigest"],
    }


def _audit_material_maps(root: Path, report: Mapping[str, Any]) -> None:
    maps = _mapping(report.get("atlas"), "candidate_material_atlas_invalid")
    del maps  # Atlas semantics are validated by the raster evaluator.
    records = report.get("maps")
    if not isinstance(records, list):
        raise AuthorityAuditError("candidate_material_map_inventory_invalid")
    required = {"baseColor", "normal", "roughness", "occlusion", "sourceContribution"}
    observed: set[str] = set()
    for raw in records:
        if not isinstance(raw, dict):
            raise AuthorityAuditError("candidate_material_map_inventory_invalid")
        map_id = raw.get("mapId")
        relative = raw.get("path")
        if not isinstance(map_id, str) or not isinstance(relative, str):
            raise AuthorityAuditError("candidate_material_map_inventory_invalid")
        path = root / relative
        if not path.is_file() or sha256_file(path) != raw.get("sha256"):
            raise AuthorityAuditError(f"candidate_material_map_mismatch:{map_id}")
        observed.add(map_id)
    if not required <= observed:
        raise AuthorityAuditError("candidate_material_slot_missing")
    pbr = _mapping(report.get("pbr"), "candidate_pbr_authority_invalid")
    if pbr.get("normalRoughnessAoPhysicalAccuracy") != "not_measured":
        raise AuthorityAuditError("candidate_physical_pbr_overclaim")


def _fallback_bounds(meshset: Any) -> dict[str, Any]:
    vertices = [vertex for mesh in meshset.meshes for vertex in mesh.vertices]
    if not vertices or any(
        not all(math.isfinite(value) for value in vertex) for vertex in vertices
    ):
        raise AuthorityAuditError("candidate_fallback_nonfinite_or_empty")
    minimum = tuple(min(vertex[axis] for vertex in vertices) for axis in range(3))
    maximum = tuple(max(vertex[axis] for vertex in vertices) for axis in range(3))
    center = tuple((minimum[axis] + maximum[axis]) * 0.5 for axis in range(3))
    return {
        "minimum": list(minimum),
        "maximum": list(maximum),
        "center": list(center),
        "heightMeters": maximum[1] - minimum[1],
    }


def _object(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise AuthorityAuditError(f"authority_object_required:{path.name}")
    return value


def _mapping(value: Any, code: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise AuthorityAuditError(code)
    return value


def _sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and _hex(value)


def _hex(value: str) -> bool:
    return all(character in "0123456789abcdef" for character in value)
