from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from closy_forge.avatar.reference_avatar import (
    avatar_contract,
    build_collision_mesh,
    build_reference_avatar_mesh,
)
from closy_forge.binding.builder import build_binding
from closy_forge.binding.reconstruct import reconstruct_vertices, reconstruction_error
from closy_forge.contracts.common import COORDINATE_CONVENTION, DEFAULT_SEED
from closy_forge.garments.assembly import canonicalize_meshset
from closy_forge.garments.jacket_outerwear.appearance import (
    JacketOuterwearAppearanceBundle,
    build_jacket_outerwear_appearance_bundle,
)
from closy_forge.garments.jacket_outerwear.assembly import (
    CANONICAL_GEOMETRY_DIGITS,
    build_constraints,
    build_simulation_mesh,
)
from closy_forge.garments.jacket_outerwear.fitting import fit_jacket_outerwear
from closy_forge.garments.jacket_outerwear.motion import build_jacket_outerwear_motion_suite
from closy_forge.garments.jacket_outerwear.parameters import JacketOuterwearParameters
from closy_forge.garments.jacket_outerwear.pattern_generator import (
    GARMENT_CLASS,
    GARMENT_ID,
    build_jacket_outerwear_pattern,
)
from closy_forge.garments.jacket_outerwear.semantic_graph import (
    build_jacket_outerwear_semantic_graph,
)
from closy_forge.garments.vertical_slice.package import (
    ContractWriteSpec,
    SummarySpec,
    material_selection_input,
    pending_validation,
    render_materials,
    write_summary_files,
    write_vertical_slice_contracts,
)
from closy_forge.geometry.mesh_model import MeshSet, mesh_bounds
from closy_forge.geometry.subdivision import subdivide_for_render
from closy_forge.package_io.canonical_json import write_canonical_json
from closy_forge.package_io.hashing import geometry_content_hash, topology_hash
from closy_forge.package_io.writer import (
    EXCLUDED_FROM_CANONICAL_INVENTORY,
    canonical_package_digest,
    cleanup_staging,
    collect_inventory,
    prepare_staging,
    publish_staging,
)
from closy_forge.simulation.material_physics import (
    build_material_preset_registry,
    select_material_preset,
    solver_material_payload,
)
from closy_forge.simulation.reference_cloth_solver import flatten_mesh, replace_mesh_positions
from closy_forge.validation.validator import validate_package

PACKAGE_VERSION = "closy.jacket_outerwear.package.d0.v1"
SELECTED_PRESET_ID = "material.heavy_jersey_d0_v1"
CONTRACT_WRITE_SPEC = ContractWriteSpec(
    package_version=PACKAGE_VERSION,
    simulation_node_name="closy_jacket_outerwear_simulation_v1",
    dense_render_node_name="closy_jacket_outerwear_dense_render_v1",
    independent_fallback_node_name="closy_jacket_outerwear_independent_simulation_fallback_v1",
    fit_report_path="fitting/jacket_outerwear_fit.json",
    quality_report_path="reports/jacket_outerwear_quality.json",
    normalize_signed_zero=True,
    selected_material_preset_id=SELECTED_PRESET_ID,
)
SUMMARY_SPEC = SummarySpec(
    completion_key="jacketOuterwearD0Complete",
    completion_label="Jacket/outerwear D0",
)


@dataclass(frozen=True)
class JacketOuterwearBuildResult:
    package_dir: Path
    manifest: dict[str, Any]
    validation: dict[str, Any]


def build_demo_jacket_outerwear_package(
    output: Path,
    *,
    params: JacketOuterwearParameters | None = None,
    seed: int = DEFAULT_SEED,
    force: bool = False,
) -> JacketOuterwearBuildResult:
    prior = params or JacketOuterwearParameters()
    prior.validate()
    staging = prepare_staging(output)
    try:
        context = _write_package_contents(staging, prior, seed)
        write_summary_files(staging, context, pending_validation(), SUMMARY_SPEC)
        validation = validate_package(staging)
        if validation["status"] != "passed":
            write_canonical_json(staging / "reports/package_validation.json", validation)
            details = ";".join(
                f"{item.get('code', 'unknown')}={item.get('message', '')}"
                for item in validation["issues"]
            )
            raise RuntimeError(
                f"jacket-outerwear package validation failed before publish: {details}"
            )
        write_summary_files(staging, context, validation, SUMMARY_SPEC)
        publish_staging(staging, output, force=force)
        return JacketOuterwearBuildResult(output, context["manifest"], validation)
    except Exception:
        cleanup_staging(staging)
        raise


