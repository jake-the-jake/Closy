from __future__ import annotations

from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.simulation_topology_v2.temporal_quality import (
    TEMPORAL_DEFORMATION_QUALITY_VERSION,
    audit_temporal_deformation_quality,
)


def _mesh(points: list[tuple[float, float, float]]) -> MeshSet:
    return MeshSet([Mesh("panel", "panel", points, [(0.0, 0.0)] * 3, [(0, 1, 2)])])


def test_temporal_oracle_is_rotation_invariant_and_allows_valid_fold() -> None:
    frames = [
        _mesh([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]),
        _mesh([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)]),
        _mesh([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, -1.0, 0.0)]),
    ]
    transformed = [
        _mesh([(2.0 - y, -1.0 + z, 3.0 + x) for x, y, z in frame.meshes[0].vertices])
        for frame in frames
    ]

    original = audit_temporal_deformation_quality(frames)
    rotated = audit_temporal_deformation_quality(transformed)

    assert original["auditVersion"] == TEMPORAL_DEFORMATION_QUALITY_VERSION
    assert original["status"] == "pass"
    assert rotated["counts"] == original["counts"]


def test_temporal_oracle_rejects_reversal_through_zero_area() -> None:
    frames = [
        _mesh([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]),
        _mesh([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.5, 0.0, 0.0)]),
        _mesh([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, -1.0, 0.0)]),
    ]

    audit = audit_temporal_deformation_quality(frames)

    assert audit["status"] == "fail"
    assert audit["counts"]["degenerateFrameTriangles"] == 1
    assert audit["counts"]["trueInversions"] == 1


def test_temporal_oracle_detects_unsampled_crossing() -> None:
    audit = audit_temporal_deformation_quality(
        [
            _mesh([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]),
            _mesh([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, -1.0, 0.0)]),
        ]
    )

    assert audit["counts"]["degenerateFrameTriangles"] == 0
    assert audit["counts"]["sweptDegenerateTransitions"] == 1
    assert audit["counts"]["trueInversions"] == 1
