from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from closy_forge.geometry.glb_io import write_glb
from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.runtime_delivery import (
    RUNTIME_CAPABILITY_VERSION,
    RuntimeLimits,
    RuntimePackageError,
    RuntimePackageInputs,
    TransferError,
    TransferLimits,
    TransferReceiver,
    build_chunk_inventory,
    build_runtime_package,
    evict_transfer_state,
    load_runtime_package,
)


def _write_minimal_glb(path: Path) -> bytes:
    mesh = Mesh(
        name="runtime-fixture",
        panel_id="panel.runtime-fixture",
        vertices=[(-0.1, 0.0, 0.0), (0.1, 0.0, 0.0), (0.0, 0.2, 0.0)],
        panel_uvs=[(0.0, 0.0), (1.0, 0.0), (0.5, 1.0)],
        triangles=[(0, 1, 2)],
    )
    write_glb(path, MeshSet(meshes=[mesh]), "runtime_fixture", (0.7, 0.6, 0.5, 1.0))
    return path.read_bytes()


def _source_link() -> dict[str, str]:
    return {
        "opaqueId": "src_runtime_fixture",
        "consentScope": "project-authored-synthetic-only",
        "retentionPolicy": "fixture-lifetime",
        "deletionPolicy": "managed-withdrawal",
        "derivationPolicy": "non-identifying-runtime-artifact",
        "withdrawalStatus": "active",
    }


def _build_package(
    root: Path,
    name: str = "fixture.closyruntime",
    *,
    include_optional: bool = True,
) -> tuple[Path, bytes]:
    source = root / f"{name}.glb"
    glb = _write_minimal_glb(source)
    static = root / f"{name}.static"
    dynamic = root / f"{name}.dynamic.json"
    if include_optional:
        static.write_bytes(b"zeroone-static-fixture")
        dynamic.write_text('{"candidateDynamicMetadataOnly":true}\n', encoding="utf-8")
    target = root / name
    build_runtime_package(
        target,
        inputs=RuntimePackageInputs(
            conventional_fallback_glb=source,
            source_link=_source_link(),
            zeroone_static_artifact=static if include_optional else None,
            zeroone_dynamic_metadata=dynamic if include_optional else None,
            pose_id="pose.relaxed.prebaked_v1",
            pose_payload={"frame": 0, "jointCount": 17, "dynamicDeformationExecuted": False},
        ),
    )
    return target, glb


def _manifest(path: Path) -> dict[str, object]:
    return json.loads((path / "manifest.json").read_text(encoding="utf-8"))


def _write_manifest(path: Path, payload: dict[str, object]) -> None:
    (path / "manifest.json").write_text(canonical_dumps(payload), encoding="utf-8", newline="\n")


def _inventory_digest(inventory: list[dict[str, object]]) -> str:
    payload = "\n".join(
        f"{entry['path']}\0{entry['byteSize']}\0{entry['sha256']}"
        for entry in sorted(inventory, key=lambda item: str(item["path"]))
    )
    return sha256_bytes(payload.encode())


def test_runtime_package_is_deterministic_and_exercises_declared_fallback_order(
    tmp_path: Path,
) -> None:
    first, glb = _build_package(tmp_path, "first.closyruntime")
    second, _ = _build_package(tmp_path, "second.closyruntime")

    first_manifest = _manifest(first)
    second_manifest = _manifest(second)
    assert first_manifest == second_manifest
    assert first_manifest["capabilityVersion"] == RUNTIME_CAPABILITY_VERSION
    assert first_manifest["candidatePreparatoryOnly"] is True

    dynamic = load_runtime_package(first, support_zeroone_dynamic=True)
    assert dynamic.selected_source == "zeroone_dynamic"
    static = load_runtime_package(first)
    assert static.selected_source == "zeroone_static"
    conventional = load_runtime_package(first, support_zeroone_static=False)
    assert conventional.selected_source == "conventional_glb"
    assert conventional.selected_bytes == glb
    offline = load_runtime_package(first, offline=True)
    assert offline.selected_source == "zeroone_static"
    assert offline.pose_id == "pose.relaxed.prebaked_v1"
    assert offline.pose_payload["jointCount"] == 17


