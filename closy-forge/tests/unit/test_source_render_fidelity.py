from __future__ import annotations

from closy_forge.inspection.source_render_fidelity import (
    validate_persisted_source_render_fidelity,
)
from closy_forge.raster import decode_png_rgba, encode_png_rgba
from closy_forge.validation.validator import validate_package
from tests.helpers import build_demo, clone_package, issue_codes, read_json


def test_public_fixture_source_render_fidelity_is_literal_and_tiered(tmp_path) -> None:  # type: ignore[no-untyped-def]
    package = build_demo(tmp_path)
    report = read_json(package / "reports" / "fidelity" / "source_render_fidelity.json")

    assert report["status"] == "pass_d0_public_fixture"
    assert report["acceptanceTiers"]["acceptedForD0PublicFixture"]["accepted"] is True
    assert report["acceptanceTiers"]["acceptedForCanonicalProduction"]["accepted"] is False
    assert all(view["accepted"] for view in report["viewComparisons"])
    assert all(view["renderedForegroundPixels"] > 0 for view in report["viewComparisons"])
    assert all(control["detected"] for control in report["corruptionControls"])
    assert validate_persisted_source_render_fidelity(package, report) == {
        "status": "pass",
        "recomputedViewCount": 4,
        "acceptedForD0PublicFixture": True,
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
