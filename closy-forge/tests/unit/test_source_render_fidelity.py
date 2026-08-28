from __future__ import annotations

from dataclasses import replace

import pytest

from closy_forge.geometry.glb_io import read_glb_meshset, write_glb
from closy_forge.geometry.mesh_model import MeshSet
from closy_forge.inspection.source_render_fidelity import (
    hash_source_render_fidelity_report,
    validate_persisted_source_render_fidelity,
)
from closy_forge.package_io.hashing import geometry_content_hash, sha256_file
from closy_forge.raster import decode_png_rgba, encode_png_rgba
from closy_forge.validation.validator import validate_package
from tests.helpers import build_demo, clone_package, issue_codes, read_json


def test_public_fixture_source_render_fidelity_is_literal_and_tiered(tmp_path) -> None:  # type: ignore[no-untyped-def]
    package = build_demo(tmp_path)
    report = read_json(package / "reports" / "fidelity" / "source_render_fidelity.json")

    public_accepted = report["acceptanceTiers"]["acceptedForD0PublicFixture"]["accepted"]
    assert report["status"] == (
        "pass_d0_public_fixture" if public_accepted else "fail_d0_public_fixture"
    )
    assert report["acceptanceTiers"]["acceptedForCanonicalProduction"]["accepted"] is False
    assert all(view["renderedForegroundPixels"] > 0 for view in report["viewComparisons"])
    assert all(control["detected"] for control in report["corruptionControls"])
    assert validate_persisted_source_render_fidelity(package, report) == {
        "status": "pass",
        "recomputedViewCount": 4,
        "acceptedForD0PublicFixture": public_accepted,
    }


def test_fidelity_validator_rejects_changed_decoded_render(tmp_path) -> None:  # type: ignore[no-untyped-def]
    package = build_demo(tmp_path)
    corrupt = clone_package(package, tmp_path / "bad_fidelity.closygarment")
    path = corrupt / "reports" / "fidelity" / "rendered_front.png"
    decoded = decode_png_rgba(path.read_bytes())
    pixels = bytearray(decoded.rgba)
    pixels[0:4] = bytes((255, 0, 0, 255))
    path.write_bytes(encode_png_rgba(decoded.width, decoded.height, bytes(pixels)))

    assert "source_render_fidelity_validation_failed" in issue_codes(validate_package(corrupt))


def test_fidelity_validator_rerenders_after_camera_corruption(tmp_path) -> None:  # type: ignore[no-untyped-def]
    package = build_demo(tmp_path)
    report_path = package / "reports" / "fidelity" / "source_render_fidelity.json"
    report = read_json(report_path)
    report["viewComparisons"][0]["camera"]["azimuthDegrees"] = 17.0
    _rehash(report)

    with pytest.raises(ValueError, match="independent_rerender_mismatch"):
        validate_persisted_source_render_fidelity(package, report)


def test_fidelity_validator_rerenders_after_atlas_corruption(tmp_path) -> None:  # type: ignore[no-untyped-def]
    package = build_demo(tmp_path)
    report_path = package / "reports" / "fidelity" / "source_render_fidelity.json"
    report = read_json(report_path)
    atlas_path = package / report["sourceSettledMesh"]["baseColorAtlasPath"]
    atlas = decode_png_rgba(atlas_path.read_bytes())
    pixels = bytearray(atlas.rgba)
    for offset in range(0, len(pixels), 4):
        if pixels[offset + 3] > 0:
            pixels[offset] = (pixels[offset] + 71) % 256
    atlas_path.write_bytes(encode_png_rgba(atlas.width, atlas.height, bytes(pixels)))
    report["sourceSettledMesh"]["baseColorAtlasSha256"] = sha256_file(atlas_path)
    _rehash(report)

    with pytest.raises(ValueError, match="independent_rerender_mismatch"):
        validate_persisted_source_render_fidelity(package, report)


def test_fidelity_validator_rerenders_after_mesh_uv_corruption(tmp_path) -> None:  # type: ignore[no-untyped-def]
    package = build_demo(tmp_path)
    report_path = package / "reports" / "fidelity" / "source_render_fidelity.json"
    report = read_json(report_path)
    mesh_path = package / report["sourceSettledMesh"]["path"]
    meshset = read_glb_meshset(mesh_path)
    first = meshset.meshes[0]
    shifted_uvs = [((uv[0] + 0.31) % 1.0, uv[1]) for uv in first.panel_uvs]
    changed = MeshSet([replace(first, panel_uvs=shifted_uvs), *meshset.meshes[1:]])
    write_glb(mesh_path, changed, "corruption_fixture", (0.2, 0.3, 0.8, 1.0))
    reread = read_glb_meshset(mesh_path)
    report["sourceSettledMesh"]["contentHash"] = geometry_content_hash(reread)
    _rehash(report)

    with pytest.raises(ValueError, match="independent_rerender_mismatch"):
        validate_persisted_source_render_fidelity(package, report)


def _rehash(report: dict[str, object]) -> None:
    integrity = report["integrity"]
    assert isinstance(integrity, dict)
    integrity["sourceRenderFidelityHash"] = hash_source_render_fidelity_report(report)
