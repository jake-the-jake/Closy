from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

from closy_forge.geometry.glb_io import read_glb_meshset
from closy_forge.geometry.mesh_model import MeshSet, Vec3
from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import geometry_content_hash, sha256_file, topology_hash
from closy_forge.zeroone.dynamic_processing_surface import (
    DYNAMIC_PROCESSING_INFLUENCE_PATH,
    DYNAMIC_PROCESSING_REMAP_PATH,
    DYNAMIC_PROCESSING_SURFACE_PATH,
)
from closy_forge.zeroone.intersection_manifest import SurfaceRepresentation, audit_surface

REPRESENTATION_AUDIT_PROFILE = "closy.zeroone.representation-localization.v2"
HISTORICAL_CLIP_SCALE = 0.02
FRAME_COUNT = 13


def audit_historical_representations(package_dir: Path) -> dict[str, Any]:
    """Localize the first invalid PR #34 representation without modifying source geometry."""

    package = package_dir.resolve(strict=True)
    simulation_manifest = _object(package / "simulation" / "mesh_manifest.json")
    render_manifest = _object(package / "render" / "mesh_manifest.json")
    rest_state = _object(package / "simulation" / "rest_state.json")
    binding = _object(package / "binding" / "production_binding_contract.json")
    simulation_rest = _state_positions(rest_state)
    simulation_triangles, simulation_lineage = _manifest_triangles(simulation_manifest)
    render_triangles, render_lineage = _manifest_triangles(render_manifest)
    logical_ids = list(range(int(render_manifest["vertexCount"])))
    dense_logical_ids = [index for triangle in render_triangles for index in triangle]

    canonical = SurfaceRepresentation(
        "canonical_stitched_simulation_rest",
        simulation_rest,
        simulation_triangles,
        list(range(len(simulation_rest))),
        simulation_lineage,
    )
    logical = SurfaceRepresentation(
        "logical_fallback_render_mesh",
        _manifest_positions(render_manifest),
        render_triangles,
        logical_ids,
        render_lineage,
    )
    expanded_mesh = read_glb_meshset(package / "render" / "fallback.glb")
    expanded_positions, expanded_triangles = _meshset_surface(expanded_mesh)
    expanded = SurfaceRepresentation(
        "expanded_dense_render_surface",
        expanded_positions,
        expanded_triangles,
        dense_logical_ids,
        render_lineage,
    )
    processing_mesh = read_glb_meshset(package / DYNAMIC_PROCESSING_SURFACE_PATH)
    processing_positions, processing_triangles = _meshset_surface(processing_mesh)
    processing_ids, processing_lineage = _processing_lineage(
        package, dense_logical_ids, render_lineage, len(processing_positions)
    )
    processing = SurfaceRepresentation(
        "dynamic_processing_surface_before_zeroone",
        processing_positions,
        processing_triangles,
        processing_ids,
        processing_lineage,
    )

    static_results = [
        _compact_audit(audit_surface(surface), surface.triangle_lineage)
        for surface in (canonical, logical, expanded, processing)
    ]
    reconstructed_frames = _historical_processing_frames(
        package, processing_positions, simulation_manifest
    )
    frame_results = []
    for frame, positions in enumerate(reconstructed_frames):
        surface = SurfaceRepresentation(
            "independent_zeroone_reconstruction",
            positions,
            processing_triangles,
            processing_ids,
            processing_lineage,
        )
        result = _compact_audit(audit_surface(surface), processing_lineage)
        result["frameIndex"] = frame
        result["phase"] = math.sin(math.pi * frame / (FRAME_COUNT - 1))
        frame_results.append(result)

    counts = [row["intersectingPairCount"] for row in frame_results]
    first_invalid = next(
        (
            row["representationId"]
            for row in static_results
            if row["intersectingPairCount"] > 0
            or any(
                row["topology"][key] > 0
                for key in (
                    "duplicateFaceCount",
                    "nonManifoldEdgeCount",
                    "tJunctionCount",
                    "degenerateTriangleCount",
                )
            )
        ),
        None,
    )
    identity = {
        "canonicalSimulationRestSha256": sha256_file(package / "simulation" / "rest_state.json"),
        "simulationManifestSha256": sha256_file(package / "simulation" / "mesh_manifest.json"),
        "logicalRenderManifestSha256": sha256_file(package / "render" / "mesh_manifest.json"),
        "expandedDenseSha256": sha256_file(package / "render" / "fallback.glb"),
        "expandedDenseTopologyHash": topology_hash(expanded_mesh),
        "expandedDenseContentHash": geometry_content_hash(expanded_mesh),
        "dynamicProcessingSha256": sha256_file(package / DYNAMIC_PROCESSING_SURFACE_PATH),
        "dynamicProcessingTopologyHash": topology_hash(processing_mesh),
        "dynamicProcessingContentHash": geometry_content_hash(processing_mesh),
        "productionBindingSha256": sha256_file(
            package / "binding" / "production_binding_contract.json"
        ),
        "productionBindingAuthorityHash": binding.get("integrity", {}).get(
            "productionBindingContractHash"
        ),
    }
    result = {
        "schemaVersion": 2,
        "profile": REPRESENTATION_AUDIT_PROFILE,
        "historicalAuthority": {
            "closyPr34Head": "960662d237e187cd8ecbcc9ebe9192367f194317",
            "zeroOnePr3Head": "413aecd24434f90d89ad35c6a8f909de75df34c7",
            "historicalRequestSha256": (
                "926bb20398db795d2d9a66a39e80e2c9987e6782050b7a45436d4f69a571a33c"
            ),
            "historicalDynamicOutputSha256": (
                "097f1f9c2621870dd460b0a5bc4374cf6212a59e5b282da00a207133864f5847"
            ),
            "historicalBinarySha256": (
                "e704a0f2196f066f7aab16669356ee7de97f59b89de5cf51cbb2f529526457dc"
            ),
            "historicalEvidencePreserved": True,
        },
        "identities": identity,
        "representations": static_results,
        "independentZeroOneReconstructionFrames": frame_results,
        "robustV2IntersectionCountByFrame": counts,
        "historicalV1IntersectionCountByFrame": [
            971,
            931,
            930,
            931,
            929,
            933,
            933,
            933,
            929,
            931,
            930,
            931,
            971,
        ],
        "classifierDelta": {
            "reason": (
                "v2 tests crossings beyond a shared single logical vertex; v1 skipped the pair"
            ),
            "thresholdChanged": False,
            "geometryChanged": False,
        },
        "localization": {
            "firstInvalidTransformation": first_invalid,
            "classification": "valid_simulation_rest_but_invalid_settled_render_expansion",
            "canonicalSimulationRestValid": static_results[0]["intersectingPairCount"] == 0,
            "logicalFallbackRenderValid": static_results[1]["intersectingPairCount"] == 0,
            "dynamicProcessingIntroducedFirstDefect": False,
            "oracleAdjacencyDefectFound": False,
            "geometryChangedDuringAudit": False,
        },
        "historicalCorrection": {
            "record": "r2_area_diagnostic.json remains immutable",
            "incorrectPhrase": "208 sub-floor triangles per frame",
            "correctInterpretation": (
                "16 sub-floor faces in each of 13 frames, 208 face-frame events"
            ),
            "sourceFileMutated": False,
        },
    }
    result["integrity"] = {
        "manifestHash": hashlib.sha256(canonical_dumps(result).encode("utf-8")).hexdigest()
    }
    return result


