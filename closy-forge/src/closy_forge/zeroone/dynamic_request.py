from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from closy_forge.geometry.glb_io import read_glb_meshset
from closy_forge.package_io.canonical_json import read_json
from closy_forge.package_io.paths import assert_safe_child, posix_rel
from closy_forge.zeroone.dynamic_oracle import (
    BINDINGS,
    FRAME_SIMULATION_POSITIONS,
    RENDER_IDS,
    SIMULATION_IDS,
    SIMULATION_REST,
    TIMESTAMPS,
    Section,
    canonical_json,
    digest_bytes,
    encode_document,
    json_section,
    render_topology_hash,
    simulation_topology_hash,
    source_to_cluster_hash,
    static_inventory_hash,
    u64_section,
    vec3_section,
)
from closy_forge.zeroone.dynamic_processing_surface import (
    DYNAMIC_PROCESSING_INFLUENCE_PATH,
    DYNAMIC_PROCESSING_SURFACE_PATH,
    inspect_dynamic_processing_surface,
)
from closy_forge.zeroone.mechanical_reference_surface import (
    MECHANICAL_REFERENCE_CORNER_MAP_PATH,
    MECHANICAL_REFERENCE_PROFILE,
    MECHANICAL_REFERENCE_SURFACE_PATH,
    inspect_mechanical_reference_surface,
)
from closy_forge.zeroone.request import build_zeroone_request

DYNAMIC_REQUEST_SCHEMA_VERSION = "closy.zeroone.dynamic-request.v1"
DYNAMIC_REPORT_SCHEMA_VERSION = "zeroone.closy.dynamic-report.v2"
DYNAMIC_PROFILE = "closy-dynamic-d0-single-lod-reference-v1"
SCOPED_ACCEPTANCE_PROFILE = "MT1-CleanReferenceMotion-D0-v2"
CLIP_PROFILE = "closy.dynamic.mechanical-reference.torso-twist.v1"
MECHANICAL_CLIP_PROFILE = "closy.dynamic.clean-analytic-reference.v2"
FRAME_COUNT = 13
FRAME_STEP_MICROSECONDS = 16_667
DEFAULT_CLIP_SCALE = 0.02
MINIMUM_NORMALIZED_DISPLACEMENT = 0.01
MAXIMUM_NORMALIZED_DISPLACEMENT = 0.05
MINIMUM_MOVING_DESTINATION_FRACTION = 0.70
MINIMUM_NONRIGID_DESTINATION_FRACTION = 0.20
MOVEMENT_THRESHOLD_DIAGONAL_FRACTION = 0.001
MINIMUM_BEND_ANGLE_DEGREES = 5.0

Vec2 = tuple[float, float]
Vec3 = tuple[float, float, float]


@dataclass(frozen=True)
class DynamicRequestBundle:
    encoded: bytes
    metadata: dict[str, Any]
    request_sha256: str
    clip_inventory: dict[str, Any]
    influence_inventory: dict[str, Any]
    topology_inventory: dict[str, Any]