def _write_package_contents(
    package_dir: Path, prior: JacketOuterwearParameters, seed: int
) -> dict[str, Any]:
    fitted, fit_report = fit_jacket_outerwear(prior)
    pattern = build_jacket_outerwear_pattern(fitted)
    semantic = build_jacket_outerwear_semantic_graph(pattern)
    rest_mesh, edge_maps = build_simulation_mesh(pattern)
    constraints = build_constraints(pattern, edge_maps)

    avatar_mesh = canonicalize_meshset(build_reference_avatar_mesh(), CANONICAL_GEOMETRY_DIGITS)
    collision_mesh = canonicalize_meshset(build_collision_mesh(), CANONICAL_GEOMETRY_DIGITS)
    avatar = avatar_contract(avatar_mesh, collision_mesh)
    render_template, binding_seeds = subdivide_for_render(rest_mesh)
    binding, binding_manifest = build_binding(rest_mesh, render_template, binding_seeds)
    material_registry = build_material_preset_registry()
    material_selection = select_material_preset(
        material_selection_input(
            "jacket_outerwear",
            observations={
                "massClass": "heavy",
                "stretchClass": "moderate",
                "drapeClass": "structured_soft",
                "surfaceClass": "jersey_knit",
            },
        ),
        material_registry,
    )
    if material_selection["selection"]["selectedPresetId"] != SELECTED_PRESET_ID:
        raise RuntimeError("jacket-outerwear material selector did not choose heavy jersey")
    material_physics = solver_material_payload(material_selection["selectedDescriptor"])
    motion_report, motion_states, simulation_mesh = build_jacket_outerwear_motion_suite(
        rest_mesh=rest_mesh,
        constraints=constraints,
        avatar_contract=avatar,
        preset_registry=material_registry,
        binding=binding,
    )
    reconstructed = reconstruct_vertices(simulation_mesh, binding)
    render_mesh = replace_mesh_positions(
        render_template, reconstructed, flatten_mesh(render_template).mesh_offsets
    )
    max_error, rms_error = reconstruction_error(render_mesh, reconstructed)
    binding_manifest.update(
        {
            "maximumReconstructionError": max_error,
            "rmsReconstructionError": rms_error,
            "authority": "binding/sim_to_render.bin",
            "independentFallbackPath": "render/simulation_fallback.glb",
            "fallbackUsesDenseBinding": False,
        }
    )
    appearance = build_jacket_outerwear_appearance_bundle(
        pattern=pattern, settled_mesh=simulation_mesh, seed=seed
    )
    quality = _quality_report(
        pattern=pattern,
        semantic=semantic,
        simulation_mesh=simulation_mesh,
        render_mesh=render_mesh,
        binding_manifest=binding_manifest,
        fit_report=fit_report,
        motion_report=motion_report,
        appearance=appearance,
        material_selection=material_selection,
    )
    write_vertical_slice_contracts(
        spec=CONTRACT_WRITE_SPEC,
        package_dir=package_dir,
        pattern=pattern,
        semantic=semantic,
        rest_mesh=rest_mesh,
        simulation_mesh=simulation_mesh,
        render_mesh=render_mesh,
        edge_maps=edge_maps,
        constraints=constraints,
        binding=binding,
        binding_manifest=binding_manifest,
        avatar_mesh=avatar_mesh,
        collision_mesh=collision_mesh,
        avatar=avatar,
        material_registry=material_registry,
        material_selection=material_selection,
        material_physics=material_physics,
        motion_report=motion_report,
        motion_states=motion_states,
        fit_report=fit_report,
        appearance=appearance,
        render_materials=render_materials(appearance),
        quality=quality,
        seed=seed,
    )
    inventory = collect_inventory(package_dir, exclude=EXCLUDED_FROM_CANONICAL_INVENTORY)
    digest = canonical_package_digest(inventory)
    manifest = _manifest(
        seed=seed,
        fitted=fitted,
        avatar=avatar,
        rest_mesh=rest_mesh,
        simulation_mesh=simulation_mesh,
        render_mesh=render_mesh,
        binding_manifest=binding_manifest,
        inventory=inventory,
        digest=digest,
        quality=quality,
    )
    write_canonical_json(package_dir / "manifest.json", manifest)
    return {
        "manifest": manifest,
        "quality": quality,
        "fit": fit_report,
        "motion": motion_report,
        "appearance": appearance,
    }


