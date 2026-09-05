from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from closy_forge.geometry.glb_io import read_glb_meshset, write_indexed_glb
from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.runtime_delivery.package_v2 import (
    RuntimePackageV2Error,
    RuntimeV2Inputs,
    RuntimeV2Limits,
    RuntimeV2Profile,
    build_runtime_package_v2,
    load_runtime_package_v2,
)
from closy_forge.runtime_delivery.streaming import TransferError, TransferLimits
from closy_forge.runtime_delivery.streaming_v2 import (
    RuntimeStreamReceiverV2,
    build_runtime_stream_v2,
    load_fallback_from_archive_prefix_v2,
    materialize_runtime_archive_v2,
)

PROFILES = (
    RuntimeV2Profile("cpu-balanced-32k", 32 * 1024, 1531),
    RuntimeV2Profile("cpu-small-page-16k", 16 * 1024, 997),
)


@pytest.mark.parametrize("profile", PROFILES, ids=lambda value: value.profile_id)
def test_runtime_v2_two_clean_builds_are_exact_and_decode_real_assets(
    tmp_path: Path, profile: RuntimeV2Profile
) -> None:
    glb, inputs, expected_poses = _inputs(tmp_path)
    first = build_runtime_package_v2(
        tmp_path / "first.closyruntime", inputs=inputs, profile=profile
    )
    second = build_runtime_package_v2(
        tmp_path / "second.closyruntime", inputs=inputs, profile=profile
    )

    left = load_runtime_package_v2(first)
    right = load_runtime_package_v2(second)
    manifest = _json(first / "manifest.json")
    report = _json(first / "build_report.json")
    assert left.package_digest == right.package_digest == manifest["packageDigest"]
    assert left.conventional_fallback_glb == right.conventional_fallback_glb == glb.read_bytes()
    assert report["smallerThanEquivalentDuplicateStorageV1"] is True
    assert report["compressedPayloadBytes"] < report["equivalentPayloadV1DuplicateBytes"]
    assert not any(path.suffix == ".glb" for path in first.rglob("*"))
    assert len(list((first / "blobs").glob("*.zlib"))) == len(manifest["blobs"])
    assert len({row["path"] for row in manifest["blobs"].values()}) == len(manifest["blobs"])
    assert max(row["decodedBytes"] for row in manifest["blobs"].values()) <= 65_536

    decoded_glb = tmp_path / f"decoded-{profile.profile_id}.glb"
    decoded_glb.write_bytes(left.conventional_fallback_glb)
    source_mesh = read_glb_meshset(glb)
    decoded_mesh = read_glb_meshset(decoded_glb)
    assert decoded_mesh.triangle_count == source_mesh.triangle_count
    assert decoded_mesh.meshes[0].panel_uvs == source_mesh.meshes[0].panel_uvs
    assert decoded_mesh.meshes[0].material_id == source_mesh.meshes[0].material_id
    for pose_id, expected in expected_poses.items():
        actual = left.pose_positions[pose_id]
        maximum_error = max(
            abs(expected_value - actual_value)
            for expected_row, actual_row in zip(expected, actual, strict=True)
            for expected_value, actual_value in zip(expected_row, actual_row, strict=True)
        )
        assert maximum_error <= 1e-6
        assert all(-10.0 <= value <= 10.0 for row in actual for value in row)


def test_runtime_v2_fallback_is_available_from_verified_stream_prefix(tmp_path: Path) -> None:
    glb, inputs, _ = _inputs(tmp_path)
    package = build_runtime_package_v2(
        tmp_path / "profile.closyruntime", inputs=inputs, profile=PROFILES[0]
    )
    stream = build_runtime_stream_v2(package, chunk_size=PROFILES[0].transport_chunk_bytes)
    ready_count = int(stream.manifest["fallbackReadyChunkCount"])
    prefix = b"".join(stream.chunks[:ready_count])

    assert load_fallback_from_archive_prefix_v2(prefix) == glb.read_bytes()
    with pytest.raises(TransferError, match="pending"):
        load_fallback_from_archive_prefix_v2(b"".join(stream.chunks[: ready_count - 1]))