def build_dynamic_request(
    *,
    package: Path,
    invocation_root: Path,
    static_derivative: Path,
    output: Path,
    closy_sha: str,
    clip_scale: float = DEFAULT_CLIP_SCALE,
) -> DynamicRequestBundle:
    root = invocation_root.resolve(strict=True)
    package_root = package.resolve(strict=True)
    static_root = static_derivative.resolve(strict=True)
    output_root = output.resolve(strict=False)
    for candidate in (package_root, static_root, output_root):
        assert_safe_child(root, candidate)
    if not 0.0 < clip_scale <= 0.1:
        raise ValueError("dynamic_clip_scale_out_of_range")

    manifest = _object(package_root / "manifest.json")
    render_manifest = _object(package_root / "render" / "mesh_manifest.json")
    simulation_manifest = _object(package_root / "simulation" / "mesh_manifest.json")
    binding_contract = _object(package_root / "binding" / "production_binding_contract.json")
    derivative = _object(static_root / "derivative.json")
    source = _object_value(derivative, "source")
    source_relative = source.get("inputAssetRelativePath")
    uses_mechanical_reference = source_relative == MECHANICAL_REFERENCE_SURFACE_PATH
    uses_dynamic_processing = source_relative == DYNAMIC_PROCESSING_SURFACE_PATH
    neutral_reference = _state_positions(
        package_root / "simulation" / "motion_states" / "neutral_settled.json",
        simulation_manifest,
    )
    target_reference = _state_positions(
        package_root / "simulation" / "motion_states" / "torso_twist.json",
        simulation_manifest,
    )
    canonical_motion_delta = [
        (
            target[0] - neutral[0],
            target[1] - neutral[1],
            target[2] - neutral[2],
        )
        for neutral, target in zip(neutral_reference, target_reference, strict=True)
    ]
    processing_influence: dict[str, Any] = {}
    motion_audit: dict[str, Any] = {}
    if uses_mechanical_reference:
        reference_audit = inspect_mechanical_reference_surface(package_root)
        if reference_audit.get("status") != "valid":
            raise ValueError(f"mechanical_reference_invalid:{reference_audit.get('reason')}")
        render_meshset = read_glb_meshset(package_root / MECHANICAL_REFERENCE_SURFACE_PATH)
        simulation_ids = [
            _stable_id(0x2, index) for index in range(_vertex_count(simulation_manifest))
        ]
        render_ids = [_stable_id(0x1, index) for index in range(render_meshset.vertex_count)]
        render_indices, render_texcoords, bindings = _mechanical_reference_render_contract(
            package=package_root,
            render_manifest=render_manifest,
            render_meshset=render_meshset,
            binding_contract=binding_contract,
            render_ids=render_ids,
            simulation_ids=simulation_ids,
        )
        simulation_rest = _state_positions(
            package_root / "simulation" / "rest_state.json", simulation_manifest
        )
        analytic_scale = clip_scale / DEFAULT_CLIP_SCALE
        timestamps, frames = _analytic_reference_frames(
            simulation_rest, scale_factor=analytic_scale
        )
        motion_audit = _audit_reference_motion(
            simulation_rest=simulation_rest,
            frames=frames,
            bindings=bindings,
            binding_contract=binding_contract,
            scale_factor=analytic_scale,
        )
        influence_authority = "canonical_production_binding_contract_inside_zeroone"
        maximum_canonical_influences = max(record["count"] for record in bindings)
        maximum_processor_influences = maximum_canonical_influences
    elif uses_dynamic_processing:
        processing_audit = inspect_dynamic_processing_surface(package_root)
        if processing_audit.get("status") != "valid":
            raise ValueError(f"dynamic_processing_surface_invalid:{processing_audit.get('reason')}")
        render_meshset = read_glb_meshset(package_root / DYNAMIC_PROCESSING_SURFACE_PATH)
        processing_influence = _object(package_root / DYNAMIC_PROCESSING_INFLUENCE_PATH)
        simulation_ids = [_stable_id(0x4, index) for index in range(render_meshset.vertex_count)]
        render_ids = [_stable_id(0x1, index) for index in range(render_meshset.vertex_count)]
        render_indices, render_texcoords, bindings = _processing_render_contract(
            render_meshset=render_meshset,
            render_ids=render_ids,
            simulation_ids=simulation_ids,
        )
        simulation_rest = [position for mesh in render_meshset.meshes for position in mesh.vertices]
        motion_delta = _processing_motion_delta(processing_influence, canonical_motion_delta)
        influence_authority = "canonical_production_binding_composed_to_dynamic_processing_vertices"
        maximum_canonical_influences = 3
        maximum_processor_influences = 1
    else:
        render_meshset = read_glb_meshset(package_root / "render" / "fallback.glb")
        simulation_ids = [
            _stable_id(0x2, index) for index in range(_vertex_count(simulation_manifest))
        ]
        render_ids = [_stable_id(0x1, index) for index in range(render_meshset.vertex_count)]
        render_indices, render_texcoords, bindings = _expanded_render_contract(
            render_manifest=render_manifest,
            render_meshset=render_meshset,
            binding_contract=binding_contract,
            render_ids=render_ids,
            simulation_ids=simulation_ids,
        )
        simulation_rest = _manifest_positions(simulation_manifest)
        motion_delta = canonical_motion_delta
        influence_authority = "canonical_production_binding_contract"
        maximum_canonical_influences = 3
        maximum_processor_influences = 3
    if not uses_mechanical_reference:
        timestamps, frames = _mechanical_frames(simulation_rest, motion_delta, clip_scale)
    binding_bytes = _binding_payload(bindings)

    static_identity = static_derivative_identity_hash(derivative)
    static_inventory = static_inventory_hash(_object_value(derivative, "nanite"))
    simulation_topology = simulation_topology_hash(simulation_ids)
    render_topology = render_topology_hash(render_ids, render_indices)
    source_cluster = source_to_cluster_hash(render_ids, render_indices)
    clip_payload = b"".join(struct.pack("<3f", *position) for position in frames)
    clip_sha256 = digest_bytes(clip_payload)

    static_request = build_zeroone_request(
        invocation_root=root,
        package=package_root,
        output=output_root,
        closy_sha=closy_sha,
        request_label="closy-phase11-dynamic-reference",
    )
    semantic_ids = dict(_object_value(static_request, "semanticIds"))
    semantic_ids["materials"] = sorted(
        {str(mesh.get("materialId")) for mesh in _mesh_rows(render_manifest)}
    )
    semantic_ids["layers"] = ["layer.base.top"]
    cache_key = digest_bytes(
        canonical_json(
            {
                "profile": DYNAMIC_PROFILE,
                "package": manifest.get("canonicalPackageDigest"),
                "staticIdentity": static_identity,
                "clip": clip_sha256,
                "renderTopology": render_topology,
                "simulationTopology": simulation_topology,
                "binding": digest_bytes(binding_bytes),
            }
        )
    )
    metadata: dict[str, Any] = {
        "schemaVersion": DYNAMIC_REQUEST_SCHEMA_VERSION,
        "profile": DYNAMIC_PROFILE,
        "garmentId": manifest.get("garmentId"),
        "canonicalPackageDigest": manifest.get("canonicalPackageDigest"),
        "staticDerivativeIdentitySha256": static_identity,
        "staticClusterInventorySha256": static_inventory,
        "simulationTopologySha256": simulation_topology,
        "bindingContractSha256": digest_bytes(binding_bytes),
        "renderTopologySha256": render_topology,
        "sourceToClusterMapSha256": source_cluster,
        "coordinateConventionId": "closy-rh-yup-plus-z-v1",
        "unitScaleMetres": 1.0,
        "staticDerivativeRoot": posix_rel(static_root, root),
        "outputRoot": posix_rel(output_root, root),
        "cancellationToken": posix_rel(output_root / "cancel.requested", root),
        "cacheKey": cache_key,
        "deadlineMs": 120_000,
        "limits": {
            "maximumFrames": 4096,
            "maximumVertices": 4_000_000,
            "maximumClusters": 1_000_000,
            "maximumInfluences": 12_000_000,
            "maximumTotalBytes": 512 * 1024 * 1024,
        },
        "semanticIds": semantic_ids,
        "provenance": {
            "classification": "manually_authored_mechanical_reference",
            "physicalTruth": False,
            "generator": MECHANICAL_CLIP_PROFILE if uses_mechanical_reference else CLIP_PROFILE,
            "sourceMotionState": (
                "independently_authored_analytic_reference"
                if uses_mechanical_reference
                else "torso_twist"
            ),
            "sourceStateProvenance": (
                "deterministic_project_authored_analytic_reference"
                if uses_mechanical_reference
                else "deterministic_public_fixture_reference_solver"
            ),
            "clipScale": None if uses_mechanical_reference else clip_scale,
            "mechanicalReferenceProfile": (
                MECHANICAL_REFERENCE_PROFILE if uses_mechanical_reference else None
            ),
            "dynamicProcessingSurface": uses_dynamic_processing,
            "bodyProxySpheres": [],
        },
    }
    sections = (
        json_section(metadata),
        u64_section(SIMULATION_IDS, simulation_ids),
        u64_section(RENDER_IDS, render_ids),
        vec3_section(SIMULATION_REST, simulation_rest),
        Section(BINDINGS, len(bindings), 4, binding_bytes),
        u64_section(TIMESTAMPS, timestamps),
        vec3_section(FRAME_SIMULATION_POSITIONS, frames),
    )
    encoded = encode_document(sections, request=True)
    return DynamicRequestBundle(
        encoded=encoded,
        metadata=metadata,
        request_sha256=digest_bytes(encoded),
        clip_inventory={
            "schemaVersion": "closy.zeroone.dynamic-clip-inventory.v1",
            "profile": MECHANICAL_CLIP_PROFILE if uses_mechanical_reference else CLIP_PROFILE,
            "classification": "mechanical_reference",
            "physicalTruth": False,
            "sourceState": (
                "independently_authored_analytic_reference"
                if uses_mechanical_reference
                else "torso_twist"
            ),
            "restAuthority": (
                "canonical_simulation_rest_state"
                if uses_mechanical_reference
                else (
                    "exact_validated_dynamic_processing_surface"
                    if uses_dynamic_processing
                    else "canonical_simulation_mesh_manifest"
                )
            ),
            "motionDeltaAuthority": (
                "independent_analytic_spatial_deformation_v2"
                if uses_mechanical_reference
                else "torso_twist_minus_neutral_settled_solver_states"
            ),
            "sourceStateHash": (
                None
                if uses_mechanical_reference
                else _object(package_root / "simulation" / "motion_states" / "torso_twist.json")[
                    "integrity"
                ]["stateHash"]
            ),
            "neutralStateHash": (
                None
                if uses_mechanical_reference
                else _object(
                    package_root / "simulation" / "motion_states" / "neutral_settled.json"
                )["integrity"]["stateHash"]
            ),
            "clipScale": None if uses_mechanical_reference else clip_scale,
            "frameCount": len(timestamps),
            "timestampsMicroseconds": timestamps,
            "firstAndLastFrameRestIdentity": True,
            "clipPayloadSha256": clip_sha256,
            "motionAudit": motion_audit,
        },
        influence_inventory={
            "schemaVersion": "closy.zeroone.dynamic-influence-inventory.v1",
            "authority": influence_authority,
            "canonicalBindingContractHash": binding_contract["integrity"][
                "productionBindingContractHash"
            ],
            "destinationCount": len(bindings),
            "classifiedDestinationCount": len(bindings),
            "missingDestinationCount": 0,
            "maximumCanonicalInfluencesPerDestination": maximum_canonical_influences,
            "maximumProcessorInfluencesPerDestination": maximum_processor_influences,
            "dynamicProcessingSurface": uses_dynamic_processing,
            "mechanicalReferenceSurface": uses_mechanical_reference,
            "dynamicProcessingInfluenceHash": (
                processing_influence.get("integrity", {}).get("influenceHash")
                if uses_dynamic_processing
                else None
            ),
            "bindingContractSha256": digest_bytes(binding_bytes),
        },
        topology_inventory={
            "schemaVersion": "closy.zeroone.dynamic-topology-inventory.v1",
            "simulationVertexCount": len(simulation_ids),
            "canonicalSimulationVertexCount": _vertex_count(simulation_manifest),
            "renderVertexCount": len(render_ids),
            "triangleCount": len(render_indices) // 3,
            "simulationTopologySha256": simulation_topology,
            "renderTopologySha256": render_topology,
            "sourceToClusterMapSha256": source_cluster,
            "renderTexcoordCount": len(render_texcoords),
        },
    )


