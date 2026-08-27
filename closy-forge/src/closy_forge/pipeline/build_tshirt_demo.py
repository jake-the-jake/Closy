from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from closy_forge.appearance import (
    BITMAP_ATLAS_VERSION,
    TEXTURE_IDENTITY_VERSION,
    build_texture_identity_bundle,
)
from closy_forge.avatar.reference_avatar import (
    avatar_contract,
    body_regions,
    build_collision_mesh,
    build_reference_avatar_mesh,
)
from closy_forge.binding.binary_format import write_binding
from closy_forge.binding.builder import build_binding
from closy_forge.binding.c3_evidence import prepare_c3_evidence_assets
from closy_forge.binding.production_binding import (
    PRODUCTION_BINDING_C3_REPORT_VERSION,
    PRODUCTION_BINDING_CONTRACT_VERSION,
    build_production_binding_c3_report_from_package,
    build_production_binding_contract,
)
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
from closy_forge.geometry.glb_io import audit_glb, read_glb_meshset, write_glb, write_indexed_glb
from closy_forge.geometry.mesh_model import MeshSet, mesh_bounds
from closy_forge.geometry.subdivision import subdivide_for_render
from closy_forge.inspection import (
    INSPECTION_ARTIFACT_REPORT_VERSION,
    INSPECTION_RENDERER_VERSION,
    SOURCE_RENDER_FIDELITY_VERSION,
    write_inspection_artifacts,
    write_source_render_fidelity_artifacts,
)
from closy_forge.package_io.canonical_json import (
    canonical_dumps,
    write_canonical_json,
    write_canonical_text,
)
from closy_forge.package_io.hashing import (
    geometry_content_hash,
    sha256_bytes,
    sha256_file,
    topology_hash,
)
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
    GEOMETRY_STITCHED_SHELL_VERSION,
    GEOMETRY_VISUAL_SHELL_REVIEW_VERSION,
    PROVIDER_BAKEOFF_REPORT_VERSION,
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
    build_provider_bakeoff_report,
    build_raw_geometry_topology_report,
    build_stitched_shell_assets,
    clean_geometry_proposal_quality_report,
    geometry_proposal_quality_report,
    hash_geometry_stitched_shell_report,
    provider_registry_quality_report,
    reproject_cleanup_preview_to_settled_simulation,
)
from closy_forge.rendering import (
    FRAME_POSE_SUITE_VERSION,
    build_render_frame_pose_suite_report,
)
from closy_forge.simulation.material_calibration import (
    CALIBRATION_VERSION,
    run_material_calibration,
)
from closy_forge.simulation.material_motion_suite import (
    MATERIAL_MOTION_SUITE_VERSION,
    build_material_motion_suite,
)
from closy_forge.simulation.material_physics import (
    FABRIC_DESCRIPTOR_VERSION,
    MATERIAL_SELECTION_VERSION,
    PRESET_REGISTRY_VERSION,
    build_material_preset_registry,
    select_material_preset,
    solver_material_payload,
)
from closy_forge.simulation.reference_cloth_solver import (
    SOLVER_VERSION,
    settle_reference_cloth,
    simulation_state_json,
)
from closy_forge.simulation.self_collision import (
    SELF_COLLISION_REPORT_VERSION,
    build_self_collision_report,
)
from closy_forge.validation.validator import validate_package
from closy_forge.visual_understanding import (
    CORRECTION_RECORD_VERSION,
    MULTIVIEW_FUSION_VERSION,
    TSHIRT_VISUAL_OBSERVATION_VERSION,
    build_default_applied_correction_record,
    build_multiview_fusion_record,
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
            issue_details = ";".join(
                f"{issue.get('code', 'unknown')}={issue.get('message', '')}"
                for issue in final_validation["issues"]
            )
            raise RuntimeError(f"package validation failed before publish: {issue_details}")
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
    correction_record = build_default_applied_correction_record(visual_observations)
    multiview_fusion = build_multiview_fusion_record(
        capture_record, visual_observations, correction_record
    )
    fit_report = fit_tshirt_parameters_from_visual_observations(
        visual_observations,
        multiview_fusion=multiview_fusion,
        prior=params,
    )
    params = TShirtParameters(**fit_report["fittedParameters"])
    params.validate()
    pattern = build_tshirt_pattern(params)
    semantic = build_semantic_graph(pattern)
    rest_mesh, edge_maps = build_simulation_mesh(pattern)
    constraints = build_constraints(pattern, edge_maps)
    render_materials = _render_materials()
    texture_bundle = build_texture_identity_bundle(
        capture_record=capture_record,
        visual_observations=visual_observations,
        fit_report=fit_report,
        render_materials=render_materials,
        multiview_fusion=multiview_fusion,
    )
    texture_identity = texture_bundle.report
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
    provider_bakeoff = build_provider_bakeoff_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        provider_registry=provider_registry,
        raw_geometry_proposal=geometry_proposal,
        raw_topology_report=raw_geometry_topology,
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
    material_registry = build_material_preset_registry()
    material_selection = select_material_preset(_material_selection_input(), material_registry)
    material_physics = solver_material_payload(material_selection["selectedDescriptor"])
    material_calibration = run_material_calibration(material_selection["selectedDescriptor"])
    settle = settle_reference_cloth(rest_mesh, constraints, avatar, material_physics)
    simulation_mesh = settle.settled_mesh
    self_collision_report = build_self_collision_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        rest_mesh=rest_mesh,
        settled_mesh=simulation_mesh,
        seam_constraints=constraints,
    )
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
    geometry_stitched_shell, stitched_analysis_shell, stitched_shell_mesh = (
        build_stitched_shell_assets(
            garment_id="garment.demo_tshirt.reference_v1",
            garment_class="tshirt",
            source_simulation_mesh=simulation_mesh,
            constraints=constraints,
            analysis_asset_path="stitch/logical_stitched_analysis_shell.json",
            render_asset_path="render/stitched_shell.glb",
        )
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
        stitched_shell_report=geometry_stitched_shell,
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
    material_motion_suite, material_motion_states = build_material_motion_suite(
        rest_mesh=rest_mesh,
        constraints=constraints,
        avatar_contract=avatar,
        preset_registry=material_registry,
        binding=binding,
    )

    write_canonical_json(package_dir / "source" / "capture_record.json", capture_record)
    write_canonical_json(package_dir / "source" / "capture_quality.json", capture_quality)
    write_canonical_json(package_dir / "source" / "visual_observations.json", visual_observations)
    write_canonical_json(package_dir / "source" / "correction_record.json", correction_record)
    write_canonical_json(package_dir / "source" / "multiview_fusion.json", multiview_fusion)
    write_canonical_json(package_dir / "fitting" / "tshirt_fit.json", fit_report)
    write_canonical_json(package_dir / "textures" / "texture_identity.json", texture_identity)
    for texture_path, texture_payload in texture_bundle.artifacts.items():
        destination = package_dir / texture_path
        if isinstance(texture_payload, bytes):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(texture_payload)
        else:
            write_canonical_json(destination, texture_payload)
    write_canonical_json(
        package_dir / "proposals" / "raw_geometry_proposal.json", geometry_proposal
    )
    write_canonical_json(
        package_dir / "proposals" / "clean_geometry_proposal.json", clean_geometry_proposal
    )
    write_canonical_json(package_dir / "proposals" / "provider_registry.json", provider_registry)
    write_canonical_json(package_dir / "reports" / "provider_bakeoff.json", provider_bakeoff)
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
    write_canonical_json(package_dir / "simulation" / "material_presets.json", material_registry)
    write_canonical_json(package_dir / "reports" / "material_selection.json", material_selection)
    write_canonical_json(
        package_dir / "reports" / "material_calibration.json", material_calibration
    )
    write_canonical_json(
        package_dir / "reports" / "material_motion_suite.json", material_motion_suite
    )
    for preset_id, state in material_motion_states.items():
        state_name = preset_id.removeprefix("material.").removesuffix("_d0_v1")
        write_canonical_json(
            package_dir / "simulation" / "material_motion_states" / f"{state_name}.json",
            state,
        )
    write_canonical_json(
        package_dir / "reports" / "self_collision_report.json",
        self_collision_report,
    )
    write_canonical_json(
        package_dir / "stitch" / "logical_stitched_analysis_shell.json",
        stitched_analysis_shell,
    )
    write_glb(
        package_dir / "render" / "fallback.glb",
        render_mesh,
        "closy_render_cotton_fixture_v1",
        (0.08, 0.26, 0.78, 1.0),
    )
    write_indexed_glb(
        package_dir / "render" / "stitched_shell.glb",
        stitched_shell_mesh,
        "closy_stitched_shell_preview_v1",
        (0.10, 0.36, 0.70, 1.0),
    )
    _record_stitched_shell_package_writer_evidence(geometry_stitched_shell, package_dir)
    write_canonical_json(
        package_dir / "render" / "mesh_manifest.json", _mesh_manifest(render_mesh, "render")
    )
    write_canonical_json(package_dir / "render" / "materials.json", render_materials)
    write_binding(package_dir / "binding" / "sim_to_render.bin", binding)
    write_canonical_json(package_dir / "binding" / "binding_manifest.json", binding_manifest)
    production_binding_contract = build_production_binding_contract(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        simulation_mesh=simulation_mesh,
        render_mesh=render_mesh,
        binding=binding,
        binding_manifest=binding_manifest,
        render_binding_seeds=render_binding_seeds,
        constraints=constraints,
    )
    write_canonical_json(
        package_dir / "binding" / "production_binding_contract.json",
        production_binding_contract,
    )
    prepare_c3_evidence_assets(
        package_dir=package_dir,
        settled_mesh=simulation_mesh,
        constraints=constraints,
        avatar_contract=avatar,
        material=material_physics,
    )
    render_frame_pose_suite = build_render_frame_pose_suite_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        render_asset_path=package_dir / "render" / "fallback.glb",
        render_asset_package_path="render/fallback.glb",
        simulation_mesh_manifest_path=package_dir / "simulation" / "mesh_manifest.json",
        render_mesh_manifest_path=package_dir / "render" / "mesh_manifest.json",
        binding_asset_path=package_dir / "binding" / "sim_to_render.bin",
        binding_manifest_path=package_dir / "binding" / "binding_manifest.json",
        simulation_mesh=simulation_mesh,
        render_mesh=render_mesh,
        binding=binding,
        binding_manifest=binding_manifest,
    )
    write_canonical_json(
        package_dir / "reports" / "render_frame_pose_suite.json",
        render_frame_pose_suite,
    )
    write_canonical_json(
        package_dir / "reports" / "geometry_binding_validation.json",
        geometry_binding_validation,
    )
    write_canonical_json(
        package_dir / "reports" / "geometry_runtime_binding_result.json",
        geometry_runtime_binding_result,
    )
    write_canonical_json(
        package_dir / "reports" / "geometry_stitched_shell.json",
        geometry_stitched_shell,
    )
    production_binding_c3 = build_production_binding_c3_report_from_package(
        package_dir=package_dir,
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
    )
    write_canonical_json(
        package_dir / "reports" / "production_binding_c3.json",
        production_binding_c3,
    )

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
        multiview_fusion,
        fit_report,
        texture_identity,
        geometry_proposal,
        raw_geometry_topology,
        provider_bakeoff,
        geometry_cleanup_plan,
        geometry_cleanup_result,
        geometry_semantic_transfer,
        geometry_binding_candidate,
        geometry_binding_validation,
        geometry_repair_retopology_plan,
        geometry_repair_result,
        geometry_runtime_binding_result,
        geometry_material_uv_transfer,
        geometry_stitched_shell,
        geometry_visual_shell_review,
        render_frame_pose_suite,
        production_binding_c3,
        self_collision_report,
        geometry_clean_acceptance_gate,
        clean_geometry_proposal,
        provider_registry,
    )
    for name, report in quality_reports.items():
        write_canonical_json(package_dir / "reports" / name, report)

    source_render_fidelity = write_source_render_fidelity_artifacts(
        package_dir,
        visual_observations=visual_observations,
        settled_mesh=simulation_mesh,
    )
    inspection_manifest, inspection_report = write_inspection_artifacts(
        package_dir,
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        pattern=pattern,
        rest_mesh=rest_mesh,
        settled_mesh=simulation_mesh,
        render_mesh=render_mesh,
        avatar_collision_mesh=collision_mesh,
        manual_raw_mesh=read_glb_meshset(manual_proposal_asset),
        cleanup_preview_mesh=read_glb_meshset(cleanup_preview_asset),
        repair_preview_mesh=read_glb_meshset(repair_preview_asset),
        runtime_bound_mesh=read_glb_meshset(proposal_runtime_render_asset),
        logical_stitched_mesh=stitched_shell_mesh,
        render_split_stitched_mesh=read_glb_meshset(package_dir / "render" / "stitched_shell.glb"),
        geometry_stitched_shell=geometry_stitched_shell,
        geometry_visual_shell_review=geometry_visual_shell_review,
        clean_geometry_proposal=clean_geometry_proposal,
        source_render_fidelity=source_render_fidelity,
    )

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
        multiview_fusion,
        fit_report,
        texture_identity,
        geometry_proposal,
        raw_geometry_topology,
        provider_bakeoff,
        geometry_cleanup_plan,
        geometry_cleanup_result,
        geometry_semantic_transfer,
        geometry_binding_candidate,
        geometry_binding_validation,
        geometry_repair_retopology_plan,
        geometry_repair_result,
        geometry_runtime_binding_result,
        geometry_material_uv_transfer,
        geometry_stitched_shell,
        geometry_visual_shell_review,
        render_frame_pose_suite,
        production_binding_c3,
        self_collision_report,
        geometry_clean_acceptance_gate,
        clean_geometry_proposal,
        provider_registry,
        inspection_report,
        source_render_fidelity,
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
        multiview_fusion,
        fit_report,
        texture_identity,
        geometry_proposal,
        raw_geometry_topology,
        provider_bakeoff,
        geometry_cleanup_plan,
        geometry_cleanup_result,
        geometry_semantic_transfer,
        geometry_binding_candidate,
        geometry_binding_validation,
        geometry_repair_retopology_plan,
        geometry_repair_result,
        geometry_runtime_binding_result,
        geometry_material_uv_transfer,
        geometry_stitched_shell,
        stitched_analysis_shell,
        stitched_shell_mesh,
        geometry_visual_shell_review,
        render_frame_pose_suite,
        production_binding_contract,
        production_binding_c3,
        self_collision_report,
        geometry_clean_acceptance_gate,
        clean_geometry_proposal,
        provider_registry,
        inspection_manifest,
        inspection_report,
        source_render_fidelity,
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
        "materialRegistry": material_registry,
        "materialSelection": material_selection,
        "materialCalibration": material_calibration,
        "materialMotionSuite": material_motion_suite,
        "captureRecord": capture_record,
        "captureQuality": capture_quality,
        "visualObservations": visual_observations,
        "correctionRecord": correction_record,
        "multiviewFusion": multiview_fusion,
        "fitReport": fit_report,
        "textureIdentity": texture_identity,
        "geometryProposal": geometry_proposal,
        "rawGeometryTopology": raw_geometry_topology,
        "providerBakeoff": provider_bakeoff,
        "geometryCleanupPlan": geometry_cleanup_plan,
        "geometryCleanupResult": geometry_cleanup_result,
        "geometrySemanticTransfer": geometry_semantic_transfer,
        "geometryBindingCandidate": geometry_binding_candidate,
        "geometryBindingValidation": geometry_binding_validation,
        "geometryRepairRetopologyPlan": geometry_repair_retopology_plan,
        "geometryRepairResult": geometry_repair_result,
        "geometryRuntimeBindingResult": geometry_runtime_binding_result,
        "geometryMaterialUvTransfer": geometry_material_uv_transfer,
        "geometryStitchedShell": geometry_stitched_shell,
        "stitchedAnalysisShell": stitched_analysis_shell,
        "stitchedShellMesh": stitched_shell_mesh,
        "geometryVisualShellReview": geometry_visual_shell_review,
        "renderFramePoseSuite": render_frame_pose_suite,
        "productionBindingContract": production_binding_contract,
        "productionBindingC3": production_binding_c3,
        "selfCollisionReport": self_collision_report,
        "geometryCleanAcceptanceGate": geometry_clean_acceptance_gate,
        "cleanGeometryProposal": clean_geometry_proposal,
        "providerRegistry": provider_registry,
        "inspectionManifest": inspection_manifest,
        "inspectionReport": inspection_report,
        "sourceRenderFidelity": source_render_fidelity,
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