def _manifest(
    *,
    seed: int,
    fitted: JacketOuterwearParameters,
    avatar: dict[str, Any],
    rest_mesh: MeshSet,
    simulation_mesh: MeshSet,
    render_mesh: MeshSet,
    binding_manifest: dict[str, Any],
    inventory: list[dict[str, object]],
    digest: str,
    quality: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "packageVersion": PACKAGE_VERSION,
        "packageKind": "closy.garment",
        "garmentId": GARMENT_ID,
        "displayName": "Deterministic Open-Front Jacket/Outerwear D0 Fixture",
        "garmentClass": GARMENT_CLASS,
        "units": "metres",
        "coordinateConvention": COORDINATE_CONVENTION,
        "status": "validated_public_d0_fixture",
        "seed": seed,
        "parameters": fitted.to_json(),
        "avatar": {
            "contractId": avatar["avatarContractId"],
            "path": "avatar/avatar_contract.json",
            "sourceKind": "procedural_fixture",
        },
        "canonicalPaths": {
            "pattern": "pattern/pattern.json",
            "semantic": "semantic/garment_graph.json",
            "simulation": "simulation/simulation_mesh.glb",
            "denseRender": "render/fallback.glb",
            "independentFallback": "render/simulation_fallback.glb",
            "binding": "binding/sim_to_render.bin",
            "material": "simulation/material_physics.json",
            "source": "source/capture_record.json",
            "fidelity": "reports/fidelity/source_render_fidelity.json",
        },
        "counts": {
            "panelCount": len(rest_mesh.meshes),
            "simulationVertexCount": simulation_mesh.vertex_count,
            "simulationTriangleCount": simulation_mesh.triangle_count,
            "renderVertexCount": render_mesh.vertex_count,
            "renderTriangleCount": render_mesh.triangle_count,
            "bindingRecordCount": binding_manifest["recordCount"],
        },
        "hashes": {
            "restTopology": topology_hash(rest_mesh),
            "settledContent": geometry_content_hash(simulation_mesh),
            "renderTopology": topology_hash(render_mesh),
        },
        "quality": {
            "reportPath": "reports/jacket_outerwear_quality.json",
            "jacketOuterwearD0Complete": quality["readiness"]["jacketOuterwearD0Complete"],
            "phase8GlobalStatus": "partial",
        },
        "inventory": inventory,
        "packageDigest": digest,
        "packageByteSize": sum(cast(int, entry["byteSize"]) for entry in inventory),
        "warnings": [
            "public_synthetic_fixture_not_private_user_fit",
            "reference_cpu_solver_not_production_gpu_cloth",
            "open_front_jacket_has_no_fastening_mechanics",
            "internal_facing_offset_is_bounded_reference_geometry",
            "phase8_global_partial_after_seven_families",
        ],
    }


