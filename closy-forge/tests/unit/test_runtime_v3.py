from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest

from closy_forge.binding.binary_format import write_binding
from closy_forge.binding.builder import build_binding
from closy_forge.geometry.glb_io import read_glb_meshset, write_indexed_glb
from closy_forge.geometry.mesh_model import Mesh, MeshSet, Vec3
from closy_forge.geometry.subdivision import subdivide_for_render
from closy_forge.manual_provider_binding_v2.binding import build_binding_v2, write_binding_v2
from closy_forge.package_io.canonical_json import canonical_dumps, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.runtime_delivery.package_v2 import (
    RuntimeV2Inputs,
    RuntimeV2Limits,
    build_runtime_package_v2,
)
from closy_forge.runtime_delivery.package_v3 import (
    BINDING_CODEC,
    LOCAL_FRAME_CODEC,
    POSE_IDS,
    PROFILES,
    RuntimeIdentityV3,
    RuntimeV3Error,
    analytic_cage_poses_v3,
    bound_pose_positions_v3,
    build_runtime_outfit_v3,
    build_runtime_package_v3,
    decode_binding_v3,
    decode_glb_v3,
    load_or_compatible_last_good,
    load_runtime_package_v3,
    manifest_identity,
    safe_relative_v3,
)
from closy_forge.runtime_delivery.streaming import TransferError, TransferLimits
from closy_forge.runtime_delivery.streaming_v2 import _encode_archive
from closy_forge.runtime_delivery.streaming_v3 import (
    RuntimeStreamV3,
    build_runtime_stream_v3,
    load_prefix_v3,
    materialize_v3,
    receive_v3,
    transfer_identity_v3,
)


@dataclass
class Source:
    root: Path
    inputs: RuntimeV2Inputs
    identity: RuntimeIdentityV3
    poses: dict[str, list[Vec3]]
    codec: str = BINDING_CODEC

    def build(self, target: Path, *, outfit: bool = False) -> dict[str, Any]:
        kwargs: dict[str, Any] = dict(
            inputs=self.inputs,
            profile=PROFILES[0],
            identity=self.identity,
            cage=self.root / "cage.glb",
            binding=self.root / "binding.bin",
            cage_poses=self.poses,
            binding_codec=self.codec,
        )
        if outfit:
            return build_runtime_outfit_v3(
                target,
                **kwargs,
                members=[
                    replace(self.identity, garment_id="garment.inner"),
                    replace(self.identity, garment_id="garment.outer"),
                ],
            )
        return build_runtime_package_v3(target, **kwargs)


def source(root: Path, *, local: bool = False, outfit: bool = False) -> Source:
    root.mkdir()
    mesh = Mesh(
        "tiny",
        "panel.front",
        [(c * 0.1, r * 0.1, 0.003 * ((c + r) % 2)) for r in range(5) for c in range(5)],
        [(c / 4, r / 4) for r in range(5) for c in range(5)],
        [
            (a, b, d)
            for r in range(4)
            for c in range(4)
            for a, b, d in (
                (r * 5 + c, r * 5 + c + 1, (r + 1) * 5 + c),
                (r * 5 + c + 1, (r + 1) * 5 + c + 1, (r + 1) * 5 + c),
            )
        ],
    )
    meshset = MeshSet([mesh])
    if outfit:
        meshset = MeshSet(
            [
                mesh,
                replace(
                    mesh,
                    name="outer",
                    panel_id="panel.outer",
                    vertices=[(x, y, z + 0.05) for x, y, z in mesh.vertices],
                ),
            ]
        )
    if local:
        write_indexed_glb(root / "render.glb", meshset, "fixture", (0.2, 0.3, 0.4, 1.0))
        rendered = read_glb_meshset(root / "render.glb")
        bound = build_binding_v2(rendered)
        write_indexed_glb(root / "cage.glb", bound.cage, "fixture", (0.2, 0.3, 0.4, 1.0))
        write_binding_v2(root / "binding.bin", bound.binding)
    else:
        write_indexed_glb(root / "cage.glb", meshset, "fixture", (0.2, 0.3, 0.4, 1.0))
        cage = read_glb_meshset(root / "cage.glb")
        rendered, seeds = subdivide_for_render(cage)
        binding, _ = build_binding(cage, rendered, seeds)
        write_binding(root / "binding.bin", binding)
        write_indexed_glb(root / "render.glb", rendered, "fixture", (0.2, 0.3, 0.4, 1.0))
    cage = decode_glb_v3((root / "cage.glb").read_bytes())
    rendered = decode_glb_v3((root / "render.glb").read_bytes())
    codec = LOCAL_FRAME_CODEC if local else BINDING_CODEC
    decoded_binding = decode_binding_v3(
        (root / "binding.bin").read_bytes(),
        cage,
        rendered,
        binding_codec=codec,
        cage_glb=(root / "cage.glb").read_bytes(),
        render_glb=(root / "render.glb").read_bytes(),
    )
    poses = analytic_cage_poses_v3(cage)
    identity = RuntimeIdentityV3(
        "garment.tiny", "avatar.reference", PROFILES[0].profile_id, "1" * 64
    )
    inputs = RuntimeV2Inputs(
        identity.garment_id,
        identity.provenance,
        root / "render.glb",
        {"cloth": {"roughness": 0.8}},
        b"\x89PNG\r\n\x1a\nfixture",
        bound_pose_positions_v3(cage, decoded_binding, poses),
    )
    return Source(root, inputs, identity, poses, codec)