def _material_selection_input() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "inputId": "material_selection.public_tshirt_d0_v1",
        "garmentFamily": "tshirt",
        "observations": {
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


def _material_physics() -> dict[str, Any]:
    """Compatibility adapter for tests and callers that request the selected D0 material."""

    registry = build_material_preset_registry()
    selection = select_material_preset(_material_selection_input(), registry)
    return solver_material_payload(selection["selectedDescriptor"])


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
    multiview_fusion: dict[str, Any],
    fit_report: dict[str, Any],
    texture_identity: dict[str, Any],
    geometry_proposal: dict[str, Any],
    raw_geometry_topology: dict[str, Any],
    provider_bakeoff: dict[str, Any],
    geometry_cleanup_plan: dict[str, Any],
    geometry_cleanup_result: dict[str, Any],
    geometry_semantic_transfer: dict[str, Any],
    geometry_binding_candidate: dict[str, Any],
    geometry_binding_validation: dict[str, Any],
    geometry_repair_retopology_plan: dict[str, Any],
    geometry_repair_result: dict[str, Any],
    geometry_runtime_binding_result: dict[str, Any],
    geometry_material_uv_transfer: dict[str, Any],
    geometry_stitched_shell: dict[str, Any],
    stitched_analysis_shell: dict[str, Any],
    stitched_shell_mesh: MeshSet,
    geometry_visual_shell_review: dict[str, Any],
    render_frame_pose_suite: dict[str, Any],
    production_binding_contract: dict[str, Any],
    production_binding_c3: dict[str, Any],
    self_collision_report: dict[str, Any],
    geometry_clean_acceptance_gate: dict[str, Any],
    clean_geometry_proposal: dict[str, Any],
    provider_registry: dict[str, Any],
    inspection_manifest: dict[str, Any],
    inspection_report: dict[str, Any],
    source_render_fidelity: dict[str, Any],
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
            "sourceMultiviewFusion": "source/multiview_fusion.json",
            "multiviewFusionQuality": "reports/multiview_fusion_quality.json",
            "tshirtFitReport": "fitting/tshirt_fit.json",
            "textureIdentity": "textures/texture_identity.json",
            "sourceTextureProjection": "textures/source_projection.json",
            "generatedTextureAtlas": "textures/generated_atlas.json",
            "pbrMaterialMaps": "textures/pbr_material_maps.json",
            "conventionalFallbackMaterials": "textures/conventional_fallback_materials.json",
            "rawGeometryProposal": "proposals/raw_geometry_proposal.json",
            "rawGeometryProposalAsset": "proposals/manual_raw_visual_proposal.glb",
            "rawGeometryTopology": "reports/raw_geometry_topology.json",
            "providerBakeoff": "reports/provider_bakeoff.json",
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
            "geometryStitchedShell": "reports/geometry_stitched_shell.json",
            "stitchedAnalysisShell": "stitch/logical_stitched_analysis_shell.json",
            "stitchedRenderShell": "render/stitched_shell.glb",
            "geometryVisualShellReview": "reports/geometry_visual_shell_review.json",
            "renderFramePoseSuite": "reports/render_frame_pose_suite.json",
            "productionBindingContract": "binding/production_binding_contract.json",
            "productionBindingC3": "reports/production_binding_c3.json",
            "selfCollisionReport": "reports/self_collision_report.json",
            "inspectionArtifactManifest": "reports/inspection/manifest.json",
            "inspectionArtifactReport": "reports/inspection/inspection_report.json",
            "sourceRenderFidelity": "reports/fidelity/source_render_fidelity.json",
            "decodedBitmapPbrReport": "textures/bitmap_pbr_report.json",
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
            "materialPresetRegistry": "simulation/material_presets.json",
            "materialSelection": "reports/material_selection.json",
            "materialCalibration": "reports/material_calibration.json",
            "materialMotionSuite": "reports/material_motion_suite.json",
            "materialMotionStates": "simulation/material_motion_states",
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
            "sourceMultiviewFusionHash": _hash_from_inventory(
                inventory, "source/multiview_fusion.json"
            ),
            "sourceMultiviewFusionPayloadHash": str(
                multiview_fusion["integrity"]["multiviewFusionRecordHash"]
            ),
            "multiviewFusionQualityHash": _hash_from_inventory(
                inventory, "reports/multiview_fusion_quality.json"
            ),
            "tshirtFitReportHash": _hash_from_inventory(inventory, "fitting/tshirt_fit.json"),
            "tshirtFitReportPayloadHash": str(fit_report["integrity"]["fitReportHash"]),
            "textureIdentityHash": _hash_from_inventory(
                inventory, "textures/texture_identity.json"
            ),
            "textureIdentityPayloadHash": str(texture_identity["integrity"]["textureIdentityHash"]),
            "sourceTextureProjectionHash": _hash_from_inventory(
                inventory, "textures/source_projection.json"
            ),
            "sourceTextureProjectionPayloadHash": str(
                texture_identity["artifactRefs"]["sourceProjection"]["sha256"]
            ),
            "generatedTextureAtlasHash": _hash_from_inventory(
                inventory, "textures/generated_atlas.json"
            ),
            "generatedTextureAtlasPayloadHash": str(
                texture_identity["artifactRefs"]["generatedAtlas"]["sha256"]
            ),
            "pbrMaterialMapsHash": _hash_from_inventory(
                inventory, "textures/pbr_material_maps.json"
            ),
            "pbrMaterialMapsPayloadHash": str(
                texture_identity["artifactRefs"]["pbrMaterialMaps"]["sha256"]
            ),
            "conventionalFallbackMaterialsHash": _hash_from_inventory(
                inventory, "textures/conventional_fallback_materials.json"
            ),
            "conventionalFallbackMaterialsPayloadHash": str(
                texture_identity["artifactRefs"]["conventionalFallbackMaterials"]["sha256"]
            ),
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
            "providerBakeoffHash": _hash_from_inventory(inventory, "reports/provider_bakeoff.json"),
            "providerBakeoffPayloadHash": str(provider_bakeoff["integrity"]["providerBakeoffHash"]),
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
            "geometryStitchedShellHash": _hash_from_inventory(
                inventory, "reports/geometry_stitched_shell.json"
            ),
            "geometryStitchedShellPayloadHash": str(
                geometry_stitched_shell["integrity"]["geometryStitchedShellHash"]
            ),
            "stitchedAnalysisShellHash": _hash_from_inventory(
                inventory, "stitch/logical_stitched_analysis_shell.json"
            ),
            "stitchedAnalysisShellPayloadHash": str(
                stitched_analysis_shell["integrity"]["stitchedAnalysisShellHash"]
            ),
            "stitchedRenderShellHash": _hash_from_inventory(inventory, "render/stitched_shell.glb"),
            "stitchedShellTopologyHash": topology_hash(stitched_shell_mesh),
            "stitchedShellContentHash": geometry_content_hash(stitched_shell_mesh),
            "geometryVisualShellReviewHash": _hash_from_inventory(
                inventory, "reports/geometry_visual_shell_review.json"
            ),
            "geometryVisualShellReviewPayloadHash": str(
                geometry_visual_shell_review["integrity"]["geometryVisualShellReviewHash"]
            ),
            "renderFramePoseSuiteHash": _hash_from_inventory(
                inventory, "reports/render_frame_pose_suite.json"
            ),
            "renderFramePoseSuitePayloadHash": str(
                render_frame_pose_suite["integrity"]["renderFramePoseSuiteHash"]
            ),
            "productionBindingContractHash": _hash_from_inventory(
                inventory, "binding/production_binding_contract.json"
            ),
            "productionBindingContractPayloadHash": str(
                production_binding_contract["integrity"]["productionBindingContractHash"]
            ),
            "productionBindingC3Hash": _hash_from_inventory(
                inventory, "reports/production_binding_c3.json"
            ),
            "productionBindingC3PayloadHash": str(
                production_binding_c3["integrity"]["productionBindingC3ReportHash"]
            ),
            "selfCollisionReportHash": _hash_from_inventory(
                inventory, "reports/self_collision_report.json"
            ),
            "selfCollisionReportPayloadHash": str(
                self_collision_report["integrity"]["selfCollisionReportHash"]
            ),
            "inspectionArtifactManifestHash": _hash_from_inventory(
                inventory, "reports/inspection/manifest.json"
            ),
            "inspectionArtifactManifestPayloadHash": str(
                inspection_manifest["integrity"]["inspectionManifestHash"]
            ),
            "inspectionArtifactReportHash": _hash_from_inventory(
                inventory, "reports/inspection/inspection_report.json"
            ),
            "inspectionArtifactReportPayloadHash": str(
                inspection_report["integrity"]["inspectionReportHash"]
            ),
            "sourceRenderFidelityHash": _hash_from_inventory(
                inventory, "reports/fidelity/source_render_fidelity.json"
            ),
            "sourceRenderFidelityPayloadHash": str(
                source_render_fidelity["integrity"]["sourceRenderFidelityHash"]
            ),
            "decodedBitmapPbrReportHash": _hash_from_inventory(
                inventory, "textures/bitmap_pbr_report.json"
            ),
            "decodedBitmapPbrReportPayloadHash": str(
                texture_identity["decodedBitmapAtlas"]["reportHash"]
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
            "materialPresetRegistryHash": _hash_from_inventory(
                inventory, "simulation/material_presets.json"
            ),
            "materialSelectionHash": _hash_from_inventory(
                inventory, "reports/material_selection.json"
            ),
            "materialCalibrationHash": _hash_from_inventory(
                inventory, "reports/material_calibration.json"
            ),
            "materialMotionSuiteHash": _hash_from_inventory(
                inventory, "reports/material_motion_suite.json"
            ),
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
            "multiviewFusion": MULTIVIEW_FUSION_VERSION,
            "tshirtFit": TSHIRT_FIT_REPORT_VERSION,
            "textureIdentity": TEXTURE_IDENTITY_VERSION,
            "decodedBitmapAtlas": BITMAP_ATLAS_VERSION,
            "geometryProposal": GEOMETRY_PROPOSAL_VERSION,
            "rawGeometryTopology": RAW_GEOMETRY_TOPOLOGY_REPORT_VERSION,
            "providerBakeoff": PROVIDER_BAKEOFF_REPORT_VERSION,
            "geometryCleanupPlan": GEOMETRY_CLEANUP_PLAN_VERSION,
            "geometryCleanupResult": GEOMETRY_CLEANUP_RESULT_VERSION,
            "geometrySemanticTransfer": GEOMETRY_SEMANTIC_TRANSFER_VERSION,
            "geometryBindingCandidate": GEOMETRY_BINDING_CANDIDATE_VERSION,
            "geometryBindingValidation": GEOMETRY_BINDING_VALIDATION_VERSION,
            "geometryRepairRetopologyPlan": GEOMETRY_REPAIR_RETOPOLOGY_PLAN_VERSION,
            "geometryRepairResult": GEOMETRY_REPAIR_RESULT_VERSION,
            "geometryRuntimeBindingResult": GEOMETRY_RUNTIME_BINDING_RESULT_VERSION,
            "geometryMaterialUvTransfer": GEOMETRY_MATERIAL_UV_TRANSFER_VERSION,
            "geometryStitchedShell": GEOMETRY_STITCHED_SHELL_VERSION,
            "geometryVisualShellReview": GEOMETRY_VISUAL_SHELL_REVIEW_VERSION,
            "renderFramePoseSuite": FRAME_POSE_SUITE_VERSION,
            "productionBindingContract": PRODUCTION_BINDING_CONTRACT_VERSION,
            "productionBindingC3": PRODUCTION_BINDING_C3_REPORT_VERSION,
            "selfCollision": SELF_COLLISION_REPORT_VERSION,
            "inspectionRenderer": INSPECTION_RENDERER_VERSION,
            "inspectionArtifactReport": INSPECTION_ARTIFACT_REPORT_VERSION,
            "sourceRenderFidelity": SOURCE_RENDER_FIDELITY_VERSION,
            "geometryCleanAcceptanceGate": GEOMETRY_CLEAN_ACCEPTANCE_GATE_VERSION,
            "cleanGeometryProposal": CLEAN_GEOMETRY_PROPOSAL_VERSION,
            "geometryProviderRegistry": PROVIDER_REGISTRY_VERSION,
            "patternGenerator": "closy.tshirt.pattern.v1",
            "curveSampler": "closy.curve_sampler.v1",
            "panelTriangulator": "closy.fan_triangulator.v1",
            "clothSettle": SOLVER_VERSION,
            "fabricPhysicsDescriptor": FABRIC_DESCRIPTOR_VERSION,
            "materialPresetRegistry": PRESET_REGISTRY_VERSION,
            "materialPresetSelection": MATERIAL_SELECTION_VERSION,
            "materialCalibration": CALIBRATION_VERSION,
            "materialMotionSuite": MATERIAL_MOTION_SUITE_VERSION,
            "renderSubdivision": "closy.render_subdivision.v1",
            "binding": str(binding_manifest["algorithm"]),
            "glbWriter": "closy.glb_writer.v2.persistent_tangent_vec4",
        },
        "seed": seed,
        "buildProfile": {
            "name": "phase7_material_physics_public_fixture",
            "timestamp": FIXED_TIMESTAMP,
            "parameters": params.to_json(),
        },
        "capabilities": _capabilities(production_binding_c3, source_render_fidelity),
        "warnings": [
            "self_collision_d0_reference_only",
            "self_collision_unresolved_contacts_d0_reference",
            "unsupported_high_velocity_tunnelling",
            "synthetic_capture_metadata_only",
            "d0_pixel_parser_synthetic_fixture_only",
            "d0_multiview_fusion_synthetic_fixture_only",
            "d0_image_conditioned_fitting_synthetic_fixture_only",
            "local_algorithmic_parser_not_trained_model",
            "private_user_raster_processing_not_enabled",
            "synthetic_fit_not_trained_from_real_images",
            "settled_render_fit_comparison_d0_public_fixture_only",
            "d0_source_texture_recovery_synthetic_fixture_only",
            "public_synthetic_source_pixels_packaged_private_pixels_not_allowed",
            "decoded_pbr_maps_d0_derived_not_real_fabric_calibration",
            "material_presets_authored_not_measured_real_fabric",
            "material_motion_cpu_reference_not_production_gpu",
            "learned_material_inference_not_run",
            "private_user_material_estimation_not_run",
            "hidden_texture_regions_not_hallucinated",
            "manual_raw_geometry_proposal_not_canonical",
            "partial_geometry_cleanup_not_clean_proposal",
            "geometry_semantic_transfer_not_simulation_binding",
            "geometry_binding_candidate_not_runtime_binding",
            "geometry_binding_validation_rejected_runtime_binding",
            "geometry_repair_result_partial_reprojection_not_clean",
            "geometry_runtime_binding_result_clean_acceptance_pending",
            "geometry_material_uv_transfer_source_projection_preview_only",
            "geometry_stitched_shell_output_not_clean_proven",
            "geometry_visual_shell_review_clean_rejected",
            "inspection_artifacts_not_visual_fidelity_acceptance",
            "bp48_pose_suite_not_full_cloth_motion",
            "production_binding_c3_d0_profile_only",
            *(
                ["production_binding_c3_partial_scoped_reference_profile"]
                if not production_binding_c3["readiness"]["acceptedForD0RuntimeBindingProfile"]
                else []
            ),
            "performance_wall_clock_omitted_from_canonical_digest",
            "private_provider_human_visual_fidelity_tiers_not_run",
            "geometry_clean_acceptance_gate_rejected",
            "clean_geometry_proposal_not_available",
            "provider_bakeoff_d0_contract_only",
            "local_open_model_adapter_not_run_missing_runtime_or_weights",
            "zeroone_unavailable_optional",
            "procedural_fixture_not_production_asset",
        ],
        "zeroOne": {"staticAvailable": False, "dynamicAvailable": False, "required": False},
        "extensions": {"closyImplementation": "phase7-material-physics-d0-public-tshirt"},
    }


