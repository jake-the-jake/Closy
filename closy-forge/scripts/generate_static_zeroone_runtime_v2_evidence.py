from __future__ import annotations

import argparse
import json
import math
import platform
import shutil
import statistics
import subprocess
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from closy_forge.geometry.glb_io import audit_glb_geometry, read_glb_meshset
from closy_forge.package_io.canonical_json import read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.package_io.managed_output import (
    cleanup_managed_staging,
    create_managed_staging,
)
from closy_forge.pipeline.build_button_shirt_demo import build_demo_button_shirt_package
from closy_forge.pipeline.build_jacket_outerwear_demo import (
    build_demo_jacket_outerwear_package,
)
from closy_forge.pipeline.build_layered_asymmetric_demo import (
    build_demo_layered_asymmetric_package,
)
from closy_forge.pipeline.build_long_sleeved_demo import build_demo_long_sleeved_package
from closy_forge.pipeline.build_simple_dress_demo import build_demo_simple_dress_package
from closy_forge.pipeline.build_simple_skirt_demo import build_demo_simple_skirt_package
from closy_forge.pipeline.build_simple_trousers_demo import (
    build_demo_simple_trousers_package,
)
from closy_forge.pipeline.build_sleeveless_demo import build_demo_sleeveless_package
from closy_forge.pipeline.build_tshirt_demo import build_demo_tshirt_package
from closy_forge.raster import encode_png_rgba
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
    RuntimeStreamV2,
    build_runtime_stream_v2,
    load_fallback_from_archive_prefix_v2,
    materialize_runtime_archive_v2,
)
from closy_forge.zeroone.integration import integrate_zeroone_static
from closy_forge.zeroone.static_stage_audit_v2 import audit_static_zeroone_stages
from closy_forge.zeroone.tool import resolve_zeroone_tool

