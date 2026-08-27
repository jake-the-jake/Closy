from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from closy_forge.binding.binary_format import BindingFile, write_binding
from closy_forge.contracts.common import COORDINATE_CONVENTION, FIXED_TIMESTAMP
from closy_forge.garments.vertical_slice.appearance import AppearanceBundle
from closy_forge.geometry.glb_io import write_indexed_glb
from closy_forge.geometry.mesh_model import MeshSet, mesh_bounds
from closy_forge.package_io.canonical_json import write_canonical_json, write_canonical_text
from closy_forge.package_io.hashing import geometry_content_hash, topology_hash


@dataclass(frozen=True)
class ContractWriteSpec:
    package_version: str
    simulation_node_name: str
    dense_render_node_name: str
    independent_fallback_node_name: str
    fit_report_path: str
    quality_report_path: str
    normalize_signed_zero: bool = False
    selected_material_preset_id: str = "material.cotton_jersey_d0_v1"


@dataclass(frozen=True)
class SummarySpec:
    completion_key: str
    completion_label: str


def write_vertical_slice_contracts(
    *,
    spec: ContractWriteSpec,
    package_dir: Path,
    pattern: dict[str, Any],
    semantic: dict[str, Any],
    rest_mesh: MeshSet,
    simulation_mesh: MeshSet,
    render_mesh: MeshSet,
    edge_maps: dict[str, dict[str, list[int]]],
    constraints: dict[str, Any],
    binding: BindingFile,
    binding_manifest: dict[str, Any],
    avatar_mesh: MeshSet,
    collision_mesh: MeshSet,
    avatar: dict[str, Any],
    material_registry: dict[str, Any],
    material_selection: dict[str, Any],
    material_physics: dict[str, Any],
    motion_report: dict[str, Any],
    motion_states: dict[str, dict[str, Any]],
    fit_report: dict[str, Any],
    appearance: AppearanceBundle,
    render_materials: dict[str, Any],
    quality: dict[str, Any],
    seed: int,
) -> None:
    write_canonical_json(package_dir / "pattern/pattern.json", pattern)
    write_canonical_json(package_dir / "semantic/garment_graph.json", semantic)
    write_canonical_json(
        package_dir / "simulation/rest_state.json",
        mesh_manifest(rest_mesh, "simulation_rest", edge_maps=edge_maps),
    )
    write_canonical_json(
        package_dir / "simulation/settled_state.json",
        motion_states[spec.selected_material_preset_id],
    )
    write_canonical_json(package_dir / "simulation/constraints.json", constraints)
    write_canonical_json(package_dir / "simulation/material_presets.json", material_registry)
    write_canonical_json(package_dir / "simulation/material_selection.json", material_selection)
    write_canonical_json(package_dir / "simulation/material_physics.json", material_physics)
    for state_id, state in sorted(motion_states.items()):
        safe_name = state_id.replace("material.", "").replace("_d0_v1", "")
        write_canonical_json(package_dir / f"simulation/motion_states/{safe_name}.json", state)
    write_canonical_json(package_dir / "reports/material_motion_suite.json", motion_report)

    write_indexed_glb(
        package_dir / "simulation/simulation_mesh.glb",
        simulation_mesh,
        spec.simulation_node_name,
        (0.18, 0.37, 0.69, 1.0),
        normalize_signed_zero=spec.normalize_signed_zero,
    )
    write_indexed_glb(
        package_dir / "render/fallback.glb",
        render_mesh,
        spec.dense_render_node_name,
        (0.18, 0.37, 0.69, 1.0),
        normalize_signed_zero=spec.normalize_signed_zero,
    )
    write_indexed_glb(
        package_dir / "render/simulation_fallback.glb",
        simulation_mesh,
        spec.independent_fallback_node_name,
        (0.18, 0.37, 0.69, 1.0),
        normalize_signed_zero=spec.normalize_signed_zero,
    )
    write_canonical_json(package_dir / "render/materials.json", render_materials)
    write_binding(package_dir / "binding/sim_to_render.bin", binding)
    write_canonical_json(package_dir / "binding/binding_manifest.json", binding_manifest)

    write_indexed_glb(
        package_dir / "avatar/reference_avatar.glb",
        avatar_mesh,
        "closy_reference_avatar_v1",
        (0.72, 0.68, 0.62, 1.0),
    )
    write_indexed_glb(
        package_dir / "avatar/collision.glb",
        collision_mesh,
        "closy_reference_collision_v1",
        (0.72, 0.2, 0.2, 0.34),
    )
    write_canonical_json(package_dir / "avatar/avatar_contract.json", avatar)
    write_canonical_json(package_dir / spec.fit_report_path, fit_report)
    for relpath, artifact in sorted(appearance.artifacts.items()):
        path = package_dir / relpath
        if isinstance(artifact, bytes):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(artifact)
        else:
            write_canonical_json(path, artifact)
    write_canonical_json(package_dir / "source/capture_record.json", appearance.capture_record)
    write_canonical_json(
        package_dir / "reports/fidelity/source_render_fidelity.json",
        appearance.fidelity_report,
    )
    write_canonical_json(package_dir / spec.quality_report_path, quality)
    write_canonical_json(
        package_dir / "provenance.json",
        {
            "schemaVersion": 1,
            "createdAt": FIXED_TIMESTAMP,
            "generator": spec.package_version,
            "seed": seed,
            "sourceKind": "public_synthetic_fixture",
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "learnedModelRun": False,
            "externalProviderRun": False,
            "actualReferenceSolverRun": True,
            "productionGpuRun": False,
        },
    )


