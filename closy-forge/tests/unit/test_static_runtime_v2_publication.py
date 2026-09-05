from __future__ import annotations

import copy
import json
from pathlib import Path

from closy_forge.zeroone.static_runtime_v2_publication import (
    FAMILIES,
    PROFILES,
    check_result,
    validate_schema_instance,
)


def _result() -> dict[str, object]:
    static = []
    runtime = []
    for family in FAMILIES:
        failed = family in {"long_sleeved_top", "button_shirt", "jacket_outerwear"}
        static.append(
            {
                "family": family,
                "capabilitySupport": "supported",
                "terminalOutcome": "failed" if failed else "passed",
                "failureReason": "process_failed" if failed else None,
                "fallbackSha256Before": family,
                "fallbackSha256After": family,
                "conventionalFallbackAvailable": True,
                "conventionalFallbackGeometryValid": not failed,
                "conventionalFallbackGeometryAudit": {"status": "fail" if failed else "pass"},
                "optionalDerivativeSelectedForRuntime": not failed,
            }
        )
        for profile in PROFILES:
            for rebuild in (1, 2):
                runtime.append(
                    {
                        "family": family,
                        "profileId": profile,
                        "rebuild": rebuild,
                        "packageDigest": f"{family}-{profile}",
                        "terminalOutcome": "corrupt_or_invalid" if failed else "passed",
                        "failureReason": "conventional_fallback_geometry_invalid"
                        if failed
                        else None,
                        "glbGeometryAudit": {"status": "fail" if failed else "pass"},
                        "maximumDecodedPageBytes": 65_536,
                        "maximumDecompressionRatio": 6.0,
                        "maximumPosePositionErrorMeters": 1e-8,
                        "poseBoundsContainEveryVertex": True,
                        "uniqueCompressedBlobCount": 1,
                        "smallerThanEquivalentDuplicateStorageV1": True,
                        "fallbackPrefix": {"verified": True},
                        "resume": [
                            {"point": point, "aggregateHashMatch": True}
                            for point in ("first", "middle", "final")
                        ],
                        "claims": {
                            "hostCpu": True,
                            "mobile": False,
                            "gpu": False,
                            "network": False,
                        },
                    }
                )
    negative = {
        name: {"passed": True, "failureReason": name}
        for name in (
            "corrupt_chunk",
            "truncated_stream",
            "trailing_stream",
            "stale_version",
            "decompression_bomb",
            "cancelled_transfer",
            "storage_quota_exceeded",
            "last_good_rollback",
        )
    }
    negative["cross_package_chunk"] = {
        "passed": False,
        "failureReason": "transfer_chunk_size_mismatch",
    }
    stage = {
        name: {
            "planned": 9,
            "passed": 6 if name not in {"Z3", "Z7"} else 0,
            "failed": 0,
            "not_run": 6 if name in {"Z3", "Z7"} else 0,
            "dependency_blocked": 3,
            "corrupt_or_invalid": 0,
            "terminalConservation": True,
        }
        for name in ("Z3", "Z4", "Z5", "Z6", "Z7", "Z8")
    }
    return {
        "resultVersion": "closy.static_zeroone_runtime_v2.result.v2",
        "protocolId": "CLOSY-STATIC-ZEROONE-RUNTIME-V2-20260904",
        "protocolDigest": "b67193ebd322340fb758d98411334aec26084554f9ce7eefec5698ce90a6ed01",
        "classification": "public_synthetic_static_runtime_engineering_host_cpu_only",
        "source": {
            "closyCommit": "afd2101b2dbfa5da067cc8b1f9d3038a8950af1a",
            "closyTree": "f60156c948a108996390fe31c85a8ca3b59f41f1",
            "zeroOneCommit": "9cbae4a8e6ef2e61c1839ecbdf8a462aaa560027",
            "zeroOneTree": "6e058711449fdd98c41c82d05294339b3f21fc16",
            "zeroOneExecutableSha256": (
                "38adb7797344b9fcbbe814ed0bb47c0b23b40577341ecda92d911410ad8ba1a6"
            ),
            "trustedBuildRecordSha256": (
                "aea342d86a550a28a5e88c90ffb2c2595836c36568eef3a7c8eed5491cdde375"
            ),
        },
        "staticZeroOne": static,
        "conventionalRuntime": runtime,
        "negativeCases": negative,
        "denominators": {
            "staticFamilyCount": 9,
            "staticPassedCount": 6,
            "staticFailedCount": 3,
            "staticUnsupportedCount": 0,
            "staticCorruptOrInvalidCount": 0,
            "runtimeBuildCount": 36,
            "runtimePassedCount": 24,
            "runtimeFailedCount": 0,
            "runtimeCorruptOrInvalidCount": 12,
            "profileCount": 2,
            "cleanRebuildsPerProfile": 2,
            "poseCountPerBuild": 4,
            "resumePointCountPerBuild": 3,
            "negativeCaseCount": 9,
        },
        "stageOutcome": stage,
        "acceptance": {
            "allNineFamiliesAccounted": True,
            "allNineFamiliesProcessed": False,
            "allThirtySixRuntimeBuildsPassed": False,
            "allNegativeCasesRejectedOrRecovered": False,
            "canonicalAuthorityChanged": False,
            "productRuntimeDefaultChanged": False,
            "dynamicZ2Claimed": False,
            "mobileClaimed": False,
            "gpuClaimed": False,
            "productionNetworkClaimed": False,
            "globalBlueprintComplete": False,
        },
        "performance": {
            "totalWallNanoseconds": 1,
            "totalCpuNanoseconds": 1,
            "pythonTracedPeakBytes": 1,
            "zeroOnePeakMemoryBytesMaximum": 1,
        },
        "host": {
            "cpuOnly": True,
            "measurementScope": "host_cpu_not_mobile_gpu_battery_thermal_or_network",
        },
        "literalOutcome": "static_runtime_v2_engineering_failed_global_partial",
    }


def test_independent_checker_accepts_failed_but_conserved_result() -> None:
    assert check_result(_result()) == []


def test_independent_checker_rejects_denominator_and_claim_substitution() -> None:
    result = _result()
    changed = copy.deepcopy(result)
    changed["denominators"]["runtimeBuildCount"] = 35  # type: ignore[index]
    changed["acceptance"]["mobileClaimed"] = True  # type: ignore[index]
    failures = check_result(changed)
    assert "denominators" in failures
    assert "forbidden_claim:mobileClaimed" in failures


def test_independent_checker_rejects_corrupt_runtime_identity_and_private_path() -> None:
    result = _result()
    changed = copy.deepcopy(result)
    changed["conventionalRuntime"][1]["packageDigest"] = "substituted"  # type: ignore[index]
    changed["host"]["private"] = "C:\\Users\\person\\secret"  # type: ignore[index]
    failures = check_result(changed)
    assert "runtime_rebuild_identity" in failures
    assert any(item.startswith("absolute_path:") for item in failures)


def test_schema_subset_validator_enforces_required_const_and_cardinality(tmp_path: Path) -> None:
    schema = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "schemas/static_zeroone_runtime_v2/result.schema.json"
        ).read_text()
    )
    failures = validate_schema_instance({"schemaVersion": 2}, schema)
    assert "schema_const:$.schemaVersion" in failures
    assert "schema_required:$.resultVersion" in failures
