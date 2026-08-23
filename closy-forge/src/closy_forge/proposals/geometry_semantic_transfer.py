from __future__ import annotations

from collections import Counter
from copy import deepcopy
from math import dist, sqrt
from pathlib import Path
from typing import Any

from closy_forge.geometry.curves import sample_curve
from closy_forge.geometry.glb_io import read_glb_meshset
from closy_forge.geometry.mesh_model import Mesh, MeshSet, Vec2
from closy_forge.geometry.topology_diagnostics import meshset_topology_diagnostics
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes, sha256_file

GEOMETRY_SEMANTIC_TRANSFER_VERSION = (
    "closy.geometry_semantic_transfer.panel_boundary_classification.v1"
)

_BOUNDARY_CLASSIFICATION_TOLERANCE_METERS = 0.012


def build_geometry_semantic_transfer_report(
    *,
    garment_id: str,
    garment_class: str,
    semantic_graph: dict[str, Any],
    pattern: dict[str, Any],
    cleanup_result_report: dict[str, Any],
    cleanup_asset_path: Path,
) -> dict[str, Any]:
    """Transfer stable panel IDs and classify cleanup-preview boundaries.

    This is deliberately a semantic evidence report, not a clean geometry
    proposal. It proves panel-space correspondence survived safe cleanup while
    leaving repair, retopology, simulation binding and canonical acceptance to
    later gates.
    """

    meshset = read_glb_meshset(cleanup_asset_path)
    topology = meshset_topology_diagnostics(meshset)
    panel_transfers = _panel_transfers(meshset, semantic_graph, pattern, topology)
    boundary_classifications = _boundary_classifications(meshset, pattern)
    aggregate = _aggregate(panel_transfers, boundary_classifications, semantic_graph, topology)
    semantic_transfer_run = (
        aggregate["missingPanelCount"] == 0
        and aggregate["unexpectedPanelCount"] == 0
        and aggregate["unclassifiedBoundaryEdgeCount"] == 0
    )
    blocking_reasons = [
        "simulation_binding_missing",
        "canonical_acceptance_gate_not_run",
    ]
    if aggregate["ambiguousBoundaryEdgeCount"] > 0:
        blocking_reasons.append("multi_seam_boundary_spans_require_split_before_binding")
    if topology["componentCount"] > 1:
        blocking_reasons.append("component_stitching_or_binding_pending")

    report: dict[str, Any] = {
        "schemaVersion": 1,
        "reportId": "semantic_transfer.cleanup_preview_tshirt_visual_geometry_v1",
        "stageVersion": GEOMETRY_SEMANTIC_TRANSFER_VERSION,
        "garmentId": garment_id,
        "garmentClass": garment_class,
        "sourceGeometryCleanupResultId": cleanup_result_report["reportId"],
        "sourceGeometryCleanupResultHash": cleanup_result_report["integrity"][
            "geometryCleanupResultHash"
        ],
        "sourceSemanticGraphHash": _hash_json(semantic_graph),
        "sourcePatternHash": _hash_json(pattern),
        "inputAsset": {
            "path": cleanup_result_report["outputAsset"]["path"],
            "sourceAssetHash": sha256_file(cleanup_asset_path),
            "byteSize": cleanup_asset_path.stat().st_size,
            "purpose": cleanup_result_report["outputAsset"]["purpose"],
            "canonicalUseAllowed": False,
        },
        "topologySnapshot": _topology_snapshot(topology),
        "panelTransfers": panel_transfers,
        "boundaryClassifications": boundary_classifications,
        "aggregate": aggregate,
        "execution": {
            "semanticTransferRun": semantic_transfer_run,
            "panelIdTransferRun": True,
            "boundaryClassificationRun": True,
            "repairRun": False,
            "retopologyRun": False,
            "simulationBindingRun": False,
            "uvTransferRun": False,
            "materialTransferRun": False,
        },
        "readiness": {
            "status": "semantic_transfer_completed_binding_pending"
            if semantic_transfer_run
            else "semantic_transfer_partial",
            "acceptedForCleanProposal": False,
            "acceptedForCanonical": False,
            "acceptedForSimulation": False,
            "acceptedForRuntimeRender": False,
            "nextExecutableStage": "simulation_binding_for_cleanup_preview",
            "blockingReasons": blocking_reasons,
        },
        "quality": {
            "status": "partial_pass" if semantic_transfer_run else "warn",
            "transferredPanelCount": aggregate["transferredPanelCount"],
            "expectedPanelCount": aggregate["expectedPanelCount"],
            "classifiedBoundaryEdgeCount": aggregate["classifiedBoundaryEdgeCount"],
            "boundaryEdgeCount": aggregate["boundaryEdgeCount"],
            "classificationCompleteness": aggregate["classificationCompleteness"],
            "acceptedForCleanProposal": False,
            "warnings": [
                "semantic_transfer_visual_only_not_canonical",
                "simulation_binding_not_generated",
            ],
        },
        "policy": {
            "allowExternalApis": False,
            "allowTrainingUse": False,
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "approvedDomain": "avatar_and_garment_only",
        },
        "integrity": {"geometrySemanticTransferHash": ""},
    }
    report["integrity"]["geometrySemanticTransferHash"] = hash_geometry_semantic_transfer_report(
        report
    )
    return report