def test_runtime_package_without_optional_artifacts_uses_conventional_glb(tmp_path: Path) -> None:
    package, glb = _build_package(tmp_path, include_optional=False)
    loaded = load_runtime_package(package)
    assert loaded.selected_source == "conventional_glb"
    assert loaded.selected_bytes == glb


def test_runtime_loader_preserves_last_good_on_primary_corruption(tmp_path: Path) -> None:
    current, _ = _build_package(tmp_path, "current.closyruntime")
    last_good, glb = _build_package(tmp_path, "last-good.closyruntime", include_optional=False)
    (current / "assets" / "conventional_fallback.glb").write_bytes(b"corrupt")

    loaded = load_runtime_package(current, last_good_package=last_good)

    assert loaded.selected_source == "conventional_glb"
    assert loaded.selected_bytes == glb
    assert loaded.offline is True
    assert loaded.fallback_reason == "last_good_after:runtime_inventory_hash_mismatch"


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("extra_file", "runtime_exact_inventory_mismatch"),
        ("stale_capability", "runtime_manifest_version_unsupported"),
        ("duplicate_authority", "runtime_duplicate_authority"),
        ("traversal_reference", "runtime_reference_path_invalid"),
        ("undeclared_reference", "runtime_reference_not_in_inventory"),
        ("decompression_ratio", "runtime_decompression_ratio_exceeded"),
    ],
)
def test_runtime_loader_rejects_hostile_manifest_and_tree_mutations(
    tmp_path: Path, mutation: str, code: str
) -> None:
    package, _ = _build_package(tmp_path)
    manifest = _manifest(package)
    if mutation == "extra_file":
        (package / "unlisted.bin").write_bytes(b"unexpected")
    elif mutation == "stale_capability":
        manifest["capabilityVersion"] = "closy.runtime_capabilities.stale"
        _write_manifest(package, manifest)
    elif mutation == "duplicate_authority":
        artifacts = manifest["artifacts"]
        assert isinstance(artifacts, dict)
        artifacts["zeroOneStatic"] = artifacts["conventionalGlb"]
        _write_manifest(package, manifest)
    elif mutation in {"traversal_reference", "undeclared_reference"}:
        motion = manifest["motion"]
        assert isinstance(motion, dict)
        options = motion["prebakedOptions"]
        assert isinstance(options, list)
        options[0]["path"] = (
            "../escape.json" if mutation == "traversal_reference" else "missing.json"
        )
        _write_manifest(package, manifest)
    elif mutation == "decompression_ratio":
        pages = manifest["pages"]
        assert isinstance(pages, dict)
        records = pages["records"]
        assert isinstance(records, list)
        records[0]["sourceLength"] = int(records[0]["compressedLength"]) * 129
        _write_manifest(package, manifest)

    with pytest.raises(RuntimePackageError, match=code):
        load_runtime_package(package)


def test_runtime_loader_rejects_corrupt_chunk_and_tight_memory_budget(tmp_path: Path) -> None:
    package, _ = _build_package(tmp_path)
    page = package / "pages" / "00000.zlib"
    page.write_bytes(page.read_bytes()[:-1] + b"x")
    with pytest.raises(RuntimePackageError, match="runtime_inventory_hash_mismatch"):
        load_runtime_package(package)

    independently_corrupt, _ = _build_package(tmp_path, "independently-corrupt.closyruntime")
    manifest = _manifest(independently_corrupt)
    page = independently_corrupt / "pages" / "00000.zlib"
    page.write_bytes(page.read_bytes()[:-1] + b"x")
    inventory = manifest["inventory"]
    assert isinstance(inventory, list)
    page_entry = next(entry for entry in inventory if entry["path"] == "pages/00000.zlib")
    page_entry["sha256"] = sha256_bytes(page.read_bytes())
    manifest["packageDigest"] = _inventory_digest(inventory)
    _write_manifest(independently_corrupt, manifest)
    with pytest.raises(RuntimePackageError, match="runtime_chunk_corrupt"):
        load_runtime_package(independently_corrupt)

    clean, _ = _build_package(tmp_path, "clean.closyruntime")
    with pytest.raises(RuntimePackageError, match="runtime_decoded_memory_limit_exceeded"):
        load_runtime_package(clean, limits=RuntimeLimits(max_decoded_bytes=8))