def write_dynamic_request(path: Path, bundle: DynamicRequestBundle) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bundle.encoded)


def static_derivative_identity_hash(derivative: dict[str, Any]) -> str:
    nanite = _object_value(derivative, "nanite")
    return digest_bytes(
        canonical_json(
            {
                "schemaVersion": derivative["schemaVersion"],
                "profile": derivative["profile"],
                "garmentId": derivative["garmentId"],
                "source": derivative["source"],
                "nanite": {
                    key: nanite[key]
                    for key in (
                        "clusterCount",
                        "hierarchyNodeCount",
                        "pageCount",
                        "pagePackCount",
                        "pagePackFormatVersion",
                        "geometryHash",
                        "topologyHash",
                        "materialHash",
                    )
                },
                "garmentSemantics": derivative["garmentSemantics"],
            }
        )
    )


def _expanded_render_contract(
    *,
    render_manifest: dict[str, Any],
    render_meshset: Any,
    binding_contract: dict[str, Any],
    render_ids: list[int],
    simulation_ids: list[int],
) -> tuple[list[int], list[Vec2], list[dict[str, Any]]]:
    contract_records = {
        int(record["globalRenderVertexIndex"]): record
        for record in binding_contract.get("records", [])
    }
    indices: list[int] = []
    texcoords: list[Vec2] = []
    bindings: list[dict[str, Any]] = []
    logical_offset = 0
    expanded_offset = 0
    global_triangle_offset = 0
    manifest_meshes = _mesh_rows(render_manifest)
    if len(manifest_meshes) != len(render_meshset.meshes):
        raise ValueError("dynamic_render_mesh_count_mismatch")
    for mesh_index, (logical, expanded) in enumerate(
        zip(manifest_meshes, render_meshset.meshes, strict=True)
    ):
        vertices = [_vec3(value) for value in logical.get("vertices", [])]
        uvs = [_vec2(value) for value in logical.get("panelUvs", [])]
        triangles = [tuple(int(index) for index in row) for row in logical.get("triangles", [])]
        if len(expanded.vertices) != len(triangles) * 3 or len(expanded.triangles) != len(
            triangles
        ):
            raise ValueError("dynamic_expanded_render_topology_mismatch")
        for triangle_index, triangle in enumerate(triangles):
            for corner, logical_local in enumerate(triangle):
                expanded_local = triangle_index * 3 + corner
                expanded_global = expanded_offset + expanded_local
                logical_global = logical_offset + logical_local
                if _f32_vec3(vertices[logical_local]) != expanded.vertices[expanded_local]:
                    raise ValueError("dynamic_render_position_order_mismatch")
                if _f32_vec2(uvs[logical_local]) != expanded.panel_uvs[expanded_local]:
                    raise ValueError("dynamic_render_uv_order_mismatch")
                record = contract_records.get(logical_global)
                if record is None or int(record.get("renderMeshIndex", -1)) != mesh_index:
                    raise ValueError("dynamic_binding_record_missing")
                source = record.get("sourceTriangle", {})
                source_indices = [int(value) for value in source.get("globalVertexIndices", [])]
                weights = [float(value) for value in record.get("binding", {}).get("weights", [])]
                if len(source_indices) != 3 or len(weights) != 3:
                    raise ValueError("dynamic_binding_influence_invalid")
                if any(index < 0 or index >= len(simulation_ids) for index in source_indices):
                    raise ValueError("dynamic_binding_source_out_of_range")
                bindings.append(
                    {
                        "destination": render_ids[expanded_global],
                        "authority": 1,
                        "count": 3,
                        "sources": tuple(simulation_ids[index] for index in source_indices),
                        "weights": tuple(weights),
                        "triangle": _stable_id(0x3, int(source["globalTriangleIndex"])),
                    }
                )
                indices.append(expanded_global)
                texcoords.append(expanded.panel_uvs[expanded_local])
        logical_offset += len(vertices)
        expanded_offset += len(expanded.vertices)
        global_triangle_offset += len(triangles)
    if logical_offset != len(contract_records) or expanded_offset != len(render_ids):
        raise ValueError("dynamic_render_inventory_mismatch")
    if global_triangle_offset != render_manifest.get("triangleCount"):
        raise ValueError("dynamic_render_triangle_inventory_mismatch")
    return indices, texcoords, bindings


