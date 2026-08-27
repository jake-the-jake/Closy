from __future__ import annotations

from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.inspection import project_mesh_signature
from closy_forge.inspection.deterministic_renderer import required_artifact_specs
from closy_forge.validation.validator import validate_package
from tests.helpers import build_demo, clone_package, issue_codes, read_json, write_json


def test_demo_package_contains_deterministic_inspection_artifacts(tmp_path) -> None:  # type: ignore[no-untyped-def]
    package = build_demo(tmp_path)
    manifest = read_json(package / "reports" / "inspection" / "manifest.json")
    report = read_json(package / "reports" / "inspection" / "inspection_report.json")

    expected_ids = {str(spec["artifactId"]) for spec in required_artifact_specs()}
    artifacts = manifest["artifacts"]

    assert manifest["artifactCount"] == 12
    assert {artifact["artifactId"] for artifact in artifacts} == expected_ids
    assert report["readiness"]["topologyRepresentationInspectionRun"] is True
    assert report["readiness"]["canonicalSimulationToRenderSilhouetteRun"] is True
    assert report["readiness"]["providerGeometryAppearanceComparisonRun"] is False
    assert report["readiness"]["sourceImageSilhouetteComparisonRun"] is True
    assert report["readiness"]["sourceImageAppearanceComparisonRun"] is True
    assert report["readiness"]["humanVisualReviewRun"] is False
    assert report["readiness"]["acceptedForD0PublicFixture"] is False
    assert report["readiness"]["acceptedForVisualFidelity"] is False
    assert report["readiness"]["acceptedForCleanProposal"] is False
    assert (
        "clean_candidate_artifact_omitted_because_no_clean_candidate_exists"
        in report["limitations"]
    )

    pattern_artifact = next(
        artifact for artifact in artifacts if artifact["artifactId"] == "pattern_panels_labels"
    )
    assert "panel.sleeve.left" in pattern_artifact["semanticIdsIncluded"]
    assert "panel.sleeve.right" in pattern_artifact["semanticIdsIncluded"]
    assert "opening.neck" in pattern_artifact["semanticIdsIncluded"]
    assert "opening.hem" in pattern_artifact["semanticIdsIncluded"]
    for artifact in artifacts:
        artifact_path = package / artifact["path"]
        assert artifact_path.exists()
        assert artifact_path.read_text(encoding="utf-8").startswith("<?xml")


def test_inspection_artifacts_are_byte_identical_across_rebuilds(tmp_path) -> None:  # type: ignore[no-untyped-def]
    left = build_demo(tmp_path, "left.closygarment")
    right = build_demo(tmp_path, "right.closygarment")

    left_manifest = read_json(left / "reports" / "inspection" / "manifest.json")
    right_manifest = read_json(right / "reports" / "inspection" / "manifest.json")

    assert left_manifest["integrity"] == right_manifest["integrity"]
    for left_artifact, right_artifact in zip(
        left_manifest["artifacts"], right_manifest["artifacts"], strict=True
    ):
        assert left_artifact["artifactId"] == right_artifact["artifactId"]
        assert left_artifact["contentHash"] == right_artifact["contentHash"]


def test_front_projection_signature_does_not_hide_wrong_depth_in_side_view() -> None:
    flat = _single_triangle(z_offset=0.0)
    deep = _single_triangle(z_offset=0.4)

    assert project_mesh_signature(flat, "front") == project_mesh_signature(deep, "front")
    assert project_mesh_signature(flat, "side") != project_mesh_signature(deep, "side")
    assert project_mesh_signature(flat, "three_quarter") != project_mesh_signature(
        deep, "three_quarter"
    )


def test_swapped_inspection_view_metadata_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_inspection_view.closygarment")
    manifest = read_json(corrupt / "reports" / "inspection" / "manifest.json")
    manifest["artifacts"][0]["camera"]["viewId"] = "side"
    write_json(corrupt / "reports" / "inspection" / "manifest.json", manifest)

    codes = issue_codes(validate_package(corrupt))

    assert "inspection_manifest_hash_mismatch" in codes
    assert "inspection_artifact_metadata_mismatch" in codes


def test_changed_source_geometry_invalidates_inspection_source_hashes(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_inspection_source.closygarment")
    pattern = read_json(corrupt / "pattern" / "pattern.json")
    pattern["panels"][0]["id"] = "panel.front.changed"
    write_json(corrupt / "pattern" / "pattern.json", pattern)

    codes = issue_codes(validate_package(corrupt))

    assert "file_hash_mismatch" in codes
    assert {"inspection_source_hash_mismatch", "inspection_report_source_hash_mismatch"} <= codes


def _single_triangle(*, z_offset: float) -> MeshSet:
    return MeshSet(
        [
            Mesh(
                name="single_triangle",
                panel_id="panel.test",
                vertices=[
                    (0.0, 0.0, z_offset),
                    (1.0, 0.0, z_offset),
                    (0.0, 1.0, z_offset),
                ],
                panel_uvs=[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)],
                triangles=[(0, 1, 2)],
            )
        ]
    )
