from __future__ import annotations

import struct
from copy import deepcopy

from closy_forge.binding.binary_format import HEADER_SIZE
from closy_forge.validation.validator import validate_package
from tests.helpers import (
    build_layered_asymmetric,
    clone_package,
    issue_codes,
    read_json,
    write_json,
)


def test_layered_asymmetric_wrong_family_is_rejected_by_family_validator(tmp_path) -> None:
    package = build_layered_asymmetric(tmp_path)
    corrupt = clone_package(package, tmp_path / "wrong_family.closygarment")
    manifest = read_json(corrupt / "manifest.json")
    manifest["garmentClass"] = "tshirt"
    write_json(corrupt / "manifest.json", manifest)

    report = validate_package(corrupt)

    assert report["status"] == "failed"
    assert "layered_asymmetric_family_mismatch" in issue_codes(report)


def test_layered_asymmetric_wrong_semantic_id_is_rejected_even_with_matching_local_lists(
    tmp_path,
) -> None:
    package = build_layered_asymmetric(tmp_path)
    corrupt = clone_package(package, tmp_path / "wrong_semantic.closygarment")
    semantic = read_json(corrupt / "semantic/garment_graph.json")
    semantic["requiredIds"]["openings"][0] = "opening.layered_asymmetric.cuff.left"
    write_json(corrupt / "semantic/garment_graph.json", semantic)

    codes = issue_codes(validate_package(corrupt))

    assert "layered_asymmetric_semantic_ids_invalid" in codes
    assert "layered_asymmetric_false_sleeve_semantics" in codes


def test_layered_asymmetric_motion_claim_cannot_be_promoted_by_refreshing_its_hash(
    tmp_path,
) -> None:
    package = build_layered_asymmetric(tmp_path)
    corrupt = clone_package(package, tmp_path / "fake_motion.closygarment")
    motion = read_json(corrupt / "reports/material_motion_suite.json")
    motion["underarmStress"]["accepted"] = False
    payload = deepcopy(motion)
    payload["integrity"]["suiteHash"] = ""
    from closy_forge.package_io.canonical_json import canonical_dumps
    from closy_forge.package_io.hashing import sha256_bytes

    motion["integrity"]["suiteHash"] = sha256_bytes(canonical_dumps(payload).encode("utf-8"))
    write_json(corrupt / "reports/material_motion_suite.json", motion)

    assert "layered_asymmetric_motion_suite_invalid" in issue_codes(validate_package(corrupt))


def test_layered_asymmetric_missing_outer_layer_is_rejected(tmp_path) -> None:
    package = build_layered_asymmetric(tmp_path)
    corrupt = clone_package(package, tmp_path / "missing_outer.closygarment")
    semantic = read_json(corrupt / "semantic/garment_graph.json")
    semantic["components"] = semantic["components"][:1]
    write_json(corrupt / "semantic/garment_graph.json", semantic)

    assert "layered_asymmetric_layer_contract_invalid" in issue_codes(validate_package(corrupt))


def test_layered_asymmetric_reversed_collision_order_is_rejected(tmp_path) -> None:
    package = build_layered_asymmetric(tmp_path)
    corrupt = clone_package(package, tmp_path / "reversed_layers.closygarment")
    semantic = read_json(corrupt / "semantic/garment_graph.json")
    semantic["components"][0]["collisionOrder"] = 20
    semantic["components"][1]["collisionOrder"] = 10
    write_json(corrupt / "semantic/garment_graph.json", semantic)

    assert "layered_asymmetric_layer_contract_invalid" in issue_codes(validate_package(corrupt))


def test_layered_asymmetric_flattened_outer_hem_is_rejected(tmp_path) -> None:
    package = build_layered_asymmetric(tmp_path)
    corrupt = clone_package(package, tmp_path / "flat_outer_hem.closygarment")
    pattern = read_json(corrupt / "pattern/pattern.json")
    outer_front = next(panel for panel in pattern["panels"] if panel["id"].endswith("outer.front"))
    hem = next(edge for edge in outer_front["boundary"] if ".outer.hem." in edge["id"])
    hem["curve"]["points"][0][1] = hem["curve"]["points"][1][1]
    write_json(corrupt / "pattern/pattern.json", pattern)

    assert "layered_asymmetric_layer_contract_invalid" in issue_codes(validate_package(corrupt))


def test_layered_asymmetric_binding_corruption_is_rejected_from_persisted_bytes(tmp_path) -> None:
    package = build_layered_asymmetric(tmp_path)
    corrupt = clone_package(package, tmp_path / "bad_binding.closygarment")
    path = corrupt / "binding/sim_to_render.bin"
    data = bytearray(path.read_bytes())
    data[HEADER_SIZE + 4 : HEADER_SIZE + 8] = struct.pack("<f", 2.0)
    path.write_bytes(data)

    assert "layered_asymmetric_binding_validation_failed" in issue_codes(validate_package(corrupt))