def _capabilities(
    production_binding_c3: dict[str, Any], source_render_fidelity: dict[str, Any]
) -> dict[str, bool]:
    return {
        "patternAvailable": True,
        "simulationReadyTopologyAvailable": True,
        "authoredMaterialPresetAvailable": True,
        "fabricPhysicsDescriptorAvailable": True,
        "materialPresetRegistryAvailable": True,
        "materialPresetSelectionAvailable": True,
        "materialCalibrationFixturesAvailable": True,
        "materialMotionSuiteAvailable": True,
        "materialDenseBindingReconstructionAvailable": True,
        "acceptedForD0MaterialPhysics": True,
        "realFabricCalibrationAvailable": False,
        "learnedMaterialInferenceAvailable": False,
        "privateUserMaterialEstimationAvailable": False,
        "productionGpuMaterialMotionAvailable": False,
        "conventionalGlbAvailable": True,
        "simToRenderBindingAvailable": True,
        "bindingReconstructionValidated": True,
        "actualClothSettleAvailable": True,
        "selfCollisionAvailable": True,
        "selfCollisionEvidenceAvailable": True,
        "sourceImageTextureAvailable": True,
        "sourceCaptureRecordAvailable": True,
        "captureQualityScored": True,
        "visualObservationsAvailable": True,
        "garmentMaskAvailable": True,
        "garmentLandmarksAvailable": True,
        "editableCorrectionRecordAvailable": True,
        "localRasterFixtureIngestionAvailable": True,
        "pixelDerivedVisualParsingAvailable": True,
        "targetGarmentPersonBackgroundMasksAvailable": True,
        "tshirtSemanticPartMasksAvailable": True,
        "tshirtOpeningBoundaryEvidenceAvailable": True,
        "structuredCorrectionReplayAvailable": True,
        "frontRearCapturePairingAvailable": True,
        "viewOrientationScaleEvidenceAvailable": True,
        "crossViewGarmentIdentityAvailable": True,
        "semanticIdentityTrackingAvailable": True,
        "multiviewVisualFusionAvailable": True,
        "phase2QualityGateAvailable": True,
        "multiviewCorrectionReplayAvailable": True,
        "phase2ResumeCacheAvailable": True,
        "privateUserRasterProcessingAvailable": False,
        "learnedSegmentationModelAvailable": False,
        "tshirtParameterFitAvailable": True,
        "fittingQualityScored": True,
        "imageConditionedFittingAvailable": True,
        "multiviewFittingLossAvailable": True,
        "confidenceWeightedFittingAvailable": True,
        "fittingPriorsSeparatedAvailable": True,
        "fittingOptimizationTraceAvailable": True,
        "fitAlternativesAvailable": True,
        "heldOutPerturbationFitEvaluationAvailable": True,
        "settledRenderFitComparisonAvailable": True,
        "decodedBitmapAtlasAvailable": True,
        "sourceRenderFidelityAvailable": True,
        "acceptedForD0PublicFixture": bool(
            source_render_fidelity["acceptanceTiers"]["acceptedForD0PublicFixture"]["accepted"]
        ),
        "textureIdentityEvidenceAvailable": True,
        "pbrMaterialObservationAvailable": True,
        "sourceTextureProjectionAvailable": True,
        "pbrMaterialMapExportAvailable": True,
        "logoPrintPreservationMaskAvailable": True,
        "controlledTextureInpaintingInterfaceAvailable": True,
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
        "geometryStitchedShellAvailable": True,
        "geometryVisualShellReviewAvailable": True,
        "renderTangentsPersistedAvailable": True,
        "poseSuiteBindingEvidenceAvailable": True,
        "productionBindingC3EvidenceAvailable": True,
        "productionBindingC3ProfileAvailable": bool(
            production_binding_c3["readiness"]["acceptedForD0RuntimeBindingProfile"]
        ),
        "productionBindingContractAvailable": True,
        "deterministicInspectionArtifactsAvailable": True,
        "visualEvidenceTiersSeparated": True,
        "geometryCleanAcceptanceGateAvailable": True,
        "providerProvenanceAvailable": True,
        "geometryProviderRegistryAvailable": True,
        "providerContractValidationAvailable": True,
        "providerBakeoffReportAvailable": True,
        "manualGeometryImportAdapterDeclared": True,
        "manualGeometryImportAssetAvailable": True,
        "localOpenModelAdapterDeclared": True,
        "localOpenModelExecutionAvailable": False,
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
    multiview_fusion: dict[str, Any],
    fit_report: dict[str, Any],
    texture_identity: dict[str, Any],
    geometry_proposal: dict[str, Any],
    raw_geometry_topology: dict[str, Any],
    provider_bakeoff: dict[str, Any],
    geometry_cleanup_plan: dict[str, Any],
    geometry_cleanup_result: dict[str, Any],
    geometry_semantic_transfer: dict[str, Any],
    geometry_binding_candidate: dict[str, Any],
    geometry_binding_validation: dict[str, Any],
    geometry_repair_retopology_plan: dict[str, Any],
    geometry_repair_result: dict[str, Any],
    geometry_runtime_binding_result: dict[str, Any],
    geometry_material_uv_transfer: dict[str, Any],
    geometry_stitched_shell: dict[str, Any],
    geometry_visual_shell_review: dict[str, Any],
    render_frame_pose_suite: dict[str, Any],
    production_binding_c3: dict[str, Any],
    self_collision_report: dict[str, Any],
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
            "stageVersion": visual_observations["stageVersion"],
            "sourceRecordId": visual_observations["sourceRecordId"],
            "providerAlgorithmVersion": visual_observations["provider"].get("algorithmVersion"),
            "maskCount": visual_observations["aggregate"]["maskCount"],
            "targetGarmentMaskCount": visual_observations["aggregate"].get(
                "targetGarmentMaskCount",
                0,
            ),
            "personBodyProxyMaskCount": visual_observations["aggregate"].get(
                "personBodyProxyMaskCount",
                0,
            ),
            "backgroundMaskCount": visual_observations["aggregate"].get(
                "backgroundMaskCount",
                0,
            ),
            "occlusionUncertaintyMaskCount": visual_observations["aggregate"].get(
                "occlusionUncertaintyMaskCount",
                0,
            ),
            "semanticPartCount": visual_observations["aggregate"].get("semanticPartCount", 0),
            "openingBoundaryCount": visual_observations["aggregate"].get(
                "openingBoundaryCount",
                0,
            ),
            "pixelDerivedViewCount": visual_observations["aggregate"].get(
                "pixelDerivedViewCount",
                0,
            ),
            "observedLandmarkCount": len(visual_observations["aggregate"]["observedLandmarks"]),
            "requiredLandmarkCount": len(visual_observations["aggregate"]["requiredLandmarks"]),
            "meanMaskConfidence": visual_observations["aggregate"]["meanMaskConfidence"],
            "meanLandmarkConfidence": visual_observations["aggregate"]["meanLandmarkConfidence"],
            "metrics": {
                "meanMaskIoU": visual_observations["aggregate"].get("meanMaskIoU"),
                "meanBoundaryFScore": visual_observations["aggregate"].get("meanBoundaryFScore"),
                "meanSemanticPartIoU": visual_observations["aggregate"].get("meanSemanticPartIoU"),
                "meanLandmarkErrorNormalised": visual_observations["aggregate"].get(
                    "meanLandmarkErrorNormalised"
                ),
                "openingPrecision": visual_observations["aggregate"].get("openingPrecision"),
                "openingRecall": visual_observations["aggregate"].get("openingRecall"),
            },
            "correctionRecordId": correction_record["correctionRecordId"],
            "correctionOperationCount": len(correction_record["operations"]),
            "correctionApplicationStatus": correction_record.get("application", {}).get("status"),
            "correctedVisualRecordHash": correction_record.get("application", {}).get(
                "afterVisualRecordHash"
            ),
            "warnings": visual_observations["warnings"],
        },
        "multiview_fusion_quality.json": {
            "schemaVersion": 1,
            "status": multiview_fusion["qualityGate"]["status"],
            "fusionRecordId": multiview_fusion["fusionRecordId"],
            "stageVersion": multiview_fusion["stageVersion"],
            "sourceVisualUnderstandingId": multiview_fusion["sourceVisualUnderstandingId"],
            "sourceCorrectionRecordId": multiview_fusion["sourceCorrectionRecordId"],
            "requiredPairStatus": multiview_fusion["viewPairing"]["requiredPairs"][0]["status"],
            "optionalRoleCount": len(multiview_fusion["viewPairing"]["optionalRoles"]),
            "fusedMaskCount": len(multiview_fusion["fusedEvidence"]["masks"]),
            "fusedLandmarkCount": len(multiview_fusion["fusedEvidence"]["landmarks"]),
            "fusedOpeningCount": len(multiview_fusion["fusedEvidence"]["openings"]),
            "registrationStatus": multiview_fusion["registration"]["status"],
            "qualityGateStatus": multiview_fusion["qualityGate"]["status"],
            "expensiveDownstreamAllowed": multiview_fusion["qualityGate"]["readiness"][
                "expensiveDownstreamAllowed"
            ],
            "correctionReplayStatus": multiview_fusion["correctionReplay"]["status"],
            "cacheKey": multiview_fusion["orchestration"]["cacheKey"],
            "warnings": multiview_fusion["warnings"],
        },
        "fitting_quality.json": {
            "schemaVersion": 1,
            "status": fit_report["status"],
            "fitReportId": fit_report["fitReportId"],
            "sourceVisualUnderstandingId": fit_report["sourceVisualUnderstandingId"],
            "sourceMultiviewFusionId": fit_report.get("sourceMultiviewFusionId"),
            "accepted": fit_report["accepted"],
            "method": fit_report["method"],
            "imageConditioned": fit_report["method"].startswith("deterministic_multiview"),
            "losses": fit_report["losses"],
            "thresholds": fit_report["thresholds"],
            "convergence": fit_report.get("convergence"),
            "heldOutEvaluation": fit_report.get("heldOutEvaluation"),
            "perturbationEvaluation": fit_report.get("perturbationEvaluation"),
            "settledRenderComparison": fit_report.get("settledRenderComparison"),
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
            "sourceProjectionCount": texture_identity["sourceViewProjection"]["projectionCount"],
            "visibleProjectionCount": texture_identity["sourceViewProjection"][
                "visibleProjectionCount"
            ],
            "meanVisibleConfidence": texture_identity["visibleRegionConfidence"][
                "meanVisibleConfidence"
            ],
            "pbrSourceBackedMapCount": texture_identity["pbrMaterialMaps"]["sourceBackedMapCount"],
            "legacyJsonPbrPlaceholderMapCount": texture_identity["pbrMaterialMaps"][
                "placeholderMapCount"
            ],
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
        "geometry_stitched_shell.json": geometry_stitched_shell,
        "geometry_visual_shell_review.json": geometry_visual_shell_review,
        "render_frame_pose_suite.json": render_frame_pose_suite,
        "production_binding_c3.json": production_binding_c3,
        "self_collision_report.json": self_collision_report,
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
            "selfCollisionReportStatus": self_collision_report["readiness"]["status"],
            "selfCollisionUnresolvedContactCount": self_collision_report["metrics"][
                "unresolvedContactCount"
            ],
            "inspectionExportPath": "simulation/simulation_mesh.glb",
        },
        "render_quality.json": {
            "schemaVersion": 1,
            "status": "pass",
            "mesh": _mesh_counts(render_mesh),
            "renderShellSeparateFromSimulation": True,
            "glbTangentsPersisted": render_frame_pose_suite["readiness"]["glbTangentsPersisted"],
            "poseSuitePass": render_frame_pose_suite["readiness"]["poseSuitePass"],
        },
        "binding_quality.json": {
            "schemaVersion": 1,
            "status": "pass",
            "recordCount": binding_manifest["recordCount"],
            "maximumReconstructionError": binding_manifest["maximumReconstructionError"],
            "rmsReconstructionError": binding_manifest["rmsReconstructionError"],
            "perturbationFollowTest": "supported_by_reconstruction_api",
            "productionBindingC3Status": production_binding_c3["readiness"]["status"],
            "productionBindingC3Profile": production_binding_c3["profile"]["id"],
            "motionStateCount": production_binding_c3["motionSuite"]["stateCount"],
            "maxMotionReconstructionErrorMeters": production_binding_c3["aggregate"][
                "maxReconstructionErrorMeters"
            ],
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
    multiview_fusion: dict[str, Any],
    fit_report: dict[str, Any],
    texture_identity: dict[str, Any],
    geometry_proposal: dict[str, Any],
    raw_geometry_topology: dict[str, Any],
    provider_bakeoff: dict[str, Any],
    geometry_cleanup_plan: dict[str, Any],
    geometry_cleanup_result: dict[str, Any],
    geometry_semantic_transfer: dict[str, Any],
    geometry_binding_candidate: dict[str, Any],
    geometry_binding_validation: dict[str, Any],
    geometry_repair_retopology_plan: dict[str, Any],
    geometry_repair_result: dict[str, Any],
    geometry_runtime_binding_result: dict[str, Any],
    geometry_material_uv_transfer: dict[str, Any],
    geometry_stitched_shell: dict[str, Any],
    geometry_visual_shell_review: dict[str, Any],
    render_frame_pose_suite: dict[str, Any],
    production_binding_c3: dict[str, Any],
    self_collision_report: dict[str, Any],
    geometry_clean_acceptance_gate: dict[str, Any],
    clean_geometry_proposal: dict[str, Any],
    provider_registry: dict[str, Any],
    inspection_report: dict[str, Any],
    source_render_fidelity: dict[str, Any],
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
                "pixel_derived_visual_observations",
                TSHIRT_VISUAL_OBSERVATION_VERSION,
                {
                    "maskRepresentation": "decoded_pixel_rle_summary",
                    "pixelDerivedViewCount": visual_observations["aggregate"].get(
                        "pixelDerivedViewCount", 0
                    ),
                    "requiredLandmarkCount": len(
                        visual_observations["aggregate"]["requiredLandmarks"]
                    ),
                    "externalApis": False,
                },
                [str(visual_observations["integrity"]["visualRecordHash"])],
            ),
            _stage(
                "applied_correction_record",
                CORRECTION_RECORD_VERSION,
                {
                    "editable": True,
                    "operationCount": len(correction_record["operations"]),
                    "applicationStatus": correction_record.get("application", {}).get("status"),
                    "externalApis": False,
                },
                [str(correction_record["integrity"]["correctionRecordHash"])],
            ),
            _stage(
                "multiview_capture_fusion",
                MULTIVIEW_FUSION_VERSION,
                {
                    "qualityGateStatus": multiview_fusion["qualityGate"]["status"],
                    "viewCount": multiview_fusion["fusedEvidence"]["viewCount"],
                    "fusedMaskCount": len(multiview_fusion["fusedEvidence"]["masks"]),
                    "fusedLandmarkCount": len(multiview_fusion["fusedEvidence"]["landmarks"]),
                    "expensiveDownstreamAllowed": multiview_fusion["qualityGate"]["readiness"][
                        "expensiveDownstreamAllowed"
                    ],
                    "cacheKey": multiview_fusion["orchestration"]["cacheKey"],
                    "externalApis": False,
                },
                [str(multiview_fusion["integrity"]["multiviewFusionRecordHash"])],
            ),
            _stage(
                "tshirt_visual_parameter_fit",
                TSHIRT_FIT_REPORT_VERSION,
                {
                    "method": fit_report["method"],
                    "accepted": bool(fit_report["accepted"]),
                    "status": fit_report["status"],
                    "sourceMultiviewFusionId": fit_report.get("sourceMultiviewFusionId"),
                    "multiviewSilhouetteMeanIoU": fit_report["losses"].get(
                        "multiviewSilhouetteMeanIoU"
                    ),
                    "optimizationHistoryCount": fit_report["convergence"]["persistedHistoryCount"],
                    "candidateEvaluationCount": fit_report["convergence"][
                        "candidateEvaluationCount"
                    ],
                    "acceptedMoveCount": fit_report["convergence"]["acceptedMoveCount"],
                    "settledRenderComparisonStatus": fit_report["settledRenderComparison"][
                        "status"
                    ],
                },
                [
                    str(fit_report["integrity"]["fitReportHash"]),
                    str(multiview_fusion["integrity"]["multiviewFusionRecordHash"]),
                ],
            ),
            _stage(
                "source_texture_pbr_recovery",
                TEXTURE_IDENTITY_VERSION,
                {
                    "sourceTextureAvailable": texture_identity["sourceTextureAvailable"],
                    "generatedAtlasAvailable": texture_identity["generatedAtlasAvailable"],
                    "textureProjectionRun": texture_identity["textureProjectionRun"],
                    "materialRegionCount": len(texture_identity["observedMaterialRegions"]),
                    "visibleProjectionCount": texture_identity["sourceViewProjection"][
                        "visibleProjectionCount"
                    ],
                    "sourceBackedPbrMapCount": texture_identity["pbrMaterialMaps"][
                        "sourceBackedMapCount"
                    ],
                    "decodedPublicSourcePixelsExported": True,
                    "decodedRasterAssetsPersisted": texture_identity["decodedBitmapAtlas"][
                        "decodedRasterAssetsPersisted"
                    ],
                    "sourceObservedFraction": texture_identity["decodedBitmapAtlas"][
                        "sourceObservedFraction"
                    ],
                },
                [str(texture_identity["integrity"]["textureIdentityHash"])],
            ),
            _stage(
                "decoded_source_render_fidelity",
                SOURCE_RENDER_FIDELITY_VERSION,
                {
                    "status": source_render_fidelity["status"],
                    "viewCount": source_render_fidelity["aggregate"]["viewCount"],
                    "meanSilhouetteIoU": source_render_fidelity["aggregate"]["meanSilhouetteIoU"],
                    "meanForegroundLinearSrgbMae": source_render_fidelity["aggregate"][
                        "meanForegroundLinearSrgbMae"
                    ],
                    "acceptedForD0PublicFixture": source_render_fidelity["acceptanceTiers"][
                        "acceptedForD0PublicFixture"
                    ]["accepted"],
                    "acceptedForCanonicalProduction": False,
                },
                [str(source_render_fidelity["integrity"]["sourceRenderFidelityHash"])],
            ),
            _stage(
                "geometry_provider_registry",
                PROVIDER_REGISTRY_VERSION,
                {
                    "selectedProviderId": provider_registry["selectedProviderId"],
                    "contractVersion": provider_registry["contractVersion"],
                    "manualLocalImportAdapterDeclared": provider_registry["d0Capabilities"][
                        "manualLocalImportAdapterDeclared"
                    ],
                    "manualLocalImportAssetAvailable": provider_registry["d0Capabilities"][
                        "manualLocalImportAssetAvailable"
                    ],
                    "localOpenModelAdapterDeclared": provider_registry["d0Capabilities"][
                        "localOpenModelAdapterDeclared"
                    ],
                    "localOpenModelExecutionAvailable": provider_registry["d0Capabilities"][
                        "localOpenModelExecutionAvailable"
                    ],
                    "externalProvidersConfigured": False,
                    "supportedDomain": provider_registry["scope"]["supportedDomain"],
                },
                [str(provider_registry["integrity"]["providerRegistryHash"])],
            ),
            _stage(
                "provider_bakeoff_report",
                PROVIDER_BAKEOFF_REPORT_VERSION,
                {
                    "providerCount": provider_bakeoff["aggregate"]["providerCount"],
                    "executedProviderCount": provider_bakeoff["aggregate"]["executedProviderCount"],
                    "notRunProviderCount": provider_bakeoff["aggregate"]["notRunProviderCount"],
                    "canonicalAcceptedProviderCount": provider_bakeoff["aggregate"][
                        "canonicalAcceptedProviderCount"
                    ],
                    "bestAvailableProviderId": provider_bakeoff["aggregate"][
                        "bestAvailableProviderId"
                    ],
                },
                [str(provider_bakeoff["integrity"]["providerBakeoffHash"])],
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
                "geometry_stitched_shell",
                GEOMETRY_STITCHED_SHELL_VERSION,
                {
                    "meshStitchOrWeldExecutionRun": geometry_stitched_shell["execution"][
                        "meshStitchOrWeldExecutionRun"
                    ],
                    "sourceVertexClassRewriteRun": geometry_stitched_shell["execution"][
                        "sourceVertexClassRewriteRun"
                    ],
                    "faceIndexRewriteRun": geometry_stitched_shell["execution"][
                        "faceIndexRewriteRun"
                    ],
                    "analysisAssetPath": geometry_stitched_shell["analysisAsset"]["path"],
                    "renderAssetPath": geometry_stitched_shell["renderAsset"]["path"],
                    "meshStitchOrWeldProven": geometry_stitched_shell["readiness"][
                        "meshStitchOrWeldProven"
                    ],
                    "status": geometry_stitched_shell["readiness"]["status"],
                },
                [str(geometry_stitched_shell["integrity"]["geometryStitchedShellHash"])],
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
                    "representationSilhouetteComparisonRun": geometry_visual_shell_review[
                        "execution"
                    ]["representationSilhouetteComparisonRun"],
                    "representationSilhouetteAccepted": geometry_visual_shell_review["readiness"][
                        "representationSilhouetteAccepted"
                    ],
                    "sourceImageVisualComparisonRun": geometry_visual_shell_review["execution"][
                        "sourceImageVisualComparisonRun"
                    ],
                    "providerAppearanceComparisonRun": geometry_visual_shell_review["execution"][
                        "providerAppearanceComparisonRun"
                    ],
                    "stitchGraphConnectivityCheckRun": geometry_visual_shell_review["execution"][
                        "stitchGraphConnectivityCheckRun"
                    ],
                    "stitchGraphConnectable": geometry_visual_shell_review["readiness"][
                        "stitchGraphConnectable"
                    ],
                    "singleShellWeldProofRun": geometry_visual_shell_review["execution"][
                        "singleShellWeldProofRun"
                    ],
                    "meshStitchOrWeldExecutionRun": geometry_visual_shell_review["execution"][
                        "meshStitchOrWeldExecutionRun"
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
                "render_frame_pose_suite",
                FRAME_POSE_SUITE_VERSION,
                {
                    "renderAssetPath": render_frame_pose_suite["sourceAssets"]["renderAsset"][
                        "path"
                    ],
                    "glbTangentsPersisted": render_frame_pose_suite["readiness"][
                        "glbTangentsPersisted"
                    ],
                    "poseSuiteRun": render_frame_pose_suite["readiness"]["poseSuiteRun"],
                    "poseSuitePass": render_frame_pose_suite["readiness"]["poseSuitePass"],
                    "acceptedForRuntimeFramePreview": render_frame_pose_suite["readiness"][
                        "acceptedForRuntimeFramePreview"
                    ],
                    "acceptedForCleanProposal": False,
                },
                [str(render_frame_pose_suite["integrity"]["renderFramePoseSuiteHash"])],
            ),
            _stage(
                "deterministic_inspection_artifacts",
                INSPECTION_ARTIFACT_REPORT_VERSION,
                {
                    "rendererVersion": INSPECTION_RENDERER_VERSION,
                    "manifestPath": inspection_report["manifestPath"],
                    "artifactCount": inspection_report["metrics"]["artifactCount"],
                    "topologyRepresentationInspectionRun": inspection_report["readiness"][
                        "topologyRepresentationInspectionRun"
                    ],
                    "providerGeometryAppearanceComparisonRun": inspection_report["readiness"][
                        "providerGeometryAppearanceComparisonRun"
                    ],
                    "sourceImageSilhouetteComparisonRun": inspection_report["readiness"][
                        "sourceImageSilhouetteComparisonRun"
                    ],
                    "sourceImageAppearanceComparisonRun": inspection_report["readiness"][
                        "sourceImageAppearanceComparisonRun"
                    ],
                    "acceptedForD0PublicFixture": inspection_report["readiness"][
                        "acceptedForD0PublicFixture"
                    ],
                    "humanVisualReviewRun": inspection_report["readiness"]["humanVisualReviewRun"],
                    "acceptedForVisualFidelity": False,
                    "acceptedForCleanProposal": False,
                },
                [str(inspection_report["integrity"]["inspectionReportHash"])],
            ),
            _stage(
                "production_binding_c3_profile",
                PRODUCTION_BINDING_C3_REPORT_VERSION,
                {
                    "profile": production_binding_c3["profile"]["id"],
                    "gateC3Status": production_binding_c3["readiness"]["gateC3Status"],
                    "motionStateCount": production_binding_c3["motionSuite"]["stateCount"],
                    "persistedByteValidationRun": production_binding_c3["execution"][
                        "persistedByteValidationRun"
                    ],
                    "denseBindingRun": production_binding_c3["execution"]["denseBindingRun"],
                    "fallbackBindingRun": production_binding_c3["execution"]["fallbackBindingRun"],
                    "acceptedForGlobalPhase6": False,
                },
                [str(production_binding_c3["integrity"]["productionBindingC3ReportHash"])],
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
                    "representationSilhouetteComparisonRun": geometry_clean_acceptance_gate[
                        "execution"
                    ]["representationSilhouetteComparisonRun"],
                    "representationSilhouetteAccepted": geometry_clean_acceptance_gate["execution"][
                        "representationSilhouetteAccepted"
                    ],
                    "meshStitchOrWeldExecutionRun": geometry_clean_acceptance_gate["execution"][
                        "meshStitchOrWeldExecutionRun"
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
                SOLVER_VERSION,
                {
                    "clothSettleRun": True,
                    "convergenceState": str(settle_diagnostics["convergenceState"]),
                    "selfCollisionAvailable": True,
                    "settings": settle_diagnostics["settings"],
                },
                [
                    str(settle_diagnostics["restContentHash"]),
                    str(settle_diagnostics["settledContentHash"]),
                ],
            ),
            _stage(
                "reference_self_collision",
                SELF_COLLISION_REPORT_VERSION,
                {
                    "selfCollisionRun": self_collision_report["execution"]["selfCollisionRun"],
                    "broadPhaseRun": self_collision_report["execution"]["broadPhaseRun"],
                    "narrowPhaseRun": self_collision_report["execution"]["narrowPhaseRun"],
                    "correctionRun": self_collision_report["execution"]["correctionRun"],
                    "status": self_collision_report["readiness"]["status"],
                    "acceptedForProductionGpuSolver": False,
                },
                [str(self_collision_report["integrity"]["selfCollisionReportHash"])],
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
            "self_collision_d0_reference_only",
            "self_collision_unresolved_contacts_d0_reference",
            "unsupported_high_velocity_tunnelling",
            "performance_wall_clock_omitted_from_canonical_digest",
            "manual_raw_geometry_proposal_not_canonical",
            "geometry_binding_candidate_not_runtime_binding",
            "geometry_binding_validation_rejected_runtime_binding",
            "geometry_stitched_shell_output_not_clean_proven",
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
    multiview_fusion = context["multiviewFusion"]
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
    geometry_stitched_shell = context["geometryStitchedShell"]
    stitched_shell_mesh = context["stitchedShellMesh"]
    geometry_visual_shell_review = context["geometryVisualShellReview"]
    render_frame_pose_suite = context["renderFramePoseSuite"]
    production_binding_c3 = context["productionBindingC3"]
    self_collision_report = context["selfCollisionReport"]
    inspection_manifest = context["inspectionManifest"]
    inspection_report = context["inspectionReport"]
    source_render_fidelity = context["sourceRenderFidelity"]
    geometry_clean_acceptance_gate = context["geometryCleanAcceptanceGate"]
    clean_geometry_proposal = context["cleanGeometryProposal"]
    provider_registry = context["providerRegistry"]
    provider_bakeoff = context["providerBakeoff"]
    material_registry = context["materialRegistry"]
    material_selection = context["materialSelection"]
    material_calibration = context["materialCalibration"]
    material_motion_suite = context["materialMotionSuite"]
    return {
        "schemaVersion": 1,
        "garmentId": manifest["garmentId"],
        "canonicalPackageDigest": manifest["canonicalPackageDigest"],
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
            "stitchedShellVertices": stitched_shell_mesh.vertex_count,
            "stitchedShellTriangles": stitched_shell_mesh.triangle_count,
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
            "stageVersion": visual_observations["stageVersion"],
            "providerAlgorithmVersion": visual_observations["provider"].get("algorithmVersion"),
            "maskCount": visual_observations["aggregate"]["maskCount"],
            "targetGarmentMaskCount": visual_observations["aggregate"].get(
                "targetGarmentMaskCount",
                0,
            ),
            "personBodyProxyMaskCount": visual_observations["aggregate"].get(
                "personBodyProxyMaskCount",
                0,
            ),
            "backgroundMaskCount": visual_observations["aggregate"].get(
                "backgroundMaskCount",
                0,
            ),
            "occlusionUncertaintyMaskCount": visual_observations["aggregate"].get(
                "occlusionUncertaintyMaskCount",
                0,
            ),
            "semanticPartCount": visual_observations["aggregate"].get("semanticPartCount", 0),
            "openingBoundaryCount": visual_observations["aggregate"].get(
                "openingBoundaryCount",
                0,
            ),
            "pixelDerivedViewCount": visual_observations["aggregate"].get(
                "pixelDerivedViewCount",
                0,
            ),
            "observedLandmarkCount": len(visual_observations["aggregate"]["observedLandmarks"]),
            "requiredLandmarkCount": len(visual_observations["aggregate"]["requiredLandmarks"]),
            "meanMaskConfidence": visual_observations["aggregate"]["meanMaskConfidence"],
            "meanLandmarkConfidence": visual_observations["aggregate"]["meanLandmarkConfidence"],
            "meanMaskIoU": visual_observations["aggregate"].get("meanMaskIoU"),
            "meanBoundaryFScore": visual_observations["aggregate"].get("meanBoundaryFScore"),
            "meanSemanticPartIoU": visual_observations["aggregate"].get("meanSemanticPartIoU"),
            "meanLandmarkErrorNormalised": visual_observations["aggregate"].get(
                "meanLandmarkErrorNormalised"
            ),
            "openingPrecision": visual_observations["aggregate"].get("openingPrecision"),
            "openingRecall": visual_observations["aggregate"].get("openingRecall"),
            "correctionRecordId": correction_record["correctionRecordId"],
            "correctionOperationCount": len(correction_record["operations"]),
            "correctionApplicationStatus": correction_record.get("application", {}).get("status"),
        },
        "multiviewFusion": {
            "fusionRecordId": multiview_fusion["fusionRecordId"],
            "stageVersion": multiview_fusion["stageVersion"],
            "status": multiview_fusion["qualityGate"]["status"],
            "viewCount": multiview_fusion["fusedEvidence"]["viewCount"],
            "requiredPairStatus": multiview_fusion["viewPairing"]["requiredPairs"][0]["status"],
            "optionalRoleCount": len(multiview_fusion["viewPairing"]["optionalRoles"]),
            "fusedMaskCount": len(multiview_fusion["fusedEvidence"]["masks"]),
            "fusedLandmarkCount": len(multiview_fusion["fusedEvidence"]["landmarks"]),
            "fusedOpeningCount": len(multiview_fusion["fusedEvidence"]["openings"]),
            "registrationStatus": multiview_fusion["registration"]["status"],
            "correctionReplayStatus": multiview_fusion["correctionReplay"]["status"],
            "expensiveDownstreamAllowed": multiview_fusion["qualityGate"]["readiness"][
                "expensiveDownstreamAllowed"
            ],
            "cacheKey": multiview_fusion["orchestration"]["cacheKey"],
        },
        "fitting": {
            "fitReportId": fit_report["fitReportId"],
            "fitterVersion": fit_report["fitterVersion"],
            "method": fit_report["method"],
            "status": fit_report["status"],
            "accepted": fit_report["accepted"],
            "landmarkRmsNormalised": fit_report["losses"]["landmarkRmsNormalised"],
            "maskWidthErrorMeters": fit_report["losses"]["maskWidthErrorMeters"],
            "multiviewSilhouetteMeanIoU": fit_report["losses"].get("multiviewSilhouetteMeanIoU"),
            "boundaryErrorNormalised": fit_report["losses"].get("boundaryErrorNormalised"),
            "openingAlignmentErrorNormalised": fit_report["losses"].get(
                "openingAlignmentErrorNormalised"
            ),
            "confidenceWeightedLoss": fit_report["losses"].get("confidenceWeightedLoss"),
            "optimizationHistoryCount": fit_report["convergence"]["persistedHistoryCount"],
            "candidateEvaluationCount": fit_report["convergence"]["candidateEvaluationCount"],
            "acceptedMoveCount": fit_report["convergence"]["acceptedMoveCount"],
            "initialObjective": fit_report["convergence"]["initialObjective"],
            "finalObjective": fit_report["convergence"]["finalObjective"],
            "settledRenderComparisonStatus": fit_report["settledRenderComparison"]["status"],
            "heldOutStatus": fit_report.get("heldOutEvaluation", {}).get("status"),
            "perturbationStatus": fit_report.get("perturbationEvaluation", {}).get("status"),
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
            "sourceProjectionCount": texture_identity["sourceViewProjection"]["projectionCount"],
            "visibleProjectionCount": texture_identity["sourceViewProjection"][
                "visibleProjectionCount"
            ],
            "meanVisibleConfidence": texture_identity["visibleRegionConfidence"][
                "meanVisibleConfidence"
            ],
            "pbrSourceBackedMapCount": texture_identity["pbrMaterialMaps"]["sourceBackedMapCount"],
            "pbrPlaceholderMapCount": texture_identity["pbrMaterialMaps"]["placeholderMapCount"],
            "decodedRasterAssetsPersisted": texture_identity["decodedBitmapAtlas"][
                "decodedRasterAssetsPersisted"
            ],
            "decodedBitmapPbrReportPath": texture_identity["decodedBitmapAtlas"]["reportPath"],
            "sourceObservedFraction": texture_identity["decodedBitmapAtlas"][
                "sourceObservedFraction"
            ],
            "generatedControlledFillFraction": texture_identity["decodedBitmapAtlas"][
                "generatedControlledFillFraction"
            ],
        },
        "sourceRenderFidelity": {
            "reportId": source_render_fidelity["reportId"],
            "status": source_render_fidelity["status"],
            "viewCount": source_render_fidelity["aggregate"]["viewCount"],
            "meanSilhouetteIoU": source_render_fidelity["aggregate"]["meanSilhouetteIoU"],
            "maximumBoundaryChamferNormalised": source_render_fidelity["aggregate"][
                "maximumBoundaryChamferNormalised"
            ],
            "meanForegroundLinearSrgbMae": source_render_fidelity["aggregate"][
                "meanForegroundLinearSrgbMae"
            ],
            "allViewsNonBlank": source_render_fidelity["aggregate"]["allViewsNonBlank"],
            "acceptedForD0PublicFixture": source_render_fidelity["acceptanceTiers"][
                "acceptedForD0PublicFixture"
            ]["accepted"],
            "acceptedForPrivateUserCapture": False,
            "acceptedForProviderGeneratedShell": False,
            "acceptedForHumanVisualReview": False,
            "acceptedForCanonicalProduction": False,
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
        "geometryStitchedShell": {
            "reportId": geometry_stitched_shell["reportId"],
            "status": geometry_stitched_shell["readiness"]["status"],
            "meshStitchOrWeldExecutionRun": geometry_stitched_shell["execution"][
                "meshStitchOrWeldExecutionRun"
            ],
            "sourceVertexClassRewriteRun": geometry_stitched_shell["execution"][
                "sourceVertexClassRewriteRun"
            ],
            "faceIndexRewriteRun": geometry_stitched_shell["execution"]["faceIndexRewriteRun"],
            "operationCount": geometry_stitched_shell["execution"]["operationCount"],
            "meshStitchOrWeldProven": geometry_stitched_shell["readiness"][
                "meshStitchOrWeldProven"
            ],
            "logicalShellCount": geometry_stitched_shell["topologyAudit"]["logicalShellCount"],
            "boundaryLoopCount": geometry_stitched_shell["topologyAudit"]["boundaryLoopCount"],
            "expectedOpeningCount": geometry_stitched_shell["topologyAudit"][
                "expectedOpeningCount"
            ],
            "nonManifoldEdgeCount": geometry_stitched_shell["topologyAudit"][
                "nonManifoldEdgeCount"
            ],
            "maxPostStitchResidualMeters": geometry_stitched_shell["topologyAudit"][
                "maxPostStitchResidualMeters"
            ],
            "analysisAssetPath": geometry_stitched_shell["analysisAsset"]["path"],
            "renderAssetPath": geometry_stitched_shell["renderAsset"]["path"],
            "topologyHash": geometry_stitched_shell["renderAsset"]["topologyHash"],
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
            "representationSilhouetteComparisonRun": geometry_visual_shell_review["execution"][
                "representationSilhouetteComparisonRun"
            ],
            "representationSilhouetteAccepted": geometry_visual_shell_review["readiness"][
                "representationSilhouetteAccepted"
            ],
            "visualFidelityScore": geometry_visual_shell_review["aggregate"]["visualFidelityScore"],
            "acceptedForVisualFidelity": geometry_visual_shell_review["readiness"][
                "acceptedForVisualFidelity"
            ],
            "sourceImageVisualComparisonRun": geometry_visual_shell_review["execution"][
                "sourceImageVisualComparisonRun"
            ],
            "sourceImageVisualFidelityAccepted": geometry_visual_shell_review["readiness"][
                "sourceImageVisualFidelityAccepted"
            ],
            "providerAppearanceComparisonRun": geometry_visual_shell_review["execution"][
                "providerAppearanceComparisonRun"
            ],
            "providerAppearanceAccepted": geometry_visual_shell_review["readiness"][
                "providerAppearanceAccepted"
            ],
            "stitchGraphConnectivityCheckRun": geometry_visual_shell_review["execution"][
                "stitchGraphConnectivityCheckRun"
            ],
            "stitchGraphConnectable": geometry_visual_shell_review["readiness"][
                "stitchGraphConnectable"
            ],
            "singleShellWeldProofRun": geometry_visual_shell_review["execution"][
                "singleShellWeldProofRun"
            ],
            "singleShellWeldProven": geometry_visual_shell_review["readiness"][
                "singleShellWeldProven"
            ],
            "meshStitchOrWeldExecutionRun": geometry_visual_shell_review["execution"][
                "meshStitchOrWeldExecutionRun"
            ],
            "meshStitchOrWeldProven": geometry_visual_shell_review["readiness"][
                "meshStitchOrWeldProven"
            ],
            "boundaryEdgeCount": geometry_visual_shell_review["aggregate"]["boundaryEdgeCount"],
        },
        "inspectionArtifacts": {
            "manifestId": inspection_manifest["manifestId"],
            "reportId": inspection_report["reportId"],
            "rendererVersion": inspection_manifest["rendererVersion"],
            "artifactCount": inspection_manifest["artifactCount"],
            "topologyRepresentationInspectionRun": inspection_report["readiness"][
                "topologyRepresentationInspectionRun"
            ],
            "canonicalSimulationToRenderSilhouetteRun": inspection_report["readiness"][
                "canonicalSimulationToRenderSilhouetteRun"
            ],
            "providerGeometryAppearanceComparisonRun": inspection_report["readiness"][
                "providerGeometryAppearanceComparisonRun"
            ],
            "sourceImageSilhouetteComparisonRun": inspection_report["readiness"][
                "sourceImageSilhouetteComparisonRun"
            ],
            "sourceImageAppearanceComparisonRun": inspection_report["readiness"][
                "sourceImageAppearanceComparisonRun"
            ],
            "humanVisualReviewRun": inspection_report["readiness"]["humanVisualReviewRun"],
            "acceptedForD0PublicFixture": inspection_report["readiness"][
                "acceptedForD0PublicFixture"
            ],
            "acceptedForVisualFidelity": inspection_report["readiness"][
                "acceptedForVisualFidelity"
            ],
            "acceptedForCleanProposal": inspection_report["readiness"]["acceptedForCleanProposal"],
        },
        "renderFramePoseSuite": {
            "reportId": render_frame_pose_suite["reportId"],
            "status": render_frame_pose_suite["readiness"]["status"],
            "framePersistenceRun": render_frame_pose_suite["readiness"]["framePersistenceRun"],
            "glbTangentsPersisted": render_frame_pose_suite["readiness"]["glbTangentsPersisted"],
            "tangentAccessorType": render_frame_pose_suite["framePersistence"][
                "tangentAccessorType"
            ],
            "normalAccessorPersisted": render_frame_pose_suite["framePersistence"][
                "normalAccessorPersisted"
            ],
            "poseSuiteRun": render_frame_pose_suite["readiness"]["poseSuiteRun"],
            "poseSuitePass": render_frame_pose_suite["readiness"]["poseSuitePass"],
            "poseCount": render_frame_pose_suite["poseSuite"]["poseCount"],
            "maxPoseBindingErrorMeters": render_frame_pose_suite["aggregate"][
                "maxPoseBindingErrorMeters"
            ],
            "acceptedForRuntimeFramePreview": render_frame_pose_suite["readiness"][
                "acceptedForRuntimeFramePreview"
            ],
            "acceptedForCleanProposal": render_frame_pose_suite["readiness"][
                "acceptedForCleanProposal"
            ],
        },
        "productionBindingC3": {
            "reportId": production_binding_c3["reportId"],
            "status": production_binding_c3["readiness"]["status"],
            "gateC3Status": production_binding_c3["readiness"]["gateC3Status"],
            "profile": production_binding_c3["profile"]["id"],
            "persistedValidationStatus": production_binding_c3["persistedValidation"]["status"],
            "motionStateCount": production_binding_c3["motionSuite"]["stateCount"],
            "maxReconstructionErrorMeters": production_binding_c3["aggregate"][
                "maxReconstructionErrorMeters"
            ],
            "maxSeamCrackMeters": production_binding_c3["aggregate"]["maxSeamCrackMeters"],
            "maxOpeningCircumferenceDriftMeters": production_binding_c3["aggregate"][
                "maxOpeningCircumferenceDriftMeters"
            ],
            "maxDenseFallbackParityErrorMeters": production_binding_c3["aggregate"][
                "maxDenseFallbackParityErrorMeters"
            ],
            "acceptedForGlobalPhase6": production_binding_c3["readiness"][
                "acceptedForGlobalPhase6"
            ],
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
            "representationSilhouetteComparisonRun": geometry_clean_acceptance_gate["execution"][
                "representationSilhouetteComparisonRun"
            ],
            "representationSilhouetteAccepted": geometry_clean_acceptance_gate["execution"][
                "representationSilhouetteAccepted"
            ],
            "meshStitchOrWeldExecutionRun": geometry_clean_acceptance_gate["execution"][
                "meshStitchOrWeldExecutionRun"
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
            "contractVersion": provider_registry["contractVersion"],
            "providerCount": len(provider_registry["providers"]),
            "manualLocalImportAdapterDeclared": provider_registry["d0Capabilities"][
                "manualLocalImportAdapterDeclared"
            ],
            "manualLocalImportAssetAvailable": provider_registry["d0Capabilities"][
                "manualLocalImportAssetAvailable"
            ],
            "localOpenModelAdapterDeclared": provider_registry["d0Capabilities"][
                "localOpenModelAdapterDeclared"
            ],
            "localOpenModelExecutionAvailable": provider_registry["d0Capabilities"][
                "localOpenModelExecutionAvailable"
            ],
            "externalProvidersConfigured": provider_registry["d0Capabilities"][
                "externalProvidersConfigured"
            ],
            "cleanProposalProviderAvailable": provider_registry["d0Capabilities"][
                "cleanProposalProviderAvailable"
            ],
        },
        "providerBakeoff": {
            "reportId": provider_bakeoff["reportId"],
            "status": provider_bakeoff["status"],
            "providerCount": provider_bakeoff["aggregate"]["providerCount"],
            "executedProviderCount": provider_bakeoff["aggregate"]["executedProviderCount"],
            "notRunProviderCount": provider_bakeoff["aggregate"]["notRunProviderCount"],
            "canonicalAcceptedProviderCount": provider_bakeoff["aggregate"][
                "canonicalAcceptedProviderCount"
            ],
            "bestAvailableProviderId": provider_bakeoff["aggregate"]["bestAvailableProviderId"],
            "bestAvailableStatus": provider_bakeoff["aggregate"]["bestAvailableStatus"],
        },
        "hashes": manifest["hashes"],
        "binding": context["bindingManifest"],
        "materialPhysics": {
            "registryVersion": material_registry["registryVersion"],
            "presetCount": len(material_registry["presets"]),
            "selectedPresetId": material_selection["selection"]["selectedPresetId"],
            "selectionConfidence": material_selection["selection"]["confidenceState"],
            "calibrationFixtureCount": len(material_calibration["fixtures"]),
            "calibrationAcceptedForD0Fixtures": material_calibration["readiness"][
                "acceptedForD0CalibrationFixtures"
            ],
            "motionPresetCount": len(material_motion_suite["presets"]),
            "motionExecutedForD0Tshirt": material_motion_suite["readiness"][
                "executedForD0FixedAvatarTshirt"
            ],
            "motionQualityAccepted": material_motion_suite["readiness"][
                "acceptedForD0FixedAvatarTshirt"
            ],
            "realFabricCalibrationRun": False,
            "productionGpuMotionRun": False,
        },
        "settle": {
            "solverVersion": settle["solverVersion"],
            "convergenceState": settle["convergenceState"],
            "maximumSeamResidualMeters": settle["maximumSeamResidualMeters"],
            "rmsSeamResidualMeters": settle["rmsSeamResidualMeters"],
            "maximumBodyPenetrationMeters": settle["maximumBodyPenetrationMeters"],
            "maximumStrain": settle["maximumStrain"],
            "selfCollisionAvailable": settle["selfCollision"]["available"],
        },
        "selfCollision": {
            "reportId": self_collision_report["reportId"],
            "status": self_collision_report["readiness"]["status"],
            "candidatePairCount": self_collision_report["metrics"]["candidatePairCount"],
            "contactCountBeforeCorrection": self_collision_report["metrics"][
                "contactCountBeforeCorrection"
            ],
            "contactCountAfterCorrection": self_collision_report["metrics"][
                "contactCountAfterCorrection"
            ],
            "unresolvedContactCount": self_collision_report["metrics"]["unresolvedContactCount"],
            "highVelocityTunnelling": self_collision_report["adversarialFixtures"][
                "highVelocityTunnelling"
            ]["status"],
            "acceptedForProductionGpuSolver": self_collision_report["readiness"][
                "acceptedForProductionGpuSolver"
            ],
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
        "- Visual observations: "
        f"{summary['visualUnderstanding']['maskCount']} pixel-derived masks, "
        f"{summary['visualUnderstanding']['observedLandmarkCount']} T-shirt landmarks, "
        f"{summary['visualUnderstanding']['semanticPartCount']} parts, "
        f"{summary['visualUnderstanding']['openingBoundaryCount']} openings, "
        f"{summary['visualUnderstanding']['correctionOperationCount']} applied corrections, "
        f"mean IoU={summary['visualUnderstanding']['meanMaskIoU']:.6f}\n"
        f"- Multiview fusion: {summary['multiviewFusion']['status']}, "
        f"{summary['multiviewFusion']['viewCount']} views, "
        f"{summary['multiviewFusion']['fusedMaskCount']} fused masks, "
        f"{summary['multiviewFusion']['fusedLandmarkCount']} fused landmarks, "
        f"downstream allowed={summary['multiviewFusion']['expensiveDownstreamAllowed']}\n"
        f"- Fitting: {summary['fitting']['status']} via "
        f"`{summary['fitting']['fitterVersion']}`, landmark RMS "
        f"{summary['fitting']['landmarkRmsNormalised']:.6f}, "
        f"multiview IoU={summary['fitting']['multiviewSilhouetteMeanIoU']:.6f}, "
        f"optimisation history={summary['fitting']['optimizationHistoryCount']}, "
        f"candidate evaluations={summary['fitting']['candidateEvaluationCount']}, "
        f"objective={summary['fitting']['initialObjective']:.6f}->"
        f"{summary['fitting']['finalObjective']:.6f}, "
        f"settled render={summary['fitting']['settledRenderComparisonStatus']}\n"
        f"- Material physics: {summary['materialPhysics']['presetCount']} presets, "
        f"selected=`{summary['materialPhysics']['selectedPresetId']}`, "
        f"calibration fixtures={summary['materialPhysics']['calibrationFixtureCount']}, "
        f"CPU motion executed={summary['materialPhysics']['motionExecutedForD0Tshirt']}, "
        f"motion quality accepted={summary['materialPhysics']['motionQualityAccepted']}, "
        "real-fabric/GPU runs=False/False\n"
        f"- Texture identity: {summary['texture']['status']}, "
        f"{summary['texture']['materialRegionCount']} PBR material observations, "
        f"source textures available={summary['texture']['sourceTextureAvailable']}, "
        f"visible projections={summary['texture']['visibleProjectionCount']}/"
        f"{summary['texture']['sourceProjectionCount']}, "
        f"mean confidence={summary['texture']['meanVisibleConfidence']:.6f}, "
        f"decoded bitmaps={summary['texture']['decodedRasterAssetsPersisted']}, "
        f"source/generated coverage={summary['texture']['sourceObservedFraction']:.6f}/"
        f"{summary['texture']['generatedControlledFillFraction']:.6f}\n"
        f"- Source/render fidelity: `{summary['sourceRenderFidelity']['status']}`, "
        f"views={summary['sourceRenderFidelity']['viewCount']}, "
        f"mean IoU={summary['sourceRenderFidelity']['meanSilhouetteIoU']:.6f}, "
        f"mean linear-sRGB MAE="
        f"{summary['sourceRenderFidelity']['meanForegroundLinearSrgbMae']:.6f}, "
        f"D0 public accepted="
        f"{summary['sourceRenderFidelity']['acceptedForD0PublicFixture']}, "
        "canonical accepted=False\n"
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
        f"- Stitched shell: status=`{summary['geometryStitchedShell']['status']}`, "
        f"executed={summary['geometryStitchedShell']['meshStitchOrWeldExecutionRun']}, "
        f"proven={summary['geometryStitchedShell']['meshStitchOrWeldProven']}, "
        f"loops={summary['geometryStitchedShell']['boundaryLoopCount']}/"
        f"{summary['geometryStitchedShell']['expectedOpeningCount']}, "
        f"non-manifold edges={summary['geometryStitchedShell']['nonManifoldEdgeCount']}\n"
        f"- Visual/shell review: status=`{summary['geometryVisualShellReview']['status']}`, "
        "representation silhouette="
        f"{summary['geometryVisualShellReview']['representationSilhouetteAccepted']}, "
        "source/provider visual fidelity="
        f"{summary['geometryVisualShellReview']['acceptedForVisualFidelity']}, "
        f"stitch graph={summary['geometryVisualShellReview']['stitchGraphConnectable']}, "
        f"mesh stitch/weld={summary['geometryVisualShellReview']['meshStitchOrWeldProven']}\n"
        f"- Render frame/pose suite: tangents="
        f"{summary['renderFramePoseSuite']['glbTangentsPersisted']}, "
        f"type=`{summary['renderFramePoseSuite']['tangentAccessorType']}`, "
        f"poses={summary['renderFramePoseSuite']['poseCount']}, "
        f"pose pass={summary['renderFramePoseSuite']['poseSuitePass']}, "
        f"max pose binding error="
        f"{summary['renderFramePoseSuite']['maxPoseBindingErrorMeters']:.8f}\n"
        f"- Production binding C3: status=`{summary['productionBindingC3']['status']}`, "
        f"profile=`{summary['productionBindingC3']['profile']}`, "
        f"motion states={summary['productionBindingC3']['motionStateCount']}, "
        f"max error={summary['productionBindingC3']['maxReconstructionErrorMeters']:.8f}, "
        f"global Phase 6={summary['productionBindingC3']['acceptedForGlobalPhase6']}\n"
        f"- Clean acceptance gate: status=`{summary['geometryCleanAcceptanceGate']['status']}`, "
        f"passed={summary['geometryCleanAcceptanceGate']['passedCheckCount']}/"
        f"{summary['geometryCleanAcceptanceGate']['checkCount']}, "
        f"failed={summary['geometryCleanAcceptanceGate']['failedCheckCount']}, "
        f"warnings={summary['geometryCleanAcceptanceGate']['warningCheckCount']}, "
        f"not run={summary['geometryCleanAcceptanceGate']['notRunCheckCount']}, "
        f"accepted={summary['geometryCleanAcceptanceGate']['acceptedForCleanProposal']}\n"
        f"- Clean proposal: {summary['cleanGeometryProposal']['qualityStatus']}, "
        f"available={summary['cleanGeometryProposal']['cleanProposalAvailable']}, "
        f"reason=`{summary['cleanGeometryProposal']['failureReason']}`\n"
        f"- Provider registry: selected `{summary['providerRegistry']['selectedProviderId']}`, "
        f"manual asset available={summary['providerRegistry']['manualLocalImportAssetAvailable']}, "
        "local open model execution="
        f"{summary['providerRegistry']['localOpenModelExecutionAvailable']}\n"
        f"- Provider bake-off: best `{summary['providerBakeoff']['bestAvailableProviderId']}`, "
        f"status=`{summary['providerBakeoff']['status']}`, "
        f"executed={summary['providerBakeoff']['executedProviderCount']}/"
        f"{summary['providerBakeoff']['providerCount']}, "
        f"canonical accepted={summary['providerBakeoff']['canonicalAcceptedProviderCount']}\n"
        f"- Simulation mesh: {counts['simulationVertices']} vertices, "
        f"{counts['simulationTriangles']} triangles\n"
        f"- Render shell: {counts['renderVertices']} vertices, "
        f"{counts['renderTriangles']} triangles\n"
        f"- Logical stitched shell: {counts['stitchedShellVertices']} vertices, "
        f"{counts['stitchedShellTriangles']} triangles\n"
        f"- Cloth settle: {summary['settle']['convergenceState']} via "
        f"`{summary['settle']['solverVersion']}`\n"
        f"- Seam RMS residual: {summary['settle']['rmsSeamResidualMeters']:.8f} m\n"
        f"- Max body penetration: {summary['settle']['maximumBodyPenetrationMeters']:.8f} m\n"
        f"- Self-collision: status=`{summary['selfCollision']['status']}`, "
        f"contacts after correction={summary['selfCollision']['contactCountAfterCorrection']}, "
        f"high velocity=`{summary['selfCollision']['highVelocityTunnelling']}`\n"
        f"- Binding max error: {summary['binding']['maximumReconstructionError']:.8f}\n"
        f"- Validation: {validation['status']} {validation['counts']}\n"
        "- Limitation: self-collision is D0 reference-only; high-velocity tunnelling is "
        "explicitly unsupported.\n"
    )


def _mesh_counts(meshset: MeshSet) -> dict[str, int]:
    return {
        "meshCount": len(meshset.meshes),
        "vertexCount": meshset.vertex_count,
        "triangleCount": meshset.triangle_count,
    }


def _record_stitched_shell_package_writer_evidence(
    geometry_stitched_shell: dict[str, Any], package_dir: Path
) -> None:
    analysis_path = package_dir / "stitch" / "logical_stitched_analysis_shell.json"
    render_path = package_dir / "render" / "stitched_shell.glb"
    geometry_stitched_shell["packageWriterEvidence"] = {
        "status": "written",
        "analysisAssetWritten": analysis_path.exists(),
        "renderAssetWritten": render_path.exists(),
        "analysisAssetPath": "stitch/logical_stitched_analysis_shell.json",
        "renderAssetPath": "render/stitched_shell.glb",
        "analysisAssetSha256": sha256_file(analysis_path),
        "renderAssetSha256": sha256_file(render_path),
        "analysisAssetByteSize": analysis_path.stat().st_size,
        "renderAssetByteSize": render_path.stat().st_size,
    }
    geometry_stitched_shell["integrity"]["geometryStitchedShellHash"] = (
        hash_geometry_stitched_shell_report(geometry_stitched_shell)
    )


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
