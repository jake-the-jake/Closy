"""Restartable Unit C runner. Declaration is cheap; --run is an explicit separate step."""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import time
import tracemalloc
from dataclasses import asdict
from pathlib import Path
from typing import Any

FORGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FORGE / "src"))

from closy_forge.package_io.canonical_json import canonical_dumps  # noqa: E402
from closy_forge.package_io.hashing import sha256_bytes, sha256_file  # noqa: E402
from closy_forge.runtime_delivery.package_v2 import (  # noqa: E402
    RuntimeV2Inputs,
    RuntimeV2Limits,
    decode_pose_positions,
)
from closy_forge.runtime_delivery.package_v3 import (  # noqa: E402
    BINDING_CODEC,
    BINDING_TOLERANCE_M,
    LOCAL_FRAME_CODEC,
    MAX_COORDINATE_M,
    MAX_MANIFEST_BYTES,
    MAX_TRIANGLES,
    MAX_VERTICES,
    MINIMUM_AREA_M2,
    POSE_IDS,
    PROFILES,
    RuntimeIdentityV3,
    analytic_cage_poses_v3,
    bound_pose_positions_v3,
    build_runtime_package_v3,
    decode_binding_v3,
    decode_glb_v3,
    inventory_v3,
    load_runtime_package_v3,
    read_bounded_v3,
    reject_links_v3,
    safe_relative_v3,
)
from closy_forge.runtime_delivery.streaming_v3 import (  # noqa: E402
    build_runtime_stream_v3,
    load_prefix_v3,
    materialize_v3,
    receive_v3,
    transfer_identity_v3,
)
from closy_forge.security.strict_json import loads_strict_json_object  # noqa: E402

FAMILIES = (
    "tshirt",
    "sleeveless_top",
    "long_sleeved_top",
    "simple_skirt",
    "simple_trousers",
    "simple_dress",
    "button_shirt",
    "jacket_outerwear",
    "layered_asymmetric",
)
VERSION = "closy.runtime_v3.development.protocol.1"


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".pending")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(canonical_dumps(value))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def object_file(path: Path) -> dict[str, Any]:
    return loads_strict_json_object(read_bounded_v3(path, MAX_MANIFEST_BYTES).decode())


def code_inventory() -> dict[str, str]:
    # Conservative transitive pinning, including untracked successor implementations.
    paths = [
        *sorted((FORGE / "src/closy_forge").rglob("*.py")),
        Path(__file__),
        FORGE / "tests/unit/test_runtime_v3.py",
        FORGE / "fixtures/static_zeroone_runtime_v2/protocol.json",
    ]
    return {p.relative_to(FORGE).as_posix(): sha256_file(p) for p in paths}


def input_descriptor(root: Path, family: str) -> dict[str, Any]:
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return {"root": str(root), "family": family, "missingAtDeclaration": True}
    doc = object_file(manifest_path)
    if doc.get("profile") != "closy.all_family_integration.development.v1":
        raise ValueError("runtime_v3_family_source_profile_invalid")
    return {
        "root": str(root),
        "family": family,
        "manifest": "manifest.json",
        "manifestSha256": sha256_file(manifest_path),
        "garmentId": doc["garmentId"],
        "avatarId": doc["avatarId"],
        "provenance": doc["packageIdentity"],
        "bindingCodec": BINDING_CODEC,
        "render": "render/fallback.glb",
        "cage": "simulation/simulation_mesh.glb",
        "binding": "binding/sim_to_render.bin",
        "members": [],
    }


