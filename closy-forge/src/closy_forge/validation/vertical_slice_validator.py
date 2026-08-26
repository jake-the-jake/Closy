from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.binding.binary_format import read_binding
from closy_forge.binding.reconstruct import reconstruct_vertices, reconstruction_error
from closy_forge.geometry.glb_io import audit_glb, read_glb_meshset
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes, sha256_file, topology_hash
from closy_forge.package_io.writer import (
    EXCLUDED_FROM_CANONICAL_INVENTORY,
    canonical_package_digest,
    collect_inventory,
)
from closy_forge.raster import decode_png_rgba
from closy_forge.simulation.material_physics import (
    FabricDescriptorError,
    validate_fabric_descriptor,
)
from closy_forge.validation.issues import Severity, ValidationIssue

PRESET_IDS = {
    "material.lightweight_knit_d0_v1",
    "material.cotton_jersey_d0_v1",
    "material.heavy_jersey_d0_v1",
    "material.lightweight_woven_d0_v1",
}


def require_files(
    package_dir: Path,
    expected_files: set[str],
    issues: list[ValidationIssue],
    *,
    family_code: str,
) -> None:
    for relpath in sorted(expected_files):
        if not (package_dir / relpath).is_file():
            issues.append(
                issue(
                    f"{family_code}_file_missing",
                    "fatal",
                    relpath,
                    f"Required {family_code.replace('_', '-')} package artifact is missing.",
                    family_code,
                )
            )


def validate_material_selection(
    presets: dict[str, Any],
    selection: dict[str, Any],
    issues: list[ValidationIssue],
    *,
    family_code: str,
    expected_preset_id: str = "material.cotton_jersey_d0_v1",
) -> None:
    descriptors = presets.get("presets", [])
    try:
        for descriptor in descriptors:
            validate_fabric_descriptor(descriptor)
    except FabricDescriptorError as exc:
        issues.append(
            issue(
                f"{family_code}_material_descriptor_invalid",
                "fatal",
                "simulation/material_presets.json",
                str(exc),
                family_code,
            )
        )
    if (
        {str(item.get("presetId")) for item in descriptors} != PRESET_IDS
        or presets.get("integrity", {}).get("registryHash")
        != hash_blank_integrity(presets, "registryHash")
        or selection.get("integrity", {}).get("selectionHash")
        != hash_blank_integrity(selection, "selectionHash")
        or selection.get("selection", {}).get("selectedPresetId") != expected_preset_id
    ):
        issues.append(
            issue(
                f"{family_code}_material_selection_invalid",
                "fatal",
                "simulation/material_selection.json",
                "Preset registry/selection must be intact and select the expected authored preset.",
                family_code,
            )
        )


def validate_geometry_binding(
    package_dir: Path,
    binding_manifest: dict[str, Any],
    issues: list[ValidationIssue],
    *,
    family_code: str,
) -> None:
    try:
        sim_path = package_dir / "simulation/simulation_mesh.glb"
        render_path = package_dir / "render/fallback.glb"
        fallback_path = package_dir / "render/simulation_fallback.glb"
        for path in (sim_path, render_path, fallback_path):
            audit = audit_glb(path)
            if audit.get("validGlb20") is not True or audit.get("hasVec4Tangents") is not True:
                raise ValueError("conventional_glb_audit_failed")
        simulation = read_glb_meshset(sim_path)
        render = read_glb_meshset(render_path)
        fallback = read_glb_meshset(fallback_path)
        binding = read_binding(package_dir / "binding/sim_to_render.bin")
        if any(
            record.barycentric_u < -1e-7
            or record.barycentric_v < -1e-7
            or record.barycentric_u + record.barycentric_v > 1.0000001
            or record.panel_table_index >= binding.panel_count
            for record in binding.records
        ):
            raise ValueError("binding_record_outside_triangle_or_panel_table")
        reconstructed = reconstruct_vertices(simulation, binding)
        maximum, rms = reconstruction_error(render, reconstructed)
        if (
            topology_hash(simulation) != binding.simulation_topology_hash
            or topology_hash(render) != binding.render_topology_hash
            or binding_manifest.get("authority") != "binding/sim_to_render.bin"
            or binding_manifest.get("fallbackUsesDenseBinding") is not False
            or maximum > 1e-6
            or rms > 1e-6
            or topology_hash(fallback) != topology_hash(simulation)
            or fallback.vertex_count != simulation.vertex_count
            or render.vertex_count <= simulation.vertex_count
        ):
            raise ValueError("persisted_binding_or_fallback_mismatch")
    except Exception as exc:
        issues.append(
            issue(
                f"{family_code}_binding_validation_failed",
                "fatal",
                "binding/sim_to_render.bin",
                str(exc),
                family_code,
            )
        )


