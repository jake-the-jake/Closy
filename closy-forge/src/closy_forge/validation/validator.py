from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from closy_forge.binding.binary_format import read_binding
from closy_forge.binding.reconstruct import reconstruct_vertices, reconstruction_error
from closy_forge.contracts.avatar import REQUIRED_BODY_REGIONS, REQUIRED_LANDMARKS
from closy_forge.contracts.common import COORDINATE_CONVENTION
from closy_forge.contracts.semantic import REQUIRED_OPENINGS, REQUIRED_PANELS, REQUIRED_SEAMS
from closy_forge.geometry.glb_io import audit_glb
from closy_forge.geometry.mesh_model import Mesh, MeshSet, Tri, Vec2, Vec3, finite_mesh
from closy_forge.geometry.triangulation import validate_panel_boundary
from closy_forge.package_io.canonical_json import read_json
from closy_forge.package_io.hashing import geometry_content_hash, sha256_file, topology_hash
from closy_forge.package_io.paths import validate_package_relpath
from closy_forge.validation.issues import Severity, ValidationIssue

EXPECTED_FILES = [
    "manifest.json",
    "provenance.json",
    "avatar/avatar_contract.json",
    "avatar/reference_avatar.glb",
    "avatar/collision.glb",
    "avatar/body_regions.json",
    "semantic/garment_graph.json",
    "semantic/confidence.json",
    "pattern/pattern.json",
    "pattern/panels.svg",
    "simulation/simulation_mesh.glb",
    "simulation/mesh_manifest.json",
    "simulation/constraints.json",
    "simulation/material_physics.json",
    "render/fallback.glb",
    "render/mesh_manifest.json",
    "render/materials.json",
    "binding/sim_to_render.bin",
    "binding/binding_manifest.json",
    "reports/avatar_quality.json",
    "reports/semantic_quality.json",
    "reports/pattern_quality.json",
    "reports/simulation_quality.json",
    "reports/render_quality.json",
    "reports/binding_quality.json",
    "reports/package_validation.json",
    "reports/summary.json",
    "reports/summary.md",
]


def validate_package(package_dir: Path) -> dict[str, Any]:
    issues: list[ValidationIssue] = []
    if package_dir.suffix != ".closygarment":
        issues.append(
            _issue("package_suffix_invalid", "fatal", ".", "Package must end with .closygarment.")
        )
        return _report(issues)
    manifest_path = package_dir / "manifest.json"
    if not manifest_path.exists():
        issues.append(
            _issue("manifest_missing", "fatal", "manifest.json", "Missing top-level manifest.")
        )
        return _report(issues)
    try:
        manifest = read_json(manifest_path)
    except Exception as exc:
        issues.append(_issue("manifest_unreadable", "fatal", "manifest.json", str(exc)))
        return _report(issues)
    _validate_required_files(package_dir, issues)
    if manifest.get("schemaVersion") != 1:
        issues.append(
            _issue(
                "unsupported_schema_version",
                "fatal",
                "manifest.json",
                "Only schemaVersion 1 is supported.",
            )
        )
    if manifest.get("packageKind") != "closy.garment":
        issues.append(
            _issue(
                "package_kind_invalid",
                "fatal",
                "manifest.json",
                "packageKind must be closy.garment.",
            )
        )
    if manifest.get("garmentClass") != "tshirt":
        issues.append(
            _issue(
                "unsupported_garment_class",
                "fatal",
                "manifest.json",
                "Implementation 01 only supports tshirt.",
            )
        )
    if manifest.get("units") != "metres":
        issues.append(
            _issue(
                "coordinate_units_invalid",
                "fatal",
                "manifest.json",
                "Forge packages must use metres.",
            )
        )
    if manifest.get("coordinateConvention", {}).get("id") != COORDINATE_CONVENTION["id"]:
        issues.append(
            _issue(
                "coordinate_convention_invalid",
                "fatal",
                "manifest.json",
                "Unexpected coordinate convention.",
            )
        )

    inventory = manifest.get("inventory", [])
    if not isinstance(inventory, list):
        issues.append(
            _issue("inventory_invalid", "fatal", "manifest.json", "inventory must be a list.")
        )
        inventory = []
    inventory_paths: set[str] = set()
    for entry in inventory:
        if not isinstance(entry, dict):
            continue
        rel = str(entry.get("path", ""))
        if rel == "manifest.json":
            issues.append(
                _issue(
                    "manifest_self_hash_cycle",
                    "fatal",
                    rel,
                    "manifest.json must not be inventoried.",
                )
            )
        if rel in inventory_paths:
            issues.append(
                _issue("duplicate_inventory_path", "fatal", rel, "Inventory paths must be unique.")
            )
        inventory_paths.add(rel)
        try:
            validate_package_relpath(rel)
        except ValueError:
            issues.append(
                _issue(
                    "unsafe_package_path",
                    "fatal",
                    rel or "manifest.json",
                    "Inventory path is unsafe.",
                )
            )
            continue
        file_path = package_dir / rel
        if file_path.is_symlink():
            try:
                file_path.resolve().relative_to(package_dir.resolve())
            except ValueError:
                issues.append(
                    _issue("escaping_symlink", "fatal", rel, "Symlink escapes package root.")
                )
        if not file_path.exists():
            issues.append(
                _issue("missing_declared_file", "fatal", rel, "Declared file is missing.")
            )
            continue
        if entry.get("byteSize") != file_path.stat().st_size:
            issues.append(
                _issue("file_size_mismatch", "fatal", rel, "Declared byte size does not match.")
            )
        if entry.get("sha256") != sha256_file(file_path):
            issues.append(
                _issue("file_hash_mismatch", "fatal", rel, "Declared SHA-256 does not match.")
            )

    _validate_avatar(package_dir, issues)
    _validate_pattern(package_dir, issues)
    _validate_meshes_and_constraints(package_dir, issues)
    _validate_glbs(package_dir, issues)
    _validate_binding(package_dir, issues)
    _validate_capabilities(manifest, issues)
    return _report(issues)