def verify_source(descriptor: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    if descriptor.get("missingAtDeclaration"):
        raise ValueError("runtime_v3_source_missing_at_declaration")
    root = Path(descriptor["root"])
    manifest = root / safe_relative_v3(descriptor["manifest"])
    payload = read_bounded_v3(manifest, MAX_MANIFEST_BYTES)
    if sha256_bytes(payload) != descriptor["manifestSha256"]:
        raise ValueError("runtime_v3_source_manifest_changed")
    doc = loads_strict_json_object(payload.decode())
    for key in ("garmentId", "avatarId"):
        if key in doc and doc[key] != descriptor[key]:
            raise ValueError("runtime_v3_source_identity_mismatch")
    inventory = doc["inventory"]
    if doc.get("packageVersion") == "closy.manual_provider_binding_v2.package.v2":
        # Explicit producer-format adapter; never relabel the source as runtime V3.
        # The original manifest hash above remains the external provenance anchor.
        if descriptor["bindingCodec"] != LOCAL_FRAME_CODEC:
            raise ValueError("runtime_v3_source_binding_codec_mismatch")
        inventory = [
            {"path": row["path"], "sha256": row["sha256"], "byteSize": row["bytes"]}
            for row in inventory
        ]
    rows = inventory_v3(inventory, RuntimeV2Limits())
    for relative, row in rows.items():
        data = read_bounded_v3(root / relative, row["byteSize"])
        if len(data) != row["byteSize"] or sha256_bytes(data) != row["sha256"]:
            raise ValueError(f"runtime_v3_source_inventory_mismatch:{relative}")
    for key in ("render", "cage", "binding"):
        if safe_relative_v3(descriptor[key]) not in rows:
            raise ValueError("runtime_v3_source_geometry_not_in_inventory")
    for path in descriptor.get("cagePoses", {}).values():
        if safe_relative_v3(path) not in rows:
            raise ValueError("runtime_v3_source_pose_not_in_inventory")
    # Either canonical identity or exact manifest bytes may serve as explicit provenance.
    if descriptor["provenance"] not in (doc.get("packageIdentity"), descriptor["manifestSha256"]):
        raise ValueError("runtime_v3_source_provenance_mismatch")
    return root, doc


def declare(input_root: Path, output: Path, representatives: Path | None) -> dict[str, Any]:
    if output.exists():
        raise ValueError("runtime_v3_protocol_output_must_be_fresh")
    cases: list[dict[str, Any]] = []
    for family in FAMILIES:
        source = input_descriptor(input_root / family / "nominal", family)
        for profile in PROFILES:
            for build in (1, 2):
                cases.append(
                    {
                        "id": f"{family}-{profile.profile_id}-build{build}",
                        "group": "family",
                        "case": family,
                        "build": build,
                        "profile": profile.profile_id,
                        "source": source,
                    }
                )
    extras = object_file(representatives)["cases"] if representatives else []
    identifiers: set[str] = set(FAMILIES)
    for extra in extras:
        identifier = safe_relative_v3(extra["caseId"])
        if (
            "/" in identifier
            or identifier in identifiers
            or extra["kind"] not in ("binding", "outfit")
        ):
            raise ValueError("runtime_v3_representative_id_invalid")
        identifiers.add(identifier)
        if extra["kind"] == "binding" and extra["bindingCodec"] != LOCAL_FRAME_CODEC:
            raise ValueError("runtime_v3_representative_binding_codec_invalid")
        if extra["kind"] == "outfit" and len(extra.get("members", [])) < 2:
            raise ValueError("runtime_v3_representative_outfit_members_required")
        verify_source(extra)
        for profile in PROFILES:
            for build in (1, 2):
                cases.append(
                    {
                        "id": f"{identifier}-{profile.profile_id}-build{build}",
                        "group": extra["kind"],
                        "case": identifier,
                        "build": build,
                        "profile": profile.profile_id,
                        "source": extra,
                    }
                )
    for case in cases:
        source_root = Path(case["source"]["root"]).resolve()
        if output.resolve() == source_root or source_root in output.resolve().parents:
            raise ValueError("runtime_v3_output_inside_readonly_source")
    historical = FORGE / "docs/evidence/static_zeroone_runtime_v2/result.json"
    collect = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-o",
            "addopts=",
            "-q",
            "-p",
            "no:cacheprovider",
            "tests/unit/test_runtime_v3.py",
        ],
        cwd=FORGE,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if collect.returncode:
        raise ValueError(f"runtime_v3_control_inventory_failed:{collect.stderr}")
    protocol: dict[str, Any] = {
        "protocolVersion": VERSION,
        "sourceInventory": code_inventory(),
        "python": sys.version,
        "platform": platform.platform(),
        "familyRows": 36,
        "poseRowsPerBuild": 4,
        "resumeRowsPerBuild": 3,
        "profiles": [asdict(p) for p in PROFILES],
        "cases": cases,
        "thresholds": {
            "codecLimits": asdict(RuntimeV2Limits()),
            "maximumVertices": MAX_VERTICES,
            "maximumTriangles": MAX_TRIANGLES,
            "maximumCoordinateMeters": MAX_COORDINATE_M,
            "minimumTriangleAreaM2": MINIMUM_AREA_M2,
            "bindingFidelityMeters": BINDING_TOLERANCE_M,
            "poseEncodingErrorMeters": 1e-6,
            "localFrameRestMeters": 0.008,
        },
        "resumePoints": ["first", "middle", "final"],
        "poseIds": list(POSE_IDS),
        "motionScope": "analytic_cage_binding_fidelity_not_articulated_avatar_or_cloth",
        "workerTimeoutSeconds": 180,
        "controlTimeoutSeconds": 180,
        "controlInventory": [line for line in collect.stdout.splitlines() if "::test_" in line],
        "historicalV2": {
            "path": str(historical),
            "sha256": sha256_file(historical),
            "controlsPassed": 8,
            "controlsTotal": 9,
            "crossPackageActual": "transfer_chunk_size_mismatch",
            "crossPackageExpected": "transfer_chunk_hash_mismatch",
            "preservedNotRerun": True,
        },
        "physicalMobile": {
            "latency": "not_run",
            "memory": "not_run",
            "battery": "not_run",
            "thermal": "not_run",
        },
        "hostTimingAcceptance": "measurement_only_no_physical_mobile_claim",
        "optionalZeroOne": "not_selected_conventional_only",
        "dynamicZ2": "not_run",
        "requiredRepresentativeKinds": ["binding", "outfit"],
    }
    protocol["protocolIdentity"] = sha256_bytes(canonical_dumps(protocol).encode())
    output.mkdir(parents=True)
    atomic_json(output / "protocol.json", protocol)
    atomic_json(
        output / "checkpoint.json",
        {
            "protocolIdentity": protocol["protocolIdentity"],
            "rows": {},
            "controls": {"status": "not_run"},
        },
    )
    return protocol