def hash_geometry_semantic_transfer_report(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["geometrySemanticTransferHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _panel_transfers(
    meshset: MeshSet,
    semantic_graph: dict[str, Any],
    pattern: dict[str, Any],
    topology: dict[str, Any],
) -> list[dict[str, Any]]:
    semantic_roles = {
        str(panel_id): str(role)
        for panel_id, role in semantic_graph.get("panelMapping", {}).items()
    }
    pattern_panels = {str(panel["id"]): panel for panel in pattern.get("panels", [])}
    component_by_panel = {
        str(panel_id): str(component["id"])
        for component in semantic_graph.get("components", [])
        for panel_id in component.get("panels", [])
    }
    topology_by_panel = {
        str(mesh_report["panelId"]): mesh_report for mesh_report in topology.get("meshes", [])
    }
    transfers: list[dict[str, Any]] = []
    for mesh in sorted(meshset.meshes, key=lambda item: (item.panel_id, item.name)):
        panel_id = mesh.panel_id
        mesh_topology = topology_by_panel.get(panel_id, {})
        stable = panel_id in pattern_panels and panel_id in semantic_roles
        transfers.append(
            {
                "meshName": mesh.name,
                "panelId": panel_id,
                "semanticRole": semantic_roles.get(panel_id),
                "componentId": component_by_panel.get(panel_id),
                "vertexCount": len(mesh.vertices),
                "triangleCount": len(mesh.triangles),
                "boundaryEdgeCount": mesh_topology.get("boundaryEdgeCount", 0),
                "transferStatus": "stable_panel_id_transferred"
                if stable
                else "missing_canonical_panel_mapping",
            }
        )
    return transfers


def _boundary_classifications(meshset: MeshSet, pattern: dict[str, Any]) -> list[dict[str, Any]]:
    pattern_edges = _pattern_edges(pattern)
    semantic_by_edge = _semantic_boundary_maps(pattern)
    classifications: list[dict[str, Any]] = []
    for mesh in sorted(meshset.meshes, key=lambda item: (item.panel_id, item.name)):
        grouped: dict[str, dict[str, Any]] = {}
        for left, right in _boundary_edges(mesh):
            edge_id, distance_to_edge = _nearest_pattern_edge(
                mesh.panel_uvs[left],
                mesh.panel_uvs[right],
                pattern_edges.get(mesh.panel_id, []),
            )
            if edge_id is None:
                group_key = "unclassified"
                semantic_kind = "unclassified"
                semantic_ids: list[str] = []
                ambiguous = False
            else:
                opening_ids = semantic_by_edge["openings"].get(edge_id, [])
                seam_ids = semantic_by_edge["seams"].get(edge_id, [])
                if opening_ids:
                    group_key = f"{edge_id}:opening"
                    semantic_kind = "opening"
                    semantic_ids = opening_ids
                    ambiguous = False
                elif seam_ids:
                    group_key = f"{edge_id}:seam"
                    semantic_kind = "seam"
                    semantic_ids = seam_ids
                    ambiguous = len(seam_ids) > 1
                else:
                    group_key = f"{edge_id}:free_pattern_boundary"
                    semantic_kind = "free_pattern_boundary"
                    semantic_ids = []
                    ambiguous = False
            record = grouped.setdefault(
                group_key,
                {
                    "panelId": mesh.panel_id,
                    "edgeId": edge_id,
                    "boundaryKind": semantic_kind,
                    "semanticIds": semantic_ids,
                    "boundaryEdgeCount": 0,
                    "maxDistanceToPatternEdgeMeters": 0.0,
                    "ambiguous": ambiguous,
                    "status": "classified"
                    if semantic_kind != "unclassified" and not ambiguous
                    else (
                        "classified_multi_seam_span"
                        if ambiguous
                        else (
                            "classified_free_pattern_boundary"
                            if semantic_kind == "free_pattern_boundary"
                            else "unclassified_boundary"
                        )
                    ),
                },
            )
            record["boundaryEdgeCount"] += 1
            record["maxDistanceToPatternEdgeMeters"] = max(
                float(record["maxDistanceToPatternEdgeMeters"]),
                round(distance_to_edge, 9),
            )
        classifications.extend(
            sorted(
                grouped.values(),
                key=lambda item: (
                    str(item["panelId"]),
                    "" if item["edgeId"] is None else str(item["edgeId"]),
                    str(item["boundaryKind"]),
                ),
            )
        )
    return classifications


def _aggregate(
    panel_transfers: list[dict[str, Any]],
    boundary_classifications: list[dict[str, Any]],
    semantic_graph: dict[str, Any],
    topology: dict[str, Any],
) -> dict[str, Any]:
    expected_panels = sorted(str(panel_id) for panel_id in semantic_graph["requiredIds"]["panels"])
    transferred_panels = sorted(
        str(transfer["panelId"])
        for transfer in panel_transfers
        if transfer["transferStatus"] == "stable_panel_id_transferred"
    )
    boundary_kind_counts: Counter[str] = Counter()
    classified_edges = 0
    ambiguous_edges = 0
    unclassified_edges = 0
    max_distance = 0.0
    for classification in boundary_classifications:
        count = int(classification["boundaryEdgeCount"])
        kind = str(classification["boundaryKind"])
        boundary_kind_counts[kind] += count
        max_distance = max(max_distance, float(classification["maxDistanceToPatternEdgeMeters"]))
        if kind == "unclassified":
            unclassified_edges += count
        else:
            classified_edges += count
        if classification["ambiguous"]:
            ambiguous_edges += count
    total_edges = int(topology["boundaryEdgeCount"])
    return {
        "expectedPanelCount": len(expected_panels),
        "transferredPanelCount": len(set(transferred_panels)),
        "missingPanelCount": len(set(expected_panels) - set(transferred_panels)),
        "unexpectedPanelCount": len(set(transferred_panels) - set(expected_panels)),
        "missingPanelIds": sorted(set(expected_panels) - set(transferred_panels)),
        "unexpectedPanelIds": sorted(set(transferred_panels) - set(expected_panels)),
        "boundaryEdgeCount": total_edges,
        "classifiedBoundaryEdgeCount": classified_edges,
        "unclassifiedBoundaryEdgeCount": unclassified_edges,
        "ambiguousBoundaryEdgeCount": ambiguous_edges,
        "openingBoundaryEdgeCount": int(boundary_kind_counts["opening"]),
        "seamBoundaryEdgeCount": int(boundary_kind_counts["seam"]),
        "classificationCompleteness": round(classified_edges / total_edges, 6)
        if total_edges
        else 1.0,
        "maxBoundaryDistanceToPatternMeters": round(max_distance, 9),
    }


def _boundary_edges(mesh: Mesh) -> list[tuple[int, int]]:
    edge_counts: Counter[tuple[int, int]] = Counter()
    for tri in mesh.triangles:
        for left, right in [(tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])]:
            edge = (left, right) if left <= right else (right, left)
            edge_counts[edge] += 1
    return sorted(edge for edge, count in edge_counts.items() if count == 1)