def _validate_avatar(package_dir: Path, issues: list[ValidationIssue]) -> None:
    avatar = _read_required_json(package_dir, "avatar/avatar_contract.json", issues)
    if avatar is None:
        return
    landmarks = avatar.get("landmarks", {})
    for landmark in REQUIRED_LANDMARKS:
        if landmark not in landmarks:
            issues.append(
                _issue(
                    "required_landmark_missing",
                    "fatal",
                    "avatar/avatar_contract.json",
                    "Required avatar landmark missing.",
                    landmark,
                )
            )
    regions_doc = _read_required_json(package_dir, "avatar/body_regions.json", issues)
    if regions_doc is None:
        return
    regions = regions_doc.get("regions", [])
    region_ids = {region.get("id") for region in regions}
    for region in REQUIRED_BODY_REGIONS:
        if region not in region_ids:
            issues.append(
                _issue(
                    "required_body_region_missing",
                    "fatal",
                    "avatar/body_regions.json",
                    "Required body region missing.",
                    region,
                )
            )
    if avatar.get("heightMeters") is None or not 1.70 <= float(avatar["heightMeters"]) <= 1.86:
        issues.append(
            _issue(
                "avatar_height_invalid",
                "fatal",
                "avatar/avatar_contract.json",
                "Reference avatar height must be approximately human scale.",
            )
        )


