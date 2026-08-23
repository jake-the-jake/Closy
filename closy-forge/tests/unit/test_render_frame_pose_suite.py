from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

from closy_forge.geometry.glb_io import audit_glb
from closy_forge.rendering import hash_render_frame_pose_suite_report
from closy_forge.validation.validator import validate_package
from tests.helpers import build_demo, clone_package, issue_codes, read_json, write_json


def test_demo_package_persists_vec4_tangents_and_pose_suite(tmp_path) -> None:  # type: ignore[no-untyped-def]
    package = build_demo(tmp_path)
    report = read_json(package / "reports" / "render_frame_pose_suite.json")
    manifest = read_json(package / "manifest.json")
    glb_audit = audit_glb(package / "render" / "fallback.glb")

    assert glb_audit["hasVec4Tangents"] is True
    assert glb_audit["semanticAttributeCounts"]["TANGENT"] == glb_audit["primitiveCount"]
    assert glb_audit["semanticAccessorTypes"]["TANGENT"] == ["VEC4"]
    assert report["readiness"]["glbTangentsPersisted"] is True
    assert report["readiness"]["poseSuitePass"] is True
    assert report["readiness"]["acceptedForRuntimeFramePreview"] is True
    assert report["readiness"]["acceptedForCleanProposal"] is False
    assert report["readiness"]["acceptedForCanonical"] is False
    assert report["poseSuite"]["poseCount"] == 4
    assert (
        report["aggregate"]["maxPoseBindingErrorMeters"]
        <= report["poseSuite"]["bindingToleranceMeters"]
    )
    assert manifest["capabilities"]["renderTangentsPersistedAvailable"] is True
    assert manifest["capabilities"]["poseSuiteBindingEvidenceAvailable"] is True


def test_tampered_pose_suite_metrics_are_rejected_even_with_fresh_hash(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_pose_suite.closygarment")
    report = read_json(corrupt / "reports" / "render_frame_pose_suite.json")
    report["poseSuite"]["poses"][0]["maxBindingErrorMeters"] = 0.25
    report["integrity"]["renderFramePoseSuiteHash"] = hash_render_frame_pose_suite_report(report)
    write_json(corrupt / "reports" / "render_frame_pose_suite.json", report)

    codes = issue_codes(validate_package(corrupt))

    assert "file_hash_mismatch" in codes
    assert "render_frame_pose_suite_recompute_mismatch" in codes


def test_render_glb_without_tangent_accessor_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_missing_tangent.closygarment")
    _strip_tangent_attributes(corrupt / "render" / "fallback.glb")

    codes = issue_codes(validate_package(corrupt))

    assert "file_hash_mismatch" in codes
    assert "render_frame_pose_suite_tangent_accessor_missing" in codes
    assert "render_frame_pose_suite_recompute_mismatch" in codes


def _strip_tangent_attributes(path: Path) -> None:
    gltf, binary = _read_glb_chunks(path)
    for mesh in gltf.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            attributes = primitive.get("attributes")
            if isinstance(attributes, dict):
                attributes.pop("TANGENT", None)
    _write_glb_chunks(path, gltf, binary)


def _read_glb_chunks(path: Path) -> tuple[dict[str, Any], bytes]:
    data = path.read_bytes()
    magic, version, total = struct.unpack_from("<III", data, 0)
    assert magic == 0x46546C67
    assert version == 2
    assert total == len(data)
    offset = 12
    gltf: dict[str, Any] | None = None
    binary = b""
    while offset + 8 <= len(data):
        length, kind = struct.unpack_from("<II", data, offset)
        payload = data[offset + 8 : offset + 8 + length]
        if kind == 0x4E4F534A:
            loaded = json.loads(payload.decode("utf-8").rstrip(" \0"))
            assert isinstance(loaded, dict)
            gltf = loaded
        elif kind == 0x004E4942:
            binary = payload
        offset += 8 + length
    assert gltf is not None
    return gltf, binary


def _write_glb_chunks(path: Path, gltf: dict[str, Any], binary: bytes) -> None:
    json_bytes = _pad4(
        json.dumps(gltf, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        b" ",
    )
    bin_bytes = _pad4(binary, b"\x00")
    total_len = 12 + 8 + len(json_bytes) + 8 + len(bin_bytes)
    path.write_bytes(
        struct.pack("<III", 0x46546C67, 2, total_len)
        + struct.pack("<II", len(json_bytes), 0x4E4F534A)
        + json_bytes
        + struct.pack("<II", len(bin_bytes), 0x004E4942)
        + bin_bytes
    )


def _pad4(data: bytes, pad: bytes) -> bytes:
    return data + pad * ((4 - len(data) % 4) % 4)
