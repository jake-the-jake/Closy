from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from closy_forge.avatar.reference_avatar import (
    avatar_contract,
    build_collision_mesh,
    build_reference_avatar_mesh,
)
from closy_forge.binding.binary_format import BindingFile, write_binding
from closy_forge.binding.builder import build_binding
from closy_forge.binding.reconstruct import reconstruct_vertices, reconstruction_error
from closy_forge.contracts.common import COORDINATE_CONVENTION, DEFAULT_SEED, FIXED_TIMESTAMP
from closy_forge.garments.assembly import canonicalize_meshset
from closy_forge.garments.sleeveless_top.appearance import (
    SleevelessAppearanceBundle,
    build_sleeveless_appearance_bundle,
)
from closy_forge.garments.sleeveless_top.assembly import (
    CANONICAL_GEOMETRY_DIGITS,
    build_constraints,
    build_simulation_mesh,
)
from closy_forge.garments.sleeveless_top.fitting import fit_sleeveless_top
from closy_forge.garments.sleeveless_top.motion import build_sleeveless_motion_suite
from closy_forge.garments.sleeveless_top.parameters import SleevelessTopParameters
from closy_forge.garments.sleeveless_top.pattern_generator import (
    GARMENT_CLASS,
    GARMENT_ID,
    build_sleeveless_top_pattern,
)
from closy_forge.garments.sleeveless_top.semantic_graph import (
    build_sleeveless_top_semantic_graph,
)
from closy_forge.geometry.glb_io import write_indexed_glb
from closy_forge.geometry.mesh_model import MeshSet, mesh_bounds
from closy_forge.geometry.subdivision import subdivide_for_render
from closy_forge.package_io.canonical_json import (
    write_canonical_json,
    write_canonical_text,
)
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
from closy_forge.simulation.reference_cloth_solver import (
    flatten_mesh,
    replace_mesh_positions,
)
from closy_forge.validation.validator import validate_package

PACKAGE_VERSION = "closy.sleeveless_top.package.d0.v1"


@dataclass(frozen=True)
class SleevelessBuildResult:
    package_dir: Path
    manifest: dict[str, Any]
    validation: dict[str, Any]


def build_demo_sleeveless_package(
    output: Path,
    *,
    params: SleevelessTopParameters | None = None,
    seed: int = DEFAULT_SEED,
    force: bool = False,
) -> SleevelessBuildResult:
    prior = params or SleevelessTopParameters()
    prior.validate()
    staging = prepare_staging(output)
    try:
        context = _write_package_contents(staging, prior, seed)
        pending = _pending_validation()
        _write_summary_files(staging, context, pending)
        validation = validate_package(staging)
        if validation["status"] != "passed":
            write_canonical_json(staging / "reports/package_validation.json", validation)
            details = ";".join(
                f"{issue.get('code', 'unknown')}={issue.get('message', '')}"
                for issue in validation["issues"]
            )
            raise RuntimeError(f"sleeveless package validation failed before publish: {details}")
        _write_summary_files(staging, context, validation)
        publish_staging(staging, output, force=force)
        return SleevelessBuildResult(output, context["manifest"], validation)
    except Exception:
        cleanup_staging(staging)
        raise