def _validate_pattern(package_dir: Path, issues: list[ValidationIssue]) -> None:
    pattern = _read_required_json(package_dir, "pattern/pattern.json", issues)
    if pattern is None:
        return
    panel_ids = [panel["id"] for panel in pattern.get("panels", [])]
    if len(panel_ids) != len(set(panel_ids)):
        issues.append(
            _issue(
                "duplicate_panel_id", "fatal", "pattern/pattern.json", "Panel IDs must be unique."
            )
        )
    for required_panel_id in REQUIRED_PANELS:
        if required_panel_id not in panel_ids:
            issues.append(
                _issue(
                    "required_panel_missing",
                    "fatal",
                    "pattern/pattern.json",
                    "Required panel missing.",
                    required_panel_id,
                )
            )
    seam_ids = [seam["id"] for seam in pattern.get("seams", [])]
    if len(seam_ids) != len(set(seam_ids)):
        issues.append(
            _issue("duplicate_seam_id", "fatal", "pattern/pattern.json", "Seam IDs must be unique.")
        )
    edge_ids = {
        edge["id"] for panel in pattern.get("panels", []) for edge in panel.get("boundary", [])
    }
    for seam in pattern.get("seams", []):
        for span in seam.get("spans", []):
            if span.get("panelId") not in panel_ids or span.get("edgeId") not in edge_ids:
                issues.append(
                    _issue(
                        "dangling_seam_reference",
                        "fatal",
                        "pattern/pattern.json",
                        "Seam references unknown panel or edge.",
                        seam.get("id"),
                    )
                )
    for seam in REQUIRED_SEAMS:
        if seam not in seam_ids:
            issues.append(
                _issue(
                    "required_seam_missing",
                    "fatal",
                    "pattern/pattern.json",
                    "Required seam missing.",
                    seam,
                )
            )
    openings = {opening.get("id") for opening in pattern.get("openings", [])}
    for opening in REQUIRED_OPENINGS:
        if opening not in openings:
            issues.append(
                _issue(
                    "required_opening_missing",
                    "fatal",
                    "pattern/pattern.json",
                    "Required opening missing.",
                    opening,
                )
            )
    for panel_doc in pattern.get("panels", []):
        boundary_issues = validate_panel_boundary(panel_doc)
        for boundary_issue in boundary_issues:
            issues.append(
                _issue(
                    boundary_issue,
                    "fatal",
                    "pattern/pattern.json",
                    "Panel boundary is invalid.",
                    panel_doc.get("id"),
                )
            )
    if _contains_nonfinite(pattern):
        issues.append(
            _issue(
                "nonfinite_numeric_value",
                "fatal",
                "pattern/pattern.json",
                "NaN or Infinity is not allowed.",
            )
        )


def _validate_meshes_and_constraints(package_dir: Path, issues: list[ValidationIssue]) -> None:
    sim_manifest = _read_required_json(package_dir, "simulation/mesh_manifest.json", issues)
    render_manifest = _read_required_json(package_dir, "render/mesh_manifest.json", issues)
    constraints = _read_required_json(package_dir, "simulation/constraints.json", issues)
    if sim_manifest is None or render_manifest is None or constraints is None:
        return
    sim_mesh = _meshset_from_manifest(sim_manifest)
    render_mesh = _meshset_from_manifest(render_manifest)
    for rel, manifest, meshset in [
        ("simulation/mesh_manifest.json", sim_manifest, sim_mesh),
        ("render/mesh_manifest.json", render_manifest, render_mesh),
    ]:
        if not finite_mesh(meshset):
            issues.append(
                _issue(
                    "mesh_nonfinite_or_invalid",
                    "fatal",
                    rel,
                    "Mesh contains nonfinite data or invalid triangles.",
                )
            )
        if manifest.get("topologyHash") != topology_hash(meshset):
            issues.append(
                _issue(
                    "mesh_topology_hash_mismatch",
                    "fatal",
                    rel,
                    "Mesh topology hash does not match manifest.",
                )
            )
        if manifest.get("contentHash") != geometry_content_hash(meshset):
            issues.append(
                _issue(
                    "mesh_content_hash_mismatch",
                    "fatal",
                    rel,
                    "Mesh content hash does not match manifest.",
                )
            )
    for constraint in constraints.get("constraints", []):
        for span_key in ["spanA", "spanB"]:
            span = constraint.get(span_key, {})
            mesh_index = int(span.get("meshIndex", -1))
            vertex_index = int(span.get("vertexIndex", -1))
            if mesh_index < 0 or mesh_index >= len(sim_mesh.meshes):
                issues.append(
                    _issue(
                        "invalid_constraint_mesh_index",
                        "fatal",
                        "simulation/constraints.json",
                        "Constraint mesh index is invalid.",
                        constraint.get("id"),
                    )
                )
                continue
            if vertex_index < 0 or vertex_index >= len(sim_mesh.meshes[mesh_index].vertices):
                issues.append(
                    _issue(
                        "invalid_constraint_vertex",
                        "fatal",
                        "simulation/constraints.json",
                        "Constraint vertex index is invalid.",
                        constraint.get("id"),
                    )
                )


