from __future__ import annotations

import argparse
import json
import platform
import subprocess
import time
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_file
from closy_forge.package_io.managed_output import (
    cleanup_managed_staging,
    create_managed_staging,
    remove_managed_output,
)
from closy_forge.pipeline.build_tshirt_demo import build_demo_tshirt_package
from closy_forge.validation.validator import validate_package
from closy_forge.zeroone.derivative_inspection import inspect_static_derivative
from closy_forge.zeroone.integration import integrate_zeroone_static
from closy_forge.zeroone.request import authority_hashes, build_zeroone_request
from closy_forge.zeroone.validation import inspect_zeroone_namespace

PROFILE_ID = "Z1-D0-representative-static"
STATIC_PROFILE = "closy-static-d0-cpu-v1"
FAMILY = "tshirt"


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze and execute representative Z1 evidence.")
    parser.add_argument("--executable", required=True, type=Path)
    parser.add_argument("--trusted-build-record", required=True, type=Path)
    parser.add_argument("--expected-executable-sha256", required=True)
    parser.add_argument("--zeroone-repo", required=True, type=Path)
    parser.add_argument("--zeroone-sha", required=True)
    parser.add_argument("--zeroone-pr-url", required=True)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--manifest-output", required=True, type=Path)
    parser.add_argument("--evidence-output", required=True, type=Path)
    parser.add_argument("--review-output", required=True, type=Path)
    parser.add_argument("--closy-sha", required=True)
    args = parser.parse_args()

    repository = Path(__file__).resolve().parents[2]
    _require_clean_exact_head(repository, args.closy_sha)
    _require_clean_exact_head(args.zeroone_repo, args.zeroone_sha)
    executable_hash = sha256_file(args.executable.resolve(strict=True))
    if executable_hash != args.expected_executable_sha256:
        raise ValueError("representative executable hash mismatch")

    requested_root = args.work_root.resolve(strict=False)
    root = create_managed_staging(
        requested_root,
        allowed_root=requested_root.parent,
        purpose="z1-representative-evidence",
    )
    started = time.perf_counter_ns()
    try:
        package = root / "representative_tshirt.closygarment"
        build_demo_tshirt_package(package, force=False)
        validation_before = validate_package(package)
        if validation_before["status"] != "passed":
            raise RuntimeError("representative package validation failed")
        manifest = read_json(package / "manifest.json")
        c3_path = package / "reports/production_binding_c3.json"
        c3 = read_json(c3_path)
        request = build_zeroone_request(
            invocation_root=root,
            package=package,
            output=root / "frozen-request-output",
            closy_sha=args.closy_sha,
            request_label="z1-representative-freeze",
        )
        frozen = _frozen_manifest(
            args=args,
            package_manifest=manifest,
            package_manifest_hash=sha256_file(package / "manifest.json"),
            c3=c3,
            c3_hash=sha256_file(c3_path),
            request=request,
            executable_hash=executable_hash,
        )
        args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
        write_canonical_json(args.manifest_output, frozen)
        frozen_hash = sha256_file(args.manifest_output)

        result = integrate_zeroone_static(
            package=package,
            invocation_root=root,
            closy_sha=args.closy_sha,
            executable=args.executable,
            trusted_build_record=args.trusted_build_record,
            expected_executable_sha256=args.expected_executable_sha256,
            expected_zeroone_sha=args.zeroone_sha,
            publish=True,
        )
        namespace = inspect_zeroone_namespace(package)
        inspection: dict[str, Any] = {"status": "not_run"}
        rebuild: dict[str, Any] = {"executed": False, "passed": False}
        if result.status == "valid" and namespace.get("status") == "derivative_valid":
            inspection = inspect_static_derivative(
                package,
                review_output=args.review_output,
                review_path_label="review/representative_tshirt/contact_sheet.png",
                fault_work_root=root / "fault-probes",
            )
            derivative_hash = result.report["canonicalDerivativeHash"]
            optional_root = package / "zeroone"
            remove_managed_output(
                optional_root / "static-d0",
                allowed_root=optional_root,
                purpose="zeroone-static-d0",
            )
            if not any(optional_root.iterdir()):
                optional_root.rmdir()
            absent_after_delete = inspect_zeroone_namespace(package).get("status") == "not_present"
            rebuilt = integrate_zeroone_static(
                package=package,
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
                absent_after_delete
                and rebuilt.status == "valid"
                and rebuilt_hash == derivative_hash
                and inspect_zeroone_namespace(package).get("status") == "derivative_valid"
            )
            rebuild = {
                "executed": True,
                "absentAfterDelete": absent_after_delete,
                "canonicalDerivativeHashBefore": derivative_hash,
                "canonicalDerivativeHashAfter": rebuilt_hash,
                "fallbackPreserved": rebuilt.fallback_preserved,
                "passed": rebuild_passed,
            }

        c3_pass = (
            c3["profile"]["capabilityId"] == "C3-Binding-D0"
            and c3["readiness"]["gateC3Status"] == "complete_for_d0_fixed_avatar_tshirt_profile"
            and c3["readiness"]["acceptedForD0RuntimeBindingProfile"] is True
            and c3["persistedValidation"]["status"] == "pass"
        )
        resume = result.report.get("resumeRun", {})
        passed = (
            result.status == "valid"
            and namespace.get("status") == "derivative_valid"
            and inspection.get("status") == "pass"
            and rebuild.get("passed") is True
            and result.fallback_preserved
            and result.canonical_authority_preserved
            and result.deterministic_derivative
            and resume.get("interruptionDiagnostic") == "E_INJECTED_INTERRUPTION_BEFORE_PUBLICATION"
            and resume.get("resumeState") == "matched"
            and resume.get("validatedNativeDerivative") is True
            and c3_pass
            and sha256_file(args.manifest_output) == frozen_hash
        )
        evidence = {
            "schemaVersion": 1,
            "reportVersion": "closy.z1.representative_static.evidence.v1",
            "profileId": PROFILE_ID,
            "status": "pass" if passed else "fail",
            "evidenceClassification": "local_candidate",
            "frozenManifest": {
                "path": args.manifest_output.name,
                "sha256": frozen_hash,
                "unchangedAfterExecution": sha256_file(args.manifest_output) == frozen_hash,
            },
            "closySha": args.closy_sha,
            "zeroOneSha": args.zeroone_sha,
            "executableSha256": executable_hash,
            "family": FAMILY,
            "garmentId": manifest["garmentId"],
            "canonicalPackageDigest": _package_digest(manifest),
            "packageValidationBefore": validation_before,
            "c3Binding": {
                "status": "pass" if c3_pass else "fail",
                "reportPath": "reports/production_binding_c3.json",
                "reportSha256": sha256_file(c3_path),
                "profile": c3["profile"],
                "readiness": c3["readiness"],
                "persistedValidation": c3["persistedValidation"],
            },
            "integration": result.to_json(),
            "namespaceAudit": namespace,
            "independentDerivativeInspection": inspection,
            "deleteAndRebuild": rebuild,
            "timings": {"wallNanoseconds": time.perf_counter_ns() - started},
            "host": {
                "platform": platform.system().lower(),
                "architecture": platform.machine().lower(),
            },
            "claims": {
                "representativeStaticProfilePassed": passed,
                "currentMasterZ1Passed": False,
                "globalZ1Passed": False,
                "humanVisualReviewPerformed": False,
                "dynamicDeformationExecuted": False,
            },
            "limitations": [
                "exact fixed-avatar project-authored synthetic T-shirt only",
                "candidate ZeroOne PR head is not current master",
                "contact sheet is persisted but not human-reviewed",
                "dynamic deformation is a separate Z2 profile",
            ],
        }
        args.evidence_output.parent.mkdir(parents=True, exist_ok=True)
        write_canonical_json(args.evidence_output, evidence)
        print(
            json.dumps(
                {
                    "output": str(args.evidence_output),
                    "profile": PROFILE_ID,
                    "status": evidence["status"],
                },
                sort_keys=True,
            )
        )
        return 0 if passed else 1
    finally:
        cleanup_managed_staging(
            root,
            allowed_root=requested_root.parent,
            purpose="z1-representative-evidence",
        )


