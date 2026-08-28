from __future__ import annotations

from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.simulation.deformation_quality import audit_rest_referenced_deformation


def _mesh(points: list[tuple[float, float, float]]) -> MeshSet:
    return MeshSet(
        [
            Mesh(
                "fixture.triangle",
                "panel.fixture",
                points,
                [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)],
                [(0, 1, 2)],
            )
        ]
    )


def test_orientation_flip_is_detected_even_when_area_magnitude_is_unchanged() -> None:
    rest = _mesh([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)])
    flipped = _mesh([(0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)])

    audit = audit_rest_referenced_deformation(rest, flipped)

    assert audit["minimumAreaRatio"] == 1.0
    assert audit["maximumAreaRatio"] == 1.0
    assert audit["counts"]["degenerate"] == 0
    assert audit["counts"]["inverted"] == 1
    assert audit["counts"]["normalFlipped"] == 1
    assert audit["status"] == "fail"


def test_degenerate_and_excessive_area_strain_are_reported_separately() -> None:
    rest = _mesh([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)])
    collapsed = _mesh([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.5, 0.0, 0.0)])
    stretched = _mesh([(0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.0, 2.0, 0.0)])

    collapsed_audit = audit_rest_referenced_deformation(rest, collapsed)
    stretched_audit = audit_rest_referenced_deformation(rest, stretched)

    assert collapsed_audit["counts"]["degenerate"] == 1
    assert collapsed_audit["counts"]["inverted"] == 0
    assert stretched_audit["counts"]["degenerate"] == 0
    assert stretched_audit["counts"]["excessiveAreaStrain"] == 1
