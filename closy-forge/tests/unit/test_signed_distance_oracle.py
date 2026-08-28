from __future__ import annotations

from closy_forge.avatar.reference_avatar import build_collision_mesh
from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.geometry.signed_distance import audit_body_signed_clearance


def _audit(points: list[tuple[float, float, float]], body: MeshSet) -> dict[str, object]:
    return audit_body_signed_clearance(
        points,
        body,
        cloth_half_thickness_meters=0.0008,
        skin_margin_meters=0.0,
        oracle_uncertainty_meters=0.000001,
        promotion_guard_band_meters=0.000005,
    )


def test_reference_collision_surface_is_qualified_after_geometric_canonicalization() -> None:
    audit = _audit([(0.5, 1.15, 0.0)], build_collision_mesh())
    topology = audit["surfaceTopology"]

    assert topology["sourceDegenerateTriangleCount"] == 60
    assert topology["queryTriangleCount"] == 280
    assert topology["watertightAfterCanonicalWeld"] is True
    assert topology["windingConsistentAfterCanonicalWeld"] is True
    assert topology["querySurfaceQualified"] is True
    assert audit["knownFixtureAudit"]["status"] == "pass"
    assert audit["worstWitness"]["signDecision"] == "outside"
    assert audit["worstWitness"]["closestBodyTriangleId"]


def test_inside_outside_and_near_surface_queries_fail_closed_as_declared() -> None:
    audit = _audit(
        [
            (0.0, 1.15, 0.0),
            (0.6, 1.15, 0.0),
            (0.27, 1.15, 0.0),
        ],
        build_collision_mesh(),
    )

    assert audit["oracleUncertainCount"] >= 1
    assert audit["promotionEligible"] is False
    assert audit["worstWitness"]["garmentPointId"] == "vertex.0"
    assert audit["worstWitness"]["signDecision"] == "inside"
    assert audit["worstWitness"]["independentGeneralizedWinding"]["agreesWithRayParity"] is True


def test_non_watertight_surface_cannot_be_promoted() -> None:
    cube = Mesh(
        "open_cube",
        "collision.open_cube",
        [
            (-1.0, -1.0, -1.0),
            (1.0, -1.0, -1.0),
            (1.0, 1.0, -1.0),
            (-1.0, 1.0, -1.0),
            (-1.0, -1.0, 1.0),
            (1.0, -1.0, 1.0),
            (1.0, 1.0, 1.0),
            (-1.0, 1.0, 1.0),
        ],
        [(0.0, 0.0)] * 8,
        [
            (0, 2, 1),
            (0, 3, 2),
            (0, 1, 5),
            (0, 5, 4),
            (1, 2, 6),
            (1, 6, 5),
            (2, 3, 7),
            (2, 7, 6),
            (3, 0, 4),
            (3, 4, 7),
        ],
    )

    audit = _audit([(0.0, 0.0, 0.0)], MeshSet([cube]))

    assert audit["surfaceTopology"]["boundaryEdgeCount"] == 4
    assert audit["surfaceTopology"]["querySurfaceQualified"] is False
    assert audit["oracleUncertainCount"] == 1
    assert audit["promotionEligible"] is False
