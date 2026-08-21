from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

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
from closy_forge.contracts.common import COORDINATE_CONVENTION, DEFAULT_SEED, FIXED_TIMESTAMP
from closy_forge.garments.tshirt.assembly import build_constraints, build_simulation_mesh
from closy_forge.garments.tshirt.parameters import TShirtParameters
from closy_forge.garments.tshirt.pattern_generator import build_tshirt_pattern
from closy_forge.garments.tshirt.semantic_graph import build_semantic_graph
from closy_forge.geometry.glb_io import audit_glb, write_glb
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
from closy_forge.validation.validator import validate_package


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
        (staging / "reports" / "summary.md").write_text(
            _summary_markdown(context, pending_validation),
            encoding="utf-8",
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
        (staging / "reports" / "summary.md").write_text(
            _summary_markdown(context, final_validation),
            encoding="utf-8",
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
    simulation_mesh, edge_maps = build_simulation_mesh(pattern)
    constraints = build_constraints(pattern, edge_maps)
    render_mesh, render_binding_seeds = subdivide_for_render(simulation_mesh)
    binding, binding_manifest = build_binding(simulation_mesh, render_mesh, render_binding_seeds)
    avatar = avatar_contract(avatar_mesh, collision_mesh)
    regions = body_regions()

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
    (package_dir / "pattern" / "panels.svg").parent.mkdir(parents=True, exist_ok=True)
    (package_dir / "pattern" / "panels.svg").write_text(_panels_svg(pattern), encoding="utf-8")
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
    write_canonical_json(package_dir / "simulation" / "material_physics.json", _material_physics())
    write_glb(
        package_dir / "render" / "fallback.glb",
        render_mesh,
        "closy_render_cotton_fixture_v1",
        (0.08, 0.26, 0.78, 1.0),
    )
    write_canonical_json(
        package_dir / "render" / "mesh_manifest.json", _mesh_manifest(render_mesh, "render")
    )
    write_canonical_json(package_dir / "render" / "materials.json", _render_materials())
    write_binding(package_dir / "binding" / "sim_to_render.bin", binding)
    write_canonical_json(package_dir / "binding" / "binding_manifest.json", binding_manifest)

    quality_reports = _quality_reports(
        avatar_mesh,
        collision_mesh,
        pattern,
        semantic,
        simulation_mesh,
        render_mesh,
        constraints,
        binding_manifest,
    )
    for name, report in quality_reports.items():
        write_canonical_json(package_dir / "reports" / name, report)

    provenance = _provenance(
        params,
        seed,
        avatar_mesh,
        collision_mesh,
        simulation_mesh,
        render_mesh,
        binding_manifest,
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
        simulation_mesh,
        render_mesh,
        binding_manifest,
    )
    write_canonical_json(package_dir / "manifest.json", manifest)
    return {
        "manifest": manifest,
        "pattern": pattern,
        "semantic": semantic,
        "simulationMesh": simulation_mesh,
        "renderMesh": render_mesh,
        "constraints": constraints,
        "bindingManifest": binding_manifest,
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
        "thicknessMeters": 0.0016,
        "clothSettleRun": False,
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
    sim_mesh: MeshSet,
    render_mesh: MeshSet,
    binding_manifest: dict[str, object],
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
            "semanticGraph": "semantic/garment_graph.json",
            "pattern": "pattern/pattern.json",
            "simulationMesh": "simulation/simulation_mesh.glb",
            "simulationMeshManifest": "simulation/mesh_manifest.json",
            "materialPhysics": "simulation/material_physics.json",
            "renderFallback": "render/fallback.glb",
            "renderMeshManifest": "render/mesh_manifest.json",
            "renderMaterials": "render/materials.json",
            "binding": "binding/sim_to_render.bin",
            "bindingManifest": "binding/binding_manifest.json",
        },
        "hashes": {
            "avatarTopologyHash": topology_hash(avatar_mesh),
            "avatarContentHash": geometry_content_hash(avatar_mesh),
            "collisionTopologyHash": topology_hash(collision_mesh),
            "collisionContentHash": geometry_content_hash(collision_mesh),
            "simulationTopologyHash": topology_hash(sim_mesh),
            "simulationContentHash": geometry_content_hash(sim_mesh),
            "renderTopologyHash": topology_hash(render_mesh),
            "renderContentHash": geometry_content_hash(render_mesh),
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
            "patternGenerator": "closy.tshirt.pattern.v1",
            "curveSampler": "closy.curve_sampler.v1",
            "panelTriangulator": "closy.fan_triangulator.v1",
            "analyticAssembly": "closy.analytic_assembly.v1",
            "renderSubdivision": "closy.render_subdivision.v1",
            "binding": str(binding_manifest["algorithm"]),
            "glbWriter": "closy.glb_writer.v1",
        },
        "seed": seed,
        "buildProfile": {
            "name": "implementation_01_demo_tshirt",
            "timestamp": FIXED_TIMESTAMP,
            "parameters": params.to_json(),
        },
        "capabilities": _capabilities(),
        "warnings": [
            "cloth_settle_not_run",
            "zeroone_unavailable_optional",
            "procedural_fixture_not_production_asset",
        ],
        "zeroOne": {"staticAvailable": False, "dynamicAvailable": False, "required": False},
        "extensions": {"closyImplementation": "01-forge-foundation-tshirt-vertical-slice"},
    }


def _capabilities() -> dict[str, bool]:
    return {
        "patternAvailable": True,
        "simulationReadyTopologyAvailable": True,
        "authoredMaterialPresetAvailable": True,
        "conventionalGlbAvailable": True,
        "simToRenderBindingAvailable": True,
        "bindingReconstructionValidated": True,
        "actualClothSettleAvailable": False,
        "sourceImageTextureAvailable": False,
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
    sim_mesh: MeshSet,
    render_mesh: MeshSet,
    constraints: dict[str, Any],
    binding_manifest: dict[str, object],
) -> dict[str, dict[str, Any]]:
    return {
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
            "status": "warning",
            "warningCode": "cloth_settle_not_run",
            "assembly": "analytic_rest_shape",
            "mesh": _mesh_counts(sim_mesh),
            "constraintCount": len(constraints["constraints"]),
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
    sim_mesh: MeshSet,
    render_mesh: MeshSet,
    binding_manifest: dict[str, object],
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
                [topology_hash(sim_mesh)],
            ),
            _stage(
                "analytic_assembly", "closy.analytic_assembly.v1", {"clothSettleRun": False}, []
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
        "warnings": ["cloth_settle_not_run", "zeroone_unavailable_optional"],
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
        "hashes": manifest["hashes"],
        "binding": context["bindingManifest"],
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
        f"- Simulation mesh: {counts['simulationVertices']} vertices, "
        f"{counts['simulationTriangles']} triangles\n"
        f"- Render shell: {counts['renderVertices']} vertices, "
        f"{counts['renderTriangles']} triangles\n"
        f"- Binding max error: {summary['binding']['maximumReconstructionError']:.8f}\n"
        f"- Validation: {validation['status']} {validation['counts']}\n"
        "- Warning: `cloth_settle_not_run` is expected for Implementation 01.\n"
    )


def _mesh_counts(meshset: MeshSet) -> dict[str, int]:
    return {
        "meshCount": len(meshset.meshes),
        "vertexCount": meshset.vertex_count,
        "triangleCount": meshset.triangle_count,
    }


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


def audit_package_glbs(package_dir: Path) -> dict[str, dict[str, Any]]:
    return {
        rel: audit_glb(package_dir / rel)
        for rel in [
            "avatar/reference_avatar.glb",
            "avatar/collision.glb",
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
