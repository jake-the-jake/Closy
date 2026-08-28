from __future__ import annotations

import argparse
import json
import platform
import subprocess
import time
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import read_json, write_canonical_json
from closy_forge.package_io.managed_output import (
    cleanup_managed_staging,
    create_managed_staging,
    remove_managed_output,
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
from closy_forge.zeroone.derivative_inspection import inspect_static_derivative
from closy_forge.zeroone.integration import integrate_zeroone_static
from closy_forge.zeroone.tool import PINNED_ZEROONE_SOURCE_SHA, resolve_zeroone_tool
from closy_forge.zeroone.validation import inspect_zeroone_namespace


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real Closy-to-ZeroOne static evidence.")
    parser.add_argument("--executable", required=True, type=Path)
    parser.add_argument("--trusted-build-record", required=True, type=Path)
    parser.add_argument("--expected-executable-sha256", default=None)
    parser.add_argument("--zeroone-repo", required=True, type=Path)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--closy-sha", required=True)
    parser.add_argument("--zeroone-sha", default=PINNED_ZEROONE_SOURCE_SHA)
    parser.add_argument("--zeroone-workflow-run-id", required=True, type=int)
    parser.add_argument("--zeroone-artifact-id", required=True, type=int)
    parser.add_argument("--zeroone-artifact-digest", required=True)
    parser.add_argument("--zeroone-pr-url", required=True)
    args = parser.parse_args()

    forge_root = Path(__file__).resolve().parents[1]
    repository_root = forge_root.parent
    _require_git_head(repository_root, args.closy_sha)
    _require_git_head(args.zeroone_repo, args.zeroone_sha)
    closy_content_dirty = _content_dirty(repository_root)
    zeroone_content_dirty = _content_dirty(args.zeroone_repo)
    if closy_content_dirty or zeroone_content_dirty:
        raise RuntimeError("evidence source checkout must be clean before generation")
    tool = resolve_zeroone_tool(
        args.executable,
        trusted_build_record=args.trusted_build_record,
        expected_executable_sha256=args.expected_executable_sha256,
        expected_source_sha=args.zeroone_sha,
    )
    if not tool.available:
        raise RuntimeError(f"pinned ZeroOne executable is unavailable: {tool.reason}")

    requested_root = args.work_root.resolve(strict=False)
    root = create_managed_staging(
        requested_root,
        allowed_root=requested_root.parent,
        purpose="zeroone-evidence-work",
    )
    started_wall = time.perf_counter_ns()
    started_cpu = time.process_time_ns()
    try:
        builds = _build_all_declared_families(root)
        garment_rows: list[dict[str, Any]] = []
        for family, build in builds.items():
            result = integrate_zeroone_static(
                package=build.package_dir,
                invocation_root=root,
                closy_sha=args.closy_sha,
                executable=args.executable,
                trusted_build_record=args.trusted_build_record,
                expected_executable_sha256=args.expected_executable_sha256,
                expected_zeroone_sha=args.zeroone_sha,
                publish=True,
            )
            if result.status != "valid":
                raise RuntimeError(f"{family} integration failed: {result.reason}")
            namespace_audit = inspect_zeroone_namespace(build.package_dir)
            if namespace_audit.get("status") != "derivative_valid":
                raise RuntimeError(f"{family} packaged derivative validation failed")
            derivative_inspection = inspect_static_derivative(
                build.package_dir,
                review_output=(args.output.parent / "review" / family / "contact_sheet.png"),
                review_path_label=f"review/{family}/contact_sheet.png",
                fault_work_root=root / "fault-probes" / family,
            )
            if derivative_inspection["status"] != "pass":
                raise RuntimeError(f"{family} independent derivative inspection failed")
            row = {
                "family": family,
                "garmentId": build.manifest["garmentId"],
                "canonicalPackageDigest": build.manifest.get(
                    "canonicalPackageDigest", build.manifest.get("packageDigest")
                ),
                "integration": result.to_json(),
                "namespaceAudit": namespace_audit,
                "familyInventory": _family_inventory(build.package_dir, result.report),
                "independentDerivativeInspection": derivative_inspection,
                "deleteAndRebuild": {"executed": False},
            }
            first_hash = result.report["canonicalDerivativeHash"]
            optional_root = build.package_dir / "zeroone"
            remove_managed_output(
                optional_root / "static-d0",
                allowed_root=optional_root,
                purpose="zeroone-static-d0",
            )
            optional_root.rmdir()
            if inspect_zeroone_namespace(build.package_dir).get("status") != "not_present":
                raise RuntimeError("ZeroOne namespace deletion did not preserve an absent state")
            rebuilt = integrate_zeroone_static(
                package=build.package_dir,
                invocation_root=root,
                closy_sha=args.closy_sha,
                executable=args.executable,
                trusted_build_record=args.trusted_build_record,
                expected_executable_sha256=args.expected_executable_sha256,
                expected_zeroone_sha=args.zeroone_sha,
                publish=True,
            )
            rebuilt_hash = rebuilt.report.get("canonicalDerivativeHash")
            rebuild_passed = (
                rebuilt.status == "valid"
                and rebuilt_hash == first_hash
                and inspect_zeroone_namespace(build.package_dir).get("status") == "derivative_valid"
            )
            if not rebuild_passed:
                raise RuntimeError(f"{family} deleted derivative did not rebuild identically")
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
            "schemaVersion": "closy.zeroone.execution-evidence.v2",
            "scope": "candidate_branch_local_cpu_static_all_predeclared_families",
            "axes": {
                "computeProfile": "D0",
                "dataProvenance": "project-authored synthetic",
                "executionProfile": "CPU",
                "gateScope": "static ZeroOne",
            },
            "closy": {
                "repository": "jake-the-jake/Closy",
                "gitSha": args.closy_sha,
                "contentDirty": closy_content_dirty,
                "evidenceRole": "paired_closy_source",
            },
            "zeroOne": {
                "repository": "jake-the-jake/ZeroOne",
                "gitSha": args.zeroone_sha,
                "contentDirty": zeroone_content_dirty,
                "evidenceRole": "exact_candidate_static_source_checkout",
                "sourceClassification": "unmerged_candidate_static_pr_head",
                "pullRequest": args.zeroone_pr_url,
            },
            "zeroOneWorkflowEvidence": {
                "runId": args.zeroone_workflow_run_id,
                "runUrl": (
                    "https://github.com/jake-the-jake/ZeroOne/actions/runs/"
                    f"{args.zeroone_workflow_run_id}"
                ),
                "artifactId": args.zeroone_artifact_id,
                "artifactDigest": args.zeroone_artifact_digest,
                "authenticatedPrivateDownload": True,
                "artifactRetentionDays": 7,
                "windowsAndUbuntuQualification": "pass",
            },
            "evidenceClassification": {
                "currentMasterRequalified": False,
                "zeroOneDurableWorkflowArtifact": True,
                "pairedClosyExecutionDurableWorkflowArtifact": False,
                "localCandidatePairedEvidence": True,
                "scopedCandidateStaticPass": True,
                "globalZ1Pass": False,
            },
            "tool": tool.version,
            "trustedBuildRecord": tool.trusted_build_record,
            "executableSha256": tool.executable_sha256,
            "commandTemplate": _command_record(args),
            "exitCode": 0,
            "host": {
                "platform": platform.system().lower(),
                "architecture": platform.machine().lower(),
                "python": platform.python_version(),
            },
            "timings": {"wallNanoseconds": wall_ns, "cpuNanoseconds": cpu_ns},
            "garments": garment_rows,
            "acceptance": {
                "actualZeroOneStaticCookExecutedThisInvocation": True,
                "actualZeroOneStaticArtifactLoaded": True,
                "cacheValidated": True,
                "actualZeroOneDynamicDeformationExecuted": False,
                "actualZeroOneGpuRuntimeExecuted": False,
                "actualZeroOneMobileRuntimeExecuted": False,
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
                "allPredeclaredFamiliesExecuted": len(garment_rows) == 9,
                "allIndependentDerivativeInspectionsPassed": all(
                    row["independentDerivativeInspection"]["status"] == "pass"
                    for row in garment_rows
                ),
                "allDeleteAndRebuildProofsPassed": all(
                    row["deleteAndRebuild"]["passed"] for row in garment_rows
                ),
                "scopedCandidateBranchGateZ1Passed": True,
                "currentMasterGateZ1Passed": False,
                "globalPhase10Complete": False,
                "remainingBlockers": [
                    "human_visual_review",
                    "zeroone_candidate_static_not_merged_to_master",
                    "mobile_profile",
                    "dynamic_profile",
                ],
            },
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_canonical_json(args.output, evidence)
        print(json.dumps({"output": str(args.output), "status": "passed"}, sort_keys=True))
        return 0
    finally:
        cleanup_managed_staging(
            root,
            allowed_root=requested_root.parent,
            purpose="zeroone-evidence-work",
        )


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
        "python",
        "scripts/generate_zeroone_integration_evidence.py",
        "--executable",
        "<trusted-zeroone-executable>",
        "--trusted-build-record",
        "<trusted-build-record>",
        "--zeroone-repo",
        "<exact-zeroone-source-checkout>",
        "--work-root",
        "<managed-work-root>",
        "--output",
        "closy-forge/docs/evidence/phase10_zeroone_static/execution_evidence.json",
        "--closy-sha",
        args.closy_sha,
        "--zeroone-sha",
        args.zeroone_sha,
        "--zeroone-workflow-run-id",
        str(args.zeroone_workflow_run_id),
        "--zeroone-artifact-id",
        str(args.zeroone_artifact_id),
        "--zeroone-artifact-digest",
        args.zeroone_artifact_digest,
        "--zeroone-pr-url",
        args.zeroone_pr_url,
    ]