def _pattern_edges(pattern: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    edge_lookup: dict[str, list[dict[str, Any]]] = {}
    for panel in pattern.get("panels", []):
        panel_id = str(panel["id"])
        edge_lookup[panel_id] = [
            {
                "edgeId": str(edge["id"]),
                "samples": sample_curve(edge["curve"], int(edge["sampleCount"])),
            }
            for edge in panel.get("boundary", [])
        ]
    return edge_lookup


def _semantic_boundary_maps(pattern: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
    opening_by_edge: dict[str, list[str]] = {}
    for opening in pattern.get("openings", []):
        opening_id = str(opening["id"])
        for edge_id in opening.get("boundaryEdges", []):
            opening_by_edge.setdefault(str(edge_id), []).append(opening_id)
    seam_by_edge: dict[str, list[str]] = {}
    for seam in pattern.get("seams", []):
        seam_id = str(seam["id"])
        for span in seam.get("spans", []):
            seam_by_edge.setdefault(str(span["edgeId"]), []).append(seam_id)
    return {
        "openings": {key: sorted(values) for key, values in opening_by_edge.items()},
        "seams": {key: sorted(values) for key, values in seam_by_edge.items()},
    }


def _nearest_pattern_edge(
    uv_a: Vec2, uv_b: Vec2, candidates: list[dict[str, Any]]
) -> tuple[str | None, float]:
    midpoint = ((uv_a[0] + uv_b[0]) * 0.5, (uv_a[1] + uv_b[1]) * 0.5)
    best_edge_id: str | None = None
    best_distance = float("inf")
    for candidate in candidates:
        samples = candidate["samples"]
        distance_to_edge = max(
            _distance_to_polyline(uv_a, samples),
            _distance_to_polyline(uv_b, samples),
            _distance_to_polyline(midpoint, samples),
        )
        if distance_to_edge < best_distance:
            best_distance = distance_to_edge
            best_edge_id = str(candidate["edgeId"])
    if best_distance > _BOUNDARY_CLASSIFICATION_TOLERANCE_METERS:
        return None, best_distance
    return best_edge_id, best_distance


def _distance_to_polyline(point: Vec2, samples: list[Vec2]) -> float:
    if len(samples) < 2:
        return float("inf")
    return min(
        _distance_to_segment(point, left, right)
        for left, right in zip(samples, samples[1:], strict=False)
    )


def _distance_to_segment(point: Vec2, left: Vec2, right: Vec2) -> float:
    vx = right[0] - left[0]
    vy = right[1] - left[1]
    length2 = vx * vx + vy * vy
    if length2 <= 1e-18:
        return dist(point, left)
    t = max(0.0, min(1.0, ((point[0] - left[0]) * vx + (point[1] - left[1]) * vy) / length2))
    projected = (left[0] + t * vx, left[1] + t * vy)
    return sqrt((point[0] - projected[0]) ** 2 + (point[1] - projected[1]) ** 2)


def _topology_snapshot(topology: dict[str, Any]) -> dict[str, Any]:
    return {
        "meshCount": topology["meshCount"],
        "vertexCount": topology["vertexCount"],
        "triangleCount": topology["triangleCount"],
        "componentCount": topology["componentCount"],
        "boundaryEdgeCount": topology["boundaryEdgeCount"],
        "nonManifoldEdgeCount": topology["nonManifoldEdgeCount"],
        "degenerateTriangleCount": topology["degenerateTriangleCount"],
        "duplicatePositionCount": topology["duplicatePositionCount"],
        "manifoldStatus": topology["manifoldStatus"],
    }


def _hash_json(payload: dict[str, Any]) -> str:
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
