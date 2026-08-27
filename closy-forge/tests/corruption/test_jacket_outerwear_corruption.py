from __future__ import annotations

import struct
from copy import deepcopy

from closy_forge.binding.binary_format import HEADER_SIZE
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.validation.validator import validate_package
from tests.helpers import build_jacket_outerwear, clone_package, issue_codes, read_json, write_json


def test_jacket_outerwear_wrong_family_is_rejected_by_family_validator(tmp_path) -> None:
    package = build_jacket_outerwear(tmp_path)
    corrupt = clone_package(package, tmp_path / "wrong_family.closygarment")
    manifest = read_json(corrupt / "manifest.json")
    manifest["garmentClass"] = "tshirt"
    write_json(corrupt / "manifest.json", manifest)

    assert "jacket_outerwear_family_mismatch" in issue_codes(validate_package(corrupt))


def test_jacket_outerwear_missing_facing_semantic_is_rejected(tmp_path) -> None:
    package = build_jacket_outerwear(tmp_path)
    corrupt = clone_package(package, tmp_path / "wrong_cuff.closygarment")
    semantic = read_json(corrupt / "semantic/garment_graph.json")
    semantic["requiredIds"]["panels"].remove("panel.jacket_outerwear.facing.left")
    write_json(corrupt / "semantic/garment_graph.json", semantic)

    assert "jacket_outerwear_semantic_ids_invalid" in issue_codes(validate_package(corrupt))


def test_jacket_outerwear_front_opening_cannot_use_attached_outer_facing_edge(tmp_path) -> None:
    package = build_jacket_outerwear(tmp_path)
    corrupt = clone_package(package, tmp_path / "sewn_front.closygarment")
    pattern = read_json(corrupt / "pattern/pattern.json")
    front = next(item for item in pattern["openings"] if item["id"].endswith(".front"))
    front["boundaryEdges"][0] = "edge.jacket_outerwear.facing.outer.left"
    write_json(corrupt / "pattern/pattern.json", pattern)

    assert "jacket_outerwear_facing_contract_invalid" in issue_codes(validate_package(corrupt))


def test_jacket_outerwear_facing_collision_order_is_guarded(tmp_path) -> None:
    package = build_jacket_outerwear(tmp_path)
    corrupt = clone_package(package, tmp_path / "bad_facing_layer.closygarment")
    semantic = read_json(corrupt / "semantic/garment_graph.json")
    facing = next(item for item in semantic["components"] if item["id"].endswith("facing.left"))
    facing["collisionOrder"] = 40
    write_json(corrupt / "semantic/garment_graph.json", semantic)

    assert "jacket_outerwear_collision_layer_invalid" in issue_codes(validate_package(corrupt))


def test_jacket_outerwear_motion_claim_cannot_be_refreshed_false(tmp_path) -> None:
    package = build_jacket_outerwear(tmp_path)
    corrupt = clone_package(package, tmp_path / "fake_motion.closygarment")
    motion = read_json(corrupt / "reports/material_motion_suite.json")
    motion["cuffStress"]["accepted"] = False
    payload = deepcopy(motion)
    payload["integrity"]["suiteHash"] = ""
    motion["integrity"]["suiteHash"] = sha256_bytes(canonical_dumps(payload).encode("utf-8"))
    write_json(corrupt / "reports/material_motion_suite.json", motion)

    assert "jacket_outerwear_motion_suite_invalid" in issue_codes(validate_package(corrupt))


def test_jacket_outerwear_binding_corruption_is_rejected(tmp_path) -> None:
    package = build_jacket_outerwear(tmp_path)
    corrupt = clone_package(package, tmp_path / "bad_binding.closygarment")
    path = corrupt / "binding/sim_to_render.bin"
    data = bytearray(path.read_bytes())
    data[HEADER_SIZE + 4 : HEADER_SIZE + 8] = struct.pack("<f", 2.0)
    path.write_bytes(data)

    assert "jacket_outerwear_binding_validation_failed" in issue_codes(validate_package(corrupt))