def _build_all_declared_families(root: Path) -> dict[str, Any]:
    return {
        "tshirt": build_demo_tshirt_package(root / "tshirt.closygarment", force=False),
        "sleeveless_top": build_demo_sleeveless_package(
            root / "sleeveless.closygarment", force=False
        ),
        "long_sleeved_top": build_demo_long_sleeved_package(
            root / "long_sleeved.closygarment", force=False
        ),
        "simple_skirt": build_demo_simple_skirt_package(
            root / "simple_skirt.closygarment", force=False
        ),
        "simple_trousers": build_demo_simple_trousers_package(
            root / "simple_trousers.closygarment", force=False
        ),
        "simple_dress": build_demo_simple_dress_package(
            root / "simple_dress.closygarment", force=False
        ),
        "button_shirt": build_demo_button_shirt_package(
            root / "button_shirt.closygarment", force=False
        ),
        "jacket_outerwear": build_demo_jacket_outerwear_package(
            root / "jacket_outerwear.closygarment", force=False
        ),
        "layered_asymmetric": build_demo_layered_asymmetric_package(
            root / "layered.closygarment", force=False
        ),
    }


def _family_inventory(package: Path, report: dict[str, Any]) -> dict[str, Any]:
    mesh = read_json(package / "simulation" / "rest_state.json")
    semantics = read_json(package / "semantic" / "garment_graph.json")
    panels = sorted(str(panel_id) for panel_id in semantics.get("panelMapping", {}))
    derivative_materials = read_json(
        package / "zeroone" / "static-d0" / "derivative" / "materials.json"
    )
    materials = sorted(
        str(item["materialId"]) for item in derivative_materials.get("materials", [])
    )
    layers = sorted(
        {
            str(item.get("layerId", "layer.default"))
            for item in semantics.get("components", [])
        }
    )
    seams = sorted(str(item["id"]) for item in semantics.get("seams", []))
    openings = sorted(str(item["id"]) for item in semantics.get("openings", []))
    asset = report["assetAudit"]
    return {
        "exactCanonicalInputHashes": report["canonicalAuthorityHashes"],
        "topologyHash": mesh["topologyHash"],
        "panelIds": panels,
        "seamIds": seams,
        "openingIds": openings,
        "materialIds": materials,
        "layerIds": layers,
        "clusterCount": int(asset["clusterCount"]),
        "hierarchyNodeCount": int(asset["hierarchyNodeCount"]),
        "pageCount": int(asset["pageCount"]),
        "pagePackCount": int(asset["pagePackCount"]),
        "bounds": mesh["bounds"],
        "semanticBoundaryPreservation": bool(panels and seams and openings and materials),
    }


if __name__ == "__main__":
    raise SystemExit(main())