def test_runtime_loader_rejects_raw_private_capture_digest(tmp_path: Path) -> None:
    source = tmp_path / "source.glb"
    _write_minimal_glb(source)
    link = _source_link()
    link["consentScope"] = "capture:" + "a" * 64
    with pytest.raises(RuntimePackageError, match="runtime_private_digest_linkage_rejected"):
        build_runtime_package(
            tmp_path / "unsafe.closyruntime",
            inputs=RuntimePackageInputs(conventional_fallback_glb=source, source_link=link),
        )


def test_runtime_loader_rejects_link_or_hardlink_when_supported(tmp_path: Path) -> None:
    package, _ = _build_package(tmp_path)
    original = package / "assets" / "zeroone_static.bin"
    hardlink = package / "assets" / "hardlink.bin"
    try:
        os.link(original, hardlink)
    except OSError:
        pytest.skip("hardlink creation unavailable")
    with pytest.raises(RuntimePackageError, match="runtime_hardlink_rejected"):
        load_runtime_package(package)


def test_streaming_resumes_after_interruption_and_accepts_reordered_chunks(tmp_path: Path) -> None:
    payload = bytes(range(251)) * 20
    inventory = build_chunk_inventory(payload, chunk_size=197)
    chunks = [payload[offset : offset + 197] for offset in range(0, len(payload), 197)]
    receiver = TransferReceiver(tmp_path / "cache", inventory)
    for index in range(0, len(chunks), 2):
        receiver.receive(index, chunks[index])

    resumed = TransferReceiver(tmp_path / "cache", inventory)
    assert resumed.received_indices == tuple(range(0, len(chunks), 2))
    for index in reversed(range(1, len(chunks), 2)):
        resumed.receive(index, chunks[index])
    output = resumed.finalize(tmp_path / "assembled.closyruntime.bin")

    assert output.read_bytes() == payload
    assert resumed.missing_indices == ()


def test_streaming_rejects_wrong_duplicate_missing_and_stale_chunks(tmp_path: Path) -> None:
    payload = b"abcdefghij" * 60
    inventory = build_chunk_inventory(payload, chunk_size=100)
    chunks = [payload[offset : offset + 100] for offset in range(0, len(payload), 100)]
    receiver = TransferReceiver(tmp_path / "cache", inventory)
    with pytest.raises(TransferError, match="transfer_chunk_hash_mismatch"):
        receiver.receive(0, b"x" * 100)
    receiver.receive(0, chunks[0])
    with pytest.raises(TransferError, match="transfer_duplicate_chunk"):
        receiver.receive(0, chunks[0])
    with pytest.raises(TransferError, match="transfer_chunks_missing"):
        receiver.finalize(tmp_path / "incomplete.bin")

    other = build_chunk_inventory(b"different" * 100, chunk_size=100)
    with pytest.raises(TransferError, match="transfer_stale_resume"):
        TransferReceiver(tmp_path / "cache", other)


def test_streaming_rejects_corrupt_cache_and_supports_bounded_eviction(tmp_path: Path) -> None:
    payload = b"0123456789" * 80
    inventory = build_chunk_inventory(
        payload, chunk_size=80, limits=TransferLimits(max_chunk_bytes=80)
    )
    first = TransferReceiver(tmp_path / "cache", inventory, session_id="first")
    first.receive(0, payload[:80])
    (first.chunk_dir / "000000.chunk").write_bytes(b"corrupt")
    with pytest.raises(TransferError, match="transfer_cached_chunk_corrupt"):
        TransferReceiver(tmp_path / "cache", inventory, session_id="first")

    TransferReceiver(tmp_path / "cache", inventory, session_id="second")
    removed = evict_transfer_state(tmp_path / "cache", keep_session_ids={"second"})
    assert removed == ("first",)
    assert (tmp_path / "cache" / "second").is_dir()