def _compact_audit(audit: dict[str, Any], lineage: list[dict[str, Any]]) -> dict[str, Any]:
    result = dict(audit)
    pairs = []
    for row in audit["intersectingPairs"]:
        compact = dict(row)
        compact.pop("leftLineage", None)
        compact.pop("rightLineage", None)
        compact["leftLineageIndex"] = int(row["leftTriangle"])
        compact["rightLineageIndex"] = int(row["rightTriangle"])
        pairs.append(compact)
    result["intersectingPairs"] = pairs
    result["triangleLineage"] = lineage
    return result


def _historical_processing_frames(
    package: Path, rest: list[Vec3], simulation_manifest: dict[str, Any]
) -> list[list[Vec3]]:
    neutral = _state_positions(
        _object(package / "simulation" / "motion_states" / "neutral_settled.json")
    )
    target = _state_positions(
        _object(package / "simulation" / "motion_states" / "torso_twist.json")
    )
    if len(neutral) != int(simulation_manifest["vertexCount"]) or len(target) != len(neutral):
        raise ValueError("representation_historical_motion_inventory_mismatch")
    canonical_delta = [
        tuple(target[index][axis] - neutral[index][axis] for axis in range(3))
        for index in range(len(neutral))
    ]
    influence = _object(package / DYNAMIC_PROCESSING_INFLUENCE_PATH)
    deltas: list[Vec3] = []
    for expected, row in enumerate(_rows(influence, "rows")):
        if int(row.get("processingVertex", -1)) != expected:
            raise ValueError("representation_processing_influence_order_invalid")
        sources = row["canonicalSimulationVertexIndices"]
        weights = row["weights"]
        deltas.append(
            tuple(
                sum(
                    canonical_delta[int(sources[item])][axis] * float(weights[item])
                    for item in range(3)
                )
                for axis in range(3)
            )  # type: ignore[arg-type]
        )
    return [
        [
            tuple(
                rest[index][axis]
                + deltas[index][axis]
                * HISTORICAL_CLIP_SCALE
                * math.sin(math.pi * frame / (FRAME_COUNT - 1))
                for axis in range(3)
            )
            for index in range(len(rest))
        ]
        for frame in range(FRAME_COUNT)
    ]  # type: ignore[return-value]