PROTOCOL_ID = "CLOSY-STATIC-ZEROONE-RUNTIME-V2-20260904"
ZEROONE_SHA = "9cbae4a8e6ef2e61c1839ecbdf8a462aaa560027"
PROFILES = (
    RuntimeV2Profile("cpu-balanced-64k-v2", 65_536, 32_768),
    RuntimeV2Profile("cpu-compact-32k-v2", 32_768, 16_384),
)
BUILDERS: tuple[tuple[str, Callable[..., Any]], ...] = (
    ("tshirt", build_demo_tshirt_package),
    ("sleeveless_top", build_demo_sleeveless_package),
    ("long_sleeved_top", build_demo_long_sleeved_package),
    ("simple_skirt", build_demo_simple_skirt_package),
    ("simple_trousers", build_demo_simple_trousers_package),
    ("simple_dress", build_demo_simple_dress_package),
    ("button_shirt", build_demo_button_shirt_package),
    ("jacket_outerwear", build_demo_jacket_outerwear_package),
    ("layered_asymmetric", build_demo_layered_asymmetric_package),
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate static ZeroOne/runtime v2 evidence.")
    parser.add_argument("--executable", required=True, type=Path)
    parser.add_argument("--trusted-build-record", required=True, type=Path)
    parser.add_argument("--zeroone-repo", required=True, type=Path)
    parser.add_argument("--closy-sha", required=True)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    forge_root = Path(__file__).resolve().parents[1]
    repository = forge_root.parent
    _require_head(repository, args.closy_sha)
    _require_head(args.zeroone_repo, ZEROONE_SHA)
    if _content_dirty(repository) or _content_dirty(args.zeroone_repo):
        raise RuntimeError("evidence_source_checkout_must_be_clean")
    protocol = read_json(forge_root / "fixtures/static_zeroone_runtime_v2/protocol.json")
    if protocol.get("protocolId") != PROTOCOL_ID:
        raise RuntimeError("static_runtime_protocol_identity_mismatch")
    tool = resolve_zeroone_tool(
        args.executable,
        trusted_build_record=args.trusted_build_record,
        expected_source_sha=ZEROONE_SHA,
    )
    if not tool.available:
        raise RuntimeError(f"trusted_zeroone_unavailable:{tool.reason}")

    requested = args.work_root.resolve(strict=False)
    work = create_managed_staging(
        requested,
        allowed_root=requested.parent,
        purpose="static-runtime-v2-evidence",
    )
    tracemalloc.start()
    started_wall = time.perf_counter_ns()
    started_cpu = time.process_time_ns()
    try:
        packages = _build_packages(work)
        static_rows: list[dict[str, Any]] = []
        runtime_rows: list[dict[str, Any]] = []
        streams: list[RuntimeStreamV2] = []
        package_paths: list[Path] = []
        for family, package, manifest in packages:
            fallback = package / "render" / "fallback.glb"
            fallback_before = sha256_file(fallback)
            static_started = time.perf_counter_ns()
            integration = integrate_zeroone_static(
                package=package,
                invocation_root=work,
                closy_sha=args.closy_sha,
                executable=args.executable,
                trusted_build_record=args.trusted_build_record,
                expected_executable_sha256=tool.executable_sha256,
                expected_zeroone_sha=ZEROONE_SHA,
                publish=True,
            )
            static_elapsed = time.perf_counter_ns() - static_started
            if integration.status != "valid":
                raise RuntimeError(f"zeroone_static_failed:{family}:{integration.reason}")
            derivative = package / "zeroone/static-d0/derivative"
            stage_audit = audit_static_zeroone_stages(
                derivative,
                canonical_package=package,
            )
            if stage_audit["failedStageIds"]:
                raise RuntimeError(f"zeroone_stage_audit_failed:{family}")
            if sha256_file(fallback) != fallback_before:
                raise RuntimeError(f"conventional_fallback_changed:{family}")
            static_rows.append(
                {
                    "family": family,
                    "garmentId": manifest["garmentId"],
                    "canonicalPackageDigest": _package_digest(manifest, package),
                    "integration": integration.to_json(),
                    "stageAudit": stage_audit,
                    "validationNanoseconds": static_elapsed,
                    "fallbackSha256Before": fallback_before,
                    "fallbackSha256After": sha256_file(fallback),
                }
            )
            poses = _pose_positions(fallback)
            geometry_audit = audit_glb_geometry(fallback)
            if geometry_audit["status"] != "pass":
                raise RuntimeError(f"fallback_geometry_invalid:{family}")
            for profile in PROFILES:
                for rebuild in (1, 2):
                    runtime_path = (
                        work / f"runtime-{family}-{profile.profile_id}-{rebuild}.closyruntime"
                    )
                    build_started = time.perf_counter_ns()
                    build_runtime_package_v2(
                        runtime_path,
                        inputs=RuntimeV2Inputs(
                            garment_id=str(manifest["garmentId"]),
                            canonical_package_digest=_package_digest(manifest, package),
                            conventional_fallback_glb=fallback,
                            material_set=_material_set(package),
                            thumbnail_png=_thumbnail(family),
                            pose_positions=poses,
                            zeroone_derivative_digest=str(
                                integration.report["canonicalDerivativeHash"]
                            ),
                        ),
                        profile=profile,
                    )
                    build_elapsed = time.perf_counter_ns() - build_started
                    runtime_row, stream = _audit_runtime_build(
                        runtime_path,
                        fallback,
                        poses,
                        profile,
                        family,
                        rebuild,
                        work,
                        build_elapsed,
                        geometry_audit,
                    )
                    runtime_rows.append(runtime_row)
                    streams.append(stream)
                    package_paths.append(runtime_path)

        _assert_runtime_rebuilds(runtime_rows)
        negative = _negative_matrix(package_paths[0], streams[0], streams[-1], work)
        current, peak = tracemalloc.get_traced_memory()
        result = {
            "schemaVersion": 1,
            "resultVersion": "closy.static_zeroone_runtime_v2.result.v1",
            "protocolId": PROTOCOL_ID,
            "protocolDigest": protocol["protocolDigest"],
            "classification": "public_synthetic_static_runtime_engineering_host_cpu_only",
            "source": {
                "closyCommit": args.closy_sha,
                "closyTree": _git(repository, "rev-parse", "HEAD^{tree}"),
                "zeroOneCommit": ZEROONE_SHA,
                "zeroOneTree": _git(args.zeroone_repo, "rev-parse", "HEAD^{tree}"),
                "zeroOneExecutableSha256": tool.executable_sha256,
                "zeroOneVersion": tool.version,
                "trustedBuildRecordSha256": sha256_file(args.trusted_build_record),
            },
            "host": {
                "platform": platform.system().lower(),
                "architecture": platform.machine().lower(),
                "python": platform.python_version(),
                "cpuOnly": True,
                "measurementScope": "host_cpu_not_mobile_gpu_battery_thermal_or_network",
            },
            "denominators": {
                "staticFamilyCount": len(static_rows),
                "runtimeBuildCount": len(runtime_rows),
                "profileCount": len(PROFILES),
                "cleanRebuildsPerProfile": 2,
                "poseCountPerBuild": 4,
                "resumePointCountPerBuild": 3,
                "negativeCaseCount": len(negative),
            },
            "staticZeroOne": static_rows,
            "conventionalRuntime": runtime_rows,
            "negativeCases": negative,
            "performance": {
                "totalWallNanoseconds": time.perf_counter_ns() - started_wall,
                "totalCpuNanoseconds": time.process_time_ns() - started_cpu,
                "pythonTracedCurrentBytes": current,
                "pythonTracedPeakBytes": peak,
                "zeroOnePeakMemoryBytesMaximum": max(
                    _zeroone_peak(row["integration"]) for row in static_rows
                ),
                "sampleScope": "actual_host_process_reports_and_python_tracemalloc",
            },
            "stageOutcome": {
                "Z3": "not_run_processor_emits_no_per_detail_classification",
                "Z4": "passed_actual_cluster_payloads_decoded",
                "Z5": "passed_actual_hierarchy_and_lod_decoded",
                "Z6": "passed_actual_page_ranges_residency_and_dependencies_decoded",
                "Z7": "not_run_processor_emits_no_recorded_or_procedural_detail_payload",
                "Z8": "passed_actual_derivative_export_and_source_identity_decoded",
            },
            "acceptance": {
                "allNineFamiliesProcessed": len(static_rows) == 9,
                "allSupportedStaticStagesPassed": all(
                    not row["stageAudit"]["failedStageIds"] for row in static_rows
                ),
                "unsupportedStaticStagesPreservedNotRun": all(
                    row["stageAudit"]["notRunStageIds"] == ["Z3", "Z7"] for row in static_rows
                ),
                "allThirtySixRuntimeBuildsPassed": len(runtime_rows) == 36,
                "allRuntimeRebuildsDeterministic": True,
                "allPoseReconstructionsWithinOneMicrometre": all(
                    row["maximumPosePositionErrorMeters"] <= 1e-6 for row in runtime_rows
                ),
                "allFallbacksAvailableFromVerifiedPrefix": all(
                    row["fallbackPrefix"]["verified"] for row in runtime_rows
                ),
                "allResumePointsExact": all(
                    all(item["aggregateHashMatch"] for item in row["resume"])
                    for row in runtime_rows
                ),
                "allNegativeCasesRejectedOrRecovered": all(
                    row["passed"] for row in negative.values()
                ),
                "canonicalAuthorityChanged": False,
                "productRuntimeDefaultChanged": False,
                "dynamicZ2Claimed": False,
                "mobileClaimed": False,
                "gpuClaimed": False,
                "productionNetworkClaimed": False,
                "globalBlueprintComplete": False,
            },
            "literalOutcome": "static_runtime_v2_scoped_host_cpu_pass_global_partial",
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_canonical_json(args.output, result)
        print(
            json.dumps(
                {
                    "output": args.output.as_posix(),
                    "literalOutcome": result["literalOutcome"],
                    "staticFamilyCount": len(static_rows),
                    "runtimeBuildCount": len(runtime_rows),
                },
                sort_keys=True,
            )
        )
        return 0
    finally:
        tracemalloc.stop()
        cleanup_managed_staging(
            work,
            allowed_root=requested.parent,
            purpose="static-runtime-v2-evidence",
        )


def _build_packages(work: Path) -> list[tuple[str, Path, dict[str, Any]]]:
    rows: list[tuple[str, Path, dict[str, Any]]] = []
    for family, builder in BUILDERS:
        package = work / f"{family}.closygarment"
        build = builder(package, force=False)
        rows.append((family, package, dict(build.manifest)))
    return rows


def _audit_runtime_build(
    package: Path,
    fallback: Path,
    expected_poses: dict[str, list[tuple[float, float, float]]],
    profile: RuntimeV2Profile,
    family: str,
    rebuild: int,
    work: Path,
    build_nanoseconds: int,
    geometry_audit: dict[str, Any],
) -> tuple[dict[str, Any], RuntimeStreamV2]:
    load_samples: list[int] = []
    loaded = None
    for _ in range(5):
        started = time.perf_counter_ns()
        loaded = load_runtime_package_v2(package)
        load_samples.append(time.perf_counter_ns() - started)
    assert loaded is not None
    position_error = max(
        abs(left - right)
        for pose_id, expected in expected_poses.items()
        for expected_row, actual_row in zip(expected, loaded.pose_positions[pose_id], strict=True)
        for left, right in zip(expected_row, actual_row, strict=True)
    )
    if position_error > 1e-6 or loaded.conventional_fallback_glb != fallback.read_bytes():
        raise RuntimeError(
            f"runtime_decode_identity_failed:{family}:{profile.profile_id}:{rebuild}"
        )
    bounds_valid = all(
        _bounds_contain(loaded.pose_positions[pose_id]) for pose_id in expected_poses
    )
    if not bounds_valid:
        raise RuntimeError("runtime_pose_bounds_invalid")
    stream = build_runtime_stream_v2(package, chunk_size=profile.transport_chunk_bytes)
    prefix_count = int(stream.manifest["fallbackReadyChunkCount"])
    prefix = b"".join(stream.chunks[:prefix_count])
    fallback_samples: list[int] = []
    for _ in range(5):
        started = time.perf_counter_ns()
        prefix_fallback = load_fallback_from_archive_prefix_v2(prefix)
        fallback_samples.append(time.perf_counter_ns() - started)
    if prefix_fallback != fallback.read_bytes():
        raise RuntimeError("fallback_prefix_identity_failed")
    resumes = [
        _resume(stream, 1, "first", work, family, profile.profile_id, rebuild),
        _resume(
            stream,
            max(1, len(stream.chunks) // 2),
            "middle",
            work,
            family,
            profile.profile_id,
            rebuild,
        ),
        _resume(
            stream,
            max(1, len(stream.chunks) - 1),
            "final",
            work,
            family,
            profile.profile_id,
            rebuild,
        ),
    ]
    manifest = read_json(package / "manifest.json")
    report = read_json(package / "build_report.json")
    return (
        {
            "family": family,
            "profileId": profile.profile_id,
            "rebuild": rebuild,
            "packageDigest": loaded.package_digest,
            "packageBytes": sum(
                path.stat().st_size for path in package.rglob("*") if path.is_file()
            ),
            "compressedPayloadBytes": report["compressedPayloadBytes"],
            "equivalentDuplicateStorageV1Bytes": report["equivalentPayloadV1DuplicateBytes"],
            "smallerThanEquivalentDuplicateStorageV1": report[
                "smallerThanEquivalentDuplicateStorageV1"
            ],
            "uniqueCompressedBlobCount": report["uniqueCompressedBlobCount"],
            "assetPageCount": sum(len(row["pages"]) for row in manifest["assets"].values()),
            "maximumDecodedPageBytes": max(
                int(row["decodedBytes"]) for row in manifest["blobs"].values()
            ),
            "maximumDecompressionRatio": max(
                float(row["decodedBytes"]) / float(row["compressedBytes"])
                for row in manifest["blobs"].values()
            ),
            "maximumPosePositionErrorMeters": position_error,
            "poseBoundsContainEveryVertex": bounds_valid,
            "glbGeometryAudit": geometry_audit,
            "buildNanoseconds": build_nanoseconds,
            "load": _samples(load_samples),
            "fallbackPrefix": {
                "verified": True,
                "readyChunkCount": prefix_count,
                "totalChunkCount": len(stream.chunks),
                "timeToFirstRenderable": _samples(fallback_samples),
            },
            "streamBytes": len(stream.payload),
            "streamChunkCount": len(stream.chunks),
            "resume": resumes,
            "claims": {
                "hostCpu": True,
                "mobile": False,
                "gpu": False,
                "network": False,
            },
        },
        stream,
    )


def _resume(
    stream: RuntimeStreamV2,
    cutoff: int,
    label: str,
    work: Path,
    family: str,
    profile: str,
    rebuild: int,
) -> dict[str, Any]:
    session = f"{family[:8]}-{profile[-6:]}-{rebuild}-{label}"
    cache = work / "transfer-cache"
    receiver = RuntimeStreamReceiverV2(cache, stream, session_id=session)
    for index in range(cutoff):
        receiver.receive(index, stream.chunks[index])
    saved = receiver.resume_bytes_saved
    resumed = RuntimeStreamReceiverV2(cache, stream, session_id=session)
    for index in resumed.missing_indices:
        resumed.receive(index, stream.chunks[index])
    target = work / f"archive-{session}.bin"
    resumed.finalize_archive(target)
    return {
        "point": label,
        "interruptedAfterChunkCount": cutoff,
        "resumeBytesSaved": saved,
        "aggregateHashMatch": sha256_file(target) == stream.manifest["aggregateSha256"],
    }


def _negative_matrix(
    package: Path,
    stream: RuntimeStreamV2,
    other_stream: RuntimeStreamV2,
    work: Path,
) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}

    receiver = RuntimeStreamReceiverV2(work / "negative-cache", stream, session_id="corrupt")
    corrupt = bytearray(stream.chunks[0])
    corrupt[-1] ^= 1
    output["corrupt_chunk"] = _expects(
        lambda: receiver.receive(0, bytes(corrupt)), "transfer_chunk_hash_mismatch"
    )
    receiver.receive(0, stream.chunks[0])
    output["corrupt_chunk"]["validReplacementAccepted"] = True
    output["truncated_stream"] = _expects(
        lambda: materialize_runtime_archive_v2(
            stream.payload[:-1], work / "negative-truncated.closyruntime"
        ),
        "transfer_v2_archive_truncated",
    )
    output["trailing_stream"] = _expects(
        lambda: materialize_runtime_archive_v2(
            stream.payload + b"x", work / "negative-trailing.closyruntime"
        ),
        "transfer_v2_archive_trailing_bytes",
    )
    stale_manifest = dict(stream.manifest)
    stale_manifest["streamVersion"] = "closy.runtime.stream.stale"
    output["stale_version"] = _expects(
        lambda: RuntimeStreamReceiverV2(
            work / "negative-cache",
            RuntimeStreamV2(stale_manifest, stream.payload, stream.chunks),
            session_id="stale",
        ),
        "transfer_v2_version_unsupported",
    )
    common = min(len(stream.chunks), len(other_stream.chunks))
    differing = next(
        index for index in range(common) if stream.chunks[index] != other_stream.chunks[index]
    )
    output["cross_package_chunk"] = _expects(
        lambda: RuntimeStreamReceiverV2(
            work / "negative-cache", stream, session_id="cross"
        ).receive(differing, other_stream.chunks[differing]),
        "transfer_chunk_hash_mismatch",
    )
    output["decompression_bomb"] = _expects(
        lambda: load_runtime_package_v2(
            package,
            limits=RuntimeV2Limits(max_decompression_ratio=0.5),
        ),
        "runtime_v2_decompression_ratio_exceeded",
    )
    cancelled = RuntimeStreamReceiverV2(work / "negative-cache", stream, session_id="cancelled")
    cancelled.cancel()
    output["cancelled_transfer"] = _expects(
        lambda: cancelled.receive(0, stream.chunks[0]), "transfer_cancelled"
    )
    output["storage_quota_exceeded"] = _expects(
        lambda: build_runtime_stream_v2(
            package,
            chunk_size=64,
            limits=TransferLimits(max_chunk_bytes=64, max_total_bytes=100),
        ),
        "transfer_total_limit_exceeded",
    )

    last_good = work / "last-good.closyruntime"
    corrupted = work / "corrupted-profile.closyruntime"
    shutil.copytree(package, last_good)
    shutil.copytree(package, corrupted)
    blob = next((corrupted / "blobs").glob("*.zlib"))
    payload = bytearray(blob.read_bytes())
    payload[len(payload) // 2] ^= 1
    blob.write_bytes(payload)
    recovered = load_runtime_package_v2(corrupted, last_good_package=last_good)
    output["last_good_rollback"] = {
        "passed": recovered.package_digest == load_runtime_package_v2(last_good).package_digest,
        "reason": recovered.fallback_reason,
    }
    return output


def _expects(operation: Callable[[], object], code: str) -> dict[str, Any]:
    try:
        operation()
    except (RuntimePackageV2Error, TransferError) as error:
        return {"passed": str(error) == code, "failureReason": str(error)}
    return {"passed": False, "failureReason": None}


def _pose_positions(path: Path) -> dict[str, list[tuple[float, float, float]]]:
    meshset = read_glb_meshset(path)
    neutral = [vertex for mesh in meshset.meshes for vertex in mesh.vertices]
    if not neutral:
        raise RuntimeError("pose_source_vertices_empty")
    minimum_y = min(value[1] for value in neutral)
    maximum_y = max(value[1] for value in neutral)
    height = max(maximum_y - minimum_y, 1e-9)
    center_y = (minimum_y + maximum_y) * 0.5
    return {
        "pose.neutral": list(neutral),
        "pose.arms_up": [
            (x, y + 0.015 * abs(x), z + 0.005 * (y - minimum_y) / height) for x, y, z in neutral
        ],
        "pose.torso_twist": [
            _twist_y(vertex, 0.06 * (vertex[1] - center_y) / height) for vertex in neutral
        ],
        "pose.walk_stride": [
            (x, y, z + (0.018 if x >= 0.0 else -0.018) * (maximum_y - y) / height)
            for x, y, z in neutral
        ],
    }


def _twist_y(vertex: tuple[float, float, float], angle: float) -> tuple[float, float, float]:
    x, y, z = vertex
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return (x * cosine + z * sine, y, -x * sine + z * cosine)


def _bounds_contain(positions: tuple[tuple[float, float, float], ...]) -> bool:
    bounds = [
        (min(row[axis] for row in positions), max(row[axis] for row in positions))
        for axis in range(3)
    ]
    return all(
        minimum <= row[axis] <= maximum
        for row in positions
        for axis, (minimum, maximum) in enumerate(bounds)
    )


def _material_set(package: Path) -> dict[str, Any]:
    value = read_json(package / "render/materials.json")
    return {"source": value, "profile": "compact_pbr_reference_only"}


def _thumbnail(family: str) -> bytes:
    digest = bytes.fromhex(sha256_bytes(family.encode())[:6])
    pixel = bytes((*digest, 255))
    return cast(bytes, encode_png_rgba(8, 8, pixel * 64))


def _package_digest(manifest: dict[str, Any], package: Path) -> str:
    value = manifest.get("canonicalPackageDigest", manifest.get("packageDigest"))
    if isinstance(value, str) and len(value) == 64:
        return cast(str, value)
    return sha256_file(package / "manifest.json")


def _assert_runtime_rebuilds(rows: list[dict[str, Any]]) -> None:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((row["family"], row["profileId"]), []).append(row)
    if len(grouped) != 18 or any(
        len(group) != 2 or len({row["packageDigest"] for row in group}) != 1
        for group in grouped.values()
    ):
        raise RuntimeError("runtime_clean_rebuild_identity_failed")


def _samples(values: list[int]) -> dict[str, Any]:
    return {
        "sampleCount": len(values),
        "coldNanoseconds": values[0],
        "warmMedianNanoseconds": int(statistics.median(values[1:])),
        "minimumNanoseconds": min(values),
        "maximumNanoseconds": max(values),
    }


def _zeroone_peak(integration: dict[str, Any]) -> int:
    report = integration.get("report", {})
    candidates = [
        report.get(key, {}).get("peakMemoryBytes", 0)
        for key in ("cleanRunA", "cacheHitRun", "resumeRun", "cleanRunB")
    ]
    return max(int(value or 0) for value in candidates)


def _require_head(repository: Path, expected: str) -> None:
    if _git(repository, "rev-parse", "HEAD") != expected:
        raise RuntimeError("evidence_source_head_mismatch")


def _content_dirty(repository: Path) -> bool:
    return bool(_git(repository, "status", "--porcelain", "--untracked-files=no"))


def _git(repository: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
