from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from closy_forge.appearance import (
    TEXTURE_IDENTITY_VERSION,
    build_texture_identity_report,
)
from closy_forge.avatar.reference_avatar import (
    avatar_contract,
    body_regions,
    build_collision_mesh,
    build_reference_avatar_mesh,
)
from closy_forge.binding.binary_format import write_binding
from closy_forge.binding.builder import build_binding
from closy_forge.binding.reconstruct import (
    perturb_simulation_vertices,
    reconstruct_vertices,
    reconstruction_error,
)
from closy_forge.capture import (
    CAPTURE_QUALITY_SCORER_VERSION,
    SYNTHETIC_CAPTURE_RECORD_VERSION,
    build_synthetic_capture_record,
    score_capture_record,
)
from closy_forge.contracts.common import COORDINATE_CONVENTION, DEFAULT_SEED, FIXED_TIMESTAMP
from closy_forge.fitting import (
    TSHIRT_FIT_REPORT_VERSION,
    fit_tshirt_parameters_from_visual_observations,
)
from closy_forge.garments.tshirt.assembly import build_constraints, build_simulation_mesh
from closy_forge.garments.tshirt.parameters import TShirtParameters
from closy_forge.garments.tshirt.pattern_generator import build_tshirt_pattern
from closy_forge.garments.tshirt.semantic_graph import build_semantic_graph
from closy_forge.geometry.glb_io import audit_glb, write_glb, write_indexed_glb
from closy_forge.geometry.mesh_model import MeshSet, mesh_bounds
from closy_forge.geometry.subdivision import subdivide_for_render
from closy_forge.package_io.canonical_json import (
    canonical_dumps,
    write_canonical_json,
    write_canonical_text,
)
from closy_forge.package_io.hashing import geometry_content_hash, sha256_bytes, topology_hash
from closy_forge.package_io.writer import (
    EXCLUDED_FROM_CANONICAL_INVENTORY,
    canonical_package_digest,
    cleanup_staging,
    collect_inventory,
    prepare_staging,
    publish_staging,
)
from closy_forge.proposals import (
    CLEAN_GEOMETRY_PROPOSAL_VERSION,
    GEOMETRY_BINDING_CANDIDATE_VERSION,
    GEOMETRY_BINDING_VALIDATION_VERSION,
    GEOMETRY_CLEAN_ACCEPTANCE_GATE_VERSION,
    GEOMETRY_CLEANUP_PLAN_VERSION,
    GEOMETRY_CLEANUP_RESULT_VERSION,
    GEOMETRY_MATERIAL_UV_TRANSFER_VERSION,
    GEOMETRY_PROPOSAL_VERSION,
    GEOMETRY_REPAIR_RESULT_VERSION,
    GEOMETRY_REPAIR_RETOPOLOGY_PLAN_VERSION,
    GEOMETRY_RUNTIME_BINDING_RESULT_VERSION,
    GEOMETRY_SEMANTIC_TRANSFER_VERSION,
    GEOMETRY_VISUAL_SHELL_REVIEW_VERSION,
    PROVIDER_REGISTRY_VERSION,
    RAW_GEOMETRY_TOPOLOGY_REPORT_VERSION,
    build_clean_geometry_proposal_rejection,
    build_geometry_binding_candidate_report,
    build_geometry_binding_validation_report,
    build_geometry_clean_acceptance_gate_report,
    build_geometry_cleanup_plan,
    build_geometry_cleanup_result,
    build_geometry_material_uv_transfer_report,
    build_geometry_provider_registry,
    build_geometry_repair_result_report,
    build_geometry_repair_retopology_plan,
    build_geometry_runtime_binding_result_report,
    build_geometry_semantic_transfer_report,
    build_geometry_visual_shell_review_report,
    build_manual_geometry_proposal,
    build_proposal_runtime_binding,
    build_proposal_runtime_render_mesh,
    build_raw_geometry_topology_report,
    clean_geometry_proposal_quality_report,
    geometry_proposal_quality_report,
    provider_registry_quality_report,
    reproject_cleanup_preview_to_settled_simulation,
)
from closy_forge.simulation.reference_cloth_solver import (
    settle_reference_cloth,
    simulation_state_json,
)
from closy_forge.validation.validator import validate_package
from closy_forge.visual_understanding import (
    CORRECTION_RECORD_VERSION,
    TSHIRT_VISUAL_OBSERVATION_VERSION,
    build_empty_correction_record,
    build_tshirt_visual_observations,
)


@dataclass(frozen=True)
class BuildResult:
    package_dir: Path
    manifest: dict[str, Any]
    validation: dict[str, Any]


def build_demo_tshirt_package(
    output: Path,
    *,
    params: TShirtParameters | None = None,
    seed: int = DEFAULT_SEED,
    force: bool = False,
) -> BuildResult:
    tshirt_params = params or TShirtParameters()
    tshirt_params.validate()
    staging = prepare_staging(output)
    try:
        context = _write_package_contents(staging, tshirt_params, seed)
        pending_validation = {
            "schemaVersion": 1,
            "status": "pending",
            "counts": {"info": 0, "warning": 0, "error": 0, "fatal": 0},
            "issues": [],
        }
        write_canonical_json(
            staging / "reports" / "package_validation.json",
            pending_validation,
        )
        write_canonical_json(
            staging / "reports" / "summary.json",
            _summary_json(context, pending_validation),
        )
        write_canonical_text(
            staging / "reports" / "summary.md",
            _summary_markdown(context, pending_validation),
        )
        final_validation = validate_package(staging)
        if final_validation["status"] != "passed":
            write_canonical_json(staging / "reports" / "package_validation.json", final_validation)
            raise RuntimeError("package validation failed before publish")
        write_canonical_json(staging / "reports" / "package_validation.json", final_validation)
        write_canonical_json(
            staging / "reports" / "summary.json",
            _summary_json(context, final_validation),
        )
        write_canonical_text(
            staging / "reports" / "summary.md",
            _summary_markdown(context, final_validation),
        )
        publish_staging(staging, output, force=force)
        return BuildResult(output, context["manifest"], final_validation)
    except Exception:
        cleanup_staging(staging)
        raise


