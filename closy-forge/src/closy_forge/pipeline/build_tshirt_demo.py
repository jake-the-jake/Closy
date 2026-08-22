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
from closy_forge.geometry.glb_io import audit_glb, write_glb
from closy_forge.geometry.mesh_model import MeshSet, mesh_bounds
from closy_forge.geometry.subdivision import subdivide_for_render
from closy_forge.package_io.canonical_json import canonical_dumps, write_canonical_json
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
    GEOMETRY_PROPOSAL_VERSION,
    PROVIDER_REGISTRY_VERSION,
    build_geometry_provider_registry,
    build_null_geometry_proposal,
    geometry_proposal_quality_report,
    provider_registry_quality_report,
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
    geometry_proposal = build_null_geometry_proposal(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        capture_record=capture_record,
        visual_observations=visual_observations,
        fit_report=fit_report,
        texture_identity=texture_identity,
    )
    provider_registry = build_geometry_provider_registry(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        capture_record=capture_record,
        visual_observations=visual_observations,
        fit_report=fit_report,
        texture_identity=texture_identity,
        geometry_proposal=geometry_proposal,
    )
    material_physics = _material_physics()
    settle = settle_reference_cloth(rest_mesh, constraints, avatar, material_physics)
    simulation_mesh = settle.settled_mesh
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
            "name": "implementation_06_provider_registry_boundary",
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
            "geometry_proposal_rejected_null_provider",
            "manual_geometry_provider_asset_not_configured",
            "zeroone_unavailable_optional",
            "procedural_fixture_not_production_asset",
        ],
        "zeroOne": {"staticAvailable": False, "dynamicAvailable": False, "required": False},
        "extensions": {"closyImplementation": "06-provider-registry-boundary"},
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
        "providerProvenanceAvailable": True,
        "geometryProviderRegistryAvailable": True,
        "manualGeometryImportAdapterDeclared": True,
        "manualGeometryImportAssetAvailable": False,
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
                "null_geometry_proposal_provider",
                GEOMETRY_PROPOSAL_VERSION,
                {
                    "providerId": geometry_proposal["provider"]["providerId"],
                    "providerKind": geometry_proposal["provider"]["providerKind"],
                    "runtimeExternalApis": False,
                    "rawProposalAvailable": False,
                    "cleanProposalAvailable": False,
                    "acceptedForCanonical": False,
                    "rejectionReasons": geometry_proposal["quality"]["rejectionReasons"],
                },
                [str(geometry_proposal["integrity"]["geometryProposalHash"])],
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
            "geometry_proposal_rejected_null_provider",
            "manual_geometry_provider_asset_not_configured",
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