def _validate_glbs(package_dir: Path, issues: list[ValidationIssue]) -> None:
    for rel in [
        "avatar/reference_avatar.glb",
        "avatar/collision.glb",
        "simulation/simulation_mesh.glb",
        "render/fallback.glb",
    ]:
        try:
            audit = audit_glb(package_dir / rel)
            if audit["primitiveCount"] <= 0 or audit["triangleEstimate"] <= 0:
                issues.append(
                    _issue(
                        "glb_has_no_renderable_geometry",
                        "fatal",
                        rel,
                        "GLB must contain renderable triangles.",
                    )
                )
        except Exception as exc:
            issues.append(_issue("glb_parse_failed", "fatal", rel, str(exc)))


def _validate_binding(package_dir: Path, issues: list[ValidationIssue]) -> None:
    try:
        binding = read_binding(package_dir / "binding" / "sim_to_render.bin")
    except Exception as exc:
        issues.append(_issue("binding_invalid", "fatal", "binding/sim_to_render.bin", str(exc)))
        return
    manifest = _read_required_json(package_dir, "binding/binding_manifest.json", issues)
    sim_manifest = _read_required_json(package_dir, "simulation/mesh_manifest.json", issues)
    render_manifest = _read_required_json(package_dir, "render/mesh_manifest.json", issues)
    if manifest is None or sim_manifest is None or render_manifest is None:
        return
    if binding.simulation_topology_hash != manifest.get("simulationTopologyHash"):
        issues.append(
            _issue(
                "binding_sim_topology_hash_mismatch",
                "fatal",
                "binding/binding_manifest.json",
                "Simulation topology hash mismatch.",
            )
        )
    if binding.render_topology_hash != manifest.get("renderTopologyHash"):
        issues.append(
            _issue(
                "binding_render_topology_hash_mismatch",
                "fatal",
                "binding/binding_manifest.json",
                "Render topology hash mismatch.",
            )
        )
    for record in binding.records:
        if record.simulation_triangle_index >= binding.simulation_triangle_count:
            issues.append(
                _issue(
                    "binding_triangle_out_of_range",
                    "fatal",
                    "binding/sim_to_render.bin",
                    "Triangle index out of range.",
                )
            )
        if (
            record.barycentric_u < -1e-6
            or record.barycentric_v < -1e-6
            or record.barycentric_u + record.barycentric_v > 1.000001
        ):
            issues.append(
                _issue(
                    "binding_barycentric_invalid",
                    "fatal",
                    "binding/sim_to_render.bin",
                    "Barycentric coordinates outside tolerance.",
                )
            )
        if record.panel_table_index >= binding.panel_count:
            issues.append(
                _issue(
                    "binding_panel_index_invalid",
                    "fatal",
                    "binding/sim_to_render.bin",
                    "Panel table index out of range.",
                )
            )
    try:
        sim_mesh = _meshset_from_manifest(sim_manifest)
        render_mesh = _meshset_from_manifest(render_manifest)
        reconstructed = reconstruct_vertices(sim_mesh, binding)
        max_error, rms_error = reconstruction_error(render_mesh, reconstructed)
        if max_error > float(manifest.get("reconstructionTolerance", 1e-6)):
            issues.append(
                _issue(
                    "binding_reconstruction_error_too_high",
                    "fatal",
                    "binding/sim_to_render.bin",
                    f"Maximum reconstruction error {max_error:.8f} exceeds tolerance.",
                )
            )
        if abs(max_error - float(manifest.get("maximumReconstructionError", 0.0))) > 1e-6:
            issues.append(
                _issue(
                    "binding_reconstruction_report_mismatch",
                    "fatal",
                    "binding/binding_manifest.json",
                    "Binding maximum error report is stale.",
                )
            )
        if abs(rms_error - float(manifest.get("rmsReconstructionError", 0.0))) > 1e-6:
            issues.append(
                _issue(
                    "binding_reconstruction_report_mismatch",
                    "fatal",
                    "binding/binding_manifest.json",
                    "Binding RMS error report is stale.",
                )
            )
    except Exception as exc:
        issues.append(
            _issue("binding_reconstruction_failed", "fatal", "binding/sim_to_render.bin", str(exc))
        )


