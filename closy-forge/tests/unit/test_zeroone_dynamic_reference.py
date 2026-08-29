from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

import pytest

from closy_forge.geometry.glb_io import read_glb_meshset
from closy_forge.package_io.canonical_json import write_canonical_json
from closy_forge.package_io.hashing import sha256_file
from closy_forge.package_io.managed_output import create_managed_staging
from closy_forge.zeroone import tool as tool_module
from closy_forge.zeroone.dynamic_namespace import (
    DYNAMIC_PAYLOAD_SPECS,
    DYNAMIC_PURPOSE,
    validate_dynamic_namespace_manifest,
    write_dynamic_namespace_manifest,
)
from closy_forge.zeroone.dynamic_oracle import (
    BINDINGS,
    FRAME_SIMULATION_POSITIONS,
    RENDER_IDS,
    SIMULATION_IDS,
    TIMESTAMPS,
    decode_bindings,
    decode_document,
    decode_metadata,
    decode_u64,
    decode_vectors,
    recompute_frames,
)
from closy_forge.zeroone.dynamic_request import (
    DYNAMIC_PROFILE,
    build_dynamic_request,
)
from closy_forge.zeroone.namespace import NamespaceIntegrityError
from closy_forge.zeroone.tool import resolve_zeroone_tool
from tests.helpers import build_demo

CLOSY_SHA = "5" * 40
ZEROONE_SHA = "4" * 40


def _static_derivative(root: Path, package: Path) -> Path:
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    target = root / "static" / "current"
    write_canonical_json(
        target / "derivative.json",
        {
            "schemaVersion": "zeroone.closy.static-derivative.v1",
            "profile": "closy-static-d0-cpu-v1",
            "garmentId": manifest["garmentId"],
            "source": {
                "inputAssetRelativePath": "render/fallback.glb",
                "inputContentSha256": sha256_file(package / "render" / "fallback.glb"),
                "coordinateConventionId": "closy-rh-yup-plus-z-v1",
                "unitScaleMetres": 1.0,
            },
            "nanite": {
                "clusterCount": 7,
                "hierarchyNodeCount": 13,
                "pageCount": 13,
                "pagePackCount": 13,
                "pagePackFormatVersion": 3,
                "geometryHash": 11,
                "topologyHash": 12,
                "materialHash": 13,
            },
            "garmentSemantics": {"broadGarmentSemanticsClaimed": False},
        },
    )
    return target


def test_package_request_maps_every_expanded_render_vertex(tmp_path: Path) -> None:
    package = build_demo(tmp_path)
    bundle = build_dynamic_request(
        package=package,
        invocation_root=tmp_path,
        static_derivative=_static_derivative(tmp_path, package),
        output=tmp_path / "dynamic-output",
        closy_sha=CLOSY_SHA,
    )
    document = decode_document(bundle.encoded, request=True)
    metadata = decode_metadata(document)
    simulation_ids = decode_u64(document.sections[SIMULATION_IDS])
    render_ids = decode_u64(document.sections[RENDER_IDS])
    timestamps = decode_u64(document.sections[TIMESTAMPS])
    frames = decode_vectors(document.sections[FRAME_SIMULATION_POSITIONS], 3, 3)
    bindings = decode_bindings(document.sections[BINDINGS])
    expected_frames = recompute_frames(document)[3]
    static_positions = [
        position
        for mesh in read_glb_meshset(package / "render" / "fallback.glb").meshes
        for position in mesh.vertices
    ]

    assert metadata["profile"] == DYNAMIC_PROFILE
    assert len(simulation_ids) == 218
    assert len(render_ids) == 2496
    assert len(bindings) == len(render_ids)
    assert len(timestamps) == 13
    assert len(frames) == len(timestamps) * len(simulation_ids)
    assert frames[: len(simulation_ids)] == frames[-len(simulation_ids) :]
    assert bundle.influence_inventory["missingDestinationCount"] == 0
    assert bundle.topology_inventory["triangleCount"] == 832
    assert (
        max(
            math.dist(expected, static)
            for expected, static in zip(expected_frames[0], static_positions, strict=True)
        )
        <= 1.0e-6
    )