def _write_package_contents(
    package_dir: Path, params: TShirtParameters, seed: int
) -> dict[str, Any]:
    avatar_mesh = build_reference_avatar_mesh()
    collision_mesh = build_collision_mesh()
    pattern = build_tshirt_pattern(params)
    semantic = build_semantic_graph(pattern)
    rest_mesh, edge_maps = build_simulation_mesh(pattern)
    constraints = build_constraints(pattern, edge_maps)
    avatar = avatar_contract(avatar_mesh, collision_mesh)
    regions = body_regions()
    capture_record = build_synthetic_capture_record(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        avatar_contract_id=str(avatar["avatarContractId"]),
        seed=seed,
    )
    capture_quality = score_capture_record(capture_record)
    visual_observations = build_tshirt_visual_observations(capture_record)
    correction_record = build_empty_correction_record(visual_observations)
    fit_report = fit_tshirt_parameters_from_visual_observations(visual_observations, prior=params)
    render_materials = _render_materials()
    texture_identity = build_texture_identity_report(
        capture_record=capture_record,
        visual_observations=visual_observations,
        fit_report=fit_report,
        render_materials=render_materials,
    )
    manual_proposal_asset = package_dir / "proposals" / "manual_raw_visual_proposal.glb"
    write_glb(
        manual_proposal_asset,
        rest_mesh,
        "closy_manual_raw_visual_tshirt_fixture_v1",
        (0.78, 0.82, 0.92, 1.0),
    )
    geometry_proposal = build_manual_geometry_proposal(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        capture_record=capture_record,
        visual_observations=visual_observations,
        fit_report=fit_report,
        texture_identity=texture_identity,
        asset_path=manual_proposal_asset,
        package_asset_path="proposals/manual_raw_visual_proposal.glb",
    )
    provider_registry = build_geometry_provider_registry(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        capture_record=capture_record,
        visual_observations=visual_observations,
        fit_report=fit_report,
        texture_identity=texture_identity,
        geometry_proposal=geometry_proposal,
        manual_asset_path=manual_proposal_asset,
        manual_asset_rights_reviewed=True,
        manual_asset_rights_status="project_authored_fixture_no_third_party_asset",
    )
    raw_geometry_topology = build_raw_geometry_topology_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        raw_geometry_proposal=geometry_proposal,
        asset_path=manual_proposal_asset,
    )
    geometry_cleanup_plan = build_geometry_cleanup_plan(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        raw_geometry_proposal=geometry_proposal,
        raw_topology_report=raw_geometry_topology,
    )
    cleanup_preview_asset = package_dir / "proposals" / "manual_cleanup_preview.glb"
    geometry_cleanup_result = build_geometry_cleanup_result(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        raw_geometry_proposal=geometry_proposal,
        raw_topology_report=raw_geometry_topology,
        cleanup_plan_report=geometry_cleanup_plan,
        source_asset_path=manual_proposal_asset,
        output_asset_path=cleanup_preview_asset,
        output_package_asset_path="proposals/manual_cleanup_preview.glb",
    )
    geometry_semantic_transfer = build_geometry_semantic_transfer_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        semantic_graph=semantic,
        pattern=pattern,
        cleanup_result_report=geometry_cleanup_result,
        cleanup_asset_path=cleanup_preview_asset,
    )
    material_physics = _material_physics()
    settle = settle_reference_cloth(rest_mesh, constraints, avatar, material_physics)
    simulation_mesh = settle.settled_mesh
    geometry_binding_candidate = build_geometry_binding_candidate_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        semantic_transfer_report=geometry_semantic_transfer,
        cleanup_asset_path=cleanup_preview_asset,
        simulation_mesh=simulation_mesh,
        simulation_mesh_path="simulation/simulation_mesh.glb",
    )
    geometry_binding_validation = build_geometry_binding_validation_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        binding_candidate_report=geometry_binding_candidate,
        cleanup_asset_path=cleanup_preview_asset,
        rest_simulation_mesh=rest_mesh,
        settled_simulation_mesh=simulation_mesh,
        rest_state_path="simulation/rest_state.json",
        settled_simulation_mesh_path="simulation/simulation_mesh.glb",
    )
    geometry_repair_retopology_plan = build_geometry_repair_retopology_plan(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        raw_topology_report=raw_geometry_topology,
        cleanup_result_report=geometry_cleanup_result,
        semantic_transfer_report=geometry_semantic_transfer,
        binding_candidate_report=geometry_binding_candidate,
        binding_validation_report=geometry_binding_validation,
    )
    repair_preview_asset = package_dir / "proposals" / "manual_repair_preview.glb"
    geometry_repair_mesh = reproject_cleanup_preview_to_settled_simulation(
        cleanup_asset_path=cleanup_preview_asset,
        binding_candidate_report=geometry_binding_candidate,
        settled_simulation_mesh=simulation_mesh,
    )
    write_indexed_glb(
        repair_preview_asset,
        geometry_repair_mesh,
        "closy_partial_repair_reprojection_preview_v1",
        (0.68, 0.78, 0.92, 1.0),
    )
    geometry_repair_result = build_geometry_repair_result_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        repair_retopology_plan_report=geometry_repair_retopology_plan,
        binding_candidate_report=geometry_binding_candidate,
        binding_validation_report=geometry_binding_validation,
        cleanup_asset_path=cleanup_preview_asset,
        output_asset_path=repair_preview_asset,
        output_package_asset_path="proposals/manual_repair_preview.glb",
        output_mesh=geometry_repair_mesh,
        settled_simulation_mesh=simulation_mesh,
        settled_simulation_mesh_path="simulation/simulation_mesh.glb",
    )
    proposal_runtime_render_mesh, proposal_runtime_binding_seeds = (
        build_proposal_runtime_render_mesh(simulation_mesh)
    )
    proposal_runtime_binding, proposal_runtime_binding_manifest = build_proposal_runtime_binding(
        settled_simulation_mesh=simulation_mesh,
        runtime_render_mesh=proposal_runtime_render_mesh,
        render_binding_seeds=proposal_runtime_binding_seeds,
        target_render_path="proposals/manual_runtime_retopology_preview.glb",
    )
    proposal_runtime_render_asset = (
        package_dir / "proposals" / "manual_runtime_retopology_preview.glb"
    )
    write_indexed_glb(
        proposal_runtime_render_asset,
        proposal_runtime_render_mesh,
        "closy_proposal_runtime_retopology_preview_v1",
        (0.54, 0.70, 0.90, 1.0),
    )
    proposal_runtime_binding_asset = package_dir / "binding" / "proposal_sim_to_render.bin"
    write_binding(proposal_runtime_binding_asset, proposal_runtime_binding)
    write_canonical_json(
        package_dir / "binding" / "proposal_binding_manifest.json",
        proposal_runtime_binding_manifest,
    )
    geometry_runtime_binding_result = build_geometry_runtime_binding_result_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        repair_result_report=geometry_repair_result,
        semantic_transfer_report=geometry_semantic_transfer,
        binding_candidate_report=geometry_binding_candidate,
        binding_validation_report=geometry_binding_validation,
        repair_asset_path=repair_preview_asset,
        output_render_asset_path=proposal_runtime_render_asset,
        output_render_package_path="proposals/manual_runtime_retopology_preview.glb",
        output_binding_path=proposal_runtime_binding_asset,
        output_binding_package_path="binding/proposal_sim_to_render.bin",
        output_binding_manifest=proposal_runtime_binding_manifest,
        output_binding_manifest_package_path="binding/proposal_binding_manifest.json",
        output_render_mesh=proposal_runtime_render_mesh,
        settled_simulation_mesh=simulation_mesh,
        settled_simulation_mesh_path="simulation/simulation_mesh.glb",
        constraints=constraints,
    )
    geometry_material_uv_transfer = build_geometry_material_uv_transfer_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        runtime_binding_result_report=geometry_runtime_binding_result,
        semantic_transfer_report=geometry_semantic_transfer,
        texture_identity_report=texture_identity,
        render_materials=render_materials,
        runtime_render_mesh=proposal_runtime_render_mesh,
    )
    geometry_visual_shell_review = build_geometry_visual_shell_review_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        runtime_binding_result_report=geometry_runtime_binding_result,
        semantic_transfer_report=geometry_semantic_transfer,
        material_uv_transfer_report=geometry_material_uv_transfer,
        runtime_render_mesh=proposal_runtime_render_mesh,
        reference_simulation_mesh=simulation_mesh,
        constraints=constraints,
    )
    geometry_clean_acceptance_gate = build_geometry_clean_acceptance_gate_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        runtime_binding_result_report=geometry_runtime_binding_result,
        semantic_transfer_report=geometry_semantic_transfer,
        texture_identity_report=texture_identity,
        material_uv_transfer_report=geometry_material_uv_transfer,
        visual_shell_review_report=geometry_visual_shell_review,
        provider_registry=provider_registry,
    )
    clean_geometry_proposal = build_clean_geometry_proposal_rejection(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        raw_geometry_proposal=geometry_proposal,
        provider_registry=provider_registry,
        raw_topology_report=raw_geometry_topology,
        cleanup_plan_report=geometry_cleanup_plan,
        cleanup_result_report=geometry_cleanup_result,
        semantic_transfer_report=geometry_semantic_transfer,
        binding_candidate_report=geometry_binding_candidate,
        binding_validation_report=geometry_binding_validation,
        repair_retopology_plan_report=geometry_repair_retopology_plan,
        repair_result_report=geometry_repair_result,
        runtime_binding_result_report=geometry_runtime_binding_result,
        material_uv_transfer_report=geometry_material_uv_transfer,
        visual_shell_review_report=geometry_visual_shell_review,
        clean_acceptance_gate_report=geometry_clean_acceptance_gate,
    )
    render_mesh, render_binding_seeds = subdivide_for_render(simulation_mesh)
    binding, binding_manifest = build_binding(simulation_mesh, render_mesh, render_binding_seeds)

    write_canonical_json(package_dir / "source" / "capture_record.json", capture_record)
    write_canonical_json(package_dir / "source" / "capture_quality.json", capture_quality)
    write_canonical_json(package_dir / "source" / "visual_observations.json", visual_observations)
    write_canonical_json(package_dir / "source" / "correction_record.json", correction_record)
    write_canonical_json(package_dir / "fitting" / "tshirt_fit.json", fit_report)
    write_canonical_json(package_dir / "textures" / "texture_identity.json", texture_identity)
    write_canonical_json(
        package_dir / "proposals" / "raw_geometry_proposal.json", geometry_proposal
    )
    write_canonical_json(
        package_dir / "proposals" / "clean_geometry_proposal.json", clean_geometry_proposal
    )
    write_canonical_json(package_dir / "proposals" / "provider_registry.json", provider_registry)
    write_canonical_json(package_dir / "avatar" / "avatar_contract.json", avatar)
    write_canonical_json(package_dir / "avatar" / "body_regions.json", regions)
    write_glb(
        package_dir / "avatar" / "reference_avatar.glb",
        avatar_mesh,
        "closy_reference_mannequin_v1",
        (0.78, 0.70, 0.62, 1.0),
    )
    write_glb(
        package_dir / "avatar" / "collision.glb",
        collision_mesh,
        "closy_collision_fixture_v1",
        (0.40, 0.62, 0.95, 0.42),
    )
    write_canonical_json(package_dir / "semantic" / "garment_graph.json", semantic)
    write_canonical_json(
        package_dir / "semantic" / "confidence.json",
        {
            "schemaVersion": 1,
            "source": "authored_deterministic_fixture",
            "overall": {"state": "pass", "confidence": 1.0},
            "aiInferred": False,
            "userCorrected": False,
        },
    )
    write_canonical_json(package_dir / "pattern" / "pattern.json", pattern)
    write_canonical_text(package_dir / "pattern" / "panels.svg", _panels_svg(pattern))
    write_glb(
        package_dir / "simulation" / "simulation_mesh.glb",
        simulation_mesh,
        "closy_simulation_cotton_fixture_v1",
        (0.12, 0.32, 0.86, 1.0),
    )
    write_canonical_json(
        package_dir / "simulation" / "mesh_manifest.json",
        _mesh_manifest(simulation_mesh, "simulation", edge_maps=edge_maps),
    )
    write_canonical_json(package_dir / "simulation" / "constraints.json", constraints)
    write_canonical_json(
        package_dir / "simulation" / "rest_state.json",
        simulation_state_json(
            state_id="state.rest_analytic_assembly",
            meshset=rest_mesh,
            source_mesh=None,
        ),
    )
    write_canonical_json(
        package_dir / "simulation" / "settled_state.json",
        simulation_state_json(
            state_id="state.settled_reference_cpu_v1",
            meshset=simulation_mesh,
            source_mesh=rest_mesh,
            diagnostics=settle.diagnostics,
        ),
    )
    write_canonical_json(package_dir / "simulation" / "settle_diagnostics.json", settle.diagnostics)
    write_canonical_json(package_dir / "simulation" / "material_physics.json", material_physics)
    write_glb(
        package_dir / "render" / "fallback.glb",
        render_mesh,
        "closy_render_cotton_fixture_v1",
        (0.08, 0.26, 0.78, 1.0),
    )
    write_canonical_json(
        package_dir / "render" / "mesh_manifest.json", _mesh_manifest(render_mesh, "render")
    )
    write_canonical_json(package_dir / "render" / "materials.json", render_materials)
    write_binding(package_dir / "binding" / "sim_to_render.bin", binding)
    write_canonical_json(package_dir / "binding" / "binding_manifest.json", binding_manifest)

    quality_reports = _quality_reports(
        avatar_mesh,
        collision_mesh,
        pattern,
        semantic,
        rest_mesh,
        simulation_mesh,
        render_mesh,
        constraints,
        binding_manifest,
        settle.diagnostics,
        capture_record,
        capture_quality,
        visual_observations,
        correction_record,
        fit_report,
        texture_identity,
        geometry_proposal,
        raw_geometry_topology,
        geometry_cleanup_plan,
        geometry_cleanup_result,
        geometry_semantic_transfer,
        geometry_binding_candidate,
        geometry_binding_validation,
        geometry_repair_retopology_plan,
        geometry_repair_result,
        geometry_runtime_binding_result,
        geometry_material_uv_transfer,
        geometry_visual_shell_review,
        geometry_clean_acceptance_gate,
        clean_geometry_proposal,
        provider_registry,
    )
    for name, report in quality_reports.items():
        write_canonical_json(package_dir / "reports" / name, report)

    provenance = _provenance(
        params,
        seed,
        avatar_mesh,
        collision_mesh,
        rest_mesh,
        simulation_mesh,
        render_mesh,
        binding_manifest,
        settle.diagnostics,
        capture_record,
        capture_quality,
        visual_observations,
        correction_record,
        fit_report,
        texture_identity,
        geometry_proposal,
        raw_geometry_topology,
        geometry_cleanup_plan,
        geometry_cleanup_result,
        geometry_semantic_transfer,
        geometry_binding_candidate,
        geometry_binding_validation,
        geometry_repair_retopology_plan,
        geometry_repair_result,
        geometry_runtime_binding_result,
        geometry_material_uv_transfer,
        geometry_visual_shell_review,
        geometry_clean_acceptance_gate,
        clean_geometry_proposal,
        provider_registry,
    )
    write_canonical_json(package_dir / "provenance.json", provenance)

    inventory = collect_inventory(package_dir, exclude=EXCLUDED_FROM_CANONICAL_INVENTORY)
    digest = canonical_package_digest(inventory)
    manifest = _manifest(
        params,
        seed,
        inventory,
        digest,
        avatar_mesh,
        collision_mesh,
        rest_mesh,
        simulation_mesh,
        render_mesh,
        binding_manifest,
        settle.diagnostics,
        capture_record,
        capture_quality,
        visual_observations,
        correction_record,
        fit_report,
        texture_identity,
        geometry_proposal,
        raw_geometry_topology,
        geometry_cleanup_plan,
        geometry_cleanup_result,
        geometry_semantic_transfer,
        geometry_binding_candidate,
        geometry_binding_validation,
        geometry_repair_retopology_plan,
        geometry_repair_result,
        geometry_runtime_binding_result,
        geometry_material_uv_transfer,
        geometry_visual_shell_review,
        geometry_clean_acceptance_gate,
        clean_geometry_proposal,
        provider_registry,
    )
    write_canonical_json(package_dir / "manifest.json", manifest)
    return {
        "manifest": manifest,
        "pattern": pattern,
        "semantic": semantic,
        "simulationMesh": simulation_mesh,
        "restMesh": rest_mesh,
        "renderMesh": render_mesh,
        "constraints": constraints,
        "bindingManifest": binding_manifest,
        "settleDiagnostics": settle.diagnostics,
        "captureRecord": capture_record,
        "captureQuality": capture_quality,
        "visualObservations": visual_observations,
        "correctionRecord": correction_record,
        "fitReport": fit_report,
        "textureIdentity": texture_identity,
        "geometryProposal": geometry_proposal,
        "rawGeometryTopology": raw_geometry_topology,
        "geometryCleanupPlan": geometry_cleanup_plan,
        "geometryCleanupResult": geometry_cleanup_result,
        "geometrySemanticTransfer": geometry_semantic_transfer,
        "geometryBindingCandidate": geometry_binding_candidate,
        "geometryBindingValidation": geometry_binding_validation,
        "geometryRepairRetopologyPlan": geometry_repair_retopology_plan,
        "geometryRepairResult": geometry_repair_result,
        "geometryRuntimeBindingResult": geometry_runtime_binding_result,
        "geometryMaterialUvTransfer": geometry_material_uv_transfer,
        "geometryVisualShellReview": geometry_visual_shell_review,
        "geometryCleanAcceptanceGate": geometry_clean_acceptance_gate,
        "cleanGeometryProposal": clean_geometry_proposal,
        "providerRegistry": provider_registry,
        "inventory": inventory,
    }


def _mesh_manifest(
    meshset: MeshSet, mesh_role: str, *, edge_maps: dict[str, dict[str, list[int]]] | None = None
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
        "provenance": "procedural_fixture",
    }


def _material_physics() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "presetId": "material.cotton_jersey_reference_v1",
        "status": "authored_fixture_not_measured",
        "units": "SI",
        "surfaceDensityKgM2": 0.16,
        "stretchStiffnessNPerM": 550.0,
        "bendStiffnessNm": 0.0018,
        "dampingRatio": 0.18,
        "frictionCoefficient": 0.42,
        "thicknessMeters": 0.0016,
        "clothSettleRun": True,
        "settleBackend": "deterministic_cpu_reference_xpbd",
        "settleSolverVersion": "closy.reference_xpbd_cpu.v1",
    }


def _render_materials() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "materials": [
            {
                "id": "material.cotton_jersey_reference_v1",
                "label": "Fixture cotton jersey blue",
                "pbr": {
                    "baseColorFactor": [0.08, 0.26, 0.78, 1.0],
                    "roughnessFactor": 0.86,
                    "metallicFactor": 0.0,
                },
                "textureSource": "unavailable_source_image_texture_not_run",
            },
            {
                "id": "material.cotton_rib_reference_v1",
                "label": "Fixture cotton rib collar",
                "pbr": {
                    "baseColorFactor": [0.06, 0.20, 0.62, 1.0],
                    "roughnessFactor": 0.9,
                    "metallicFactor": 0.0,
                },
                "textureSource": "authored_color_only",
            },
        ],
    }