def reseal(root: Path, doc: dict[str, Any] | None = None) -> str:
    if doc is None:
        doc = json.loads((root / "manifest.json").read_text())
    doc["inventory"] = [
        {
            "path": p.relative_to(root).as_posix(),
            "sha256": sha256_file(p),
            "byteSize": p.stat().st_size,
        }
        for p in sorted(root.rglob("*"))
        if p.is_file() and p != root / "manifest.json"
    ]
    doc["packageIdentity"] = manifest_identity(doc)
    write_canonical_json(root / "manifest.json", doc)
    return sha256_file(root / "manifest.json")


def stream_for(root: Path, identity: RuntimeIdentityV3) -> RuntimeStreamV3:
    return build_runtime_stream_v3(
        root,
        expected=identity,
        chunk_size=1024,
        trusted_manifest_hash=sha256_file(root / "manifest.json"),
    )


@pytest.mark.parametrize("local,outfit", [(False, False), (True, False), (False, True)])
def test_real_serialized_codecs_outfit_determinism_and_three_resumes(
    tmp_path: Path,
    local: bool,
    outfit: bool,
) -> None:
    fixture = source(tmp_path / "source", local=local, outfit=outfit)
    first, second = tmp_path / "build1", tmp_path / "build2"
    a, b = fixture.build(first, outfit=outfit), fixture.build(second, outfit=outfit)
    assert a == b
    digest = sha256_file(first / "manifest.json")
    loaded = load_runtime_package_v3(first, expected=fixture.identity, trusted_manifest_hash=digest)
    assert loaded.maximum_binding_error_m <= 2e-6
    assert len(loaded.outfit_members) == (2 if outfit else 0)
    assert loaded.cage.vertex_count < loaded.render_mesh.vertex_count
    for pose in POSE_IDS:
        assert loaded.render_pose(pose).triangle_count == loaded.render_mesh.triangle_count
    stream = stream_for(first, fixture.identity)
    assert stream == stream_for(second, fixture.identity)
    ready = stream.manifest["fallbackReadyChunkCount"]
    assert (
        load_prefix_v3(
            b"".join(stream.chunks[:ready]), expected=fixture.identity, trusted_manifest_hash=digest
        )
        == fixture.inputs.conventional_fallback_glb.read_bytes()
    )
    with pytest.raises(RuntimeV3Error):
        load_prefix_v3(
            b"".join(stream.chunks[: ready - 1]),
            expected=fixture.identity,
            trusted_manifest_hash=digest,
        )
    for cut in (1, len(stream.chunks) // 2, len(stream.chunks) - 1):
        cache = tmp_path / f"cache-{cut}"
        first_receiver = receive_v3(
            cache,
            stream,
            expected=fixture.identity,
            session_id="resume",
            trusted_transfer_hash=transfer_identity_v3(stream.manifest),
        )
        for i in range(cut):
            first_receiver.receive(i, stream.chunks[i])
        resumed = receive_v3(
            cache,
            stream,
            expected=fixture.identity,
            session_id="resume",
            trusted_transfer_hash=transfer_identity_v3(stream.manifest),
        )
        assert resumed.resume_bytes_saved == sum(map(len, stream.chunks[:cut])) > 0
        for i in resumed.missing_indices:
            resumed.receive(i, stream.chunks[i])
        assert resumed.verified_prefix() == loaded.conventional_fallback_glb
        archive = resumed.finalize(tmp_path / f"archive-{cut}.bin")
        delivered = materialize_v3(
            archive.read_bytes(),
            tmp_path / f"delivered-{cut}",
            expected=fixture.identity,
            trusted_manifest_hash=digest,
            trusted_archive_hash=stream.manifest["aggregateSha256"],
        )
        assert delivered.package_identity == loaded.package_identity


@pytest.mark.parametrize(
    "field,value",
    [
        ("garment_id", "garment.other"),
        ("avatar_id", "avatar.other"),
        ("profile_id", PROFILES[1].profile_id),
        ("provenance", "2" * 64),
    ],
)
def test_metadata_swaps_and_different_asset_last_good_rejected(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    fixture = source(tmp_path / "source")
    root = tmp_path / "package"
    fixture.build(root)
    digest = sha256_file(root / "manifest.json")
    different = replace(fixture.identity, **{field: value})
    with pytest.raises(RuntimeV3Error, match="requested_identity_mismatch"):
        load_or_compatible_last_good(
            tmp_path / "missing",
            last_good=root,
            expected=different,
            trusted_manifest_hash=digest,
            last_good_manifest_hash=digest,
        )
    doc = json.loads((root / "manifest.json").read_text())
    doc["identity"] = different.json()
    reseal(root, doc)
    with pytest.raises(RuntimeV3Error, match="untrusted_manifest"):
        load_runtime_package_v3(root, expected=fixture.identity, trusted_manifest_hash=digest)
    forged_archive = _encode_archive(
        root, ["manifest.json", *sorted(r["path"] for r in doc["inventory"])]
    )
    with pytest.raises(RuntimeV3Error, match="untrusted_manifest"):
        load_prefix_v3(forged_archive, expected=fixture.identity, trusted_manifest_hash=digest)


@pytest.mark.parametrize(
    "offset,fmt,value",
    [
        (32, "<I", 0),
        (64, "<I", 0),
        (20, "<I", 99999),
        (24, "<I", 99999),
        (96, "<I", 99999),
        (100, "<f", float("nan")),
        (100, "<f", -0.2),
        (100, "<f", 1.2),
        (108, "<f", 0.001),
        (112, "<H", 999),
        (114, "<H", 1),
    ],
)
def test_binding_hash_counts_weights_offsets_and_panel_bounds(
    tmp_path: Path,
    offset: int,
    fmt: str,
    value: int | float,
) -> None:
    fixture = source(tmp_path / "source")
    root = tmp_path / "package"
    fixture.build(root)
    path = root / "driving/binding.bin"
    data = bytearray(path.read_bytes())
    struct.pack_into(fmt, data, offset, value)
    path.write_bytes(data)
    digest = reseal(root)
    with pytest.raises(RuntimeV3Error, match="binding"):
        load_runtime_package_v3(root, expected=fixture.identity, trusted_manifest_hash=digest)


def test_payload_rejection_compatible_lastgood_and_limits(tmp_path: Path) -> None:
    fixture = source(tmp_path / "source")
    good, bad = tmp_path / "good", tmp_path / "bad"
    fixture.build(good)
    digest = sha256_file(good / "manifest.json")
    shutil.copytree(good, bad)
    path = next((bad / "payload.closyruntime/blobs").glob("*"))
    data = bytearray(path.read_bytes())
    data[-1] ^= 1
    path.write_bytes(data)
    loaded, reason = load_or_compatible_last_good(
        bad,
        last_good=good,
        expected=fixture.identity,
        trusted_manifest_hash=digest,
        last_good_manifest_hash=digest,
    )
    assert loaded.fallback_reason == reason and reason and "file_identity_mismatch" in reason
    with pytest.raises(RuntimeV3Error, match="decompression_ratio"):
        load_runtime_package_v3(
            good,
            expected=fixture.identity,
            trusted_manifest_hash=digest,
            limits=RuntimeV2Limits(max_decompression_ratio=0.5),
        )
    (good / "unlisted").write_bytes(b"x")
    with pytest.raises(RuntimeV3Error, match="exact_inventory"):
        load_runtime_package_v3(good, expected=fixture.identity, trusted_manifest_hash=digest)


def test_distinct_transport_controls_and_contracts(tmp_path: Path) -> None:
    fixture = source(tmp_path / "source")
    root = tmp_path / "package"
    fixture.build(root)
    stream = stream_for(root, fixture.identity)
    other = replace(
        fixture,
        identity=replace(fixture.identity, garment_id="garment.else"),
        inputs=replace(fixture.inputs, garment_id="garment.else"),
    )
    other.build(tmp_path / "other")
    other_stream = stream_for(tmp_path / "other", other.identity)
    slot = next(
        i
        for i, (a, b) in enumerate(zip(stream.chunks, other_stream.chunks, strict=False))
        if len(a) == len(b) and a != b
    )
    receiver = receive_v3(
        tmp_path / "cache",
        stream,
        expected=fixture.identity,
        session_id="active",
        trusted_transfer_hash=transfer_identity_v3(stream.manifest),
    )
    with pytest.raises(TransferError, match="transfer_chunk_hash_mismatch"):
        receiver.receive(slot, other_stream.chunks[slot])
    with pytest.raises(TransferError, match="transfer_chunk_size_mismatch"):
        receiver.receive(slot, stream.chunks[slot][:-1])
    corrupt = bytearray(stream.chunks[slot])
    corrupt[-1] ^= 1
    with pytest.raises(TransferError, match="transfer_chunk_hash_mismatch"):
        receiver.receive(slot, bytes(corrupt))
    with pytest.raises(TransferError, match="transfer_chunks_missing"):
        receiver.finalize(tmp_path / "missing.bin")
    receiver.receive(slot, stream.chunks[slot])
    with pytest.raises(TransferError, match="transfer_duplicate_chunk"):
        receiver.receive(slot, stream.chunks[slot])
    with pytest.raises(TransferError, match="transfer_stale_resume"):
        receive_v3(
            tmp_path / "cache",
            other_stream,
            expected=other.identity,
            session_id="active",
            trusted_transfer_hash=transfer_identity_v3(other_stream.manifest),
        )
    receiver.cancel()
    with pytest.raises(TransferError, match="transfer_cancelled"):
        receiver.receive(0, stream.chunks[0])
    with pytest.raises(TransferError, match="transfer_total_limit_exceeded"):
        build_runtime_stream_v3(
            root,
            expected=fixture.identity,
            chunk_size=1024,
            trusted_manifest_hash=sha256_file(root / "manifest.json"),
            limits=TransferLimits(max_total_bytes=10),
        )
    for data in (stream.payload[:-1], stream.payload + b"x"):
        with pytest.raises(RuntimeV3Error, match="archive_integrity_mismatch"):
            materialize_v3(
                data,
                tmp_path / "truncated",
                expected=fixture.identity,
                trusted_manifest_hash=sha256_file(root / "manifest.json"),
                trusted_archive_hash=stream.manifest["aggregateSha256"],
            )
    with pytest.raises(RuntimeV3Error, match="archive_truncated"):
        materialize_v3(
            stream.payload[:-1],
            tmp_path / "truncated",
            expected=fixture.identity,
            trusted_manifest_hash=sha256_file(root / "manifest.json"),
            trusted_archive_hash=sha256_bytes(stream.payload[:-1]),
        )
    swapped = copy.deepcopy(stream.manifest)
    swapped["expected"]["avatarId"] = "avatar.other"
    with pytest.raises(RuntimeV3Error, match="untrusted_transfer"):
        receive_v3(
            tmp_path / "swap",
            replace(stream, manifest=swapped),
            expected=fixture.identity,
            session_id="swap",
            trusted_transfer_hash=transfer_identity_v3(stream.manifest),
        )
    stale = {**stream.manifest, "streamVersion": "closy.runtime.stream.stale"}
    with pytest.raises(RuntimeV3Error, match="transfer_version_unsupported"):
        receive_v3(
            tmp_path / "stale",
            replace(stream, manifest=stale),
            expected=fixture.identity,
            session_id="stale",
            trusted_transfer_hash=transfer_identity_v3(stream.manifest),
        )


@pytest.mark.parametrize("bad_path", ["../x", "C:/x", "x:ads", "/x", "a//b", "a/./b", "NUL", "x."])
def test_inventory_paths_reject_aliases(bad_path: str) -> None:
    with pytest.raises(RuntimeV3Error, match="path_invalid"):
        safe_relative_v3(bad_path)


def test_signed_invalid_glb_rejected_by_load_and_prefix(tmp_path: Path) -> None:
    fixture = source(tmp_path / "source")
    valid = tmp_path / "valid"
    doc = fixture.build(valid)
    # V2 can encode a header-valid GLB whose decoded triangle positions collapse.
    path = fixture.inputs.conventional_fallback_glb
    glb = bytearray(path.read_bytes())
    size = struct.unpack_from("<I", glb, 12)[0]
    metadata = json.loads(glb[20 : 20 + size])
    acc = metadata["accessors"][metadata["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]
    start = 28 + size + metadata["bufferViews"][acc["bufferView"]].get("byteOffset", 0)
    glb[start : start + acc["count"] * 12] = bytes(acc["count"] * 12)
    path.write_bytes(glb)
    forged = tmp_path / "forged"
    forged.mkdir()
    shutil.copytree(valid / "driving", forged / "driving")
    build_runtime_package_v2(
        forged / "payload.closyruntime", inputs=fixture.inputs, profile=PROFILES[0]
    )
    digest = reseal(forged, doc)
    with pytest.raises(RuntimeV3Error, match="geometry"):
        load_runtime_package_v3(forged, expected=fixture.identity, trusted_manifest_hash=digest)
    archive = _encode_archive(
        forged,
        [
            "manifest.json",
            *sorted(
                p.relative_to(forged).as_posix()
                for p in forged.rglob("*")
                if p.is_file() and p != forged / "manifest.json"
            ),
        ],
    )
    with pytest.raises(RuntimeV3Error, match="geometry"):
        load_prefix_v3(archive, expected=fixture.identity, trusted_manifest_hash=digest)
    with pytest.raises(RuntimeV3Error):
        materialize_v3(
            archive,
            tmp_path / "must-not-publish",
            expected=fixture.identity,
            trusted_manifest_hash=digest,
            trusted_archive_hash=sha256_bytes(archive),
        )
    assert not (tmp_path / "must-not-publish").exists()


@pytest.mark.parametrize("mutation", ["count", "stride", "transform", "length"])
def test_glb_preflight_bounds(tmp_path: Path, mutation: str) -> None:
    fixture = source(tmp_path / "source")
    payload = fixture.inputs.conventional_fallback_glb.read_bytes()
    size = struct.unpack_from("<I", payload, 12)[0]
    doc = json.loads(payload[20 : 20 + size])
    if mutation == "count":
        doc["accessors"][0]["count"] = 2**31
    elif mutation == "stride":
        doc["bufferViews"][0]["byteStride"] = 0
    elif mutation == "transform":
        doc["nodes"][0]["translation"] = [100, 0, 0]
    else:
        doc["bufferViews"][0]["byteLength"] = 1
    raw = json.dumps(doc).encode()
    raw += b" " * (-len(raw) % 4)
    result = (
        struct.pack("<4sII", b"glTF", 2, 20 + len(raw) + len(payload[20 + size :]))
        + struct.pack("<II", len(raw), 0x4E4F534A)
        + raw
        + payload[20 + size :]
    )
    with pytest.raises(RuntimeV3Error):
        decode_glb_v3(result)


@pytest.mark.parametrize("local,producer_bytes", [(False, False), (True, False), (True, True)])
def test_evaluator_real_tiny_source_hook(tmp_path: Path, local: bool, producer_bytes: bool) -> None:
    script = Path(__file__).resolve().parents[2] / "scripts/evaluate_runtime_v3.py"
    spec = importlib.util.spec_from_file_location("runtime_v3_evaluator", script)
    assert spec and spec.loader
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    fixture = source(tmp_path / "source", local=local, outfit=not local)
    manifest = {
        "inventory": [
            {"path": p.name, "byteSize": p.stat().st_size, "sha256": sha256_file(p)}
            for p in sorted(fixture.root.iterdir())
            if p.is_file()
        ],
        "packageIdentity": fixture.identity.provenance,
    }
    if producer_bytes:
        manifest["packageVersion"] = "closy.manual_provider_binding_v2.package.v2"
        for entry in manifest["inventory"]:
            entry["bytes"] = entry.pop("byteSize")
    write_canonical_json(fixture.root / "manifest.json", manifest)
    descriptor = {
        "root": str(fixture.root),
        "manifest": "manifest.json",
        "manifestSha256": sha256_file(fixture.root / "manifest.json"),
        "garmentId": fixture.identity.garment_id,
        "avatarId": fixture.identity.avatar_id,
        "provenance": fixture.identity.provenance,
        "render": "render.glb",
        "cage": "cage.glb",
        "binding": "binding.bin",
        "bindingCodec": fixture.codec,
        "members": []
        if local
        else [
            {
                "garmentId": "garment.inner",
                "avatarId": fixture.identity.avatar_id,
                "provenance": "2" * 64,
            },
            {
                "garmentId": "garment.outer",
                "avatarId": fixture.identity.avatar_id,
                "provenance": "3" * 64,
            },
        ],
    }
    before = {p.name: sha256_file(p) for p in fixture.root.iterdir() if p.is_file()}
    row = runner.evaluate_case(
        {
            "source": descriptor,
            "profile": PROFILES[1].profile_id,
            "id": "tiny-build1",
            "group": "binding" if local else "outfit",
        },
        tmp_path / "evaluated",
    )
    assert row["status"] == "pass" and row["poseCount"] == 4
    assert len(row["resumes"]) == 3
    assert row["maximumPoseEncodingErrorM"] <= 1e-6
    assert row["outfitMembers"] == (0 if local else 2)
    assert before == {p.name: sha256_file(p) for p in fixture.root.iterdir() if p.is_file()}
    runner.atomic_json(tmp_path / "receipt.json", row)
    assert runner.object_file(tmp_path / "receipt.json") == row


def test_evaluator_declares_36_without_running_and_rejects_stale_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = Path(__file__).resolve().parents[2] / "scripts/evaluate_runtime_v3.py"
    spec = importlib.util.spec_from_file_location("runtime_v3_protocol_test", script)
    assert spec and spec.loader
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    monkeypatch.setattr(runner, "code_inventory", lambda: {"tiny-source": "1" * 64})
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(
            a, 0, stdout="tests/unit/test_runtime_v3.py::test_control\n", stderr=""
        ),
    )
    output = tmp_path / "declared"
    protocol = runner.declare(tmp_path / "missing-inputs", output, None)
    assert len(protocol["cases"]) == protocol["familyRows"] == 36
    assert protocol["controlInventory"] == ["tests/unit/test_runtime_v3.py::test_control"]
    assert not list(output.glob("*/package"))
    assert runner.object_file(output / "checkpoint.json")["rows"] == {}
    monkeypatch.setattr(runner, "code_inventory", lambda: {"tiny-source": "2" * 64})
    with pytest.raises(ValueError, match="stale_source"):
        runner.run(protocol, output)


@pytest.mark.parametrize("local", [False, True])
def test_explicit_codec_not_parser_guessing_and_stale_local_frame(
    tmp_path: Path, local: bool
) -> None:
    fixture = source(tmp_path / "source", local=local)
    root = tmp_path / "package"
    doc = fixture.build(root)
    doc["bindingCodec"] = BINDING_CODEC if local else LOCAL_FRAME_CODEC
    digest = reseal(root, doc)
    with pytest.raises(RuntimeV3Error, match="binding|local_frame"):
        load_runtime_package_v3(root, expected=fixture.identity, trusted_manifest_hash=digest)
    if local:
        doc["bindingCodec"] = LOCAL_FRAME_CODEC
        path = root / "driving/cage.glb"
        mesh = read_glb_meshset(path)
        moved = MeshSet(
            [
                replace(m, vertices=[(x, y, z + 0.001) for x, y, z in m.vertices])
                for m in mesh.meshes
            ]
        )
        write_indexed_glb(path, moved, "fixture", (0.2, 0.3, 0.4, 1.0))
        digest = reseal(root, doc)
        with pytest.raises(RuntimeV3Error, match="geometry.*mismatch"):
            load_runtime_package_v3(root, expected=fixture.identity, trusted_manifest_hash=digest)


@pytest.mark.parametrize(
    "field,value", [("garmentId", "garment.other"), ("canonicalPackageDigest", "2" * 64)]
)
def test_nested_metadata_swap_even_with_trusted_outer_is_rejected(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    fixture = source(tmp_path / "source")
    root = tmp_path / "package"
    fixture.build(root)
    path = root / "payload.closyruntime/manifest.json"
    doc = json.loads(path.read_text())
    doc[field] = value
    write_canonical_json(path, doc)
    digest = reseal(root)
    with pytest.raises(RuntimeV3Error, match="nested_identity_mismatch"):
        load_runtime_package_v3(root, expected=fixture.identity, trusted_manifest_hash=digest)


def test_optional_zeroone_digest_never_selects_unvalidated_derivative(tmp_path: Path) -> None:
    fixture = source(tmp_path / "source")
    with_digest = replace(
        fixture, inputs=replace(fixture.inputs, zeroone_derivative_digest="f" * 64)
    )
    root = tmp_path / "package"
    manifest = with_digest.build(root)
    loaded = load_runtime_package_v3(
        root, expected=fixture.identity, trusted_manifest_hash=sha256_file(root / "manifest.json")
    )
    assert manifest["optionalZeroOne"] == "not_selected_conventional_only"
    assert loaded.conventional_fallback_glb == fixture.inputs.conventional_fallback_glb.read_bytes()


def test_checkpoint_records_failed_workers_without_rerunning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = Path(__file__).resolve().parents[2] / "scripts/evaluate_runtime_v3.py"
    spec = importlib.util.spec_from_file_location("runtime_v3_checkpoint_test", script)
    assert spec and spec.loader
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    monkeypatch.setattr(runner, "code_inventory", lambda: {"unit": "1" * 64})
    history = tmp_path / "history.json"
    write_canonical_json(history, {"historical": "failed"})
    protocol: dict[str, Any] = {
        "sourceInventory": {"unit": "1" * 64},
        "python": sys.version,
        "historicalV2": {"path": str(history), "sha256": sha256_file(history)},
        "cases": [
            {
                "id": f"tiny-build{i}",
                "case": "tiny",
                "profile": PROFILES[0].profile_id,
                "group": "family",
                "build": i,
                "source": {"missingAtDeclaration": True},
            }
            for i in (1, 2)
        ],
        "workerTimeoutSeconds": 1,
        "controlTimeoutSeconds": 1,
        "requiredRepresentativeKinds": ["binding", "outfit"],
        "physicalMobile": "not_run",
    }
    protocol["protocolIdentity"] = sha256_bytes(canonical_dumps(protocol).encode())
    output = tmp_path / "run"
    runner.atomic_json(
        output / "checkpoint.json",
        {
            "protocolIdentity": protocol["protocolIdentity"],
            "rows": {},
            "controls": {"status": "not_run"},
        },
    )
    commands = []

    def fail_worker(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if "--worker" in command:
            case = command[command.index("--worker") + 1]
            runner.atomic_json(
                output / case / "receipt.json",
                {
                    "status": "fail",
                    "workerExitCode": 1,
                    "error": "missing_input",
                    "protocolIdentity": protocol["protocolIdentity"],
                },
            )
            return subprocess.CompletedProcess(command, 1)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(runner.subprocess, "run", fail_worker)
    assert runner.run(protocol, output) == 1
    assert len(commands) == 3
    result = runner.object_file(output / "result.json")
    assert result["family"] == {"pass": 0, "fail": 2, "unknown": 0}
    assert all(row["processExitCode"] == 1 for row in result["rows"].values())
    assert runner.run(protocol, output) == 1
    assert len(commands) == 3