def mesh_manifest(
    meshset: MeshSet,
    mesh_role: str,
    *,
    edge_maps: dict[str, dict[str, list[int]]] | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "meshRole": mesh_role,
        "coordinateConvention": COORDINATE_CONVENTION,
        "meshCount": len(meshset.meshes),
        "vertexCount": meshset.vertex_count,
        "triangleCount": meshset.triangle_count,
        "bounds": mesh_bounds(meshset),
        "topologyHash": topology_hash(meshset),
        "contentHash": geometry_content_hash(meshset),
        "panelTable": [
            {
                "panelId": mesh.panel_id,
                "meshName": mesh.name,
                "vertexCount": len(mesh.vertices),
                "triangleCount": len(mesh.triangles),
                "materialId": mesh.material_id,
            }
            for mesh in meshset.meshes
        ],
        "meshes": [
            {
                "name": mesh.name,
                "panelId": mesh.panel_id,
                "vertices": [list(vertex) for vertex in mesh.vertices],
                "panelUvs": [list(uv) for uv in mesh.panel_uvs],
                "triangles": [list(triangle) for triangle in mesh.triangles],
                "materialId": mesh.material_id,
            }
            for mesh in meshset.meshes
        ],
        "edgeVertexMap": edge_maps or {},
        "panelCoordinatesRetained": True,
        "provenance": "public_procedural_fixture",
    }


def material_selection_input(
    family_token: str, *, observations: dict[str, str] | None = None
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "selectionId": f"material_selection.{family_token}_public_d0_v1",
        "inputId": f"material_input.{family_token}_public_d0_v1",
        "garmentFamily": family_token,
        "observations": observations
        or {
            "massClass": "medium",
            "stretchClass": "moderate",
            "drapeClass": "soft",
            "surfaceClass": "jersey_knit",
        },
        "provenance": {
            "source": "project_authored_public_fixture_visual_cues",
            "physicalMeasurement": False,
            "learnedClassifierRun": False,
        },
    }


def render_materials(appearance: AppearanceBundle) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "materials": [appearance.texture_report["material"]],
        "mobilePbr": {
            "shaderClass": "metallic_roughness",
            "transmission": False,
            "subsurfaceScattering": False,
        },
    }


def pending_validation() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "status": "pending",
        "counts": {"info": 0, "warning": 0, "error": 0, "fatal": 0},
        "issues": [],
    }


def write_summary_files(
    package_dir: Path,
    context: dict[str, Any],
    validation: dict[str, Any],
    spec: SummarySpec,
) -> None:
    write_canonical_json(package_dir / "reports/package_validation.json", validation)
    report = summary(context, validation, spec)
    write_canonical_json(package_dir / "reports/summary.json", report)
    lines = [
        f"# {report['displayName']}",
        "",
        f"- Garment class: `{report['garmentClass']}`",
        f"- Package digest: `{report['packageDigest']}`",
        f"- Validation: `{report['validation']['status']}`",
        f"- {spec.completion_label}: `{report['readiness'][spec.completion_key]}`",
        f"- Phase 8 globally: `{report['readiness']['phase8GlobalStatus']}`",
        f"- Next family: `{report['readiness']['nextGarmentFamily']}`",
        "",
        "This is a public deterministic CPU fixture, not private-user fitting, production cloth, "
        "or learned garment inference.",
    ]
    write_canonical_text(package_dir / "reports/summary.md", "\n".join(lines))


def summary(
    context: dict[str, Any], validation: dict[str, Any], spec: SummarySpec
) -> dict[str, Any]:
    manifest = context["manifest"]
    quality = context["quality"]
    return {
        "schemaVersion": 1,
        "garmentId": manifest["garmentId"],
        "displayName": manifest["displayName"],
        "garmentClass": manifest["garmentClass"],
        "packageDigest": manifest["packageDigest"],
        "packageByteSize": manifest["packageByteSize"],
        "counts": manifest["counts"],
        "validation": validation,
        "readiness": {
            spec.completion_key: quality["readiness"][spec.completion_key],
            "phase8GlobalStatus": "partial",
            "nextGarmentFamily": quality["readiness"]["nextGarmentFamily"],
        },
        "truthfulLimitations": manifest["warnings"],
    }
