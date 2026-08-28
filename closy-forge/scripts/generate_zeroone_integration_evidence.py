from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import write_canonical_json
from closy_forge.pipeline.build_layered_asymmetric_demo import (
    build_demo_layered_asymmetric_package,
)
from closy_forge.pipeline.build_tshirt_demo import build_demo_tshirt_package
from closy_forge.zeroone.integration import integrate_zeroone_static
from closy_forge.zeroone.tool import PINNED_ZEROONE_SOURCE_SHA, resolve_zeroone_tool
from closy_forge.zeroone.validation import inspect_zeroone_namespace


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real Closy-to-ZeroOne static evidence.")
    parser.add_argument("--executable", required=True, type=Path)
    parser.add_argument("--expected-executable-sha256", required=True)
    parser.add_argument("--zeroone-repo", required=True, type=Path)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--closy-sha", required=True)
    parser.add_argument("--zeroone-sha", default=PINNED_ZEROONE_SOURCE_SHA)
    args = parser.parse_args()

    forge_root = Path(__file__).resolve().parents[1]
    repository_root = forge_root.parent
    _require_git_head(repository_root, args.closy_sha)
    _require_git_head(args.zeroone_repo, args.zeroone_sha)
    tool = resolve_zeroone_tool(
        args.executable,
        expected_executable_sha256=args.expected_executable_sha256,
        expected_source_sha=args.zeroone_sha,
    )
    if not tool.available:
        raise RuntimeError(f"pinned ZeroOne executable is unavailable: {tool.reason}")

    root = args.work_root.resolve(strict=False)
    if root.exists():
        raise FileExistsError(f"evidence work root already exists: {root}")
    root.mkdir(parents=True)
    started_wall = time.perf_counter_ns()
    started_cpu = time.process_time_ns()
    try:
        builds = {
            "tshirt": build_demo_tshirt_package(root / "tshirt.closygarment", force=False),
            "layered_asymmetric": build_demo_layered_asymmetric_package(
                root / "layered.closygarment", force=False
            ),
        }
        garment_rows: list[dict[str, Any]] = []
        for family, build in builds.items():
            result = integrate_zeroone_static(
                package=build.package_dir,
                invocation_root=root,
                closy_sha=args.closy_sha,
                executable=args.executable,
                expected_executable_sha256=args.expected_executable_sha256,
                expected_zeroone_sha=args.zeroone_sha,
                publish=True,
            )
            if result.status != "valid":
                raise RuntimeError(f"{family} integration failed: {result.reason}")
            namespace_audit = inspect_zeroone_namespace(build.package_dir)
            if namespace_audit.get("status") != "derivative_valid":
                raise RuntimeError(f"{family} packaged derivative validation failed")
            row = {
                "family": family,
                "garmentId": build.manifest["garmentId"],
                "canonicalPackageDigest": build.manifest.get(
                    "canonicalPackageDigest", build.manifest.get("packageDigest")
                ),
                "integration": result.to_json(),
                "namespaceAudit": namespace_audit,
                "deleteAndRebuild": {"executed": False},
            }
            if family == "tshirt":
                first_hash = result.report["canonicalDerivativeHash"]
                optional_root = build.package_dir / "zeroone"
                shutil.rmtree(optional_root)
                if inspect_zeroone_namespace(build.package_dir).get("status") != "not_present":
                    raise RuntimeError(
                        "ZeroOne namespace deletion did not preserve an absent state"
                    )
                rebuilt = integrate_zeroone_static(
                    package=build.package_dir,
                    invocation_root=root,
                    closy_sha=args.closy_sha,
                    executable=args.executable,
                    expected_executable_sha256=args.expected_executable_sha256,
                    expected_zeroone_sha=args.zeroone_sha,
                    publish=True,
                )
                rebuilt_hash = rebuilt.report.get("canonicalDerivativeHash")
                rebuild_passed = (
                    rebuilt.status == "valid"
                    and rebuilt_hash == first_hash
                    and inspect_zeroone_namespace(build.package_dir).get("status")
                    == "derivative_valid"
                )
                if not rebuild_passed:
                    raise RuntimeError("deleted ZeroOne derivative did not rebuild identically")
                row["deleteAndRebuild"] = {
                    "executed": True,
                    "canonicalDerivativeHashBefore": first_hash,
                    "canonicalDerivativeHashAfter": rebuilt_hash,
                    "fallbackPreserved": rebuilt.fallback_preserved,
                    "passed": True,
                }
            garment_rows.append(row)
        wall_ns = time.perf_counter_ns() - started_wall
        cpu_ns = time.process_time_ns() - started_cpu
        evidence = {
            "schemaVersion": "closy.zeroone.execution-evidence.v1",
            "scope": "d0_cpu_static_tshirt_and_layered_asymmetric",
            "closy": {
                "repository": "jake-the-jake/Closy",
                "gitSha": args.closy_sha,
                "contentDirty": _content_dirty(repository_root),
                "draftPullRequest": 23,
            },
            "zeroOne": {
                "repository": "jake-the-jake/ZeroOne",
                "gitSha": args.zeroone_sha,
                "contentDirty": _content_dirty(args.zeroone_repo),
                "draftPullRequest": 1,
            },
            "tool": tool.version,
            "executableSha256": tool.executable_sha256,
            "command": _command_record(args),
            "exitCode": 0,
            "host": {
                "platform": platform.platform(),
                "machine": platform.machine(),
                "python": platform.python_version(),
                "processor": platform.processor(),
            },
            "timings": {"wallNanoseconds": wall_ns, "cpuNanoseconds": cpu_ns},
            "garments": garment_rows,
            "acceptance": {
                "actualZeroOneRuntimeExecuted": True,
                "actualZeroOneComputeExecuted": True,
                "allCanonicalAuthoritiesPreserved": all(
                    row["integration"]["canonicalAuthorityPreserved"] for row in garment_rows
                ),
                "allFallbacksPreserved": all(
                    row["integration"]["fallbackPreserved"] for row in garment_rows
                ),
                "allDerivativesDeterministic": all(
                    row["integration"]["deterministicDerivative"] for row in garment_rows
                ),
                "allNamespacesValid": all(
                    row["namespaceAudit"]["status"] == "derivative_valid" for row in garment_rows
                ),
                "scopedGateZ1Passed": True,
                "globalPhase10Complete": False,
                "remainingBlockers": [
                    "turntable_or_human_visual_review",
                    "broader_garment_provider_evidence",
                    "mobile_profile",
                ],
            },
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_canonical_json(args.output, evidence)
        print(json.dumps({"output": str(args.output), "status": "passed"}, sort_keys=True))
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _require_git_head(repository: Path, expected: str) -> None:
    actual = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if actual != expected:
        raise ValueError(f"repository head mismatch: expected {expected}, got {actual}")


def _content_dirty(repository: Path) -> bool:
    tracked = subprocess.run(["git", "diff", "--quiet"], cwd=repository, check=False)
    staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repository, check=False)
    return tracked.returncode != 0 or staged.returncode != 0


def _command_record(args: argparse.Namespace) -> list[str]:
    return [
        sys.executable,
        "scripts/generate_zeroone_integration_evidence.py",
        "--executable",
        str(args.executable.resolve()),
        "--expected-executable-sha256",
        args.expected_executable_sha256,
        "--zeroone-repo",
        str(args.zeroone_repo.resolve()),
        "--work-root",
        str(args.work_root.resolve(strict=False)),
        "--output",
        str(args.output.resolve(strict=False)),
        "--closy-sha",
        args.closy_sha,
        "--zeroone-sha",
        args.zeroone_sha,
    ]


if __name__ == "__main__":
    raise SystemExit(main())