def _mechanical_reference_render_contract(
    *,
    package: Path,
    render_manifest: dict[str, Any],
    render_meshset: Any,
    binding_contract: dict[str, Any],
    render_ids: list[int],
    simulation_ids: list[int],
) -> tuple[list[int], list[Vec2], list[dict[str, Any]]]:
    corner_map = _object(package / MECHANICAL_REFERENCE_CORNER_MAP_PATH)
    corner_rows = corner_map.get("rows")
    if not isinstance(corner_rows, list) or len(corner_rows) != render_meshset.vertex_count:
        raise ValueError("mechanical_reference_corner_map_inventory_mismatch")
    contract_records = {
        int(record["globalRenderVertexIndex"]): record
        for record in binding_contract.get("records", [])
    }
    indices: list[int] = []
    texcoords: list[Vec2] = []
    bindings: list[dict[str, Any]] = []
    vertex_offset = 0
    for mesh in render_meshset.meshes:
        for triangle in mesh.triangles:
            indices.extend(vertex_offset + int(index) for index in triangle)
        texcoords.extend(mesh.panel_uvs)
        vertex_offset += len(mesh.vertices)
    if indices != list(range(len(render_ids))):
        raise ValueError("mechanical_reference_surface_not_expanded_triangle_order")
    for dense_index, row in enumerate(corner_rows):
        if not isinstance(row, dict) or int(row.get("denseCornerIndex", -1)) != dense_index:
            raise ValueError("mechanical_reference_corner_map_order_invalid")
        logical = int(row.get("logicalDestinationIndex", -1))
        record = contract_records.get(logical)
        if record is None:
            raise ValueError("mechanical_reference_binding_record_missing")
        source = record.get("sourceTriangle", {})
        source_indices = [int(value) for value in source.get("globalVertexIndices", [])]
        raw_weights = [float(value) for value in record.get("binding", {}).get("weights", [])]
        if len(source_indices) != 3 or len(raw_weights) != 3:
            raise ValueError("mechanical_reference_binding_influence_invalid")
        if any(index < 0 or index >= len(simulation_ids) for index in source_indices):
            raise ValueError("mechanical_reference_binding_source_out_of_range")
        active = [
            (source_index, weight)
            for source_index, weight in zip(source_indices, raw_weights, strict=True)
            if abs(weight) > 1.0e-9
        ]
        count = len(active)
        if count not in (1, 2, 3):
            raise ValueError("mechanical_reference_binding_active_influence_order_invalid")
        packed_sources = [item[0] for item in active] + [0] * (3 - count)
        packed_weights = [item[1] for item in active] + [0.0] * (3 - count)
        bindings.append(
            {
                "destination": render_ids[dense_index],
                "authority": 1,
                "count": count,
                "sources": tuple(
                    simulation_ids[index] if item < count else 0
                    for item, index in enumerate(packed_sources)
                ),
                "sourceIndices": tuple(packed_sources),
                "weights": tuple(packed_weights),
                "triangle": _stable_id(0x3, int(source["globalTriangleIndex"])),
                "logicalDestination": logical,
                "panelId": str(record.get("ownership", {}).get("panelId", "unknown")),
            }
        )
    return indices, texcoords, bindings


