from __future__ import annotations

import struct
from copy import deepcopy

from closy_forge.binding.binary_format import HEADER_SIZE
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.validation.validator import validate_package
from tests.helpers import build_long_sleeved, clone_package, issue_codes, read_json, write_json


def test_long_sleeved_wrong_family_is_rejected_by_family_validator(tmp_path) -> None:
    package = build_long_sleeved(tmp_path)
    corrupt = clone_package(package, tmp_path / "wrong_family.closygarment")
    manifest = read_json(corrupt / "manifest.json")
    manifest["garmentClass"] = "tshirt"
    write_json(corrupt / "manifest.json", manifest)

    assert "long_sleeved_family_mismatch" in issue_codes(validate_package(corrupt))


def test_long_sleeved_wrong_cuff_semantic_is_rejected(tmp_path) -> None:
    package = build_long_sleeved(tmp_path)
    corrupt = clone_package(package, tmp_path / "wrong_cuff.closygarment")
    semantic = read_json(corrupt / "semantic/garment_graph.json")
    semantic["requiredIds"]["openings"][0] = "opening.long_sleeved_top.armhole.left"
    write_json(corrupt / "semantic/garment_graph.json", semantic)

    assert "long_sleeved_semantic_ids_invalid" in issue_codes(validate_package(corrupt))


def test_long_sleeved_motion_claim_cannot_be_refreshed_false(tmp_path) -> None:
    package = build_long_sleeved(tmp_path)
    corrupt = clone_package(package, tmp_path / "fake_motion.closygarment")
    motion = read_json(corrupt / "reports/material_motion_suite.json")
    motion["cuffStress"]["accepted"] = False
    payload = deepcopy(motion)
    payload["integrity"]["suiteHash"] = ""
    motion["integrity"]["suiteHash"] = sha256_bytes(canonical_dumps(payload).encode("utf-8"))
    write_json(corrupt / "reports/material_motion_suite.json", motion)

    assert "long_sleeved_motion_suite_invalid" in issue_codes(validate_package(corrupt))


def test_long_sleeved_binding_corruption_is_rejected(tmp_path) -> None:
    package = build_long_sleeved(tmp_path)
    corrupt = clone_package(package, tmp_path / "bad_binding.closygarment")
    path = corrupt / "binding/sim_to_render.bin"
    data = bytearray(path.read_bytes())
    data[HEADER_SIZE + 4 : HEADER_SIZE + 8] = struct.pack("<f", 2.0)
    path.write_bytes(data)

    assert "long_sleeved_binding_validation_failed" in issue_codes(validate_package(corrupt))