def _manifest(
    params: TShirtParameters,
    seed: int,
    inventory: list[dict[str, object]],
    digest: str,
    avatar_mesh: MeshSet,
    collision_mesh: MeshSet,
    rest_mesh: MeshSet,
    sim_mesh: MeshSet,
    render_mesh: MeshSet,
    binding_manifest: dict[str, object],
    settle_diagnostics: dict[str, Any],
    capture_record: dict[str, Any],
    capture_quality: dict[str, Any],
    visual_observations: dict[str, Any],
    correction_record: dict[str, Any],
    fit_report: dict[str, Any],
    texture_identity: dict[str, Any],
    geometry_proposal: dict[str, Any],
    raw_geometry_topology: dict[str, Any],
    geometry_cleanup_plan: dict[str, Any],
    geometry_cleanup_result: dict[str, Any],
    geometry_semantic_transfer: dict[str, Any],
    geometry_binding_candidate: dict[str, Any],
    geometry_binding_validation: dict[str, Any],
    geometry_repair_retopology_plan: dict[str, Any],
    geometry_repair_result: dict[str, Any],
    geometry_runtime_binding_result: dict[str, Any],
    geometry_material_uv_transfer: dict[str, Any],
    geometry_visual_shell_review: dict[str, Any],
    geometry_clean_acceptance_gate: dict[str, Any],
    clean_geometry_proposal: dict[str, Any],
    provider_registry: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "packageKind": "closy.garment",
        "garmentId": "garment.demo_tshirt.reference_v1",
        "displayName": "Deterministic Demo T-Shirt",
        "garmentClass": "tshirt",
        "units": "metres",
        "coordinateConvention": COORDINATE_CONVENTION,
        "status": "validated_fixture",
        "avatar": {
            "contractId": "avatar.closy_reference_v1",
            "version": "1.0.0",
            "path": "avatar/avatar_contract.json",
            "contentHash": _hash_from_inventory(inventory, "avatar/avatar_contract.json"),
            "sourceKind": "procedural_fixture",
        },
        "canonicalPaths": {
            "sourceCaptureRecord": "source/capture_record.json",
            "sourceCaptureQuality": "source/capture_quality.json",
            "sourceVisualObservations": "source/visual_observations.json",
            "sourceCorrectionRecord": "source/correction_record.json",
            "tshirtFitReport": "fitting/tshirt_fit.json",
            "textureIdentity": "textures/texture_identity.json",
            "rawGeometryProposal": "proposals/raw_geometry_proposal.json",
            "rawGeometryProposalAsset": "proposals/manual_raw_visual_proposal.glb",
            "rawGeometryTopology": "reports/raw_geometry_topology.json",
            "geometryCleanupPlan": "reports/geometry_cleanup_plan.json",
            "geometryCleanupPreviewAsset": "proposals/manual_cleanup_preview.glb",
            "geometryCleanupResult": "reports/geometry_cleanup_result.json",
            "geometrySemanticTransfer": "reports/geometry_semantic_transfer.json",
            "geometryBindingCandidate": "reports/geometry_binding_candidate.json",
            "geometryBindingValidation": "reports/geometry_binding_validation.json",
            "geometryRepairRetopologyPlan": "reports/geometry_repair_retopology_plan.json",
            "geometryRepairPreviewAsset": "proposals/manual_repair_preview.glb",
            "geometryRepairResult": "reports/geometry_repair_result.json",
            "geometryRuntimeRetopologyPreviewAsset": (
                "proposals/manual_runtime_retopology_preview.glb"
            ),
            "geometryRuntimeBindingResult": "reports/geometry_runtime_binding_result.json",
            "geometryMaterialUvTransfer": "reports/geometry_material_uv_transfer.json",
            "geometryVisualShellReview": "reports/geometry_visual_shell_review.json",
            "geometryCleanAcceptanceGate": "reports/geometry_clean_acceptance_gate.json",
            "cleanGeometryProposal": "proposals/clean_geometry_proposal.json",
            "geometryProviderRegistry": "proposals/provider_registry.json",
            "semanticGraph": "semantic/garment_graph.json",
            "pattern": "pattern/pattern.json",
            "simulationMesh": "simulation/simulation_mesh.glb",
            "simulationMeshManifest": "simulation/mesh_manifest.json",
            "simulationRestState": "simulation/rest_state.json",
            "simulationSettledState": "simulation/settled_state.json",
            "simulationSettleDiagnostics": "simulation/settle_diagnostics.json",
            "materialPhysics": "simulation/material_physics.json",
            "renderFallback": "render/fallback.glb",
            "renderMeshManifest": "render/mesh_manifest.json",
            "renderMaterials": "render/materials.json",
            "binding": "binding/sim_to_render.bin",
            "bindingManifest": "binding/binding_manifest.json",
            "proposalRuntimeBinding": "binding/proposal_sim_to_render.bin",
            "proposalRuntimeBindingManifest": "binding/proposal_binding_manifest.json",
        },
        "hashes": {
            "avatarTopologyHash": topology_hash(avatar_mesh),
            "avatarContentHash": geometry_content_hash(avatar_mesh),
            "collisionTopologyHash": topology_hash(collision_mesh),
            "collisionContentHash": geometry_content_hash(collision_mesh),
            "sourceCaptureRecordHash": _hash_from_inventory(
                inventory, "source/capture_record.json"
            ),
            "sourceCaptureQualityHash": _hash_from_inventory(
                inventory, "source/capture_quality.json"
            ),
            "sourceCaptureRecordPayloadHash": str(
                capture_record["immutability"]["sourceRecordHash"]
            ),
            "sourceVisualObservationsHash": _hash_from_inventory(
                inventory, "source/visual_observations.json"
            ),
            "sourceVisualObservationsPayloadHash": str(
                visual_observations["integrity"]["visualRecordHash"]
            ),
            "sourceCorrectionRecordHash": _hash_from_inventory(
                inventory, "source/correction_record.json"
            ),
            "sourceCorrectionRecordPayloadHash": str(
                correction_record["integrity"]["correctionRecordHash"]
            ),
            "tshirtFitReportHash": _hash_from_inventory(inventory, "fitting/tshirt_fit.json"),
            "tshirtFitReportPayloadHash": str(fit_report["integrity"]["fitReportHash"]),
            "textureIdentityHash": _hash_from_inventory(
                inventory, "textures/texture_identity.json"
            ),
            "textureIdentityPayloadHash": str(texture_identity["integrity"]["textureIdentityHash"]),
            "rawGeometryProposalHash": _hash_from_inventory(
                inventory, "proposals/raw_geometry_proposal.json"
            ),
            "rawGeometryProposalPayloadHash": str(
                geometry_proposal["integrity"]["geometryProposalHash"]
            ),
            "rawGeometryProposalAssetHash": _hash_from_inventory(
                inventory, "proposals/manual_raw_visual_proposal.glb"
            ),
            "rawGeometryTopologyHash": _hash_from_inventory(
                inventory, "reports/raw_geometry_topology.json"
            ),
            "rawGeometryTopologyPayloadHash": str(
                raw_geometry_topology["integrity"]["rawGeometryTopologyReportHash"]
            ),
            "geometryCleanupPlanHash": _hash_from_inventory(
                inventory, "reports/geometry_cleanup_plan.json"
            ),
            "geometryCleanupPlanPayloadHash": str(
                geometry_cleanup_plan["integrity"]["geometryCleanupPlanHash"]
            ),
            "geometryCleanupPreviewAssetHash": _hash_from_inventory(
                inventory, "proposals/manual_cleanup_preview.glb"
            ),
            "geometryCleanupResultHash": _hash_from_inventory(
                inventory, "reports/geometry_cleanup_result.json"
            ),
            "geometryCleanupResultPayloadHash": str(
                geometry_cleanup_result["integrity"]["geometryCleanupResultHash"]
            ),
            "geometrySemanticTransferHash": _hash_from_inventory(
                inventory, "reports/geometry_semantic_transfer.json"
            ),
            "geometrySemanticTransferPayloadHash": str(
                geometry_semantic_transfer["integrity"]["geometrySemanticTransferHash"]
            ),
            "geometryBindingCandidateHash": _hash_from_inventory(
                inventory, "reports/geometry_binding_candidate.json"
            ),
            "geometryBindingCandidatePayloadHash": str(
                geometry_binding_candidate["integrity"]["geometryBindingCandidateHash"]
            ),
            "geometryBindingValidationHash": _hash_from_inventory(
                inventory, "reports/geometry_binding_validation.json"
            ),
            "geometryBindingValidationPayloadHash": str(
                geometry_binding_validation["integrity"]["geometryBindingValidationHash"]
            ),
            "geometryRepairRetopologyPlanHash": _hash_from_inventory(
                inventory, "reports/geometry_repair_retopology_plan.json"
            ),
            "geometryRepairRetopologyPlanPayloadHash": str(
                geometry_repair_retopology_plan["integrity"]["geometryRepairRetopologyPlanHash"]
            ),
            "geometryRepairPreviewAssetHash": _hash_from_inventory(
                inventory, "proposals/manual_repair_preview.glb"
            ),
            "geometryRepairResultHash": _hash_from_inventory(
                inventory, "reports/geometry_repair_result.json"
            ),
            "geometryRepairResultPayloadHash": str(
                geometry_repair_result["integrity"]["geometryRepairResultHash"]
            ),
            "geometryRuntimeRetopologyPreviewAssetHash": _hash_from_inventory(
                inventory, "proposals/manual_runtime_retopology_preview.glb"
            ),
            "geometryRuntimeBindingResultHash": _hash_from_inventory(
                inventory, "reports/geometry_runtime_binding_result.json"
            ),
            "geometryRuntimeBindingResultPayloadHash": str(
                geometry_runtime_binding_result["integrity"]["geometryRuntimeBindingResultHash"]
            ),
            "geometryMaterialUvTransferHash": _hash_from_inventory(
                inventory, "reports/geometry_material_uv_transfer.json"
            ),
            "geometryMaterialUvTransferPayloadHash": str(
                geometry_material_uv_transfer["integrity"]["geometryMaterialUvTransferHash"]
            ),
            "geometryVisualShellReviewHash": _hash_from_inventory(
                inventory, "reports/geometry_visual_shell_review.json"
            ),
            "geometryVisualShellReviewPayloadHash": str(
                geometry_visual_shell_review["integrity"]["geometryVisualShellReviewHash"]
            ),
            "geometryCleanAcceptanceGateHash": _hash_from_inventory(
                inventory, "reports/geometry_clean_acceptance_gate.json"
            ),
            "geometryCleanAcceptanceGatePayloadHash": str(
                geometry_clean_acceptance_gate["integrity"]["geometryCleanAcceptanceGateHash"]
            ),
            "proposalRuntimeBindingHash": _hash_from_inventory(
                inventory, "binding/proposal_sim_to_render.bin"
            ),
            "proposalRuntimeBindingManifestHash": _hash_from_inventory(
                inventory, "binding/proposal_binding_manifest.json"
            ),
            "cleanGeometryProposalHash": _hash_from_inventory(
                inventory, "proposals/clean_geometry_proposal.json"
            ),
            "cleanGeometryProposalPayloadHash": str(
                clean_geometry_proposal["integrity"]["cleanGeometryProposalHash"]
            ),
            "geometryProviderRegistryHash": _hash_from_inventory(
                inventory, "proposals/provider_registry.json"
            ),
            "geometryProviderRegistryPayloadHash": str(
                provider_registry["integrity"]["providerRegistryHash"]
            ),
            "simulationRestTopologyHash": topology_hash(rest_mesh),
            "simulationRestContentHash": geometry_content_hash(rest_mesh),
            "simulationTopologyHash": topology_hash(sim_mesh),
            "simulationContentHash": geometry_content_hash(sim_mesh),
            "renderTopologyHash": topology_hash(render_mesh),
            "renderContentHash": geometry_content_hash(render_mesh),
            "settledStateContentHash": str(settle_diagnostics["settledContentHash"]),
        },
        "inventory": inventory,
        "canonicalDigestDefinition": {
            "algorithm": "sha256",
            "domain": "CLOSY_PACKAGE_DIGEST_V1",
            "included": "sorted inventory entries excluding manifest and mutable reader reports",
            "excluded": sorted(EXCLUDED_FROM_CANONICAL_INVENTORY),
        },
        "canonicalPackageDigest": digest,
        "algorithmVersions": {
            "referenceAvatarGenerator": "closy.reference_avatar.v1",
            "syntheticCaptureRecord": SYNTHETIC_CAPTURE_RECORD_VERSION,
            "captureQualityScorer": CAPTURE_QUALITY_SCORER_VERSION,
            "visualObservations": TSHIRT_VISUAL_OBSERVATION_VERSION,
            "correctionRecord": CORRECTION_RECORD_VERSION,
            "tshirtFit": TSHIRT_FIT_REPORT_VERSION,
            "textureIdentity": TEXTURE_IDENTITY_VERSION,
            "geometryProposal": GEOMETRY_PROPOSAL_VERSION,
            "rawGeometryTopology": RAW_GEOMETRY_TOPOLOGY_REPORT_VERSION,
            "geometryCleanupPlan": GEOMETRY_CLEANUP_PLAN_VERSION,
            "geometryCleanupResult": GEOMETRY_CLEANUP_RESULT_VERSION,
            "geometrySemanticTransfer": GEOMETRY_SEMANTIC_TRANSFER_VERSION,
            "geometryBindingCandidate": GEOMETRY_BINDING_CANDIDATE_VERSION,
            "geometryBindingValidation": GEOMETRY_BINDING_VALIDATION_VERSION,
            "geometryRepairRetopologyPlan": GEOMETRY_REPAIR_RETOPOLOGY_PLAN_VERSION,
            "geometryRepairResult": GEOMETRY_REPAIR_RESULT_VERSION,
            "geometryRuntimeBindingResult": GEOMETRY_RUNTIME_BINDING_RESULT_VERSION,
            "geometryMaterialUvTransfer": GEOMETRY_MATERIAL_UV_TRANSFER_VERSION,
            "geometryVisualShellReview": GEOMETRY_VISUAL_SHELL_REVIEW_VERSION,
            "geometryCleanAcceptanceGate": GEOMETRY_CLEAN_ACCEPTANCE_GATE_VERSION,
            "cleanGeometryProposal": CLEAN_GEOMETRY_PROPOSAL_VERSION,
            "geometryProviderRegistry": PROVIDER_REGISTRY_VERSION,
            "patternGenerator": "closy.tshirt.pattern.v1",
            "curveSampler": "closy.curve_sampler.v1",
            "panelTriangulator": "closy.fan_triangulator.v1",
            "clothSettle": "closy.reference_xpbd_cpu.v1",
            "renderSubdivision": "closy.render_subdivision.v1",
            "binding": str(binding_manifest["algorithm"]),
            "glbWriter": "closy.glb_writer.v1",
        },
        "seed": seed,
        "buildProfile": {
            "name": "implementation_21_visual_shell_review_evidence",
            "timestamp": FIXED_TIMESTAMP,
            "parameters": params.to_json(),
        },
        "capabilities": _capabilities(),
        "warnings": [
            "self_collision_not_run",
            "synthetic_capture_metadata_only",
            "synthetic_visual_observations_not_real_segmentation",
            "synthetic_fit_not_trained_from_real_images",
            "source_texture_projection_not_run",
            "manual_raw_geometry_proposal_not_canonical",
            "partial_geometry_cleanup_not_clean_proposal",
            "geometry_semantic_transfer_not_simulation_binding",
            "geometry_binding_candidate_not_runtime_binding",
            "geometry_binding_validation_rejected_runtime_binding",
            "geometry_repair_result_partial_reprojection_not_clean",
            "geometry_runtime_binding_result_clean_acceptance_pending",
            "geometry_material_uv_transfer_authored_pbr_only",
            "geometry_visual_shell_review_clean_rejected",
            "geometry_clean_acceptance_gate_rejected",
            "clean_geometry_proposal_not_available",
            "zeroone_unavailable_optional",
            "procedural_fixture_not_production_asset",
        ],
        "zeroOne": {"staticAvailable": False, "dynamicAvailable": False, "required": False},
        "extensions": {"closyImplementation": "21-visual-shell-review-evidence"},
    }


def _capabilities() -> dict[str, bool]:
    return {
        "patternAvailable": True,
        "simulationReadyTopologyAvailable": True,
        "authoredMaterialPresetAvailable": True,
        "conventionalGlbAvailable": True,
        "simToRenderBindingAvailable": True,
        "bindingReconstructionValidated": True,
        "actualClothSettleAvailable": True,
        "selfCollisionAvailable": False,
        "sourceImageTextureAvailable": False,
        "sourceCaptureRecordAvailable": True,
        "captureQualityScored": True,
        "visualObservationsAvailable": True,
        "garmentMaskAvailable": True,
        "garmentLandmarksAvailable": True,
        "editableCorrectionRecordAvailable": True,
        "tshirtParameterFitAvailable": True,
        "fittingQualityScored": True,
        "textureIdentityEvidenceAvailable": True,
        "pbrMaterialObservationAvailable": True,
        "geometryProposalInterfaceAvailable": True,
        "rawGeometryProposalRecordAvailable": True,
        "geometryProposalQualityScored": True,
        "rawGeometryTopologyDiagnosticsAvailable": True,
        "geometryCleanupRecommendationAvailable": True,
        "geometryCleanupExecutionAvailable": True,
        "geometrySemanticTransferAvailable": True,
        "geometryBoundaryClassificationAvailable": True,
        "geometryBindingCandidateAvailable": True,
        "geometryBindingValidationAvailable": True,
        "geometryRepairRetopologyPlanAvailable": True,
        "geometryRepairResultAvailable": True,
        "geometryRuntimeBindingResultAvailable": True,
        "geometryMaterialUvTransferAvailable": True,
        "geometryVisualShellReviewAvailable": True,
        "geometryCleanAcceptanceGateAvailable": True,
        "providerProvenanceAvailable": True,
        "geometryProviderRegistryAvailable": True,
        "manualGeometryImportAdapterDeclared": True,
        "manualGeometryImportAssetAvailable": True,
        "externalGeometryProvidersConfigured": False,
        "cleanGeometryProposalAvailable": False,
        "personalizedAvatarAvailable": False,
        "skeletalFallbackAvailable": False,
        "zeroOneStaticAvailable": False,
        "zeroOneDynamicAvailable": False,
        "mobileOptimisedAuthoritativeAsset": False,
    }