def test_dynamic_container_rejects_checksum_corruption(tmp_path: Path) -> None:
    package = build_demo(tmp_path)
    bundle = build_dynamic_request(
        package=package,
        invocation_root=tmp_path,
        static_derivative=_static_derivative(tmp_path, package),
        output=tmp_path / "dynamic-output",
        closy_sha=CLOSY_SHA,
    )
    corrupt = bytearray(bundle.encoded)
    corrupt[-1] ^= 1

    with pytest.raises(ValueError, match="section_checksum"):
        decode_document(bytes(corrupt), request=True)


def test_dynamic_namespace_exact_inventory_and_corruption(tmp_path: Path) -> None:
    allowed = tmp_path / "zeroone"
    staging = create_managed_staging(
        allowed / "dynamic-d0-reference",
        allowed_root=allowed,
        purpose=DYNAMIC_PURPOSE,
    )
    for spec in DYNAMIC_PAYLOAD_SPECS:
        path = staging / spec.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"{}\n" if spec.media_type == "application/json" else b"dynamic")
    write_dynamic_namespace_manifest(staging)

    assert validate_dynamic_namespace_manifest(staging)["files"]
    (staging / "derivative" / "derivative.z1dyn").write_bytes(b"corrupt")
    with pytest.raises(NamespaceIntegrityError, match="file_mismatch"):
        validate_dynamic_namespace_manifest(staging)


def test_dynamic_tool_resolution_requires_dynamic_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "ZeroOneProcess.exe"
    executable.write_bytes(b"trusted-dynamic-unit-binary")
    record = {
        "schemaVersion": 1,
        "recordVersion": "closy.zeroone.trusted-build-record.v1",
        "trustDomain": "local_exact_source_capture",
        "repository": "jake-the-jake/ZeroOne",
        "sourceSha": ZEROONE_SHA,
        "buildId": "dynamic-unit",
        "compiler": "msvc-unit",
        "buildType": "Release",
        "executableRelativeName": executable.name,
        "executableSha256": sha256_file(executable),
        "requestSchemaVersions": [
            "closy.zeroone.static-request.v1",
            "closy.zeroone.dynamic-request.v1",
        ],
        "reportSchemaVersions": [
            "zeroone.closy.static-report.v1",
            "zeroone.closy.dynamic-report.v1",
        ],
        "supportedProfiles": ["closy-static-d0-cpu-v1", DYNAMIC_PROFILE],
        "attestation": {"available": False, "kind": "unit"},
        "capture": {
            "sourceClean": True,
            "networkAllowed": False,
            "commandTemplate": ["cmake", "--build", "<build>"],
        },
    }
    record_path = tmp_path / "trusted.json"
    record_path.write_text(json.dumps(record), encoding="utf-8")

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        version = {
            "tool": "ZeroOneProcess",
            "zeroOneGitSha": ZEROONE_SHA,
            "executableSha256": sha256_file(executable),
            "buildConfiguration": "Release",
            "compiler": "msvc-unit",
            "sourceDirty": False,
            "headless": True,
            "cpuOnly": True,
            "requiresGpu": False,
            "requiresWindow": False,
            "requestSchemaVersion": "closy.zeroone.static-request.v1",
            "reportSchemaVersion": "zeroone.closy.static-report.v1",
            "dynamicRequestSchemaVersion": "closy.zeroone.dynamic-request.v1",
            "dynamicReportSchemaVersion": "zeroone.closy.dynamic-report.v1",
            "profiles": ["closy-static-d0-cpu-v1", DYNAMIC_PROFILE],
            "commands": [
                "inspect",
                "cook",
                "validate",
                "resume",
                "deform",
                "validate-dynamic",
                "inspect-dynamic",
                "resume-dynamic",
            ],
        }
        return subprocess.CompletedProcess([], 0, json.dumps(version), "")

    monkeypatch.setattr(tool_module.subprocess, "run", fake_run)
    resolution = resolve_zeroone_tool(
        executable,
        trusted_build_record=record_path,
        expected_source_sha=ZEROONE_SHA,
        capability="dynamic",
    )

    assert resolution.available is True
    assert resolution.reason == "trusted_zeroone_tool_ready"