def _frozen_manifest(
    *,
    args: argparse.Namespace,
    package_manifest: dict[str, Any],
    package_manifest_hash: str,
    c3: dict[str, Any],
    c3_hash: str,
    request: dict[str, Any],
    executable_hash: str,
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "manifestVersion": "closy.z1.representative_static.manifest.v1",
        "profileId": PROFILE_ID,
        "frozenBeforeExecution": True,
        "family": FAMILY,
        "garmentId": package_manifest["garmentId"],
        "canonicalPackageDigest": _package_digest(package_manifest),
        "packageManifestSha256": package_manifest_hash,
        "closySha": args.closy_sha,
        "staticRequest": {
            "schemaVersion": request["schemaVersion"],
            "profile": request["profile"],
            "inputRole": request["inputRole"],
            "inputAssetPath": request["inputAssetPath"],
            "inputContentSha256": request["inputContentSha256"],
            "topologyHash": request["topologyHash"],
            "canonicalAuthorityHashes": authority_hashes(request),
        },
        "zeroOne": {
            "sourceSha": args.zeroone_sha,
            "executableSha256": executable_hash,
            "profile": STATIC_PROFILE,
            "pullRequest": args.zeroone_pr_url,
            "sourceClassification": "unmerged_candidate_static_pr_head",
        },
        "pairedC3Binding": {
            "capabilityId": c3["profile"]["capabilityId"],
            "reportProfileId": c3["profile"]["id"],
            "capabilityProfileHash": c3["profile"]["capabilityProfileHash"],
            "reportSha256": c3_hash,
            "reportIntegrityHash": c3["integrity"]["productionBindingC3ReportHash"],
            "gateC3Status": c3["readiness"]["gateC3Status"],
            "acceptedForD0RuntimeBindingProfile": c3["readiness"][
                "acceptedForD0RuntimeBindingProfile"
            ],
        },
        "acceptanceRule": (
            "all static clean/cache/resume/determinism/authority/inspection/rebuild checks "
            "and paired C3-Binding-D0 must pass conjunctively"
        ),
    }


def _require_clean_exact_head(repository: Path, expected: str) -> None:
    actual = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if actual != expected:
        raise ValueError(f"repository head mismatch: expected {expected}, got {actual}")
    if subprocess.run(["git", "diff", "--quiet"], cwd=repository, check=False).returncode:
        raise RuntimeError("representative evidence source checkout must be clean")
    if subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=repository, check=False
    ).returncode:
        raise RuntimeError("representative evidence source checkout has staged changes")


def _package_digest(manifest: dict[str, Any]) -> str:
    digest = manifest.get("canonicalPackageDigest", manifest.get("packageDigest"))
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("representative package digest is missing")
    return digest


if __name__ == "__main__":
    raise SystemExit(main())