def _analytic_reference_frames(
    rest: list[Vec3], *, scale_factor: float
) -> tuple[list[int], list[Vec3]]:
    minimum = [min(position[axis] for position in rest) for axis in range(3)]
    maximum = [max(position[axis] for position in rest) for axis in range(3)]
    center = tuple((minimum[axis] + maximum[axis]) * 0.5 for axis in range(3))
    diagonal = math.dist(tuple(minimum), tuple(maximum))
    height = max(maximum[1] - minimum[1], 1.0e-12)
    timestamps = [index * FRAME_STEP_MICROSECONDS for index in range(FRAME_COUNT)]
    frames: list[Vec3] = []
    maximum_angle = math.radians(5.5)
    for frame in range(FRAME_COUNT):
        if frame in (0, FRAME_COUNT - 1):
            frames.extend(rest)
            continue
        time = frame / (FRAME_COUNT - 1)
        envelope = math.sin(math.pi * time)
        sway = math.sin(2.0 * math.pi * time)
        for position in rest:
            normalized_y = (position[1] - minimum[1]) / height
            angle = maximum_angle * scale_factor * envelope * (0.25 + 0.75 * normalized_y)
            local_x = position[0] - center[0]
            local_z = position[2] - center[2]
            rotated_x = math.cos(angle) * local_x + math.sin(angle) * local_z
            rotated_z = -math.sin(angle) * local_x + math.cos(angle) * local_z
            bend = 0.004 * diagonal * scale_factor * envelope * normalized_y * normalized_y
            frames.append(
                (
                    center[0]
                    + rotated_x
                    + bend
                    + 0.005 * diagonal * scale_factor * envelope
                    + 0.0015 * diagonal * scale_factor * sway,
                    position[1] + 0.0015 * diagonal * scale_factor * sway * normalized_y,
                    center[2]
                    + rotated_z
                    + 0.003 * diagonal * scale_factor * envelope * math.sin(math.pi * normalized_y),
                )
            )
    return timestamps, frames


