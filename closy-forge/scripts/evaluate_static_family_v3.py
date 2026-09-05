"""Nine saved nominal family packages, read-only optional ZeroOne static work."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.security.strict_json import load_strict_json_object, loads_strict_json_object
from closy_forge.zeroone.family_adapter_v1 import (
    FAMILY_NAMES,
    create_family_adapter,
    is_link,
    safe_file,
    snapshot_family,
    verify_family_adapter,
)
from closy_forge.zeroone.request import build_zeroone_request
from closy_forge.zeroone.static_stage_audit_v3 import audit_static_family
from closy_forge.zeroone.tool import (
    REPORT_SCHEMA_VERSION,
    TRUST_RECORD_VERSION,
    ZeroOneToolResolution,
    _validate_trusted_build_record,
    _validate_version,
    minimal_subprocess_environment,
    resolve_zeroone_tool,
)

VERSION = "closy.static_family_evaluation.v3"
BASE_PR66 = "930b3da556c96e9ded52b6ee8df5620d4903c280"
ZEROONE_HEAD = "9cbae4a8e6ef2e61c1839ecbdf8a462aaa560027"
ZEROONE_TREE = "6e058711449fdd98c41c82d05294339b3f21fc16"
ZEROONE_EXE_SHA256 = "38adb7797344b9fcbbe814ed0bb47c0b23b40577341ecda92d911410ad8ba1a6"
HISTORICAL_RECORD_SHA256 = "aea342d86a550a28a5e88c90ffb2c2595836c36568eef3a7c8eed5491cdde375"
DEFAULT_EXE = Path("E:/apps/ZeroOne-pr4-build/Release/ZeroOneProcess.exe")
DEFAULT_SOURCE = Path("E:/apps/ZeroOne-pr4-static")
STAGES = ("Z3", "Z4", "Z5", "Z6", "Z7", "Z8")


def _write(path: Path, document: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("xb") as stream:
        stream.write(canonical_dumps(document).encode())
    temporary.replace(path)


def _git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=root, timeout=15)


def source_receipt(forge: Path, zeroone: Path) -> dict[str, Any]:
    registry_path = "closy-forge/docs/evidence/static_zeroone_runtime_v2/result.json"
    raw = _git(forge, "show", f"{BASE_PR66}:{registry_path}")
    frozen = json.loads(raw)["source"]
    if (
        frozen["zeroOneCommit"] != ZEROONE_HEAD
        or frozen["zeroOneTree"] != ZEROONE_TREE
        or frozen["zeroOneExecutableSha256"] != ZEROONE_EXE_SHA256
        or frozen["trustedBuildRecordSha256"] != HISTORICAL_RECORD_SHA256
    ):
        raise ValueError("static_v3_frozen_registry_identity_mismatch")
    local: dict[str, Any]
    try:
        local = {
            "root": str(zeroone.absolute()),
            "head": _git(zeroone, "rev-parse", "HEAD").decode().strip(),
            "tree": _git(zeroone, "rev-parse", "HEAD^{tree}").decode().strip(),
            "clean": not _git(zeroone, "status", "--porcelain").strip(),
        }
        local["matchesFrozenSource"] = (
            local["head"] == ZEROONE_HEAD and local["tree"] == ZEROONE_TREE and local["clean"]
        )
    except (OSError, subprocess.SubprocessError) as error:
        local = {"matchesFrozenSource": False, "reason": str(error)}
    paths = [
        "scripts/evaluate_static_family_v3.py",
        "tests/unit/test_static_family_v3.py",
        "src/closy_forge/zeroone/family_adapter_v1.py",
        "src/closy_forge/zeroone/static_stage_audit_v3.py",
        "src/closy_forge/zeroone/request.py",
        "src/closy_forge/zeroone/tool.py",
        "src/closy_forge/zeroone/static_stage_audit_v2.py",
        "src/closy_forge/zeroone/derivative_inspection.py",
        "src/closy_forge/geometry/glb_io.py",
        "src/closy_forge/geometry/mesh_model.py",
        "src/closy_forge/family_integration_v1/compiler.py",
    ]
    return {
        "baseRegistry": {
            "commit": BASE_PR66,
            "path": registry_path,
            "sha256": sha256_bytes(raw),
            "source": frozen,
        },
        "localSource": local,
        "closyHead": _git(forge, "rev-parse", "HEAD").decode().strip(),
        "closyDirty": bool(_git(forge, "status", "--porcelain").strip()),
        "currentReceiptScope": "selected_adapter_audit_request_decoder_and_test_files_not_A_freeze",
        "currentFiles": {p: sha256_file(forge / p) for p in paths},
        "buildExecuted": False,
        "historicalBuildReceiptReconstructed": False,
    }


def select_nominal_packages(evaluation_root: Path) -> list[tuple[str, Path, str]]:
    result = load_strict_json_object(safe_file(evaluation_root, "result.json"))
    checkpoint = load_strict_json_object(safe_file(evaluation_root, "checkpoint.json"))
    safe_file(evaluation_root, "family_index.json")  # Written after result by A.
    rows = result.get("rows", [])
    expected = {
        (repeat, f"{family}/{variation}")
        for repeat in (1, 2)
        for family in FAMILY_NAMES
        for variation in ("nominal", "variation1", "variation2")
    }
    if (
        result.get("version") != "closy.family_integration.result.v1"
        or len(rows) != 54
        or {(r["repeat"], r["caseId"]) for r in rows} != expected
        or checkpoint.get("active") is not None
        or checkpoint.get("nextBuild") != 55
        or checkpoint.get("rows") != rows
    ):
        raise ValueError("static_v3_completed_A_result_required")
    selected = []
    for family in FAMILY_NAMES:
        row = next(r for r in rows if r["repeat"] == 1 and r["caseId"] == f"{family}/nominal")
        if row["terminal"] != "passed" or not isinstance(row.get("packageIdentity"), str):
            raise ValueError(f"static_v3_nominal_A_source_not_valid:{family}")
        selected.append(
            (family, evaluation_root / "build1" / family / "nominal", row["packageIdentity"])
        )
    return selected


def inspect_pr66_reuse(forge: Path, zeroone: Path, executable: Path) -> dict[str, Any]:
    """Capture NEW owner-authorized hash reuse evidence, never a reconstructed build."""
    provenance = source_receipt(forge, zeroone)
    if not provenance["localSource"]["matchesFrozenSource"]:
        raise ValueError("pr66_reuse_source_not_frozen_clean")
    actual_hash = sha256_file(executable)
    if actual_hash != ZEROONE_EXE_SHA256:
        raise ValueError("pr66_reuse_executable_hash_mismatch")
    argv = [str(executable.absolute()), "version-json"]
    process = subprocess.run(
        argv,
        cwd=executable.absolute().parent,
        env=minimal_subprocess_environment(),
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    if process.returncode != 0 or len(process.stdout) > 1024 * 1024:
        raise ValueError("pr66_reuse_version_query_failed")
    lines = [line for line in process.stdout.splitlines() if line.strip()]
    version = loads_strict_json_object(lines[-1]) if lines else {}
    registry = provenance["baseRegistry"]
    if version != registry["source"]["zeroOneVersion"]:
        raise ValueError("pr66_reuse_version_not_exact_published_fields")
    if (
        sha256_file(executable) != actual_hash
        or _git(zeroone, "rev-parse", "HEAD").decode().strip() != ZEROONE_HEAD
        or _git(zeroone, "rev-parse", "HEAD^{tree}").decode().strip() != ZEROONE_TREE
        or _git(zeroone, "status", "--porcelain").strip()
    ):
        raise ValueError("pr66_reuse_local_identity_changed_during_capture")
    record = {
        "schemaVersion": 1,
        "recordVersion": TRUST_RECORD_VERSION,
        "trustDomain": "owner_controlled_registry",
        "repository": "jake-the-jake/ZeroOne",
        "sourceSha": ZEROONE_HEAD,
        "compiler": version["compiler"],
        "buildId": f"read-only-reuse-capture-pr66-{registry['sha256'][:16]}",
        "buildType": version["buildConfiguration"],
        "executableRelativeName": executable.name,
        "executableSha256": actual_hash,
        "requestSchemaVersions": [version["requestSchemaVersion"]],
        "reportSchemaVersions": [version["reportSchemaVersion"]],
        "supportedProfiles": ["closy-static-d0-cpu-v1"],
        "attestation": {
            "kind": "read_only_reuse_of_published_PR66_hash",
            "registryCommit": registry["commit"],
            "registryPath": registry["path"],
            "registryBytesSha256": registry["sha256"],
            "sourceTree": ZEROONE_TREE,
            "originalTrustedRecordSha256": HISTORICAL_RECORD_SHA256,
            "originalTrustRecordNotRecovered": True,
            "buildReexecuted": False,
            "scope": "new_owner_authorized_reuse_not_original_build_or_scientific_attestation",
        },
        "capture": {
            "capturedAtUtc": datetime.now(UTC).isoformat(),
            "sourceClean": True,
            "networkAllowed": False,
            "networkIsolationClaimed": False,
            "scope": "this_local_hash_git_version_capture_only_not_historical_build_environment",
            "commandTemplate": [
                f"git show {BASE_PR66}:{registry['path']}",
                f"sha256_file({executable.absolute()})",
                f"git -C {zeroone.absolute()} rev-parse HEAD",
                f"git -C {zeroone.absolute()} rev-parse HEAD^{{tree}}",
                f"git -C {zeroone.absolute()} status --porcelain",
                argv,
            ],
        },
    }
    issue = _validate_trusted_build_record(record, ZEROONE_HEAD, "static")
    issue = issue or _validate_version(version, actual_hash, record, "static")
    if issue:
        raise ValueError(f"pr66_reuse_existing_trust_contract_rejected:{issue}")
    return {
        "record": record,
        "sourceReceipt": provenance,
        "version": version,
        "versionExitCode": process.returncode,
        "versionArgv": argv,
        "versionStdoutUtf8TextSha256": sha256_bytes(process.stdout.encode()),
        "versionStderr": process.stderr,
        "buildReexecuted": False,
    }


def invoke(
    executable: Path, command: str, root: Path, request: Path, receipt_root: Path
) -> dict[str, Any]:
    argv = [str(executable), command, "--root", str(root), "--request", str(request)]
    stdout = receipt_root / f"{command}.stdout.log"
    stderr = receipt_root / f"{command}.stderr.log"
    begin = time.perf_counter()
    receipt: dict[str, Any] = {"argv": argv, "command": command, "timeoutSeconds": 180}
    try:
        with stdout.open("xb") as out, stderr.open("xb") as err:
            process = subprocess.run(
                argv,
                cwd=root,
                env=minimal_subprocess_environment(),
                stdout=out,
                stderr=err,
                check=False,
                timeout=180,
            )
        receipt["exitCode"] = process.returncode
    except (OSError, subprocess.SubprocessError) as error:
        receipt.update({"exitCode": None, "error": f"{type(error).__name__}:{error}"})
    receipt["wallSeconds"] = time.perf_counter() - begin
    receipt["logs"] = [
        {"path": p.name, "sha256": sha256_file(p), "byteSize": p.stat().st_size}
        for p in (stdout, stderr)
        if p.is_file()
    ]
    report: dict[str, Any] = {}
    try:
        if stdout.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("processor_report_limit")
        lines = [line for line in stdout.read_text(encoding="utf-8").splitlines() if line.strip()]
        report = loads_strict_json_object(lines[-1])
    except (OSError, UnicodeError, ValueError, IndexError) as error:
        receipt["reportError"] = str(error)
    passed = (
        receipt["exitCode"] == 0
        and report.get("schemaVersion") == REPORT_SCHEMA_VERSION
        and report.get("success") is True
    )
    if command == "cook":
        passed = (
            passed
            and report.get("canonicalAuthorityPreserved") is True
            and report.get("actualZeroOneStaticArtifactLoaded") is True
            and report.get("actualZeroOneStaticCookExecutedThisInvocation") is True
            and report.get("globalPhase10Complete") is False
        )
    if command == "validate":
        passed = passed and report.get("validatedNativeDerivative") is True
    receipt.update({"passed": passed, "report": report})
    _write(receipt_root / f"{command}.receipt.json", receipt)
    return receipt


def run(
    evaluation_root: Path,
    output: Path,
    *,
    executable: Path = DEFAULT_EXE,
    zeroone_source: Path = DEFAULT_SOURCE,
    trusted_build_record: Path | None = None,
    forge_root: Path | None = None,
    reuse_published_pr66: bool = False,
) -> dict[str, Any]:
    forge = (forge_root or Path(__file__).resolve().parents[1]).absolute()
    source = evaluation_root.absolute()
    root = output.absolute()
    if (
        root.exists()
        or root.resolve().is_relative_to(source.resolve())
        or source.resolve().is_relative_to(root.resolve())
        or any(is_link(p) for p in (root, *root.parents))
    ):
        raise ValueError("static_v3_output_must_be_fresh_and_disjoint")
    selected = select_nominal_packages(source)
    provenance = source_receipt(forge, zeroone_source)
    if reuse_published_pr66 and trusted_build_record is not None:
        raise ValueError("static_v3_choose_explicit_record_or_new_reuse_capture")
    configured_record = trusted_build_record
    if (
        not reuse_published_pr66
        and configured_record is None
        and os.environ.get("CLOSY_ZEROONE_TRUSTED_BUILD_RECORD")
    ):
        configured_record = Path(os.environ["CLOSY_ZEROONE_TRUSTED_BUILD_RECORD"])
    root.mkdir(parents=True, exist_ok=False)
    reuse_error: str | None = None
    if reuse_published_pr66:
        try:
            reuse = inspect_pr66_reuse(forge, zeroone_source, executable)
            configured_record = root / "read_only_reuse_record.json"
            _write(root / "read_only_reuse_capture.json", reuse)
            _write(configured_record, reuse["record"])
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            reuse_error = f"pr66_readonly_reuse_unavailable:{type(error).__name__}:{error}"
            _write(
                root / "read_only_reuse_attempt.json",
                {"passed": False, "reason": reuse_error, "buildReexecuted": False},
            )
    resolution = (
        ZeroOneToolResolution(False, reuse_error, executable, None, None)
        if reuse_error
        else resolve_zeroone_tool(
            executable,
            trusted_build_record=configured_record,
            expected_source_sha=ZEROONE_HEAD,
            expected_executable_sha256=ZEROONE_EXE_SHA256,
        )
    )
    record_digest = (
        sha256_file(configured_record)
        if configured_record is not None and configured_record.is_file()
        else None
    )
    available = resolution.available and provenance["localSource"]["matchesFrozenSource"]
    reason = resolution.reason if not resolution.available else "zeroone_source_not_frozen_clean"
    tool = {
        "available": available,
        "reason": "available" if available else reason,
        "executable": str(resolution.executable),
        "executableSha256": resolution.executable_sha256,
        "executableMatchesFrozenRegistry": resolution.executable_sha256 == ZEROONE_EXE_SHA256,
        "version": resolution.version,
        "trustedBuildRecordPath": str(configured_record) if configured_record else None,
        "trustedBuildRecordSha256": record_digest,
        "matchesHistoricalTrustedRecordHash": record_digest == HISTORICAL_RECORD_SHA256,
        "newBuildExecuted": False,
        "binaryRedistributed": False,
    }
    source_hashes = {
        name: sha256_file(source / name)
        for name in ("result.json", "checkpoint.json", "family_index.json")
    }
    _write(
        root / "protocol.json",
        {
            "version": VERSION,
            "familyDenominator": 9,
            "repeatCount": 1,
            "input": "A_build1_nominal_saved_packages",
            "commands": ["inspect", "cook", "validate"],
            "geometryAudit": "oriented_float32_position_uv_material_multiset_and_mandatory_bounds",
            "tolerance": 1e-6,
            "dynamicReadinessZ2": "not_run",
            "sourceEvaluation": source_hashes,
            "scope": "optional_static_host_CPU_not_conventional_or_outfit_delivery",
            "physicalQualification": False,
            "mobile": "not_run",
            "gpu": "not_run",
        },
    )
    _write(root / "source_receipt.json", provenance)
    _write(root / "tool_receipt.json", tool)
    rows: list[dict[str, Any]] = []
    for family, package, expected_identity in selected:
        _write(
            root / "checkpoint.json",
            {"rows": rows, "activeFamily": family, "nextRun": len(rows) + 1},
        )
        row: dict[str, Any] = {
            "family": family,
            "sourcePackageIdentity": expected_identity,
            "commands": [],
            "passedStageIds": [],
            "failedStageIds": [],
            "notRunStageIds": list(STAGES),
            "dynamicReadinessZ2": "not_run",
            "processorCookExecuted": False,
            "stageAuditStatus": "not_run",
        }
        before: dict[str, Any] | None = None
        started = time.perf_counter()
        if not available:
            row.update({"terminal": "not_run", "reason": tool["reason"]})
        else:
            work = root / family
            work.mkdir()
            try:
                before = snapshot_family(package)
                if before["packageIdentity"] != expected_identity:
                    raise ValueError("static_v3_A_source_identity_changed")
                receipt = create_family_adapter(package, work / "adapter")
                _write(work / "adapter_receipt.json", receipt)
                row["adapterIdentity"] = receipt["adapterIdentity"]
                request = build_zeroone_request(
                    invocation_root=work,
                    package=work / "adapter",
                    output=work / "processor",
                    closy_sha=provenance["closyHead"],
                    closy_dirty=provenance["closyDirty"],
                    request_label=f"static-family-v3-{family}",
                )
                _write(work / "request.json", request)
                for command in ("inspect", "cook", "validate"):
                    if sha256_file(executable) != ZEROONE_EXE_SHA256:
                        raise ValueError("static_v3_executable_changed")
                    command_receipt = invoke(
                        executable.absolute(), command, work, work / "request.json", work
                    )
                    if command == "cook":
                        row["processorCookExecuted"] = (
                            command_receipt["report"].get(
                                "actualZeroOneStaticCookExecutedThisInvocation"
                            )
                            is True
                        )
                    row["commands"].append(
                        {
                            "command": command,
                            "passed": command_receipt["passed"],
                            "exitCode": command_receipt["exitCode"],
                        }
                    )
                    if not command_receipt["passed"]:
                        raise ValueError(f"static_v3_processor_{command}_failed")
                row["stageAuditStatus"] = "attempted"
                audit = audit_static_family(
                    work / "processor/current", adapter_package=work / "adapter"
                )
                if (
                    verify_family_adapter(work / "adapter")["adapterIdentity"]
                    != receipt["adapterIdentity"]
                ):
                    raise ValueError("static_v3_adapter_changed_during_processing")
                _write(work / "static_stage_audit.json", audit)
                for key in ("passedStageIds", "failedStageIds", "notRunStageIds"):
                    row[key] = audit[key]
                row["terminal"] = "failed" if audit["failedStageIds"] else "passed"
                row["stageAuditStatus"] = row["terminal"]
            except Exception as error:
                row.update({"terminal": "failed", "reason": f"{type(error).__name__}:{error}"})
                if row["stageAuditStatus"] == "attempted":
                    row["stageAuditStatus"] = "failed_before_complete_stage_audit"
            finally:
                if before is not None:
                    try:
                        row["sourceAUnchanged"] = snapshot_family(package) == before
                    except Exception:
                        row["sourceAUnchanged"] = False
                    if not row["sourceAUnchanged"]:
                        row.update(
                            {"terminal": "failed", "sourceError": "A_source_changed_during_static"}
                        )
        row["wallSeconds"] = time.perf_counter() - started
        rows.append(row)
        _write(root / "checkpoint.json", {"rows": rows, "nextRun": len(rows) + 1})
        print(f"{len(rows)}/9 {family} {row['terminal']}", flush=True)
    current_unchanged = all(
        sha256_file(forge / p) == digest for p, digest in provenance["currentFiles"].items()
    )
    result = {
        "version": VERSION,
        "rows": rows,
        "familyDenominator": 9,
        "passed": sum(r["terminal"] == "passed" for r in rows),
        "failed": sum(r["terminal"] == "failed" for r in rows),
        "notRun": sum(r["terminal"] == "not_run" for r in rows),
        "stageCounts": {
            stage: {
                status: sum(stage in row[key] for row in rows)
                for status, key in (
                    ("passed", "passedStageIds"),
                    ("failed", "failedStageIds"),
                    ("not_run", "notRunStageIds"),
                )
            }
            for stage in STAGES
        },
        "selectedCurrentFilesUnchanged": current_unchanged,
        "sourceEvaluationUnchanged": all(
            sha256_file(source / p) == digest for p, digest in source_hashes.items()
        ),
        "host": platform.platform(),
        "python": platform.python_version(),
        "physicalQualification": False,
        "dynamicReadinessZ2": "not_run",
        "conventionalRuntimeMatrix": "outside_this_sidecar",
        "outfitRuntime": "outside_this_sidecar",
    }
    result["overallStatus"] = (
        "failed"
        if result["failed"]
        or not result["selectedCurrentFilesUnchanged"]
        or not result["sourceEvaluationUnchanged"]
        else "not_run"
        if result["notRun"]
        else "passed"
    )
    _write(root / "result.json", result)
    _write(
        root / "receipt_manifest.json",
        {
            "version": VERSION,
            "scope": "compact_receipts_only_assets_remain_in_work_directories",
            "files": [
                {
                    "path": p.relative_to(root).as_posix(),
                    "sha256": sha256_file(p),
                    "byteSize": p.stat().st_size,
                }
                for p in sorted(root.rglob("*"))
                if p.is_file() and (p.parent == root or p.parent.parent == root)
            ],
        },
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--executable", type=Path, default=DEFAULT_EXE)
    parser.add_argument("--zeroone-source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--trusted-build-record", type=Path)
    parser.add_argument(
        "--reuse-published-pr66",
        action="store_true",
        help="capture a NEW read-only owner-registry reuse record; never rebuild",
    )
    args = parser.parse_args()
    result = run(
        args.evaluation_root,
        args.output,
        executable=args.executable,
        zeroone_source=args.zeroone_source,
        trusted_build_record=args.trusted_build_record,
        reuse_published_pr66=args.reuse_published_pr66,
    )
    if (
        result["failed"]
        or not result["selectedCurrentFilesUnchanged"]
        or not result["sourceEvaluationUnchanged"]
    ):
        return 1
    return 2 if result["notRun"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