def _validate_capabilities(manifest: dict[str, Any], issues: list[ValidationIssue]) -> None:
    caps = manifest.get("capabilities", {})
    if not caps.get("actualClothSettleAvailable"):
        issues.append(
            _issue(
                "cloth_settle_not_run",
                "warning",
                "manifest.json",
                "No physical cloth-settle solver ran in Implementation 01.",
            )
        )
    if caps.get("actualClothSettleAvailable"):
        issues.append(
            _issue(
                "false_cloth_settle_capability",
                "fatal",
                "manifest.json",
                "Implementation 01 does not run cloth settle.",
            )
        )
    if caps.get("zeroOneStaticAvailable") or caps.get("zeroOneDynamicAvailable"):
        issues.append(
            _issue(
                "false_zeroone_capability",
                "fatal",
                "manifest.json",
                "ZeroOne derivatives are unavailable and optional.",
            )
        )


def _validate_required_files(package_dir: Path, issues: list[ValidationIssue]) -> None:
    for rel in EXPECTED_FILES:
        try:
            validate_package_relpath(rel)
        except ValueError:
            issues.append(
                _issue("unsafe_expected_path", "fatal", rel, "Internal expected path is invalid.")
            )
            continue
        if not (package_dir / rel).exists():
            issues.append(
                _issue("required_file_missing", "fatal", rel, "Required package file is missing.")
            )
    for path in package_dir.rglob("*"):
        if not path.is_symlink():
            continue
        rel = path.relative_to(package_dir).as_posix()
        try:
            path.resolve().relative_to(package_dir.resolve())
        except ValueError:
            issues.append(_issue("escaping_symlink", "fatal", rel, "Symlink escapes package root."))


def _read_required_json(
    package_dir: Path, rel: str, issues: list[ValidationIssue]
) -> dict[str, Any] | None:
    path = package_dir / rel
    if not path.exists():
        issues.append(
            _issue("required_file_missing", "fatal", rel, "Required JSON file is missing.")
        )
        return None
    try:
        data = read_json(path)
    except Exception as exc:
        issues.append(_issue("json_unreadable", "fatal", rel, str(exc)))
        return None
    if not isinstance(data, dict):
        issues.append(_issue("json_root_not_object", "fatal", rel, "JSON root must be an object."))
        return None
    return data


def _meshset_from_manifest(manifest: dict[str, Any]) -> MeshSet:
    meshes: list[Mesh] = []
    for mesh_doc in manifest.get("meshes", []):
        meshes.append(
            Mesh(
                name=str(mesh_doc["name"]),
                panel_id=str(mesh_doc["panelId"]),
                vertices=[_vec3(vertex) for vertex in mesh_doc["vertices"]],
                panel_uvs=[_vec2(uv) for uv in mesh_doc["panelUvs"]],
                triangles=[_tri(triangle) for triangle in mesh_doc["triangles"]],
                material_id=str(mesh_doc.get("materialId", "material.cotton_jersey_reference_v1")),
            )
        )
    return MeshSet(meshes)


def _vec3(value: Any) -> Vec3:
    if not isinstance(value, list | tuple) or len(value) != 3:
        raise ValueError("expected Vec3")
    return (float(value[0]), float(value[1]), float(value[2]))


def _vec2(value: Any) -> Vec2:
    if not isinstance(value, list | tuple) or len(value) != 2:
        raise ValueError("expected Vec2")
    return (float(value[0]), float(value[1]))


def _tri(value: Any) -> Tri:
    if not isinstance(value, list | tuple) or len(value) != 3:
        raise ValueError("expected triangle")
    return (int(value[0]), int(value[1]), int(value[2]))


def _contains_nonfinite(value: Any) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, dict):
        return any(_contains_nonfinite(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_nonfinite(v) for v in value)
    return False


def _issue(
    code: str,
    severity: Severity,
    path: str,
    message: str,
    entity_id: str | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        code,
        severity,
        path,
        message,
        "Inspect and regenerate the package from canonical Forge inputs.",
        entity_id,
    )


def _report(issues: list[ValidationIssue]) -> dict[str, Any]:
    counts = {
        "info": sum(issue.severity == "info" for issue in issues),
        "warning": sum(issue.severity == "warning" for issue in issues),
        "error": sum(issue.severity == "error" for issue in issues),
        "fatal": sum(issue.severity == "fatal" for issue in issues),
    }
    return {
        "schemaVersion": 1,
        "status": "failed" if counts["error"] or counts["fatal"] else "passed",
        "counts": counts,
        "issues": [issue.to_json() for issue in issues],
    }