def _audit_reference_motion(
    *,
    simulation_rest: list[Vec3],
    frames: list[Vec3],
    bindings: list[dict[str, Any]],
    binding_contract: dict[str, Any],
    scale_factor: float,
) -> dict[str, Any]:
    frame_rows = [
        frames[index * len(simulation_rest) : (index + 1) * len(simulation_rest)]
        for index in range(FRAME_COUNT)
    ]
    minimum = [min(position[axis] for position in simulation_rest) for axis in range(3)]
    maximum = [max(position[axis] for position in simulation_rest) for axis in range(3)]
    diagonal = math.dist(tuple(minimum), tuple(maximum))
    destination_frames: list[list[Vec3]] = []
    for frame in frame_rows:
        destination_frames.append(
            [
                (
                    sum(
                        frame[record["sourceIndices"][item]][0] * record["weights"][item]
                        for item in range(record["count"])
                    ),
                    sum(
                        frame[record["sourceIndices"][item]][1] * record["weights"][item]
                        for item in range(record["count"])
                    ),
                    sum(
                        frame[record["sourceIndices"][item]][2] * record["weights"][item]
                        for item in range(record["count"])
                    ),
                )
                for record in bindings
            ]
        )
    destination_rest = destination_frames[0]
    maximum_displacement = max(
        math.dist(position, destination_rest[index])
        for frame in destination_frames[1:-1]
        for index, position in enumerate(frame)
    )
    movement_threshold = diagonal * MOVEMENT_THRESHOLD_DIAGONAL_FRACTION
    moving = [
        index
        for index in range(len(destination_rest))
        if max(
            math.dist(frame[index], destination_rest[index]) for frame in destination_frames[1:-1]
        )
        > movement_threshold
    ]
    peak_frame = max(
        destination_frames[1:-1],
        key=lambda frame: max(
            math.dist(frame[index], destination_rest[index])
            for index in range(len(destination_rest))
        ),
    )
    residuals = _best_rigid_residuals(destination_rest, peak_frame)
    nonrigid = sum(residual > movement_threshold for residual in residuals)
    moving_regions = sorted({bindings[index]["panelId"] for index in moving})
    frame_hashes = [
        digest_bytes(b"".join(struct.pack("<3f", *position) for position in frame))
        for frame in frame_rows
    ]
    normalized = maximum_displacement / diagonal
    audit = {
        "schemaVersion": "closy.zeroone.analytic-motion-audit.v2",
        "precommittedThresholds": {
            "minimumMaximumDisplacementD": MINIMUM_NORMALIZED_DISPLACEMENT,
            "maximumMaximumDisplacementD": MAXIMUM_NORMALIZED_DISPLACEMENT,
            "minimumMovingDestinationFraction": MINIMUM_MOVING_DESTINATION_FRACTION,
            "minimumNonrigidDestinationFraction": MINIMUM_NONRIGID_DESTINATION_FRACTION,
            "movementThresholdD": MOVEMENT_THRESHOLD_DIAGONAL_FRACTION,
            "minimumBendAngleDegrees": MINIMUM_BEND_ANGLE_DEGREES,
        },
        "boundingBoxDiagonalMeters": diagonal,
        "maximumDestinationDisplacementMeters": maximum_displacement,
        "maximumDestinationDisplacementD": normalized,
        "movingDestinationCount": len(moving),
        "destinationCount": len(destination_rest),
        "movingDestinationFraction": len(moving) / len(destination_rest),
        "movingSemanticRegions": moving_regions,
        "nonrigidResidualDestinationCount": nonrigid,
        "nonrigidResidualDestinationFraction": nonrigid / len(destination_rest),
        "bestRigidFitMethod": "horn_quaternion_least_squares",
        "maximumBendAngleDegrees": 5.5 * scale_factor,
        "restFrameExact": frame_rows[0] == simulation_rest,
        "returnFrameExact": frame_rows[-1] == simulation_rest,
        "consecutiveNonRestFramesUnique": all(
            frame_hashes[index] != frame_hashes[index + 1] for index in range(1, FRAME_COUNT - 2)
        ),
        "frameHashes": frame_hashes,
        "bindingInfluenceDistribution": {
            str(count): sum(record["count"] == count for record in bindings) for count in (1, 2, 3)
        },
        "canonicalBindingAuthorityHash": binding_contract.get("integrity", {}).get(
            "productionBindingContractHash"
        ),
    }
    checks = {
        "maximumDisplacementLowerBound": normalized >= MINIMUM_NORMALIZED_DISPLACEMENT,
        "maximumDisplacementUpperBound": normalized <= MAXIMUM_NORMALIZED_DISPLACEMENT,
        "movingDestinationCoverage": audit["movingDestinationFraction"]
        >= MINIMUM_MOVING_DESTINATION_FRACTION,
        "semanticRegionCoverage": len(moving_regions) >= 3,
        "nonrigidCoverage": audit["nonrigidResidualDestinationFraction"]
        >= MINIMUM_NONRIGID_DESTINATION_FRACTION,
        "bendAngle": audit["maximumBendAngleDegrees"] > MINIMUM_BEND_ANGLE_DEGREES,
        "restReturnIdentity": audit["restFrameExact"] and audit["returnFrameExact"],
        "temporalUniqueness": audit["consecutiveNonRestFramesUnique"],
    }
    audit["checks"] = checks
    audit["passed"] = all(checks.values())
    audit["qualificationCandidate"] = abs(scale_factor - 1.0) <= 1.0e-12
    if audit["qualificationCandidate"] and not audit["passed"]:
        raise ValueError(f"mechanical_reference_motion_threshold_failed:{checks}")
    return audit