def validate_appearance(
    package_dir: Path,
    fidelity: dict[str, Any],
    texture: dict[str, Any],
    issues: list[ValidationIssue],
    *,
    acceptance_key: str,
    family_code: str,
) -> None:
    paths = [
        "source/public_fixture/front.png",
        "source/public_fixture/back.png",
        "reports/fidelity/rendered_front.png",
        "reports/fidelity/rendered_back.png",
        "textures/atlas/base_color.png",
        "textures/atlas/normal.png",
        "textures/atlas/roughness.png",
        "textures/atlas/occlusion.png",
    ]
    try:
        decoded = [decode_png_rgba((package_dir / path).read_bytes()) for path in paths]
        if any(item.width <= 0 or item.height <= 0 or not any(item.rgba[3::4]) for item in decoded):
            raise ValueError("blank_or_invalid_decoded_png")
        if (
            fidelity.get("decodedPixelComparisonRun") is not True
            or fidelity.get(acceptance_key) is not True
            or len(fidelity.get("viewComparisons", [])) != 2
            or not all(
                view.get("accepted") is True
                and int(view.get("metrics", {}).get("sourceForegroundPixels", 0)) > 0
                and int(view.get("metrics", {}).get("renderForegroundPixels", 0)) > 0
                for view in fidelity.get("viewComparisons", [])
            )
            or texture.get("decodedPbrMapsPersisted") is not True
            or len(texture.get("maps", [])) != 4
        ):
            raise ValueError("decoded_appearance_evidence_not_accepted")
    except Exception as exc:
        issues.append(
            issue(
                f"{family_code}_appearance_validation_failed",
                "fatal",
                "reports/fidelity/source_render_fidelity.json",
                str(exc),
                family_code,
            )
        )


def validate_inventory(
    package_dir: Path,
    manifest: dict[str, Any],
    issues: list[ValidationIssue],
    *,
    family_code: str,
) -> None:
    actual = collect_inventory(package_dir, exclude=EXCLUDED_FROM_CANONICAL_INVENTORY)
    declared = manifest.get("inventory", [])
    actual_map = {str(item["path"]): item for item in actual}
    declared_map = {str(item.get("path")): item for item in declared if isinstance(item, dict)}
    if set(actual_map) != set(declared_map):
        issues.append(
            issue(
                f"{family_code}_inventory_file_set_mismatch",
                "fatal",
                "manifest.json",
                "Manifest inventory does not exactly match persisted canonical files.",
                family_code,
            )
        )
        return
    for relpath, actual_entry in actual_map.items():
        declared_entry = declared_map[relpath]
        if (
            declared_entry.get("sha256") != actual_entry["sha256"]
            or declared_entry.get("byteSize") != actual_entry["byteSize"]
            or sha256_file(package_dir / relpath) != actual_entry["sha256"]
        ):
            issues.append(
                issue(
                    f"{family_code}_inventory_hash_mismatch",
                    "fatal",
                    relpath,
                    "Persisted bytes do not match manifest inventory hash/size.",
                    family_code,
                )
            )
    if manifest.get("packageDigest") != canonical_package_digest(actual):
        issues.append(
            issue(
                f"{family_code}_package_digest_mismatch",
                "fatal",
                "manifest.json",
                "Canonical package digest does not match inventoried bytes.",
                family_code,
            )
        )


def hash_blank_integrity(report: dict[str, Any], field: str) -> str:
    payload = deepcopy(report)
    payload["integrity"][field] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def issue(
    code: str,
    severity: Severity,
    path: str,
    message: str,
    family_code: str,
) -> ValidationIssue:
    return ValidationIssue(
        code,
        severity,
        path,
        message,
        f"Regenerate the {family_code.replace('_', '-')} fixture from canonical Forge inputs.",
    )


def report(issues: list[ValidationIssue]) -> dict[str, Any]:
    counts = {
        severity: sum(item.severity == severity for item in issues)
        for severity in ("info", "warning", "error", "fatal")
    }
    return {
        "schemaVersion": 1,
        "status": "failed" if counts["error"] or counts["fatal"] else "passed",
        "counts": counts,
        "issues": [item.to_json() for item in issues],
    }
