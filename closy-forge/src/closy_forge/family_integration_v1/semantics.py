from __future__ import annotations

import math
from typing import Any

from closy_forge.geometry.mesh_model import MeshSet

from .registry import FamilyInputError, family_spec


def validate_semantics(
    family: str,
    parameters: dict[str, float | int],
    pattern: dict[str, Any],
    semantic: dict[str, Any],
) -> None:
    spec = family_spec(family)
    expected = getattr(spec.module("pattern_generator"), spec.pattern_function)(
        spec.parameters(parameters)
    )
    graph = getattr(spec.module("semantic_graph"), spec.semantic_function)(expected)
    if pattern != expected or graph != semantic:
        raise FamilyInputError("semantic_or_pattern_identity_mismatch")


def boundary_metrics(mesh: MeshSet, constraints: dict[str, Any]) -> dict[str, Any]:
    panels = {m.panel_id: m for m in mesh.meshes}

    def point(span: dict[str, Any]) -> tuple[float, float, float]:
        m = panels[str(span["panelId"])]
        a = m.vertices[int(span["vertexIndex"])]
        b = m.vertices[int(span.get("nextVertexIndex", span["vertexIndex"]))]
        w = float(span.get("interpolationWeight", 0))
        return tuple(a[i] * (1 - w) + b[i] * w for i in range(3))  # type: ignore[return-value]

    gaps = [
        math.dist(point(row["spanA"]), point(row["spanB"]))
        for row in constraints["constraints"]
        if row.get("enabled", True)
    ]
    openings = []
    for opening in constraints.get("openings", []):
        length = 0.0
        count = 0
        for edge in opening["boundaryEdges"]:
            vertices = panels[str(edge["panelId"])].vertices
            indices = edge["vertexIndices"]
            length += sum(
                math.dist(vertices[a], vertices[b])
                for a, b in zip(indices, indices[1:], strict=False)
            )
            count += max(0, len(indices) - 1)
        openings.append(
            {
                "id": opening["id"],
                "boundaryLengthM": length,
                "segmentCount": count,
                "noncollapsed": length > 1e-5,
            }
        )
    return {
        "pairedSeamSampleCount": len(gaps),
        "maximumPairedSeamGapM": max(gaps, default=0.0),
        "openings": openings,
        "openingCount": len(openings),
        "allOpeningsNoncollapsed": all(o["noncollapsed"] for o in openings),
        "physicalSeamAcceptance": max(gaps, default=0.0) <= 0.008,
        "openingMetricScope": "sampled_boundary_length_not_full_opening_shape",
    }