def _quality_report(
    *,
    pattern: dict[str, Any],
    semantic: dict[str, Any],
    simulation_mesh: MeshSet,
    render_mesh: MeshSet,
    binding_manifest: dict[str, Any],
    fit_report: dict[str, Any],
    motion_report: dict[str, Any],
    appearance: JacketOuterwearAppearanceBundle,
    material_selection: dict[str, Any],
) -> dict[str, Any]:
    opening_ids = sorted(str(item["id"]) for item in pattern["openings"])
    panel_roles = sorted(str(item["semanticRole"]) for item in pattern["panels"])
    expected_roles = [
        "back_torso",
        "front_left_facing",
        "front_left_torso",
        "front_right_facing",
        "front_right_torso",
        "left_long_sleeve",
        "right_long_sleeve",
    ]
    expected_openings = [
        "opening.jacket_outerwear.cuff.left",
        "opening.jacket_outerwear.cuff.right",
        "opening.jacket_outerwear.front",
        "opening.jacket_outerwear.hem",
        "opening.jacket_outerwear.neck",
    ]
    facing_roles = {"front_left_facing", "front_right_facing"}
    components = {str(item["id"]): item for item in semantic["components"]}
    outer_collision_order_valid = all(
        components[f"component.jacket_outerwear.{component}"]["layerClass"] == "outer_shell"
        and components[f"component.jacket_outerwear.{component}"]["collisionOrder"] >= 30
        for component in ("torso", "sleeve.left", "sleeve.right")
    )
    facing_collision_order_valid = all(
        components[f"component.jacket_outerwear.facing.{side}"]["layerClass"]
        == "outer_shell_internal_facing"
        and components[f"component.jacket_outerwear.facing.{side}"]["collisionOrder"] == 29
        for side in ("left", "right")
    )
    fidelity_accepted = appearance.fidelity_report["acceptedForD0JacketOuterwearFixture"]
    readiness = all(
        [
            len(pattern["panels"]) == 7,
            len(pattern["seams"]) == 12,
            len(pattern["openings"]) == 5,
            panel_roles == expected_roles,
            opening_ids == expected_openings,
            outer_collision_order_valid,
            facing_collision_order_valid,
            fit_report["accepted"],
            motion_report["cuffStress"]["accepted"],
            motion_report["readiness"]["cuffsNonCollapsed"],
            material_selection["selection"]["selectedPresetId"] == SELECTED_PRESET_ID,
            fidelity_accepted,
        ]
    )
    return {
        "schemaVersion": 1,
        "reportVersion": "closy.jacket_outerwear.quality.d0.v1",
        "garmentId": GARMENT_ID,
        "garmentClass": GARMENT_CLASS,
        "topology": {
            "panelCount": len(pattern["panels"]),
            "seamCount": len(pattern["seams"]),
            "openingCount": len(pattern["openings"]),
            "openingIds": opening_ids,
            "panelRoles": panel_roles,
            "hasLiteralSplitFront": panel_roles == expected_roles,
            "hasSeparateFacings": facing_roles <= set(panel_roles),
            "frontOpeningUsesFacingInnerEdges": "opening.jacket_outerwear.front" in opening_ids,
            "outerLayerCollisionOrderValid": outer_collision_order_valid,
            "facingCollisionOrderValid": facing_collision_order_valid,
            "finiteBounds": mesh_bounds(simulation_mesh),
        },
        "binding": {
            "authority": binding_manifest["authority"],
            "recordCount": binding_manifest["recordCount"],
            "denseRenderVertexCount": render_mesh.vertex_count,
            "independentFallbackVertexCount": simulation_mesh.vertex_count,
            "maximumReconstructionError": binding_manifest["maximumReconstructionError"],
            "fallbackUsesDenseBinding": binding_manifest["fallbackUsesDenseBinding"],
        },
        "fit": {
            "accepted": fit_report["accepted"],
            "candidateCount": fit_report["candidateCount"],
            "learnedFitRun": fit_report["learnedFitRun"],
        },
        "motion": {
            "presetCount": len(motion_report["presetRecords"]),
            "cuffStressAccepted": motion_report["cuffStress"]["accepted"],
            "cuffsNonCollapsed": motion_report["readiness"]["cuffsNonCollapsed"],
        },
        "material": {
            "selectedPresetId": material_selection["selection"]["selectedPresetId"],
            "measuredRealFabric": False,
        },
        "appearance": {
            "decodedPbrMapsPersisted": appearance.texture_report["decodedPbrMapsPersisted"],
            "decodedSourceRenderComparisonRun": appearance.fidelity_report[
                "decodedPixelComparisonRun"
            ],
            "acceptedForD0JacketOuterwearFixture": fidelity_accepted,
        },
        "readiness": {
            "jacketOuterwearD0Complete": readiness,
            "phase8GloballyComplete": False,
            "nextGarmentFamily": "layered_unusual",
            "productionPrivateUserAcceptance": False,
        },
    }