def _best_rigid_residuals(source: list[Vec3], target: list[Vec3]) -> list[float]:
    source_center = tuple(sum(point[axis] for point in source) / len(source) for axis in range(3))
    target_center = tuple(sum(point[axis] for point in target) / len(target) for axis in range(3))
    covariance = [[0.0] * 3 for _ in range(3)]
    for left, right in zip(source, target, strict=True):
        a = tuple(left[axis] - source_center[axis] for axis in range(3))
        b = tuple(right[axis] - target_center[axis] for axis in range(3))
        for row in range(3):
            for column in range(3):
                covariance[row][column] += a[row] * b[column]
    sxx, sxy, sxz = covariance[0]
    syx, syy, syz = covariance[1]
    szx, szy, szz = covariance[2]
    matrix = [
        [sxx + syy + szz, syz - szy, szx - sxz, sxy - syx],
        [syz - szy, sxx - syy - szz, sxy + syx, szx + sxz],
        [szx - sxz, sxy + syx, -sxx + syy - szz, syz + szy],
        [sxy - syx, szx + sxz, syz + szy, -sxx - syy + szz],
    ]
    quaternion = [1.0, 0.0, 0.0, 0.0]
    for _ in range(64):
        candidate = [
            sum(matrix[row][column] * quaternion[column] for column in range(4)) for row in range(4)
        ]
        norm = math.sqrt(sum(value * value for value in candidate))
        if norm <= 1.0e-30:
            break
        quaternion = [value / norm for value in candidate]
    rotation = _quaternion_rotation(quaternion)
    residuals = []
    for left, right in zip(source, target, strict=True):
        centered = tuple(left[axis] - source_center[axis] for axis in range(3))
        rotated = tuple(
            sum(rotation[row][column] * centered[column] for column in range(3))
            + target_center[row]
            for row in range(3)
        )
        residuals.append(math.dist(rotated, right))
    return residuals


def _quaternion_rotation(quaternion: list[float]) -> list[list[float]]:
    w, x, y, z = quaternion
    return [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ]