def _write_package_contents(
    package_dir: Path, prior: SleevelessTopParameters, seed: int
) -> dict[str, Any]:
    fitted, fit_report = fit_sleeveless_top(prior)
    pattern = build_sleeveless_top_pattern(fitted)
    semantic = build_sleeveless_top_semantic_graph(pattern)
    rest_mesh, edge_maps = build_simulation_mesh(pattern)
    constraints = build_constraints(pattern, edge_maps)

    avatar_mesh = canonicalize_meshset(build_reference_avatar_mesh(), CANONICAL_GEOMETRY_DIGITS)
    collision_mesh = canonicalize_meshset(build_collision_mesh(), CANONICAL_GEOMETRY_DIGITS)
    avatar = avatar_contract(avatar_mesh, collision_mesh)

    render_template, binding_seeds = subdivide_for_render(rest_mesh)
    binding, binding_manifest = build_binding(rest_mesh, render_template, binding_seeds)
    material_registry = build_material_preset_registry()
    material_selection = select_material_preset(_material_selection_input(), material_registry)
    material_physics = solver_material_payload(material_selection["selectedDescriptor"])
    motion_report, motion_states, simulation_mesh = build_sleeveless_motion_suite(
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

    appearance = build_sleeveless_appearance_bundle(
        pattern=pattern, settled_mesh=simulation_mesh, seed=seed
    )
    render_materials = _render_materials(appearance)
    quality = _quality_report(
        pattern=pattern,
        rest_mesh=rest_mesh,
        simulation_mesh=simulation_mesh,
        render_mesh=render_mesh,
        constraints=constraints,
        binding_manifest=binding_manifest,
        fit_report=fit_report,
        motion_report=motion_report,
        appearance=appearance,
    )

    _write_contracts(
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
        render_materials=render_materials,
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


def _write_contracts(
    *,
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
    appearance: SleevelessAppearanceBundle,
    render_materials: dict[str, Any],
    quality: dict[str, Any],
    seed: int,
) -> None:
    write_canonical_json(package_dir / "pattern/pattern.json", pattern)
    write_canonical_json(package_dir / "semantic/garment_graph.json", semantic)
    write_canonical_json(
        package_dir / "simulation/rest_state.json",
        _mesh_manifest(rest_mesh, "simulation_rest", edge_maps=edge_maps),
    )
    write_canonical_json(
        package_dir / "simulation/settled_state.json",
        motion_states["material.cotton_jersey_d0_v1"],
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
        "closy_sleeveless_simulation_v1",
        (0.18, 0.37, 0.69, 1.0),
    )
    write_indexed_glb(
        package_dir / "render/fallback.glb",
        render_mesh,
        "closy_sleeveless_dense_render_v1",
        (0.18, 0.37, 0.69, 1.0),
    )
    write_indexed_glb(
        package_dir / "render/simulation_fallback.glb",
        simulation_mesh,
        "closy_sleeveless_independent_simulation_fallback_v1",
        (0.18, 0.37, 0.69, 1.0),
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
    write_canonical_json(package_dir / "fitting/sleeveless_fit.json", fit_report)
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
    write_canonical_json(package_dir / "reports/sleeveless_quality.json", quality)
    write_canonical_json(
        package_dir / "provenance.json",
        {
            "schemaVersion": 1,
            "createdAt": FIXED_TIMESTAMP,
            "generator": PACKAGE_VERSION,
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


def _manifest(
    *,
    seed: int,
    fitted: SleevelessTopParameters,
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
        "displayName": "Deterministic Sleeveless Top D0 Fixture",
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
            "reportPath": "reports/sleeveless_quality.json",
            "sleevelessTopD0Complete": quality["readiness"]["sleevelessTopD0Complete"],
            "phase8GlobalStatus": "partial",
        },
        "inventory": inventory,
        "packageDigest": digest,
        "packageByteSize": sum(cast(int, entry["byteSize"]) for entry in inventory),
        "warnings": [
            "public_synthetic_fixture_not_private_user_fit",
            "reference_cpu_solver_not_production_gpu_cloth",
            "phase8_global_partial_after_one_family",
        ],
    }


def _quality_report(
    *,
    pattern: dict[str, Any],
    rest_mesh: MeshSet,
    simulation_mesh: MeshSet,
    render_mesh: MeshSet,
    constraints: dict[str, Any],
    binding_manifest: dict[str, Any],
    fit_report: dict[str, Any],
    motion_report: dict[str, Any],
    appearance: SleevelessAppearanceBundle,
) -> dict[str, Any]:
    opening_ids = sorted(str(item["id"]) for item in pattern["openings"])
    semantic_ids = [
        *(str(item["id"]) for item in pattern["panels"]),
        *(str(item["id"]) for item in pattern["seams"]),
        *opening_ids,
    ]
    return {
        "schemaVersion": 1,
        "reportVersion": "closy.sleeveless_top.quality.d0.v1",
        "garmentId": GARMENT_ID,
        "garmentClass": GARMENT_CLASS,
        "topology": {
            "panelCount": len(pattern["panels"]),
            "seamCount": len(pattern["seams"]),
            "openingCount": len(pattern["openings"]),
            "openingIds": opening_ids,
            "hasSleeveOrCuffSemantics": any(
                _has_exact_token(identifier, {"sleeve", "cuff"}) for identifier in semantic_ids
            ),
            "simulationVertexCount": simulation_mesh.vertex_count,
            "simulationTriangleCount": simulation_mesh.triangle_count,
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
            "underarmStressAccepted": motion_report["underarmStress"]["accepted"],
            "armholesNonCollapsed": motion_report["readiness"]["armholesNonCollapsed"],
        },
        "appearance": {
            "decodedPbrMapsPersisted": appearance.texture_report["decodedPbrMapsPersisted"],
            "decodedSourceRenderComparisonRun": appearance.fidelity_report[
                "decodedPixelComparisonRun"
            ],
            "acceptedForD0SleevelessFixture": appearance.fidelity_report[
                "acceptedForD0SleevelessFixture"
            ],
        },
        "readiness": {
            "sleevelessTopD0Complete": all(
                [
                    len(pattern["panels"]) == 2,
                    len(pattern["seams"]) == 4,
                    len(pattern["openings"]) == 4,
                    not any(
                        _has_exact_token(identifier, {"sleeve", "cuff"})
                        for identifier in semantic_ids
                    ),
                    fit_report["accepted"],
                    motion_report["underarmStress"]["accepted"],
                    motion_report["readiness"]["armholesNonCollapsed"],
                    appearance.fidelity_report["acceptedForD0SleevelessFixture"],
                ]
            ),
            "phase8GloballyComplete": False,
            "nextGarmentFamily": "long_sleeved_top",
            "productionPrivateUserAcceptance": False,
        },
    }


def _mesh_manifest(
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


def _material_selection_input() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "selectionId": "material_selection.sleeveless_top_public_d0_v1",
        "inputId": "material_input.sleeveless_top_public_d0_v1",
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


def _has_exact_token(identifier: str, forbidden: set[str]) -> bool:
    tokens = identifier.replace("_", ".").replace("-", ".").split(".")
    return any(token in forbidden for token in tokens)


def _render_materials(appearance: SleevelessAppearanceBundle) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "materials": [appearance.texture_report["material"]],
        "mobilePbr": {
            "shaderClass": "metallic_roughness",
            "transmission": False,
            "subsurfaceScattering": False,
        },
    }


def _pending_validation() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "status": "pending",
        "counts": {"info": 0, "warning": 0, "error": 0, "fatal": 0},
        "issues": [],
    }


def _write_summary_files(
    package_dir: Path, context: dict[str, Any], validation: dict[str, Any]
) -> None:
    write_canonical_json(package_dir / "reports/package_validation.json", validation)
    summary = _summary(context, validation)
    write_canonical_json(package_dir / "reports/summary.json", summary)
    lines = [
        f"# {summary['displayName']}",
        "",
        f"- Garment class: `{summary['garmentClass']}`",
        f"- Package digest: `{summary['packageDigest']}`",
        f"- Validation: `{summary['validation']['status']}`",
        f"- Sleeveless-top D0: `{summary['readiness']['sleevelessTopD0Complete']}`",
        f"- Phase 8 globally: `{summary['readiness']['phase8GlobalStatus']}`",
        f"- Next family: `{summary['readiness']['nextGarmentFamily']}`",
        "",
        "This is a public deterministic CPU fixture, not private-user fitting, production cloth, "
        "or learned garment inference.",
    ]
    write_canonical_text(package_dir / "reports/summary.md", "\n".join(lines))


def _summary(context: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
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
            "sleevelessTopD0Complete": quality["readiness"]["sleevelessTopD0Complete"],
            "phase8GlobalStatus": "partial",
            "nextGarmentFamily": quality["readiness"]["nextGarmentFamily"],
        },
        "truthfulLimitations": manifest["warnings"],
    }