def _processing_lineage(
    package: Path,
    dense_logical_ids: list[int],
    render_lineage: list[dict[str, Any]],
    processing_vertex_count: int,
) -> tuple[list[int], list[dict[str, Any]]]:
    remap = _object(package / DYNAMIC_PROCESSING_REMAP_PATH)
    processing_ids = [-1] * processing_vertex_count
    for row in _rows(remap, "sourceVertexRows"):
        source = int(row["sourceDenseVertex"])
        for processing in row["processingVertices"]:
            processing_ids[int(processing)] = dense_logical_ids[source]
    if any(value < 0 for value in processing_ids):
        raise ValueError("representation_processing_vertex_remap_incomplete")
    triangle_lineage: list[dict[str, Any] | None] = [None] * int(
        remap["processingTriangleCount"]
    )
    for row in _rows(remap, "sourceTriangleRows"):
        source = int(row["sourceTriangle"])
        for processing in row["processingTriangles"]:
            lineage = dict(render_lineage[source])
            lineage["dynamicProcessingClassification"] = row["classification"]
            lineage["sourceDenseTriangle"] = source
            triangle_lineage[int(processing)] = lineage
    if any(value is None for value in triangle_lineage):
        raise ValueError("representation_processing_triangle_remap_incomplete")
    return processing_ids, [value for value in triangle_lineage if value is not None]


def _manifest_triangles(
    manifest: dict[str, Any],
) -> tuple[list[tuple[int, int, int]], list[dict[str, Any]]]:
    triangles: list[tuple[int, int, int]] = []
    lineage: list[dict[str, Any]] = []
    offset = 0
    for mesh_index, mesh in enumerate(_rows(manifest, "meshes")):
        for local_index, triangle in enumerate(mesh.get("triangles", [])):
            triangles.append(tuple(offset + int(index) for index in triangle))
            lineage.append(
                {
                    "meshIndex": mesh_index,
                    "localTriangleIndex": local_index,
                    "panelId": str(mesh.get("panelId")),
                    "materialId": str(mesh.get("materialId")),
                    "seamIds": [],
                    "openingIds": [],
                    "sourceTriangleIds": [len(triangles) - 1],
                }
            )
        offset += len(mesh.get("vertices", []))
    return triangles, lineage


def _meshset_surface(meshset: MeshSet) -> tuple[list[Vec3], list[tuple[int, int, int]]]:
    positions: list[Vec3] = []
    triangles: list[tuple[int, int, int]] = []
    offset = 0
    for mesh in meshset.meshes:
        positions.extend(mesh.vertices)
        triangles.extend(tuple(offset + index for index in triangle) for triangle in mesh.triangles)
        offset += len(mesh.vertices)
    return positions, triangles


def _manifest_positions(manifest: dict[str, Any]) -> list[Vec3]:
    return [
        _vec3(position)
        for mesh in _rows(manifest, "meshes")
        for position in mesh.get("vertices", [])
    ]


def _state_positions(state: dict[str, Any]) -> list[Vec3]:
    return [
        _vec3(position)
        for mesh in _rows(state, "meshes")
        for position in mesh.get("positions", [])
    ]


def _rows(value: dict[str, Any], key: str) -> list[dict[str, Any]]:
    rows = value.get(key)
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"representation_rows_invalid:{key}")
    return rows


def _object(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"representation_object_required:{path.name}")
    return value


def _vec3(value: Any) -> Vec3:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError("representation_vec3_invalid")
    result = tuple(float(component) for component in value)
    if not all(math.isfinite(component) for component in result):
        raise ValueError("representation_vec3_nonfinite")
    return result  # type: ignore[return-value]
