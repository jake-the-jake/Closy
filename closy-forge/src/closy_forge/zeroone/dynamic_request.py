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
from closy_forge.zeroone.request import build_zeroone_request

DYNAMIC_REQUEST_SCHEMA_VERSION = "closy.zeroone.dynamic-request.v1"
DYNAMIC_REPORT_SCHEMA_VERSION = "zeroone.closy.dynamic-report.v1"
DYNAMIC_PROFILE = "closy-dynamic-d0-single-lod-reference-v1"
SCOPED_ACCEPTANCE_PROFILE = "Z2-D0-single-LOD-reference"
CLIP_PROFILE = "closy.dynamic.mechanical-reference.torso-twist.v1"
FRAME_COUNT = 13
FRAME_STEP_MICROSECONDS = 16_667
DEFAULT_CLIP_SCALE = 0.02

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
    render_meshset = read_glb_meshset(package_root / "render" / "fallback.glb")

    simulation_ids = [_stable_id(0x2, index) for index in range(_vertex_count(simulation_manifest))]
    render_ids = [_stable_id(0x1, index) for index in range(render_meshset.vertex_count)]
    render_indices, render_texcoords, bindings = _expanded_render_contract(
        render_manifest=render_manifest,
        render_meshset=render_meshset,
        binding_contract=binding_contract,
        render_ids=render_ids,
        simulation_ids=simulation_ids,
    )
    simulation_rest = _state_positions(
        package_root / "simulation" / "motion_states" / "neutral_settled.json",
        simulation_manifest,
    )
    target_positions = _state_positions(
        package_root / "simulation" / "motion_states" / "torso_twist.json",
        simulation_manifest,
    )
    timestamps, frames = _mechanical_frames(simulation_rest, target_positions, clip_scale)
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
            "generator": CLIP_PROFILE,
            "sourceMotionState": "torso_twist",
            "sourceStateProvenance": "deterministic_public_fixture_reference_solver",
            "clipScale": clip_scale,
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
            "profile": CLIP_PROFILE,
            "classification": "mechanical_reference",
            "physicalTruth": False,
            "sourceState": "torso_twist",
            "sourceStateHash": _object(
                package_root / "simulation" / "motion_states" / "torso_twist.json"
            )["integrity"]["stateHash"],
            "neutralStateHash": _object(
                package_root / "simulation" / "motion_states" / "neutral_settled.json"
            )["integrity"]["stateHash"],
            "clipScale": clip_scale,
            "frameCount": len(timestamps),
            "timestampsMicroseconds": timestamps,
            "firstAndLastFrameRestIdentity": True,
            "clipPayloadSha256": clip_sha256,
        },
        influence_inventory={
            "schemaVersion": "closy.zeroone.dynamic-influence-inventory.v1",
            "authority": "canonical_production_binding_contract",
            "canonicalBindingContractHash": binding_contract["integrity"][
                "productionBindingContractHash"
            ],
            "destinationCount": len(bindings),
            "classifiedDestinationCount": len(bindings),
            "missingDestinationCount": 0,
            "maximumInfluencesPerDestination": 3,
            "bindingContractSha256": digest_bytes(binding_bytes),
        },
        topology_inventory={
            "schemaVersion": "closy.zeroone.dynamic-topology-inventory.v1",
            "simulationVertexCount": len(simulation_ids),
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
    rest: list[Vec3], target: list[Vec3], clip_scale: float
) -> tuple[list[int], list[Vec3]]:
    if len(rest) != len(target):
        raise ValueError("dynamic_motion_state_topology_mismatch")
    timestamps = [index * FRAME_STEP_MICROSECONDS for index in range(FRAME_COUNT)]
    frames: list[Vec3] = []
    for frame in range(FRAME_COUNT):
        phase = math.sin(math.pi * frame / (FRAME_COUNT - 1))
        for source, destination in zip(rest, target, strict=True):
            frames.append(
                (
                    source[0] + (destination[0] - source[0]) * clip_scale * phase,
                    source[1] + (destination[1] - source[1]) * clip_scale * phase,
                    source[2] + (destination[2] - source[2]) * clip_scale * phase,
                )
            )
    return timestamps, frames


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
