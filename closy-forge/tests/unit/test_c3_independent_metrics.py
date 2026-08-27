from __future__ import annotations

from closy_forge.binding.c3_evidence import _seam_metrics
from closy_forge.binding.c3_metrics import (
    evaluate_independent_surface_agreement,
    unweighted_vertex_centroid,
)
from closy_forge.geometry.mesh_model import Mesh, MeshSet


def test_area_weighted_metric_is_stable_across_biased_retessellation() -> None:
    fallback = _square_mesh("fallback", [(0, 1, 2), (0, 2, 3)])
    dense = Mesh(
        "dense",
        "panel.test",
        [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (2.0, 1.0, 0.0), (0.0, 1.0, 0.0), (0.2, 0.5, 0.0)],
        [(0.0, 0.0)] * 5,
        [(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)],
    )

    report = evaluate_independent_surface_agreement(
        MeshSet([dense]),
        MeshSet([fallback]),
        constraints={},
        binding_contract={"records": []},
    )

    assert unweighted_vertex_centroid(dense) != unweighted_vertex_centroid(fallback)
    assert report["maxAreaWeightedCentroidDeltaMeters"] <= 1e-12
    assert report["maxSampledSurfaceDistanceMeters"] <= 1e-12
    assert report["silhouetteBoundsDeltaNormalised"] == 0.0


def test_surface_metric_detects_symmetric_corruption_hidden_by_vertex_centroid() -> None:
    fallback = Mesh(
        "fallback",
        "panel.test",
        [(-1.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        [(0.0, 0.0)] * 3,
        [(0, 1, 2)],
    )
    corrupt = Mesh(
        "corrupt",
        "panel.test",
        [(-1.5, 0.0, 0.0), (1.5, 0.0, 0.0), (0.0, 1.0, 0.0)],
        [(0.0, 0.0)] * 3,
        [(0, 1, 2)],
    )

    report = evaluate_independent_surface_agreement(
        MeshSet([corrupt]),
        MeshSet([fallback]),
        constraints={},
        binding_contract={"records": []},
    )

    assert unweighted_vertex_centroid(corrupt) == unweighted_vertex_centroid(fallback)
    assert report["maxSampledSurfaceDistanceMeters"] == 0.5
    assert report["maxSemanticLandmarkDeltaMeters"] == 0.5


def test_relative_seam_slip_removes_common_cloth_motion() -> None:
    reference = MeshSet([_seam_pair_mesh(0.0, 0.0)])
    common_motion = MeshSet([_seam_pair_mesh(0.2, 0.2)])
    relative_motion = MeshSet([_seam_pair_mesh(0.2, 0.23)])
    contract = _identity_contract()
    constraints = {
        "constraints": [
            {
                "seamId": "seam.test",
                "spanA": {
                    "meshIndex": 0,
                    "panelId": "panel.test",
                    "vertexIndex": 0,
                    "nextVertexIndex": 1,
                },
                "spanB": {
                    "meshIndex": 0,
                    "panelId": "panel.test",
                    "vertexIndex": 2,
                    "nextVertexIndex": 3,
                },
            }
        ]
    }

    shared = _seam_metrics(
        common_motion,
        reference,
        common_motion.meshes[0].vertices,
        common_motion,
        contract,
        constraints,
    )
    relative = _seam_metrics(
        relative_motion,
        reference,
        relative_motion.meshes[0].vertices,
        relative_motion,
        contract,
        constraints,
    )

    assert shared["maxTangentialSlidingMeters"] == 0.0
    assert shared["maxLegacyAbsoluteMidpointTravelMeters"] == 0.2
    assert relative["maxTangentialSlidingMeters"] == 0.03


def _square_mesh(name: str, triangles: list[tuple[int, int, int]]) -> Mesh:
    return Mesh(
        name,
        "panel.test",
        [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (2.0, 1.0, 0.0), (0.0, 1.0, 0.0)],
        [(0.0, 0.0)] * 4,
        triangles,
    )


def _seam_pair_mesh(left_shift: float, right_shift: float) -> Mesh:
    return Mesh(
        "seam",
        "panel.test",
        [
            (left_shift, 0.0, 0.0),
            (1.0 + left_shift, 0.0, 0.0),
            (right_shift, 0.1, 0.0),
            (1.0 + right_shift, 0.1, 0.0),
        ],
        [(0.0, 0.0)] * 4,
        [(0, 1, 2), (1, 3, 2)],
    )


def _identity_contract() -> dict[str, object]:
    records = []
    for index in range(4):
        records.append(
            {
                "globalRenderVertexIndex": index,
                "sourceTriangle": {"globalVertexIndices": [index, index, index]},
                "binding": {"weights": [1.0, 0.0, 0.0]},
            }
        )
    return {"records": records}
