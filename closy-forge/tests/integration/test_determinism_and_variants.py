from __future__ import annotations

from pathlib import Path

from closy_forge.garments.tshirt.parameters import PARAMETER_VARIANTS
from closy_forge.package_io.hashing import sha256_file
from closy_forge.pipeline.build_tshirt_demo import build_demo_tshirt_package
from closy_forge.validation.validator import validate_package
from tests.helpers import read_json


def _file_hashes(package: Path) -> dict[str, str]:
    return {
        path.relative_to(package).as_posix(): sha256_file(path)
        for path in sorted(package.rglob("*"))
        if path.is_file()
    }


def test_repeated_builds_are_byte_identical(tmp_path) -> None:  # type: ignore[no-untyped-def]
    first = tmp_path / "a" / "demo_tshirt.closygarment"
    second = tmp_path / "b" / "demo_tshirt.closygarment"
    build_demo_tshirt_package(first)
    build_demo_tshirt_package(second)
    assert _file_hashes(first) == _file_hashes(second)
    assert (
        read_json(first / "manifest.json")["canonicalPackageDigest"]
        == read_json(second / "manifest.json")["canonicalPackageDigest"]
    )


def test_bounded_tshirt_variants_validate_and_keep_stable_semantics(tmp_path) -> None:  # type: ignore[no-untyped-def]
    seam_sets = []
    body_lengths = []
    source_acceptance = {}
    fit_acceptance = {}
    for name, params in PARAMETER_VARIANTS.items():
        package = tmp_path / f"{name}.closygarment"
        build_demo_tshirt_package(package, params=params)
        assert validate_package(package)["status"] == "passed"
        pattern = read_json(package / "pattern" / "pattern.json")
        seam_sets.append(tuple(seam["id"] for seam in pattern["seams"]))
        body_lengths.append(pattern["parameters"]["garment_body_length"])
        manifest = read_json(package / "manifest.json")
        fit = read_json(package / "fitting" / "tshirt_fit.json")
        source_acceptance[name] = manifest["capabilities"]["acceptedForD0PublicFixture"]
        fit_acceptance[name] = fit["accepted"]
    assert len(set(seam_sets)) == 1
    assert len(set(body_lengths)) == len(PARAMETER_VARIANTS)
    assert source_acceptance == {"boxy": False, "default": False, "long_slim": False}
    assert fit_acceptance == {"boxy": False, "default": False, "long_slim": False}