def _processing_render_contract(
    *,
    render_meshset: Any,
    render_ids: list[int],
    simulation_ids: list[int],
) -> tuple[list[int], list[Vec2], list[dict[str, Any]]]:
    if len(render_ids) != len(simulation_ids) or len(render_ids) != render_meshset.vertex_count:
        raise ValueError("dynamic_processing_vertex_inventory_mismatch")
    indices: list[int] = []
    texcoords: list[Vec2] = []
    bindings: list[dict[str, Any]] = []
    vertex_offset = 0
    triangle_offset = 0
    for mesh in render_meshset.meshes:
        for triangle in mesh.triangles:
            for local_vertex in triangle:
                global_vertex = vertex_offset + int(local_vertex)
                indices.append(global_vertex)
        texcoords.extend(mesh.panel_uvs)
        triangle_offset += len(mesh.triangles)
        vertex_offset += len(mesh.vertices)
    for index, (render_id, simulation_id) in enumerate(
        zip(render_ids, simulation_ids, strict=True)
    ):
        bindings.append(
            {
                "destination": render_id,
                "authority": 2,
                "count": 1,
                "sources": (simulation_id, 0, 0),
                "weights": (1.0, 0.0, 0.0),
                "triangle": _stable_id(0x5, index // 3),
            }
        )
    if indices != list(range(len(render_ids))) or triangle_offset * 3 != len(indices):
        raise ValueError("dynamic_processing_surface_not_expanded_triangle_order")
    return indices, texcoords, bindings


def _processing_motion_delta(influence: dict[str, Any], canonical_delta: list[Vec3]) -> list[Vec3]:
    rows = influence.get("rows")
    if not isinstance(rows, list):
        raise ValueError("dynamic_processing_influence_rows_missing")
    result: list[Vec3] = []
    for expected, row in enumerate(rows):
        if not isinstance(row, dict) or row.get("processingVertex") != expected:
            raise ValueError("dynamic_processing_influence_order_invalid")
        sources = row.get("canonicalSimulationVertexIndices")
        weights = row.get("weights")
        if (
            not isinstance(sources, list)
            or not isinstance(weights, list)
            or len(sources) != 3
            or len(weights) != 3
        ):
            raise ValueError("dynamic_processing_influence_record_invalid")
        value = [0.0, 0.0, 0.0]
        for source, weight in zip(sources, weights, strict=True):
            index = int(source)
            if index < 0 or index >= len(canonical_delta):
                raise ValueError("dynamic_processing_influence_source_out_of_range")
            for axis in range(3):
                value[axis] += canonical_delta[index][axis] * float(weight)
        result.append((value[0], value[1], value[2]))
    if len(result) != int(influence.get("processingVertexCount", -1)):
        raise ValueError("dynamic_processing_influence_count_mismatch")
    return result


def _binding_payload(records: list[dict[str, Any]]) -> bytes:
    output = bytearray()
    for record in records:
        output.extend(
            struct.pack(
                "<QII3Q3fQI",
                record["destination"],
                record["authority"],
                record["count"],
                *record["sources"],
                *record["weights"],
                record["triangle"],
                0,
            )
        )
    return bytes(output)


def _state_positions(path: Path, simulation_manifest: dict[str, Any]) -> list[Vec3]:
    state = _object(path)
    state_meshes = state.get("meshes", [])
    manifest_meshes = _mesh_rows(simulation_manifest)
    if not isinstance(state_meshes, list) or len(state_meshes) != len(manifest_meshes):
        raise ValueError("dynamic_motion_state_mesh_count_mismatch")
    positions: list[Vec3] = []
    for expected, actual in zip(manifest_meshes, state_meshes, strict=True):
        if actual.get("name") != expected.get("name"):
            raise ValueError("dynamic_motion_state_mesh_order_mismatch")
        rows = [_vec3(value) for value in actual.get("positions", [])]
        if len(rows) != len(expected.get("vertices", [])):
            raise ValueError("dynamic_motion_state_vertex_count_mismatch")
        positions.extend(rows)
    return positions


def _mechanical_frames(
    rest: list[Vec3], motion_delta: list[Vec3], clip_scale: float
) -> tuple[list[int], list[Vec3]]:
    if len(rest) != len(motion_delta):
        raise ValueError("dynamic_motion_state_topology_mismatch")
    timestamps = [index * FRAME_STEP_MICROSECONDS for index in range(FRAME_COUNT)]
    frames: list[Vec3] = []
    for frame in range(FRAME_COUNT):
        phase = math.sin(math.pi * frame / (FRAME_COUNT - 1))
        for source, delta in zip(rest, motion_delta, strict=True):
            frames.append(
                (
                    source[0] + delta[0] * clip_scale * phase,
                    source[1] + delta[1] * clip_scale * phase,
                    source[2] + delta[2] * clip_scale * phase,
                )
            )
    return timestamps, frames


def _manifest_positions(simulation_manifest: dict[str, Any]) -> list[Vec3]:
    return [
        _vec3(position)
        for mesh in _mesh_rows(simulation_manifest)
        for position in mesh.get("vertices", [])
    ]


def _stable_id(namespace: int, index: int) -> int:
    return namespace << 60 | index + 1


def _vertex_count(manifest: dict[str, Any]) -> int:
    value = int(manifest.get("vertexCount", -1))
    if value <= 0:
        raise ValueError("dynamic_vertex_inventory_invalid")
    return value


def _mesh_rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    rows = manifest.get("meshes")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("dynamic_mesh_inventory_invalid")
    return rows


def _object(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"dynamic_json_object_required:{path.name}")
    return value


def _object_value(value: dict[str, Any], key: str) -> dict[str, Any]:
    candidate = value.get(key)
    if not isinstance(candidate, dict):
        raise ValueError(f"dynamic_object_field_required:{key}")
    return candidate


def _vec3(value: Any) -> Vec3:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError("dynamic_vec3_invalid")
    result = tuple(float(component) for component in value)
    if not all(math.isfinite(component) for component in result):
        raise ValueError("dynamic_vec3_nonfinite")
    return result  # type: ignore[return-value]


def _vec2(value: Any) -> Vec2:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("dynamic_vec2_invalid")
    result = tuple(float(component) for component in value)
    if not all(math.isfinite(component) for component in result):
        raise ValueError("dynamic_vec2_nonfinite")
    return result  # type: ignore[return-value]


def _f32_vec3(value: Vec3) -> Vec3:
    return struct.unpack("<3f", struct.pack("<3f", *value))


def _f32_vec2(value: Vec2) -> Vec2:
    return struct.unpack("<2f", struct.pack("<2f", *value))