def evaluate_case(case: dict[str, Any], output: Path) -> dict[str, Any]:
    """Public hook for a parent's inventoried A/B/whole-outfit source, without rebuilding it."""
    started, cpu = time.perf_counter(), time.process_time()
    tracemalloc.start()
    try:
        root, _ = verify_source(case["source"])
        source = case["source"]
        profile = next(p for p in PROFILES if p.profile_id == case["profile"])
        identity = RuntimeIdentityV3(
            source["garmentId"], source["avatarId"], profile.profile_id, source["provenance"]
        )
        cage_bytes = read_bounded_v3(root / source["cage"], RuntimeV2Limits().max_file_bytes)
        render_bytes = read_bounded_v3(root / source["render"], RuntimeV2Limits().max_file_bytes)
        cage, render = decode_glb_v3(cage_bytes), decode_glb_v3(render_bytes)
        binding = decode_binding_v3(
            read_bounded_v3(root / source["binding"], RuntimeV2Limits().max_file_bytes),
            cage,
            render,
            binding_codec=source["bindingCodec"],
            cage_glb=cage_bytes,
            render_glb=render_bytes,
        )
        pose_paths = source.get("cagePoses")
        poses = (
            {
                p: list(
                    decode_pose_positions(
                        read_bounded_v3(root / pose_paths[p], 12 + MAX_VERTICES * 12)
                    )
                )
                for p in POSE_IDS
            }
            if pose_paths
            else analytic_cage_poses_v3(cage)
        )
        dense = bound_pose_positions_v3(cage, binding, poses)
        members = tuple(
            RuntimeIdentityV3(m["garmentId"], m["avatarId"], profile.profile_id, m["provenance"])
            for m in source.get("members", [])
        )
        inputs = RuntimeV2Inputs(
            identity.garment_id,
            identity.provenance,
            root / source["render"],
            source.get("materials", {"development": {"roughness": 0.8}}),
            # Valid authored 1x1 PNG, solely a transport thumbnail fixture.
            bytes.fromhex(
                "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
                "0000000b49444154789c636000020000050001a5f645400000000049454e44ae426082"
            ),
            dense,
            source.get("zeroOneDerivativeDigest"),
        )
        package = output / "package"
        build_runtime_package_v3(
            package,
            inputs=inputs,
            profile=profile,
            identity=identity,
            cage=root / source["cage"],
            binding=root / source["binding"],
            cage_poses=poses,
            outfit_members=members,
            binding_codec=source["bindingCodec"],
        )
        digest = sha256_file(package / "manifest.json")
        load_start = time.perf_counter()
        loaded = load_runtime_package_v3(package, expected=identity, trusted_manifest_hash=digest)
        load_seconds = time.perf_counter() - load_start
        encoding_error = max(
            abs(a - b)
            for p in POSE_IDS
            for x, y in zip(dense[p], loaded.pose_positions[p], strict=True)
            for a, b in zip(x, y, strict=True)
        )
        if encoding_error > 1e-6 or loaded.conventional_fallback_glb != render_bytes:
            raise ValueError("runtime_v3_pose_encoding_or_fallback_identity_failed")
        stream = build_runtime_stream_v3(
            package,
            expected=identity,
            trusted_manifest_hash=digest,
            chunk_size=profile.transport_chunk_bytes,
        )
        ready = stream.manifest["fallbackReadyChunkCount"]
        prefix_start = time.perf_counter()
        fallback = load_prefix_v3(
            b"".join(stream.chunks[:ready]), expected=identity, trusted_manifest_hash=digest
        )
        prefix_seconds = time.perf_counter() - prefix_start
        if fallback != render_bytes:
            raise ValueError("runtime_v3_prefix_identity_failed")
        resumes = []
        for label, cut in (
            ("first", 1),
            ("middle", max(1, len(stream.chunks) // 2)),
            ("final", max(1, len(stream.chunks) - 1)),
        ):
            cache = output / f"cache-{label}"
            receiver = receive_v3(
                cache,
                stream,
                session_id="resume",
                expected=identity,
                trusted_transfer_hash=transfer_identity_v3(stream.manifest),
            )
            for i in range(cut):
                receiver.receive(i, stream.chunks[i])
            resumed = receive_v3(
                cache,
                stream,
                session_id="resume",
                expected=identity,
                trusted_transfer_hash=transfer_identity_v3(stream.manifest),
            )
            saved = resumed.resume_bytes_saved
            for i in resumed.missing_indices:
                resumed.receive(i, stream.chunks[i])
            archive = resumed.finalize(output / f"{label}.archive")
            delivered = materialize_v3(
                archive.read_bytes(),
                output / f"reloaded-{label}",
                expected=identity,
                trusted_manifest_hash=digest,
                trusted_archive_hash=stream.manifest["aggregateSha256"],
            )
            match = (
                delivered.package_identity == loaded.package_identity
                and delivered.pose_positions == loaded.pose_positions
                and delivered.conventional_fallback_glb == render_bytes
            )
            if not match or saved != sum(map(len, stream.chunks[:cut])):
                raise ValueError("runtime_v3_resume_identity_failed")
            resumes.append(
                {
                    "point": label,
                    "cut": cut,
                    "resumeBytesSaved": saved,
                    "aggregateHashMatch": True,
                    "decodedIdentityMatch": match,
                }
            )
        manifest = object_file(package / "payload.closyruntime/manifest.json")
        report = object_file(package / "payload.closyruntime/build_report.json")
        verify_source(source)
        return {
            "status": "pass",
            "caseId": case["id"],
            "group": case["group"],
            "packageIdentity": loaded.package_identity,
            "manifestSha256": digest,
            "streamSha256": stream.manifest["aggregateSha256"],
            "transferIdentity": transfer_identity_v3(stream.manifest),
            "packageBytes": sum(p.stat().st_size for p in package.rglob("*") if p.is_file()),
            "streamBytes": len(stream.payload),
            "streamChunkCount": len(stream.chunks),
            "compressedPayloadBytes": report["compressedPayloadBytes"],
            "equivalentV1DuplicateBytes": report["equivalentPayloadV1DuplicateBytes"],
            "maximumDecodedPageBytes": max(b["decodedBytes"] for b in manifest["blobs"].values()),
            "maximumPageExpansion": max(
                b["decodedBytes"] / b["compressedBytes"] for b in manifest["blobs"].values()
            ),
            "maximumPoseEncodingErrorM": encoding_error,
            "maximumBindingFidelityErrorM": loaded.maximum_binding_error_m,
            "poseCount": len(loaded.pose_positions),
            "resumes": resumes,
            "prefix": {"readyChunkCount": ready, "verified": True, "hostSeconds": prefix_seconds},
            "hostLoadSeconds": load_seconds,
            "hostWallSeconds": time.perf_counter() - started,
            "hostCpuSeconds": time.process_time() - cpu,
            "hostPeakPythonAllocatedBytes": tracemalloc.get_traced_memory()[1],
            "physicalMobile": "not_run",
            "outfitMembers": len(loaded.outfit_members),
            "sourceQuality": source.get("sourceQuality", "outside_runtime_scope"),
            "motionScope": "persisted_cage_poses" if pose_paths else "analytic_cage_drivers",
        }
    finally:
        tracemalloc.stop()


def run(protocol: dict[str, Any], output: Path) -> int:
    identity_doc = dict(protocol)
    claimed = identity_doc.pop("protocolIdentity")
    if claimed != sha256_bytes(canonical_dumps(identity_doc).encode()):
        raise ValueError("runtime_v3_protocol_identity_mismatch")
    if protocol["sourceInventory"] != code_inventory() or protocol["python"] != sys.version:
        raise ValueError("runtime_v3_stale_source_or_python_protocol")
    if sha256_file(Path(protocol["historicalV2"]["path"])) != protocol["historicalV2"]["sha256"]:
        raise ValueError("runtime_v3_historical_evidence_changed")
    state = object_file(output / "checkpoint.json")
    if state["protocolIdentity"] != claimed:
        raise ValueError("runtime_v3_checkpoint_protocol_mismatch")
    for case in protocol["cases"]:
        identifier = case["id"]
        folder = output / identifier
        receipt = folder / "receipt.json"
        previous = state["rows"].get(identifier)
        if previous is not None:
            # Recover completed durable workers; never silently rerun an interrupted attempt.
            if previous["status"] == "running":
                state["rows"][identifier] = (
                    object_file(receipt)
                    if receipt.exists()
                    else {"status": "unknown", "reason": "receipt_missing"}
                )
                atomic_json(output / "checkpoint.json", state)
            saved = state["rows"][identifier]
            if saved["status"] == "pass":
                try:
                    if saved.get("protocolIdentity") != claimed or saved.get("workerExitCode") != 0:
                        raise ValueError("runtime_v3_saved_receipt_identity_invalid")
                    source, _ = verify_source(case["source"])
                    expected = RuntimeIdentityV3(
                        case["source"]["garmentId"],
                        case["source"]["avatarId"],
                        case["profile"],
                        case["source"]["provenance"],
                    )
                    loaded = load_runtime_package_v3(
                        folder / "package",
                        expected=expected,
                        trusted_manifest_hash=saved["manifestSha256"],
                    )
                    if loaded.conventional_fallback_glb != read_bounded_v3(
                        source / case["source"]["render"], RuntimeV2Limits().max_file_bytes
                    ):
                        raise ValueError("runtime_v3_saved_fallback_changed")
                except (ValueError, OSError, KeyError) as error:
                    state["rows"][identifier] = {**saved, "status": "fail", "error": str(error)}
                    atomic_json(output / "checkpoint.json", state)
            continue
        folder.mkdir()
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--worker",
            identifier,
            "--output",
            str(output),
        ]
        state["rows"][identifier] = {"status": "running", "command": command}
        atomic_json(output / "checkpoint.json", state)
        with (folder / "process.log").open("w", encoding="utf-8") as log:
            try:
                result = subprocess.run(
                    command,
                    cwd=FORGE,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=protocol["workerTimeoutSeconds"],
                    check=False,
                )
                row = object_file(receipt) if receipt.exists() else {"status": "unknown"}
                row["processExitCode"] = result.returncode
                if result.returncode != 0:
                    row["status"] = "fail"
            except subprocess.TimeoutExpired:
                row = {"status": "fail", "reason": "worker_timeout", "processExitCode": None}
        atomic_json(receipt, row)
        state["rows"][identifier] = row
        atomic_json(output / "checkpoint.json", state)
    if state["controls"]["status"] == "running":
        state["controls"] = {"status": "unknown", "reason": "control_exit_receipt_missing"}
        atomic_json(output / "checkpoint.json", state)
    controls = state["controls"]
    if controls["status"] == "not_run":
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "tests/unit/test_runtime_v3.py",
            f"--junitxml={output / 'controls.xml'}",
        ]
        state["controls"] = {"status": "running", "command": command}
        atomic_json(output / "checkpoint.json", state)
        with (output / "controls.log").open("w", encoding="utf-8") as log:
            try:
                result = subprocess.run(
                    command,
                    cwd=FORGE,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=protocol["controlTimeoutSeconds"],
                    check=False,
                )
                state["controls"] = {
                    "status": "pass" if result.returncode == 0 else "fail",
                    "processExitCode": result.returncode,
                    "command": command,
                }
            except subprocess.TimeoutExpired:
                state["controls"] = {"status": "fail", "reason": "control_timeout"}
        atomic_json(output / "checkpoint.json", state)
    pairs = []
    for case in protocol["cases"]:
        if case["build"] != 1:
            continue
        other_id = case["id"].removesuffix("build1") + "build2"
        a, b = state["rows"][case["id"]], state["rows"][other_id]
        pairs.append(
            {
                "case": case["case"],
                "profile": case["profile"],
                "passed": a["status"] == b["status"] == "pass"
                and all(
                    a.get(k) == b.get(k)
                    for k in (
                        "packageIdentity",
                        "manifestSha256",
                        "streamSha256",
                        "transferIdentity",
                    )
                ),
            }
        )
    missing = [
        kind
        for kind in protocol["requiredRepresentativeKinds"]
        if not any(c["group"] == kind for c in protocol["cases"])
    ]
    fresh = protocol["sourceInventory"] == code_inventory()
    passed = (
        all(r["status"] == "pass" for r in state["rows"].values())
        and all(p["passed"] for p in pairs)
        and state["controls"]["status"] == "pass"
        and not missing
        and fresh
    )
    summary = {
        "protocolIdentity": claimed,
        "status": "pass" if passed else "incomplete_or_failed",
        "family": {
            status: sum(
                c["group"] == "family" and state["rows"][c["id"]]["status"] == status
                for c in protocol["cases"]
            )
            for status in ("pass", "fail", "unknown")
        },
        "rows": state["rows"],
        "controls": state["controls"],
        "determinism": pairs,
        "missingRepresentativeKinds": missing,
        "sourceFresh": fresh,
        "physicalMobile": protocol["physicalMobile"],
        "historicalV2": protocol["historicalV2"],
    }
    atomic_json(output / "result.json", summary)
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, default=FORGE / ".tmp/family-final-v2/build1")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--representatives", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--declare-only", action="store_true")
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--worker")
    args = parser.parse_args()
    output = args.output.resolve()
    reject_links_v3(args.output)
    if args.declare_only:
        declare(args.input_root.resolve(), output, args.representatives)
        print("Protocol declared; no runtime matrix executed.")
        return 0
    protocol = object_file(output / "protocol.json")
    if args.worker:
        case = next(c for c in protocol["cases"] if c["id"] == args.worker)
        folder = output / safe_relative_v3(args.worker)
        started = time.perf_counter()
        try:
            if protocol["sourceInventory"] != code_inventory():
                raise ValueError("runtime_v3_worker_source_changed")
            receipt = evaluate_case(case, folder)
            if protocol["sourceInventory"] != code_inventory():
                raise ValueError("runtime_v3_worker_source_changed_during_evaluation")
            receipt["workerExitCode"] = 0
        except Exception as error:
            receipt = {
                "status": "fail",
                "caseId": case["id"],
                "workerExitCode": 1,
                "error": f"{type(error).__name__}:{error}",
                "hostWallSeconds": time.perf_counter() - started,
            }
        receipt["protocolIdentity"] = protocol["protocolIdentity"]
        atomic_json(folder / "receipt.json", receipt)
        return int(receipt["workerExitCode"])
    return run(protocol, output)


if __name__ == "__main__":
    raise SystemExit(main())