@pytest.mark.parametrize("cut", [1, 0.5, -1], ids=["first", "middle", "final"])
def test_runtime_v2_resume_reuses_verified_chunks_and_reconstructs_identity(
    tmp_path: Path, cut: int | float
) -> None:
    _, inputs, _ = _inputs(tmp_path)
    package = build_runtime_package_v2(
        tmp_path / f"source-{cut}.closyruntime", inputs=inputs, profile=PROFILES[1]
    )
    stream = build_runtime_stream_v2(package, chunk_size=PROFILES[1].transport_chunk_bytes)
    count = len(stream.chunks)
    interruption = 1 if cut == 1 else count - 1 if cut == -1 else max(1, count // 2)
    cache = tmp_path / f"cache-{cut}"
    first = RuntimeStreamReceiverV2(cache, stream, session_id="resume")
    for index in range(interruption):
        first.receive(index, stream.chunks[index])
    saved = first.resume_bytes_saved

    resumed = RuntimeStreamReceiverV2(cache, stream, session_id="resume")
    assert resumed.resume_bytes_saved == saved > 0
    for index in resumed.missing_indices:
        resumed.receive(index, stream.chunks[index])
    archive = resumed.finalize_archive(tmp_path / f"archive-{cut}.bin")
    loaded = materialize_runtime_archive_v2(
        archive.read_bytes(), tmp_path / f"materialized-{cut}.closyruntime"
    )
    assert sha256_bytes(archive.read_bytes()) == stream.manifest["aggregateSha256"]
    assert loaded.package_digest == load_runtime_package_v2(package).package_digest


def test_runtime_v2_corrupt_chunk_can_be_rejected_then_replaced(tmp_path: Path) -> None:
    _, inputs, _ = _inputs(tmp_path)
    package = build_runtime_package_v2(
        tmp_path / "source.closyruntime", inputs=inputs, profile=PROFILES[0]
    )
    stream = build_runtime_stream_v2(package, chunk_size=PROFILES[0].transport_chunk_bytes)
    receiver = RuntimeStreamReceiverV2(tmp_path / "cache", stream, session_id="replace")
    corrupt = bytearray(stream.chunks[0])
    corrupt[-1] ^= 1
    with pytest.raises(TransferError, match="transfer_chunk_hash_mismatch"):
        receiver.receive(0, bytes(corrupt))
    receiver.receive(0, stream.chunks[0])
    assert receiver.received_indices == (0,)


def test_runtime_v2_rejects_stale_cross_package_cancel_and_quota(tmp_path: Path) -> None:
    _, inputs, _ = _inputs(tmp_path)
    first_package = build_runtime_package_v2(
        tmp_path / "first.closyruntime", inputs=inputs, profile=PROFILES[0]
    )
    changed = replace(inputs, garment_id="garment.runtime-v2.changed")
    second_package = build_runtime_package_v2(
        tmp_path / "second.closyruntime", inputs=changed, profile=PROFILES[0]
    )
    first_stream = build_runtime_stream_v2(first_package, chunk_size=1024)
    second_stream = build_runtime_stream_v2(second_package, chunk_size=1024)
    cache = tmp_path / "cache"
    first = RuntimeStreamReceiverV2(cache, first_stream, session_id="same")
    first.receive(0, first_stream.chunks[0])
    with pytest.raises(TransferError, match="transfer_stale_resume"):
        RuntimeStreamReceiverV2(cache, second_stream, session_id="same")
    differing = next(
        index
        for index, (left, right) in enumerate(
            zip(first_stream.chunks, second_stream.chunks, strict=True)
        )
        if left != right
    )
    with pytest.raises(TransferError, match="transfer_chunk_hash_mismatch"):
        RuntimeStreamReceiverV2(cache, first_stream, session_id="cross").receive(
            differing, second_stream.chunks[differing]
        )
    cancelled = RuntimeStreamReceiverV2(cache, first_stream, session_id="cancel")
    cancelled.cancel()
    with pytest.raises(TransferError, match="transfer_cancelled"):
        cancelled.receive(0, first_stream.chunks[0])
    with pytest.raises(TransferError, match="transfer_total_limit_exceeded"):
        build_runtime_stream_v2(
            first_package,
            chunk_size=64,
            limits=TransferLimits(max_chunk_bytes=64, max_total_bytes=100),
        )


def test_runtime_v2_corruption_fails_before_selection_and_uses_last_good(tmp_path: Path) -> None:
    _, inputs, _ = _inputs(tmp_path)
    good = build_runtime_package_v2(
        tmp_path / "good.closyruntime", inputs=inputs, profile=PROFILES[0]
    )
    corrupt = tmp_path / "corrupt.closyruntime"
    shutil.copytree(good, corrupt)
    blob = next((corrupt / "blobs").glob("*.zlib"))
    payload = bytearray(blob.read_bytes())
    payload[len(payload) // 2] ^= 1
    blob.write_bytes(payload)

    with pytest.raises(RuntimePackageV2Error, match="runtime_v2_inventory_hash_mismatch"):
        load_runtime_package_v2(corrupt)
    recovered = load_runtime_package_v2(corrupt, last_good_package=good)
    assert recovered.fallback_reason == "last_good_after:runtime_v2_inventory_hash_mismatch"
    assert recovered.package_digest == load_runtime_package_v2(good).package_digest


def test_runtime_v2_rejects_bombs_extra_files_and_malformed_archives(tmp_path: Path) -> None:
    _, inputs, _ = _inputs(tmp_path)
    package = build_runtime_package_v2(
        tmp_path / "source.closyruntime", inputs=inputs, profile=PROFILES[0]
    )
    with pytest.raises(RuntimePackageV2Error, match="runtime_v2_decompression_ratio_exceeded"):
        load_runtime_package_v2(
            package,
            limits=RuntimeV2Limits(max_decompression_ratio=1.01),
        )
    extra = tmp_path / "extra.closyruntime"
    shutil.copytree(package, extra)
    (extra / "undeclared.bin").write_bytes(b"not-selected")
    with pytest.raises(RuntimePackageV2Error, match="runtime_v2_exact_inventory_mismatch"):
        load_runtime_package_v2(extra)

    stream = build_runtime_stream_v2(package, chunk_size=1024)
    with pytest.raises(TransferError, match="transfer_v2_archive_truncated"):
        materialize_runtime_archive_v2(stream.payload[:-1], tmp_path / "truncated.closyruntime")
    with pytest.raises(TransferError, match="transfer_v2_archive_trailing_bytes"):
        materialize_runtime_archive_v2(
            stream.payload + b"trailing", tmp_path / "trailing.closyruntime"
        )


def _inputs(
    root: Path,
) -> tuple[Path, RuntimeV2Inputs, dict[str, list[tuple[float, float, float]]]]:
    source = MeshSet(
        [
            Mesh(
                "runtime.fixture",
                "panel.front",
                [
                    (-0.5, 0.0, 0.0),
                    (0.5, 0.0, 0.0),
                    (-0.45, 0.8, 0.05),
                    (0.45, 0.8, 0.05),
                    (-0.3, 1.3, 0.0),
                    (0.3, 1.3, 0.0),
                ],
                [(0.0, 0.0), (1.0, 0.0), (0.05, 0.6), (0.95, 0.6), (0.2, 1.0), (0.8, 1.0)],
                [(0, 1, 2), (1, 3, 2), (2, 3, 4), (3, 5, 4)],
                "material.runtime.fixture",
            )
        ]
    )
    glb = root / "fallback.glb"
    write_indexed_glb(glb, source, "runtime.fixture", (0.18, 0.32, 0.55, 1.0))
    neutral = source.meshes[0].vertices
    poses = {
        "pose.neutral": list(neutral),
        "pose.arms_up": [(x, y + 0.02 * abs(x), z) for x, y, z in neutral],
        "pose.torso_twist": [(x, y, z + 0.03 * x) for x, y, z in neutral],
        "pose.walk_stride": [(x + (0.02 if x > 0 else -0.02), y, z) for x, y, z in neutral],
    }
    inputs = RuntimeV2Inputs(
        garment_id="garment.runtime-v2.fixture",
        canonical_package_digest="1" * 64,
        conventional_fallback_glb=glb,
        material_set={"material.runtime.fixture": {"roughness": 0.82, "metalness": 0.0}},
        thumbnail_png=b"\x89PNG\r\n\x1a\nfixture",
        pose_positions=poses,
        zeroone_derivative_digest="2" * 64,
    )
    return glb, inputs, poses


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value