def _quality_reports(
    avatar_mesh: MeshSet,
    collision_mesh: MeshSet,
    pattern: dict[str, Any],
    semantic: dict[str, Any],
    rest_mesh: MeshSet,
    sim_mesh: MeshSet,
    render_mesh: MeshSet,
    constraints: dict[str, Any],
    binding_manifest: dict[str, object],
    settle_diagnostics: dict[str, Any],
    capture_record: dict[str, Any],
    capture_quality: dict[str, Any],
    visual_observations: dict[str, Any],
    correction_record: dict[str, Any],
    fit_report: dict[str, Any],
    texture_identity: dict[str, Any],
    geometry_proposal: dict[str, Any],
    raw_geometry_topology: dict[str, Any],
    geometry_cleanup_plan: dict[str, Any],
    geometry_cleanup_result: dict[str, Any],
    geometry_semantic_transfer: dict[str, Any],
    geometry_binding_candidate: dict[str, Any],
    geometry_binding_validation: dict[str, Any],
    geometry_repair_retopology_plan: dict[str, Any],
    geometry_repair_result: dict[str, Any],
    geometry_runtime_binding_result: dict[str, Any],
    geometry_material_uv_transfer: dict[str, Any],
    geometry_visual_shell_review: dict[str, Any],
    geometry_clean_acceptance_gate: dict[str, Any],
    clean_geometry_proposal: dict[str, Any],
    provider_registry: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    return {
        "capture_quality.json": {
            "schemaVersion": 1,
            "status": capture_quality["overallStatus"],
            "recordId": capture_record["recordId"],
            "recordVersion": capture_record["recordVersion"],
            "sourceKind": capture_record["sourceKind"],
            "viewCount": capture_quality["viewCount"],
            "overallScore": capture_quality["overallScore"],
            "qualityThreshold": capture_quality["qualityThreshold"],
            "privacy": capture_record["privacy"],
            "warnings": capture_quality["warnings"],
        },
        "visual_understanding_quality.json": {
            "schemaVersion": 1,
            "status": "pass",
            "visualUnderstandingId": visual_observations["visualUnderstandingId"],
            "sourceRecordId": visual_observations["sourceRecordId"],
            "maskCount": visual_observations["aggregate"]["maskCount"],
            "observedLandmarkCount": len(visual_observations["aggregate"]["observedLandmarks"]),
            "requiredLandmarkCount": len(visual_observations["aggregate"]["requiredLandmarks"]),
            "meanMaskConfidence": visual_observations["aggregate"]["meanMaskConfidence"],
            "meanLandmarkConfidence": visual_observations["aggregate"]["meanLandmarkConfidence"],
            "correctionRecordId": correction_record["correctionRecordId"],
            "correctionOperationCount": len(correction_record["operations"]),
            "warnings": visual_observations["warnings"],
        },
        "fitting_quality.json": {
            "schemaVersion": 1,
            "status": fit_report["status"],
            "fitReportId": fit_report["fitReportId"],
            "sourceVisualUnderstandingId": fit_report["sourceVisualUnderstandingId"],
            "accepted": fit_report["accepted"],
            "method": fit_report["method"],
            "losses": fit_report["losses"],
            "thresholds": fit_report["thresholds"],
            "warnings": fit_report["warnings"],
        },
        "texture_quality.json": {
            "schemaVersion": 1,
            "status": texture_identity["status"],
            "textureIdentityId": texture_identity["textureIdentityId"],
            "sourceTextureAvailable": texture_identity["sourceTextureAvailable"],
            "generatedAtlasAvailable": texture_identity["generatedAtlasAvailable"],
            "textureProjectionRun": texture_identity["textureProjectionRun"],
            "materialRegionCount": len(texture_identity["observedMaterialRegions"]),
            "recommendedAtlasSizePx": texture_identity["projectionPlan"]["recommendedAtlasSizePx"],
            "warnings": texture_identity["warnings"],
        },
        "geometry_proposal_quality.json": geometry_proposal_quality_report(geometry_proposal),
        "raw_geometry_topology.json": raw_geometry_topology,
        "geometry_cleanup_plan.json": geometry_cleanup_plan,
        "geometry_cleanup_result.json": geometry_cleanup_result,
        "geometry_semantic_transfer.json": geometry_semantic_transfer,
        "geometry_binding_candidate.json": geometry_binding_candidate,
        "geometry_binding_validation.json": geometry_binding_validation,
        "geometry_repair_retopology_plan.json": geometry_repair_retopology_plan,
        "geometry_repair_result.json": geometry_repair_result,
        "geometry_runtime_binding_result.json": geometry_runtime_binding_result,
        "geometry_material_uv_transfer.json": geometry_material_uv_transfer,
        "geometry_visual_shell_review.json": geometry_visual_shell_review,
        "geometry_clean_acceptance_gate.json": geometry_clean_acceptance_gate,
        "clean_geometry_proposal_quality.json": clean_geometry_proposal_quality_report(
            clean_geometry_proposal
        ),
        "provider_registry_quality.json": provider_registry_quality_report(provider_registry),
        "avatar_quality.json": {
            "schemaVersion": 1,
            "status": "pass",
            "avatarContractId": "avatar.closy_reference_v1",
            "mesh": _mesh_counts(avatar_mesh),
            "collisionMesh": _mesh_counts(collision_mesh),
            "limitations": ["synthetic_fixture", "not_anatomical", "not_skinned"],
        },
        "semantic_quality.json": {
            "schemaVersion": 1,
            "status": "pass",
            "componentCount": len(semantic["components"]),
            "seamCount": len(semantic["seams"]),
            "openingCount": len(semantic["openings"]),
        },
        "pattern_quality.json": {
            "schemaVersion": 1,
            "status": "pass",
            "panelCount": len(pattern["panels"]),
            "edgeCount": sum(len(panel["boundary"]) for panel in pattern["panels"]),
            "seamCount": len(pattern["seams"]),
            "openingCount": len(pattern["openings"]),
            "curvedConstruction": True,
        },
        "simulation_quality.json": {
            "schemaVersion": 1,
            "status": "pass",
            "assembly": "deterministic_reference_cpu_settle",
            "solverVersion": settle_diagnostics["solverVersion"],
            "convergenceState": settle_diagnostics["convergenceState"],
            "restMesh": _mesh_counts(rest_mesh),
            "mesh": _mesh_counts(sim_mesh),
            "constraintCount": len(constraints["constraints"]),
            "maximumSeamResidualMeters": settle_diagnostics["maximumSeamResidualMeters"],
            "rmsSeamResidualMeters": settle_diagnostics["rmsSeamResidualMeters"],
            "maximumBodyPenetrationMeters": settle_diagnostics["maximumBodyPenetrationMeters"],
            "maximumStrain": settle_diagnostics["maximumStrain"],
            "selfCollision": settle_diagnostics["selfCollision"],
            "inspectionExportPath": "simulation/simulation_mesh.glb",
        },
        "render_quality.json": {
            "schemaVersion": 1,
            "status": "pass",
            "mesh": _mesh_counts(render_mesh),
            "renderShellSeparateFromSimulation": True,
        },
        "binding_quality.json": {
            "schemaVersion": 1,
            "status": "pass",
            "recordCount": binding_manifest["recordCount"],
            "maximumReconstructionError": binding_manifest["maximumReconstructionError"],
            "rmsReconstructionError": binding_manifest["rmsReconstructionError"],
            "perturbationFollowTest": "supported_by_reconstruction_api",
        },
    }


def _provenance(
    params: TShirtParameters,
    seed: int,
    avatar_mesh: MeshSet,
    collision_mesh: MeshSet,
    rest_mesh: MeshSet,
    sim_mesh: MeshSet,
    render_mesh: MeshSet,
    binding_manifest: dict[str, object],
    settle_diagnostics: dict[str, Any],
    capture_record: dict[str, Any],
    capture_quality: dict[str, Any],
    visual_observations: dict[str, Any],
    correction_record: dict[str, Any],
    fit_report: dict[str, Any],
    texture_identity: dict[str, Any],
    geometry_proposal: dict[str, Any],
    raw_geometry_topology: dict[str, Any],
    geometry_cleanup_plan: dict[str, Any],
    geometry_cleanup_result: dict[str, Any],
    geometry_semantic_transfer: dict[str, Any],
    geometry_binding_candidate: dict[str, Any],
    geometry_binding_validation: dict[str, Any],
    geometry_repair_retopology_plan: dict[str, Any],
    geometry_repair_result: dict[str, Any],
    geometry_runtime_binding_result: dict[str, Any],
    geometry_material_uv_transfer: dict[str, Any],
    geometry_visual_shell_review: dict[str, Any],
    geometry_clean_acceptance_gate: dict[str, Any],
    clean_geometry_proposal: dict[str, Any],
    provider_registry: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "sourceKind": "procedural_fixture",
        "allowExternalApis": False,
        "allowTrainingUse": False,
        "containsUserImagery": False,
        "containsPersonalBodyData": False,
        "coordinateConvention": COORDINATE_CONVENTION,
        "sourceConvention": COORDINATE_CONVENTION,
        "appliedConversionMatrix": [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        "seed": seed,
        "fixedTimestamp": FIXED_TIMESTAMP,
        "stages": [
            _stage(
                "synthetic_capture_record",
                SYNTHETIC_CAPTURE_RECORD_VERSION,
                {
                    "sourceKind": capture_record["sourceKind"],
                    "viewCount": capture_record["captureSession"]["viewCount"],
                    "containsUserImagery": False,
                    "runtimeExternalApis": False,
                },
                [str(capture_record["immutability"]["sourceRecordHash"])],
            ),
            _stage(
                "capture_quality_scoring",
                CAPTURE_QUALITY_SCORER_VERSION,
                {
                    "qualityThreshold": capture_quality["qualityThreshold"],
                    "overallStatus": capture_quality["overallStatus"],
                    "rasterImagesAvailable": False,
                },
                [_json_hash(capture_quality)],
            ),
            _stage(
                "synthetic_visual_observations",
                TSHIRT_VISUAL_OBSERVATION_VERSION,
                {
                    "maskRepresentation": "normalised_polygon",
                    "requiredLandmarkCount": len(
                        visual_observations["aggregate"]["requiredLandmarks"]
                    ),
                    "externalApis": False,
                },
                [str(visual_observations["integrity"]["visualRecordHash"])],
            ),
            _stage(
                "empty_correction_record",
                CORRECTION_RECORD_VERSION,
                {"editable": True, "operationCount": 0, "externalApis": False},
                [str(correction_record["integrity"]["correctionRecordHash"])],
            ),
            _stage(
                "tshirt_visual_parameter_fit",
                TSHIRT_FIT_REPORT_VERSION,
                {
                    "method": fit_report["method"],
                    "accepted": bool(fit_report["accepted"]),
                    "status": fit_report["status"],
                },
                [str(fit_report["integrity"]["fitReportHash"])],
            ),
            _stage(
                "synthetic_texture_identity_scaffold",
                TEXTURE_IDENTITY_VERSION,
                {
                    "sourceTextureAvailable": False,
                    "generatedAtlasAvailable": False,
                    "textureProjectionRun": False,
                    "materialRegionCount": len(texture_identity["observedMaterialRegions"]),
                },
                [str(texture_identity["integrity"]["textureIdentityHash"])],
            ),
            _stage(
                "geometry_provider_registry",
                PROVIDER_REGISTRY_VERSION,
                {
                    "selectedProviderId": provider_registry["selectedProviderId"],
                    "manualLocalImportAdapterDeclared": provider_registry["d0Capabilities"][
                        "manualLocalImportAdapterDeclared"
                    ],
                    "manualLocalImportAssetAvailable": provider_registry["d0Capabilities"][
                        "manualLocalImportAssetAvailable"
                    ],
                    "externalProvidersConfigured": False,
                    "supportedDomain": provider_registry["scope"]["supportedDomain"],
                },
                [str(provider_registry["integrity"]["providerRegistryHash"])],
            ),
            _stage(
                "manual_local_geometry_proposal_provider",
                GEOMETRY_PROPOSAL_VERSION,
                {
                    "providerId": geometry_proposal["provider"]["providerId"],
                    "providerKind": geometry_proposal["provider"]["providerKind"],
                    "runtimeExternalApis": False,
                    "rawProposalAvailable": geometry_proposal["rawProposal"]["available"],
                    "cleanProposalAvailable": False,
                    "acceptedForCanonical": False,
                    "rejectionReasons": geometry_proposal["quality"]["rejectionReasons"],
                },
                [str(geometry_proposal["integrity"]["geometryProposalHash"])],
            ),
            _stage(
                "raw_geometry_topology_diagnostics",
                RAW_GEOMETRY_TOPOLOGY_REPORT_VERSION,
                {
                    "sourceRawProposalId": raw_geometry_topology["sourceRawProposalId"],
                    "meshCount": raw_geometry_topology["topology"]["meshCount"],
                    "componentCount": raw_geometry_topology["topology"]["componentCount"],
                    "nonManifoldEdgeCount": raw_geometry_topology["topology"][
                        "nonManifoldEdgeCount"
                    ],
                    "degenerateTriangleCount": raw_geometry_topology["topology"][
                        "degenerateTriangleCount"
                    ],
                    "acceptedForCleanProposal": False,
                },
                [str(raw_geometry_topology["integrity"]["rawGeometryTopologyReportHash"])],
            ),
            _stage(
                "geometry_cleanup_plan",
                GEOMETRY_CLEANUP_PLAN_VERSION,
                {
                    "sourceRawTopologyReportId": geometry_cleanup_plan["sourceRawTopologyReportId"],
                    "recommendedOperationCount": len(
                        geometry_cleanup_plan["recommendedOperations"]
                    ),
                    "cleanupRun": False,
                    "repairRun": False,
                    "acceptedForCleanProposal": False,
                    "status": geometry_cleanup_plan["readiness"]["status"],
                },
                [str(geometry_cleanup_plan["integrity"]["geometryCleanupPlanHash"])],
            ),
            _stage(
                "local_geometry_cleanup_adapter",
                GEOMETRY_CLEANUP_RESULT_VERSION,
                {
                    "adapterId": geometry_cleanup_result["adapterId"],
                    "cleanupRun": geometry_cleanup_result["execution"]["cleanupRun"],
                    "repairRun": geometry_cleanup_result["execution"]["repairRun"],
                    "outputAssetPath": geometry_cleanup_result["outputAsset"]["path"],
                    "acceptedForCleanProposal": False,
                    "deferredOperationCount": len(geometry_cleanup_result["deferredOperations"]),
                    "status": geometry_cleanup_result["readiness"]["status"],
                },
                [str(geometry_cleanup_result["integrity"]["geometryCleanupResultHash"])],
            ),
            _stage(
                "geometry_semantic_transfer",
                GEOMETRY_SEMANTIC_TRANSFER_VERSION,
                {
                    "sourceGeometryCleanupResultId": geometry_semantic_transfer[
                        "sourceGeometryCleanupResultId"
                    ],
                    "semanticTransferRun": geometry_semantic_transfer["execution"][
                        "semanticTransferRun"
                    ],
                    "boundaryClassificationRun": geometry_semantic_transfer["execution"][
                        "boundaryClassificationRun"
                    ],
                    "transferredPanelCount": geometry_semantic_transfer["aggregate"][
                        "transferredPanelCount"
                    ],
                    "classifiedBoundaryEdgeCount": geometry_semantic_transfer["aggregate"][
                        "classifiedBoundaryEdgeCount"
                    ],
                    "acceptedForCleanProposal": False,
                    "status": geometry_semantic_transfer["readiness"]["status"],
                },
                [str(geometry_semantic_transfer["integrity"]["geometrySemanticTransferHash"])],
            ),
            _stage(
                "geometry_binding_candidate",
                GEOMETRY_BINDING_CANDIDATE_VERSION,
                {
                    "sourceGeometrySemanticTransferId": geometry_binding_candidate[
                        "sourceGeometrySemanticTransferId"
                    ],
                    "candidateBindingRun": geometry_binding_candidate["execution"][
                        "candidateBindingRun"
                    ],
                    "simulationBindingRun": geometry_binding_candidate["execution"][
                        "simulationBindingRun"
                    ],
                    "mappedVertexCount": geometry_binding_candidate["aggregate"][
                        "mappedVertexCount"
                    ],
                    "unmappedVertexCount": geometry_binding_candidate["aggregate"][
                        "unmappedVertexCount"
                    ],
                    "candidateCompleteness": geometry_binding_candidate["aggregate"][
                        "candidateCompleteness"
                    ],
                    "acceptedForCleanProposal": False,
                    "status": geometry_binding_candidate["readiness"]["status"],
                },
                [str(geometry_binding_candidate["integrity"]["geometryBindingCandidateHash"])],
            ),
            _stage(
                "geometry_binding_validation",
                GEOMETRY_BINDING_VALIDATION_VERSION,
                {
                    "sourceGeometryBindingCandidateId": geometry_binding_validation[
                        "sourceGeometryBindingCandidateId"
                    ],
                    "deformationValidationRun": geometry_binding_validation["execution"][
                        "deformationValidationRun"
                    ],
                    "runtimeBindingAccepted": geometry_binding_validation["execution"][
                        "runtimeBindingAccepted"
                    ],
                    "maxCleanupToSettledOffsetMeters": geometry_binding_validation["aggregate"][
                        "maxCleanupToSettledOffsetMeters"
                    ],
                    "rmsCleanupToSettledOffsetMeters": geometry_binding_validation["aggregate"][
                        "rmsCleanupToSettledOffsetMeters"
                    ],
                    "failedCheckCount": geometry_binding_validation["quality"]["failedCheckCount"],
                    "notRunCheckCount": geometry_binding_validation["quality"]["notRunCheckCount"],
                    "acceptedForCleanProposal": False,
                    "status": geometry_binding_validation["readiness"]["status"],
                },
                [str(geometry_binding_validation["integrity"]["geometryBindingValidationHash"])],
            ),
            _stage(
                "geometry_repair_retopology_plan",
                GEOMETRY_REPAIR_RETOPOLOGY_PLAN_VERSION,
                {
                    "sourceGeometryBindingValidationId": geometry_repair_retopology_plan[
                        "sourceGeometryBindingValidationId"
                    ],
                    "repairRetopologyPlanGenerated": geometry_repair_retopology_plan["execution"][
                        "repairRetopologyPlanGenerated"
                    ],
                    "requiredOperationCount": geometry_repair_retopology_plan["aggregate"][
                        "requiredOperationCount"
                    ],
                    "deformationFailedVertexCount": geometry_repair_retopology_plan["aggregate"][
                        "deformationFailedVertexCount"
                    ],
                    "estimatedRepairComplexity": geometry_repair_retopology_plan["aggregate"][
                        "estimatedRepairComplexity"
                    ],
                    "repairRun": geometry_repair_retopology_plan["execution"]["repairRun"],
                    "retopologyRun": geometry_repair_retopology_plan["execution"]["retopologyRun"],
                    "acceptedForCleanProposal": False,
                    "status": geometry_repair_retopology_plan["readiness"]["status"],
                },
                [
                    str(
                        geometry_repair_retopology_plan["integrity"][
                            "geometryRepairRetopologyPlanHash"
                        ]
                    )
                ],
            ),
            _stage(
                "geometry_repair_partial_reprojection",
                GEOMETRY_REPAIR_RESULT_VERSION,
                {
                    "sourceGeometryRepairRetopologyPlanId": geometry_repair_result[
                        "sourceGeometryRepairRetopologyPlanId"
                    ],
                    "deformationReprojectionRun": geometry_repair_result["execution"][
                        "deformationReprojectionRun"
                    ],
                    "movedVertexCount": geometry_repair_result["aggregate"]["movedVertexCount"],
                    "deferredOperationCount": geometry_repair_result["aggregate"][
                        "deferredOperationCount"
                    ],
                    "retopologyRun": geometry_repair_result["execution"]["retopologyRun"],
                    "runtimeBindingAccepted": geometry_repair_result["execution"][
                        "runtimeBindingAccepted"
                    ],
                    "acceptedForCleanProposal": False,
                    "status": geometry_repair_result["readiness"]["status"],
                },
                [str(geometry_repair_result["integrity"]["geometryRepairResultHash"])],
            ),
            _stage(
                "geometry_runtime_binding_result",
                GEOMETRY_RUNTIME_BINDING_RESULT_VERSION,
                {
                    "sourceGeometryRepairResultId": geometry_runtime_binding_result[
                        "sourceGeometryRepairResultId"
                    ],
                    "retopologyRun": geometry_runtime_binding_result["execution"]["retopologyRun"],
                    "seamSplitRun": geometry_runtime_binding_result["execution"]["seamSplitRun"],
                    "componentStitchingRun": geometry_runtime_binding_result["execution"][
                        "componentStitchingRun"
                    ],
                    "runtimeBindingWritten": geometry_runtime_binding_result["execution"][
                        "runtimeBindingWritten"
                    ],
                    "runtimeBindingAccepted": geometry_runtime_binding_result["execution"][
                        "runtimeBindingAccepted"
                    ],
                    "recordCount": geometry_runtime_binding_result["aggregate"][
                        "runtimeBindingRecordCount"
                    ],
                    "acceptedForCleanProposal": False,
                    "status": geometry_runtime_binding_result["readiness"]["status"],
                },
                [
                    str(
                        geometry_runtime_binding_result["integrity"][
                            "geometryRuntimeBindingResultHash"
                        ]
                    )
                ],
            ),
            _stage(
                "geometry_material_uv_transfer",
                GEOMETRY_MATERIAL_UV_TRANSFER_VERSION,
                {
                    "sourceGeometryRuntimeBindingResultId": geometry_material_uv_transfer[
                        "sourceGeometryRuntimeBindingResultId"
                    ],
                    "sourceTextureIdentityId": geometry_material_uv_transfer[
                        "sourceTextureIdentityId"
                    ],
                    "uvTransferRun": geometry_material_uv_transfer["execution"]["uvTransferRun"],
                    "materialTransferRun": geometry_material_uv_transfer["execution"][
                        "materialTransferRun"
                    ],
                    "acceptedForMaterialPreview": geometry_material_uv_transfer["readiness"][
                        "acceptedForMaterialPreview"
                    ],
                    "sourceTextureProjectionRun": geometry_material_uv_transfer["execution"][
                        "sourceTextureProjectionRun"
                    ],
                    "status": geometry_material_uv_transfer["readiness"]["status"],
                },
                [str(geometry_material_uv_transfer["integrity"]["geometryMaterialUvTransferHash"])],
            ),
            _stage(
                "geometry_visual_shell_review",
                GEOMETRY_VISUAL_SHELL_REVIEW_VERSION,
                {
                    "sourceGeometryRuntimeBindingResultId": geometry_visual_shell_review[
                        "sourceGeometryRuntimeBindingResultId"
                    ],
                    "sourceGeometryMaterialUvTransferId": geometry_visual_shell_review[
                        "sourceGeometryMaterialUvTransferId"
                    ],
                    "visualFidelityReviewRun": geometry_visual_shell_review["execution"][
                        "visualFidelityReviewRun"
                    ],
                    "renderedPixelComparisonRun": geometry_visual_shell_review["execution"][
                        "renderedPixelComparisonRun"
                    ],
                    "singleShellWeldProofRun": geometry_visual_shell_review["execution"][
                        "singleShellWeldProofRun"
                    ],
                    "acceptedForVisualFidelity": geometry_visual_shell_review["readiness"][
                        "acceptedForVisualFidelity"
                    ],
                    "singleShellWeldProven": geometry_visual_shell_review["readiness"][
                        "singleShellWeldProven"
                    ],
                    "status": geometry_visual_shell_review["readiness"]["status"],
                },
                [str(geometry_visual_shell_review["integrity"]["geometryVisualShellReviewHash"])],
            ),
            _stage(
                "geometry_clean_acceptance_gate",
                GEOMETRY_CLEAN_ACCEPTANCE_GATE_VERSION,
                {
                    "sourceGeometryRuntimeBindingResultId": geometry_clean_acceptance_gate[
                        "sourceGeometryRuntimeBindingResultId"
                    ],
                    "cleanAcceptanceGateRun": geometry_clean_acceptance_gate["execution"][
                        "cleanAcceptanceGateRun"
                    ],
                    "runtimeBindingEvidenceReviewed": geometry_clean_acceptance_gate["execution"][
                        "runtimeBindingEvidenceReviewed"
                    ],
                    "visualFidelityReviewRun": geometry_clean_acceptance_gate["execution"][
                        "visualFidelityReviewRun"
                    ],
                    "materialTransferRun": geometry_clean_acceptance_gate["execution"][
                        "materialTransferRun"
                    ],
                    "singleShellWeldProofRun": geometry_clean_acceptance_gate["execution"][
                        "singleShellWeldProofRun"
                    ],
                    "acceptedForCleanProposal": geometry_clean_acceptance_gate["readiness"][
                        "acceptedForCleanProposal"
                    ],
                    "status": geometry_clean_acceptance_gate["readiness"]["status"],
                },
                [
                    str(
                        geometry_clean_acceptance_gate["integrity"][
                            "geometryCleanAcceptanceGateHash"
                        ]
                    )
                ],
            ),
            _stage(
                "clean_geometry_proposal_rejection",
                CLEAN_GEOMETRY_PROPOSAL_VERSION,
                {
                    "sourceRawProposalId": clean_geometry_proposal["sourceRawProposalId"],
                    "sourceRawTopologyReportId": clean_geometry_proposal[
                        "sourceRawTopologyReportId"
                    ],
                    "sourceGeometryCleanupPlanId": clean_geometry_proposal[
                        "sourceGeometryCleanupPlanId"
                    ],
                    "sourceGeometryCleanupResultId": clean_geometry_proposal[
                        "sourceGeometryCleanupResultId"
                    ],
                    "sourceGeometrySemanticTransferId": clean_geometry_proposal[
                        "sourceGeometrySemanticTransferId"
                    ],
                    "sourceGeometryBindingCandidateId": clean_geometry_proposal[
                        "sourceGeometryBindingCandidateId"
                    ],
                    "sourceGeometryBindingValidationId": clean_geometry_proposal[
                        "sourceGeometryBindingValidationId"
                    ],
                    "sourceGeometryRepairRetopologyPlanId": clean_geometry_proposal[
                        "sourceGeometryRepairRetopologyPlanId"
                    ],
                    "sourceGeometryRepairResultId": clean_geometry_proposal[
                        "sourceGeometryRepairResultId"
                    ],
                    "sourceGeometryRuntimeBindingResultId": clean_geometry_proposal[
                        "sourceGeometryRuntimeBindingResultId"
                    ],
                    "sourceGeometryVisualShellReviewId": clean_geometry_proposal[
                        "sourceGeometryVisualShellReviewId"
                    ],
                    "sourceGeometryCleanAcceptanceGateId": clean_geometry_proposal[
                        "sourceGeometryCleanAcceptanceGateId"
                    ],
                    "topologyDiagnosticsRun": True,
                    "cleanupPlanGenerated": True,
                    "cleanupResultGenerated": True,
                    "semanticTransferReportGenerated": True,
                    "bindingCandidateReportGenerated": True,
                    "bindingValidationReportGenerated": True,
                    "repairRetopologyPlanGenerated": True,
                    "partialRepairResultGenerated": True,
                    "runtimeBindingResultGenerated": clean_geometry_proposal["cleanupPipeline"][
                        "runtimeBindingResultGenerated"
                    ],
                    "visualShellReviewGenerated": clean_geometry_proposal["cleanupPipeline"][
                        "visualShellReviewGenerated"
                    ],
                    "cleanAcceptanceGateGenerated": clean_geometry_proposal["cleanupPipeline"][
                        "cleanAcceptanceGateGenerated"
                    ],
                    "cleanupRun": True,
                    "repairRun": False,
                    "retopologyRun": clean_geometry_proposal["cleanupPipeline"]["retopologyRun"],
                    "seamSplitRun": clean_geometry_proposal["cleanupPipeline"]["seamSplitRun"],
                    "componentStitchingRun": clean_geometry_proposal["cleanupPipeline"][
                        "componentStitchingRun"
                    ],
                    "deformationReprojectionRun": True,
                    "semanticTransferRun": True,
                    "boundaryClassificationRun": True,
                    "candidateBindingRun": True,
                    "deformationValidationRun": True,
                    "simulationBindingRun": clean_geometry_proposal["cleanupPipeline"][
                        "simulationBindingRun"
                    ],
                    "runtimeBindingWritten": clean_geometry_proposal["cleanupPipeline"][
                        "runtimeBindingWritten"
                    ],
                    "runtimeBindingAccepted": clean_geometry_proposal["cleanupPipeline"][
                        "runtimeBindingAccepted"
                    ],
                    "cleanAcceptanceGateRun": clean_geometry_proposal["cleanupPipeline"][
                        "cleanAcceptanceGateRun"
                    ],
                    "cleanAcceptanceGateAccepted": clean_geometry_proposal["cleanupPipeline"][
                        "cleanAcceptanceGateAccepted"
                    ],
                    "visualFidelityReviewRun": clean_geometry_proposal["cleanupPipeline"][
                        "visualFidelityReviewRun"
                    ],
                    "providerVisualFidelityAccepted": clean_geometry_proposal["cleanupPipeline"][
                        "providerVisualFidelityAccepted"
                    ],
                    "singleShellWeldProofRun": clean_geometry_proposal["cleanupPipeline"][
                        "singleShellWeldProofRun"
                    ],
                    "singleShellWeldProven": clean_geometry_proposal["cleanupPipeline"][
                        "singleShellWeldProven"
                    ],
                    "acceptedForCanonical": False,
                    "rejectionReasons": clean_geometry_proposal["quality"]["rejectionReasons"],
                },
                [str(clean_geometry_proposal["integrity"]["cleanGeometryProposalHash"])],
            ),
            _stage(
                "reference_avatar_parameters",
                "closy.reference_avatar.parameters.v1",
                {},
                [topology_hash(avatar_mesh)],
            ),
            _stage(
                "reference_avatar_collision_generator",
                "closy.reference_avatar.collision.v1",
                {},
                [topology_hash(collision_mesh)],
            ),
            _stage("tshirt_parameters", "closy.tshirt.parameters.v1", asdict(params), []),
            _stage("pattern_generator", "closy.tshirt.pattern.v1", params.to_json(), []),
            _stage("curve_sampler", "closy.curve_sampler.v1", {"deterministic": True}, []),
            _stage(
                "panel_triangulator",
                "closy.fan_triangulator.v1",
                {"winding": "ccw"},
                [topology_hash(rest_mesh)],
            ),
            _stage(
                "reference_cloth_settle",
                "closy.reference_xpbd_cpu.v1",
                {
                    "clothSettleRun": True,
                    "convergenceState": str(settle_diagnostics["convergenceState"]),
                    "selfCollisionAvailable": False,
                    "settings": settle_diagnostics["settings"],
                },
                [
                    str(settle_diagnostics["restContentHash"]),
                    str(settle_diagnostics["settledContentHash"]),
                ],
            ),
            _stage(
                "render_subdivision",
                "closy.render_subdivision.v1",
                {"splitEachTriangleInto": 4},
                [topology_hash(render_mesh)],
            ),
            _stage(
                "barycentric_binding",
                "closy.barycentric.subdivision_binding.v1",
                {},
                [
                    str(binding_manifest["simulationTopologyHash"]),
                    str(binding_manifest["renderTopologyHash"]),
                ],
            ),
            _stage("glb_package_writer", "closy.glb_writer.v1", {"format": "glb2"}, []),
        ],
        "warnings": [
            "self_collision_not_run",
            "source_texture_projection_not_run",
            "manual_raw_geometry_proposal_not_canonical",
            "geometry_binding_candidate_not_runtime_binding",
            "geometry_binding_validation_rejected_runtime_binding",
            "clean_geometry_proposal_not_available",
            "zeroone_unavailable_optional",
        ],
    }


def _stage(
    stage_id: str,
    version: str,
    settings: Mapping[str, object],
    output_hashes: list[str],
) -> dict[str, object]:
    return {
        "stageId": stage_id,
        "version": version,
        "inputFingerprint": _stable_stage_fingerprint(stage_id, settings),
        "settings": settings,
        "outputHashes": output_hashes,
        "status": "pass",
        "warnings": [],
        "recoverability": "regenerable_from_authored_fixture_inputs",
    }


def _stable_stage_fingerprint(stage_id: str, settings: Mapping[str, object]) -> str:
    import json
    from hashlib import sha256

    payload = json.dumps(
        {"stageId": stage_id, "settings": settings}, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _summary_json(context: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
    manifest = context["manifest"]
    pattern = context["pattern"]
    sim_mesh = context["simulationMesh"]
    render_mesh = context["renderMesh"]
    constraints = context["constraints"]
    settle = context["settleDiagnostics"]
    capture_record = context["captureRecord"]
    capture_quality = context["captureQuality"]
    visual_observations = context["visualObservations"]
    correction_record = context["correctionRecord"]
    fit_report = context["fitReport"]
    texture_identity = context["textureIdentity"]
    geometry_proposal = context["geometryProposal"]
    raw_geometry_topology = context["rawGeometryTopology"]
    geometry_cleanup_plan = context["geometryCleanupPlan"]
    geometry_cleanup_result = context["geometryCleanupResult"]
    geometry_semantic_transfer = context["geometrySemanticTransfer"]
    geometry_binding_candidate = context["geometryBindingCandidate"]
    geometry_binding_validation = context["geometryBindingValidation"]
    geometry_repair_retopology_plan = context["geometryRepairRetopologyPlan"]
    geometry_repair_result = context["geometryRepairResult"]
    geometry_runtime_binding_result = context["geometryRuntimeBindingResult"]
    geometry_material_uv_transfer = context["geometryMaterialUvTransfer"]
    geometry_visual_shell_review = context["geometryVisualShellReview"]
    geometry_clean_acceptance_gate = context["geometryCleanAcceptanceGate"]
    clean_geometry_proposal = context["cleanGeometryProposal"]
    provider_registry = context["providerRegistry"]
    return {
        "schemaVersion": 1,
        "garmentId": manifest["garmentId"],
        "packageDigest": manifest["canonicalPackageDigest"],
        "counts": {
            "panels": len(pattern["panels"]),
            "edges": sum(len(panel["boundary"]) for panel in pattern["panels"]),
            "seams": len(pattern["seams"]),
            "openings": len(pattern["openings"]),
            "constraints": len(constraints["constraints"]),
            "simulationVertices": sim_mesh.vertex_count,
            "simulationTriangles": sim_mesh.triangle_count,
            "renderVertices": render_mesh.vertex_count,
            "renderTriangles": render_mesh.triangle_count,
            "inventoriedFiles": len(manifest["inventory"]),
        },
        "capture": {
            "recordId": capture_record["recordId"],
            "sourceKind": capture_record["sourceKind"],
            "viewCount": capture_quality["viewCount"],
            "overallStatus": capture_quality["overallStatus"],
            "overallScore": capture_quality["overallScore"],
            "scorerVersion": capture_quality["scorerVersion"],
            "containsUserImagery": capture_record["privacy"]["containsUserImagery"],
            "externalApisAllowed": capture_record["privacy"]["allowExternalApis"],
        },
        "visualUnderstanding": {
            "visualUnderstandingId": visual_observations["visualUnderstandingId"],
            "maskCount": visual_observations["aggregate"]["maskCount"],
            "observedLandmarkCount": len(visual_observations["aggregate"]["observedLandmarks"]),
            "requiredLandmarkCount": len(visual_observations["aggregate"]["requiredLandmarks"]),
            "meanMaskConfidence": visual_observations["aggregate"]["meanMaskConfidence"],
            "meanLandmarkConfidence": visual_observations["aggregate"]["meanLandmarkConfidence"],
            "correctionRecordId": correction_record["correctionRecordId"],
            "correctionOperationCount": len(correction_record["operations"]),
        },
        "fitting": {
            "fitReportId": fit_report["fitReportId"],
            "fitterVersion": fit_report["fitterVersion"],
            "status": fit_report["status"],
            "accepted": fit_report["accepted"],
            "landmarkRmsNormalised": fit_report["losses"]["landmarkRmsNormalised"],
            "maskWidthErrorMeters": fit_report["losses"]["maskWidthErrorMeters"],
            "fittedParameters": fit_report["fittedParameters"],
        },
        "texture": {
            "textureIdentityId": texture_identity["textureIdentityId"],
            "status": texture_identity["status"],
            "sourceTextureAvailable": texture_identity["sourceTextureAvailable"],
            "generatedAtlasAvailable": texture_identity["generatedAtlasAvailable"],
            "textureProjectionRun": texture_identity["textureProjectionRun"],
            "materialRegionCount": len(texture_identity["observedMaterialRegions"]),
            "recommendedAtlasSizePx": texture_identity["projectionPlan"]["recommendedAtlasSizePx"],
        },
        "geometryProposal": {
            "proposalId": geometry_proposal["proposalId"],
            "providerId": geometry_proposal["provider"]["providerId"],
            "providerKind": geometry_proposal["provider"]["providerKind"],
            "qualityStatus": geometry_proposal["quality"]["status"],
            "rawProposalAvailable": geometry_proposal["rawProposal"]["available"],
            "cleanProposalAvailable": geometry_proposal["cleanProposal"]["available"],
            "acceptedForCanonical": geometry_proposal["quality"]["acceptedForCanonical"],
            "meshCount": geometry_proposal["geometryAudit"]["meshCount"],
            "visibleMeshCount": geometry_proposal["geometryAudit"]["visibleMeshCount"],
            "triangleEstimate": geometry_proposal["geometryAudit"]["triangleEstimate"],
            "failureReason": geometry_proposal["geometryAudit"]["failureReason"],
        },
        "rawGeometryTopology": {
            "reportId": raw_geometry_topology["reportId"],
            "sourceRawProposalId": raw_geometry_topology["sourceRawProposalId"],
            "meshCount": raw_geometry_topology["topology"]["meshCount"],
            "componentCount": raw_geometry_topology["topology"]["componentCount"],
            "largestComponentTriangleCount": raw_geometry_topology["topology"][
                "largestComponentTriangleCount"
            ],
            "boundaryEdgeCount": raw_geometry_topology["topology"]["boundaryEdgeCount"],
            "nonManifoldEdgeCount": raw_geometry_topology["topology"]["nonManifoldEdgeCount"],
            "degenerateTriangleCount": raw_geometry_topology["topology"]["degenerateTriangleCount"],
            "duplicatePositionCount": raw_geometry_topology["topology"]["duplicatePositionCount"],
            "manifoldStatus": raw_geometry_topology["topology"]["manifoldStatus"],
            "acceptedForCleanProposal": raw_geometry_topology["cleanReadiness"][
                "acceptedForCleanProposal"
            ],
        },
        "geometryCleanupPlan": {
            "reportId": geometry_cleanup_plan["reportId"],
            "sourceRawProposalId": geometry_cleanup_plan["sourceRawProposalId"],
            "sourceRawTopologyReportId": geometry_cleanup_plan["sourceRawTopologyReportId"],
            "status": geometry_cleanup_plan["readiness"]["status"],
            "estimatedRepairComplexity": geometry_cleanup_plan["readiness"][
                "estimatedRepairComplexity"
            ],
            "recommendedOperationCount": len(geometry_cleanup_plan["recommendedOperations"]),
            "requiredOperationCount": sum(
                1
                for operation in geometry_cleanup_plan["recommendedOperations"]
                if operation["required"]
            ),
            "cleanupRun": geometry_cleanup_plan["execution"]["cleanupRun"],
            "repairRun": geometry_cleanup_plan["execution"]["repairRun"],
            "acceptedForCleanProposal": geometry_cleanup_plan["readiness"][
                "acceptedForCleanProposal"
            ],
        },
        "geometryCleanupResult": {
            "reportId": geometry_cleanup_result["reportId"],
            "sourceGeometryCleanupPlanId": geometry_cleanup_result["sourceGeometryCleanupPlanId"],
            "status": geometry_cleanup_result["readiness"]["status"],
            "outputAssetPath": geometry_cleanup_result["outputAsset"]["path"],
            "cleanupRun": geometry_cleanup_result["execution"]["cleanupRun"],
            "repairRun": geometry_cleanup_result["execution"]["repairRun"],
            "verticesBefore": geometry_cleanup_result["topologyBefore"]["vertexCount"],
            "verticesAfter": geometry_cleanup_result["topologyAfter"]["vertexCount"],
            "duplicatePositionCountBefore": geometry_cleanup_result["topologyBefore"][
                "duplicatePositionCount"
            ],
            "duplicatePositionCountAfter": geometry_cleanup_result["topologyAfter"][
                "duplicatePositionCount"
            ],
            "removedDuplicateVertexCount": _operation_removed_count(
                geometry_cleanup_result, "duplicate_position_weld"
            ),
            "removedDegenerateTriangleCount": _operation_removed_count(
                geometry_cleanup_result, "degenerate_triangle_removal"
            ),
            "deferredOperationCount": len(geometry_cleanup_result["deferredOperations"]),
            "acceptedForCleanProposal": geometry_cleanup_result["readiness"][
                "acceptedForCleanProposal"
            ],
        },
        "geometrySemanticTransfer": {
            "reportId": geometry_semantic_transfer["reportId"],
            "sourceGeometryCleanupResultId": geometry_semantic_transfer[
                "sourceGeometryCleanupResultId"
            ],
            "status": geometry_semantic_transfer["readiness"]["status"],
            "semanticTransferRun": geometry_semantic_transfer["execution"]["semanticTransferRun"],
            "boundaryClassificationRun": geometry_semantic_transfer["execution"][
                "boundaryClassificationRun"
            ],
            "transferredPanelCount": geometry_semantic_transfer["aggregate"][
                "transferredPanelCount"
            ],
            "expectedPanelCount": geometry_semantic_transfer["aggregate"]["expectedPanelCount"],
            "classifiedBoundaryEdgeCount": geometry_semantic_transfer["aggregate"][
                "classifiedBoundaryEdgeCount"
            ],
            "boundaryEdgeCount": geometry_semantic_transfer["aggregate"]["boundaryEdgeCount"],
            "unclassifiedBoundaryEdgeCount": geometry_semantic_transfer["aggregate"][
                "unclassifiedBoundaryEdgeCount"
            ],
            "ambiguousBoundaryEdgeCount": geometry_semantic_transfer["aggregate"][
                "ambiguousBoundaryEdgeCount"
            ],
            "classificationCompleteness": geometry_semantic_transfer["aggregate"][
                "classificationCompleteness"
            ],
            "acceptedForCleanProposal": geometry_semantic_transfer["readiness"][
                "acceptedForCleanProposal"
            ],
        },
        "geometryBindingCandidate": {
            "reportId": geometry_binding_candidate["reportId"],
            "sourceGeometrySemanticTransferId": geometry_binding_candidate[
                "sourceGeometrySemanticTransferId"
            ],
            "status": geometry_binding_candidate["readiness"]["status"],
            "candidateBindingRun": geometry_binding_candidate["execution"]["candidateBindingRun"],
            "simulationBindingRun": geometry_binding_candidate["execution"]["simulationBindingRun"],
            "runtimeBindingWritten": geometry_binding_candidate["execution"][
                "runtimeBindingWritten"
            ],
            "mappedVertexCount": geometry_binding_candidate["aggregate"]["mappedVertexCount"],
            "cleanupVertexCount": geometry_binding_candidate["aggregate"]["cleanupVertexCount"],
            "unmappedVertexCount": geometry_binding_candidate["aggregate"]["unmappedVertexCount"],
            "candidateCompleteness": geometry_binding_candidate["aggregate"][
                "candidateCompleteness"
            ],
            "maxPanelUvDistance": geometry_binding_candidate["aggregate"]["maxPanelUvDistance"],
            "maxRestToSimulationOffsetMeters": geometry_binding_candidate["aggregate"][
                "maxRestToSimulationOffsetMeters"
            ],
            "acceptedForCleanProposal": geometry_binding_candidate["readiness"][
                "acceptedForCleanProposal"
            ],
        },
        "geometryBindingValidation": {
            "reportId": geometry_binding_validation["reportId"],
            "sourceGeometryBindingCandidateId": geometry_binding_validation[
                "sourceGeometryBindingCandidateId"
            ],
            "status": geometry_binding_validation["readiness"]["status"],
            "deformationValidationRun": geometry_binding_validation["execution"][
                "deformationValidationRun"
            ],
            "runtimeBindingAccepted": geometry_binding_validation["execution"][
                "runtimeBindingAccepted"
            ],
            "validationRecordCount": geometry_binding_validation["aggregate"][
                "validationRecordCount"
            ],
            "failedCheckCount": geometry_binding_validation["quality"]["failedCheckCount"],
            "notRunCheckCount": geometry_binding_validation["quality"]["notRunCheckCount"],
            "maxCleanupToSettledOffsetMeters": geometry_binding_validation["aggregate"][
                "maxCleanupToSettledOffsetMeters"
            ],
            "rmsCleanupToSettledOffsetMeters": geometry_binding_validation["aggregate"][
                "rmsCleanupToSettledOffsetMeters"
            ],
            "acceptedForCleanProposal": geometry_binding_validation["readiness"][
                "acceptedForCleanProposal"
            ],
        },
        "geometryRepairRetopologyPlan": {
            "reportId": geometry_repair_retopology_plan["reportId"],
            "sourceGeometryBindingValidationId": geometry_repair_retopology_plan[
                "sourceGeometryBindingValidationId"
            ],
            "status": geometry_repair_retopology_plan["readiness"]["status"],
            "repairRetopologyPlanGenerated": geometry_repair_retopology_plan["execution"][
                "repairRetopologyPlanGenerated"
            ],
            "repairRun": geometry_repair_retopology_plan["execution"]["repairRun"],
            "retopologyRun": geometry_repair_retopology_plan["execution"]["retopologyRun"],
            "seamSplitRun": geometry_repair_retopology_plan["execution"]["seamSplitRun"],
            "recommendedOperationCount": geometry_repair_retopology_plan["aggregate"][
                "recommendedOperationCount"
            ],
            "requiredOperationCount": geometry_repair_retopology_plan["aggregate"][
                "requiredOperationCount"
            ],
            "deformationFailedVertexCount": geometry_repair_retopology_plan["aggregate"][
                "deformationFailedVertexCount"
            ],
            "estimatedRepairComplexity": geometry_repair_retopology_plan["aggregate"][
                "estimatedRepairComplexity"
            ],
            "acceptedForCleanProposal": geometry_repair_retopology_plan["readiness"][
                "acceptedForCleanProposal"
            ],
        },
        "geometryRepairResult": {
            "reportId": geometry_repair_result["reportId"],
            "sourceGeometryRepairRetopologyPlanId": geometry_repair_result[
                "sourceGeometryRepairRetopologyPlanId"
            ],
            "status": geometry_repair_result["readiness"]["status"],
            "repairResultGenerated": geometry_repair_result["execution"]["repairResultGenerated"],
            "deformationReprojectionRun": geometry_repair_result["execution"][
                "deformationReprojectionRun"
            ],
            "repairRun": geometry_repair_result["execution"]["repairRun"],
            "retopologyRun": geometry_repair_result["execution"]["retopologyRun"],
            "seamSplitRun": geometry_repair_result["execution"]["seamSplitRun"],
            "movedVertexCount": geometry_repair_result["aggregate"]["movedVertexCount"],
            "unmappedVertexCount": geometry_repair_result["aggregate"]["unmappedVertexCount"],
            "executedOperationCount": geometry_repair_result["aggregate"]["executedOperationCount"],
            "deferredOperationCount": geometry_repair_result["aggregate"]["deferredOperationCount"],
            "maxOutputToSettledOffsetMeters": geometry_repair_result["aggregate"][
                "maxOutputToSettledOffsetMeters"
            ],
            "acceptedForCleanProposal": geometry_repair_result["readiness"][
                "acceptedForCleanProposal"
            ],
        },
        "geometryRuntimeBindingResult": {
            "reportId": geometry_runtime_binding_result["reportId"],
            "sourceGeometryRepairResultId": geometry_runtime_binding_result[
                "sourceGeometryRepairResultId"
            ],
            "status": geometry_runtime_binding_result["readiness"]["status"],
            "retopologyRun": geometry_runtime_binding_result["execution"]["retopologyRun"],
            "seamSplitRun": geometry_runtime_binding_result["execution"]["seamSplitRun"],
            "componentStitchingRun": geometry_runtime_binding_result["execution"][
                "componentStitchingRun"
            ],
            "normalContinuityValidationRun": geometry_runtime_binding_result["execution"][
                "normalContinuityValidationRun"
            ],
            "tangentContinuityValidationRun": geometry_runtime_binding_result["execution"][
                "tangentContinuityValidationRun"
            ],
            "runtimeBindingWritten": geometry_runtime_binding_result["execution"][
                "runtimeBindingWritten"
            ],
            "runtimeBindingAccepted": geometry_runtime_binding_result["execution"][
                "runtimeBindingAccepted"
            ],
            "runtimeBindingRecordCount": geometry_runtime_binding_result["aggregate"][
                "runtimeBindingRecordCount"
            ],
            "maxReconstructionError": geometry_runtime_binding_result["aggregate"][
                "maxReconstructionError"
            ],
            "maxSeamPairDistanceMeters": geometry_runtime_binding_result["aggregate"][
                "maxSeamPairDistanceMeters"
            ],
            "maxNormalAngleDegrees": geometry_runtime_binding_result["aggregate"][
                "maxNormalAngleDegrees"
            ],
            "maxTangentAngleDegrees": geometry_runtime_binding_result["aggregate"][
                "maxTangentAngleDegrees"
            ],
            "acceptedForCleanProposal": geometry_runtime_binding_result["readiness"][
                "acceptedForCleanProposal"
            ],
        },
        "geometryMaterialUvTransfer": {
            "reportId": geometry_material_uv_transfer["reportId"],
            "sourceGeometryRuntimeBindingResultId": geometry_material_uv_transfer[
                "sourceGeometryRuntimeBindingResultId"
            ],
            "status": geometry_material_uv_transfer["readiness"]["status"],
            "uvTransferRun": geometry_material_uv_transfer["execution"]["uvTransferRun"],
            "materialTransferRun": geometry_material_uv_transfer["execution"][
                "materialTransferRun"
            ],
            "sourceTextureProjectionRun": geometry_material_uv_transfer["execution"][
                "sourceTextureProjectionRun"
            ],
            "acceptedForMaterialPreview": geometry_material_uv_transfer["readiness"][
                "acceptedForMaterialPreview"
            ],
            "transferredMaterialCount": geometry_material_uv_transfer["aggregate"][
                "transferredMaterialCount"
            ],
            "missingMaterialCount": geometry_material_uv_transfer["aggregate"][
                "missingMaterialCount"
            ],
            "missingUvCount": geometry_material_uv_transfer["aggregate"]["missingUvCount"],
        },
        "geometryVisualShellReview": {
            "reportId": geometry_visual_shell_review["reportId"],
            "sourceGeometryRuntimeBindingResultId": geometry_visual_shell_review[
                "sourceGeometryRuntimeBindingResultId"
            ],
            "status": geometry_visual_shell_review["readiness"]["status"],
            "visualFidelityReviewRun": geometry_visual_shell_review["execution"][
                "visualFidelityReviewRun"
            ],
            "renderedPixelComparisonRun": geometry_visual_shell_review["execution"][
                "renderedPixelComparisonRun"
            ],
            "visualFidelityScore": geometry_visual_shell_review["aggregate"]["visualFidelityScore"],
            "acceptedForVisualFidelity": geometry_visual_shell_review["readiness"][
                "acceptedForVisualFidelity"
            ],
            "singleShellWeldProofRun": geometry_visual_shell_review["execution"][
                "singleShellWeldProofRun"
            ],
            "singleShellWeldProven": geometry_visual_shell_review["readiness"][
                "singleShellWeldProven"
            ],
            "boundaryEdgeCount": geometry_visual_shell_review["aggregate"]["boundaryEdgeCount"],
        },
        "geometryCleanAcceptanceGate": {
            "reportId": geometry_clean_acceptance_gate["reportId"],
            "sourceGeometryRuntimeBindingResultId": geometry_clean_acceptance_gate[
                "sourceGeometryRuntimeBindingResultId"
            ],
            "status": geometry_clean_acceptance_gate["readiness"]["status"],
            "cleanAcceptanceGateRun": geometry_clean_acceptance_gate["execution"][
                "cleanAcceptanceGateRun"
            ],
            "runtimeBindingEvidenceReviewed": geometry_clean_acceptance_gate["execution"][
                "runtimeBindingEvidenceReviewed"
            ],
            "visualFidelityReviewRun": geometry_clean_acceptance_gate["execution"][
                "visualFidelityReviewRun"
            ],
            "materialTransferRun": geometry_clean_acceptance_gate["execution"][
                "materialTransferRun"
            ],
            "singleShellWeldProofRun": geometry_clean_acceptance_gate["execution"][
                "singleShellWeldProofRun"
            ],
            "checkCount": geometry_clean_acceptance_gate["aggregate"]["checkCount"],
            "passedCheckCount": geometry_clean_acceptance_gate["aggregate"]["passedCheckCount"],
            "failedCheckCount": geometry_clean_acceptance_gate["aggregate"]["failedCheckCount"],
            "warningCheckCount": geometry_clean_acceptance_gate["aggregate"]["warningCheckCount"],
            "notRunCheckCount": geometry_clean_acceptance_gate["aggregate"]["notRunCheckCount"],
            "acceptedForCleanProposal": geometry_clean_acceptance_gate["readiness"][
                "acceptedForCleanProposal"
            ],
            "acceptedForRuntimeRender": geometry_clean_acceptance_gate["readiness"][
                "acceptedForRuntimeRender"
            ],
            "blockingReasons": geometry_clean_acceptance_gate["readiness"]["blockingReasons"],
        },
        "cleanGeometryProposal": {
            "proposalId": clean_geometry_proposal["proposalId"],
            "sourceRawProposalId": clean_geometry_proposal["sourceRawProposalId"],
            "qualityStatus": clean_geometry_proposal["quality"]["status"],
            "cleanProposalAvailable": clean_geometry_proposal["cleanProposal"]["available"],
            "acceptedForCanonical": clean_geometry_proposal["quality"]["acceptedForCanonical"],
            "acceptedForSimulation": clean_geometry_proposal["quality"]["acceptedForSimulation"],
            "topologyDiagnosticsRun": clean_geometry_proposal["cleanupPipeline"][
                "topologyDiagnosticsRun"
            ],
            "cleanupPlanGenerated": clean_geometry_proposal["cleanupPipeline"][
                "cleanupPlanGenerated"
            ],
            "cleanupResultGenerated": clean_geometry_proposal["cleanupPipeline"][
                "cleanupResultGenerated"
            ],
            "semanticTransferReportGenerated": clean_geometry_proposal["cleanupPipeline"][
                "semanticTransferReportGenerated"
            ],
            "bindingCandidateReportGenerated": clean_geometry_proposal["cleanupPipeline"][
                "bindingCandidateReportGenerated"
            ],
            "bindingValidationReportGenerated": clean_geometry_proposal["cleanupPipeline"][
                "bindingValidationReportGenerated"
            ],
            "repairRetopologyPlanGenerated": clean_geometry_proposal["cleanupPipeline"][
                "repairRetopologyPlanGenerated"
            ],
            "partialRepairResultGenerated": clean_geometry_proposal["cleanupPipeline"][
                "partialRepairResultGenerated"
            ],
            "runtimeBindingResultGenerated": clean_geometry_proposal["cleanupPipeline"][
                "runtimeBindingResultGenerated"
            ],
            "materialUvTransferReportGenerated": clean_geometry_proposal["cleanupPipeline"][
                "materialUvTransferReportGenerated"
            ],
            "cleanAcceptanceGateGenerated": clean_geometry_proposal["cleanupPipeline"][
                "cleanAcceptanceGateGenerated"
            ],
            "cleanupRun": clean_geometry_proposal["cleanupPipeline"]["cleanupRun"],
            "repairRun": clean_geometry_proposal["cleanupPipeline"]["repairRun"],
            "deformationReprojectionRun": clean_geometry_proposal["cleanupPipeline"][
                "deformationReprojectionRun"
            ],
            "semanticTransferRun": clean_geometry_proposal["cleanupPipeline"][
                "semanticTransferRun"
            ],
            "candidateBindingRun": clean_geometry_proposal["cleanupPipeline"][
                "candidateBindingRun"
            ],
            "deformationValidationRun": clean_geometry_proposal["cleanupPipeline"][
                "deformationValidationRun"
            ],
            "simulationBindingRun": clean_geometry_proposal["cleanupPipeline"][
                "simulationBindingRun"
            ],
            "runtimeBindingAccepted": clean_geometry_proposal["cleanupPipeline"][
                "runtimeBindingAccepted"
            ],
            "cleanAcceptanceGateRun": clean_geometry_proposal["cleanupPipeline"][
                "cleanAcceptanceGateRun"
            ],
            "cleanAcceptanceGateAccepted": clean_geometry_proposal["cleanupPipeline"][
                "cleanAcceptanceGateAccepted"
            ],
            "materialTransferRun": clean_geometry_proposal["cleanupPipeline"][
                "materialTransferRun"
            ],
            "materialTransferAccepted": clean_geometry_proposal["cleanupPipeline"][
                "materialTransferAccepted"
            ],
            "failureReason": clean_geometry_proposal["cleanGeometryAudit"]["failureReason"],
            "rejectionReasons": clean_geometry_proposal["quality"]["rejectionReasons"],
        },
        "providerRegistry": {
            "registryId": provider_registry["registryId"],
            "selectedProviderId": provider_registry["selectedProviderId"],
            "selectionReason": provider_registry["selectionReason"],
            "providerCount": len(provider_registry["providers"]),
            "manualLocalImportAdapterDeclared": provider_registry["d0Capabilities"][
                "manualLocalImportAdapterDeclared"
            ],
            "manualLocalImportAssetAvailable": provider_registry["d0Capabilities"][
                "manualLocalImportAssetAvailable"
            ],
            "externalProvidersConfigured": provider_registry["d0Capabilities"][
                "externalProvidersConfigured"
            ],
            "cleanProposalProviderAvailable": provider_registry["d0Capabilities"][
                "cleanProposalProviderAvailable"
            ],
        },
        "hashes": manifest["hashes"],
        "binding": context["bindingManifest"],
        "settle": {
            "solverVersion": settle["solverVersion"],
            "convergenceState": settle["convergenceState"],
            "maximumSeamResidualMeters": settle["maximumSeamResidualMeters"],
            "rmsSeamResidualMeters": settle["rmsSeamResidualMeters"],
            "maximumBodyPenetrationMeters": settle["maximumBodyPenetrationMeters"],
            "maximumStrain": settle["maximumStrain"],
            "selfCollisionAvailable": settle["selfCollision"]["available"],
        },
        "validation": validation,
        "warnings": manifest["warnings"],
        "capabilities": manifest["capabilities"],
    }


def _summary_markdown(context: dict[str, Any], validation: dict[str, Any]) -> str:
    summary = _summary_json(context, validation)
    counts = summary["counts"]
    return (
        "# Closy Demo T-Shirt Package\n\n"
        f"- Garment: `{summary['garmentId']}`\n"
        f"- Package digest: `{summary['packageDigest']}`\n"
        f"- Panels/seams/openings: {counts['panels']} / {counts['seams']} / {counts['openings']}\n"
        f"- Constraints: {counts['constraints']}\n"
        f"- Synthetic capture: {summary['capture']['viewCount']} metadata-only views, "
        f"quality {summary['capture']['overallScore']:.6f} "
        f"({summary['capture']['overallStatus']})\n"
        f"- Visual observations: {summary['visualUnderstanding']['maskCount']} masks, "
        f"{summary['visualUnderstanding']['observedLandmarkCount']} T-shirt landmarks, "
        f"{summary['visualUnderstanding']['correctionOperationCount']} corrections\n"
        f"- Fitting: {summary['fitting']['status']} via "
        f"`{summary['fitting']['fitterVersion']}`, landmark RMS "
        f"{summary['fitting']['landmarkRmsNormalised']:.6f}\n"
        f"- Texture identity: {summary['texture']['status']}, "
        f"{summary['texture']['materialRegionCount']} PBR material observations, "
        f"source textures available={summary['texture']['sourceTextureAvailable']}\n"
        f"- Geometry proposal: {summary['geometryProposal']['qualityStatus']} via "
        f"`{summary['geometryProposal']['providerId']}`, "
        f"raw available={summary['geometryProposal']['rawProposalAvailable']}\n"
        f"- Raw topology: components={summary['rawGeometryTopology']['componentCount']}, "
        f"non-manifold edges={summary['rawGeometryTopology']['nonManifoldEdgeCount']}, "
        f"status=`{summary['rawGeometryTopology']['manifoldStatus']}`\n"
        f"- Cleanup plan: {summary['geometryCleanupPlan']['requiredOperationCount']} required "
        f"operations, status=`{summary['geometryCleanupPlan']['status']}`\n"
        f"- Cleanup result: status=`{summary['geometryCleanupResult']['status']}`, "
        f"removed duplicate vertices="
        f"{summary['geometryCleanupResult']['removedDuplicateVertexCount']}, "
        f"accepted={summary['geometryCleanupResult']['acceptedForCleanProposal']}\n"
        f"- Semantic transfer: status=`{summary['geometrySemanticTransfer']['status']}`, "
        f"panels={summary['geometrySemanticTransfer']['transferredPanelCount']}/"
        f"{summary['geometrySemanticTransfer']['expectedPanelCount']}, "
        f"boundaries={summary['geometrySemanticTransfer']['classifiedBoundaryEdgeCount']}/"
        f"{summary['geometrySemanticTransfer']['boundaryEdgeCount']}, "
        f"accepted={summary['geometrySemanticTransfer']['acceptedForCleanProposal']}\n"
        f"- Binding candidate: status=`{summary['geometryBindingCandidate']['status']}`, "
        f"mapped={summary['geometryBindingCandidate']['mappedVertexCount']}/"
        f"{summary['geometryBindingCandidate']['cleanupVertexCount']}, "
        f"runtime binding={summary['geometryBindingCandidate']['runtimeBindingWritten']}, "
        f"accepted={summary['geometryBindingCandidate']['acceptedForCleanProposal']}\n"
        f"- Binding validation: status=`{summary['geometryBindingValidation']['status']}`, "
        f"max offset="
        f"{summary['geometryBindingValidation']['maxCleanupToSettledOffsetMeters']:.8f} m, "
        f"failed checks={summary['geometryBindingValidation']['failedCheckCount']}, "
        f"runtime accepted="
        f"{summary['geometryBindingValidation']['runtimeBindingAccepted']}\n"
        f"- Repair/retopology plan: status=`{summary['geometryRepairRetopologyPlan']['status']}`, "
        f"required operations={summary['geometryRepairRetopologyPlan']['requiredOperationCount']}, "
        f"complexity=`{summary['geometryRepairRetopologyPlan']['estimatedRepairComplexity']}`, "
        f"executed={summary['geometryRepairRetopologyPlan']['repairRun']}\n"
        f"- Repair result: status=`{summary['geometryRepairResult']['status']}`, "
        f"reprojected vertices={summary['geometryRepairResult']['movedVertexCount']}, "
        f"deferred operations={summary['geometryRepairResult']['deferredOperationCount']}, "
        f"retopology={summary['geometryRepairResult']['retopologyRun']}\n"
        f"- Runtime binding result: status=`{summary['geometryRuntimeBindingResult']['status']}`, "
        f"records={summary['geometryRuntimeBindingResult']['runtimeBindingRecordCount']}, "
        f"accepted={summary['geometryRuntimeBindingResult']['runtimeBindingAccepted']}, "
        f"max reconstruction error="
        f"{summary['geometryRuntimeBindingResult']['maxReconstructionError']:.8f}\n"
        f"- Material/UV transfer: status=`{summary['geometryMaterialUvTransfer']['status']}`, "
        f"uv={summary['geometryMaterialUvTransfer']['uvTransferRun']}, "
        f"materials={summary['geometryMaterialUvTransfer']['materialTransferRun']}, "
        f"preview accepted="
        f"{summary['geometryMaterialUvTransfer']['acceptedForMaterialPreview']}\n"
        f"- Visual/shell review: status=`{summary['geometryVisualShellReview']['status']}`, "
        f"score={summary['geometryVisualShellReview']['visualFidelityScore']:.6f}, "
        f"rendered={summary['geometryVisualShellReview']['renderedPixelComparisonRun']}, "
        f"single shell={summary['geometryVisualShellReview']['singleShellWeldProven']}\n"
        f"- Clean acceptance gate: status=`{summary['geometryCleanAcceptanceGate']['status']}`, "
        f"passed={summary['geometryCleanAcceptanceGate']['passedCheckCount']}/"
        f"{summary['geometryCleanAcceptanceGate']['checkCount']}, "
        f"failed={summary['geometryCleanAcceptanceGate']['failedCheckCount']}, "
        f"not run={summary['geometryCleanAcceptanceGate']['notRunCheckCount']}, "
        f"accepted={summary['geometryCleanAcceptanceGate']['acceptedForCleanProposal']}\n"
        f"- Clean proposal: {summary['cleanGeometryProposal']['qualityStatus']}, "
        f"available={summary['cleanGeometryProposal']['cleanProposalAvailable']}, "
        f"reason=`{summary['cleanGeometryProposal']['failureReason']}`\n"
        f"- Provider registry: selected `{summary['providerRegistry']['selectedProviderId']}`, "
        f"manual asset available={summary['providerRegistry']['manualLocalImportAssetAvailable']}\n"
        f"- Simulation mesh: {counts['simulationVertices']} vertices, "
        f"{counts['simulationTriangles']} triangles\n"
        f"- Render shell: {counts['renderVertices']} vertices, "
        f"{counts['renderTriangles']} triangles\n"
        f"- Cloth settle: {summary['settle']['convergenceState']} via "
        f"`{summary['settle']['solverVersion']}`\n"
        f"- Seam RMS residual: {summary['settle']['rmsSeamResidualMeters']:.8f} m\n"
        f"- Max body penetration: {summary['settle']['maximumBodyPenetrationMeters']:.8f} m\n"
        f"- Binding max error: {summary['binding']['maximumReconstructionError']:.8f}\n"
        f"- Validation: {validation['status']} {validation['counts']}\n"
        "- Limitation: `self_collision_not_run` is expected for the first reference solver.\n"
    )


def _mesh_counts(meshset: MeshSet) -> dict[str, int]:
    return {
        "meshCount": len(meshset.meshes),
        "vertexCount": meshset.vertex_count,
        "triangleCount": meshset.triangle_count,
    }


def _operation_removed_count(cleanup_result: dict[str, Any], operation_id: str) -> int:
    for operation in cleanup_result["executedOperations"]:
        if operation["operationId"] == operation_id:
            return int(operation["removedCount"])
    return 0


def _panels_svg(pattern: dict[str, Any]) -> str:
    paths = []
    x_offset = 500.0
    for panel_index, panel in enumerate(pattern["panels"]):
        samples: list[tuple[float, float]] = []
        for edge in panel["boundary"]:
            from closy_forge.geometry.curves import sample_curve

            edge_samples = sample_curve(edge["curve"], int(edge["sampleCount"]))
            if samples and edge_samples and samples[-1] == edge_samples[0]:
                edge_samples = edge_samples[1:]
            samples.extend(edge_samples)
        if not samples:
            continue
        points = " ".join(
            f"{(x + panel_index * 0.9) * 220 + 80:.2f},{420 - y * 220:.2f}" for x, y in samples
        )
        paths.append(f'<polygon points="{points}" fill="none" stroke="#1d4ed8" stroke-width="2"/>')
        label = panel["id"]
        first_x, first_y = samples[0]
        paths.append(
            f'<text x="{(first_x + panel_index * 0.9) * 220 + 80:.2f}" '
            f'y="{420 - first_y * 220 - 8:.2f}" font-size="13">{label}</text>'
        )
    width = int(max(900, len(pattern["panels"]) * x_offset))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="520" '
        f'viewBox="0 0 {width} 520">\n'
        '<rect width="100%" height="100%" fill="white"/>\n' + "\n".join(paths) + "\n</svg>\n"
    )


def _hash_from_inventory(inventory: list[dict[str, object]], relpath: str) -> str:
    for entry in inventory:
        if entry["path"] == relpath:
            return str(entry["sha256"])
    raise KeyError(relpath)


def _json_hash(doc: dict[str, Any]) -> str:
    return sha256_bytes(canonical_dumps(doc).encode("utf-8"))


def audit_package_glbs(package_dir: Path) -> dict[str, dict[str, Any]]:
    return {
        rel: audit_glb(package_dir / rel)
        for rel in [
            "avatar/reference_avatar.glb",
            "avatar/collision.glb",
            "proposals/manual_repair_preview.glb",
            "proposals/manual_runtime_retopology_preview.glb",
            "simulation/simulation_mesh.glb",
            "render/fallback.glb",
        ]
    }


def binding_perturbation_report(
    sim_mesh: MeshSet, binding_records: Any, render_mesh: MeshSet
) -> dict[str, float]:
    perturbed = perturb_simulation_vertices(sim_mesh)
    reconstructed = reconstruct_vertices(perturbed, binding_records)
    max_error, rms_error = reconstruction_error(render_mesh, reconstructed)
    return {
        "maximumErrorAgainstOriginalRender": max_error,
        "rmsErrorAgainstOriginalRender": rms_error,
    }
