from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any

from closy_forge.garments.button_shirt.parameters import ButtonShirtParameters
from closy_forge.garments.jacket_outerwear.parameters import JacketOuterwearParameters
from closy_forge.garments.long_sleeved_top.parameters import LongSleevedTopParameters
from closy_forge.package_io.canonical_json import read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_file
from closy_forge.package_io.managed_output import (
    cleanup_managed_staging,
    create_managed_staging,
)
from closy_forge.pipeline.build_button_shirt_demo import (
    ButtonShirtBuildResult,
    build_demo_button_shirt_package,
)
from closy_forge.pipeline.build_jacket_outerwear_demo import (
    JacketOuterwearBuildResult,
    build_demo_jacket_outerwear_package,
)
from closy_forge.pipeline.build_long_sleeved_demo import (
    LongSleevedBuildResult,
    build_demo_long_sleeved_package,
)
from closy_forge.validation.validator import validate_package
from closy_forge.zeroone.parameter_regression import (
    AffectedFamily,
    ParameterRegressionCase,
    declared_parameter_bounds,
    parameter_regression_cases,
)
from closy_forge.zeroone.processing_surface import (
    PROCESSING_MANIFEST_PATH,
    PROCESSING_REPORT_PATH,
    inspect_processing_surface,
)

FAMILIES: tuple[AffectedFamily, ...] = (
    "long_sleeved_top",
    "button_shirt",
    "jacket_outerwear",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Z1 parameter-range repair evidence.")
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--closy-sha", required=True)
    parser.add_argument("--pre-fix-witnesses", required=True, type=Path)
    args = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[2]
    _require_clean_exact_head(repository_root, args.closy_sha)
    pre_fix = read_json(args.pre_fix_witnesses)
    expected_default_fallbacks = {
        str(row["family"]): str(row["conventionalFallback"]["sha256"])
        for row in pre_fix["rejectedFamilyWitnesses"]
    }
    requested_root = args.work_root.resolve(strict=False)
    root = create_managed_staging(
        requested_root,
        allowed_root=requested_root.parent,
        purpose="z1-parameter-regression",
    )
    started = time.perf_counter_ns()
    rows: list[dict[str, Any]] = []
    try:
        for family in FAMILIES:
            for case in parameter_regression_cases(family):
                row = _execute_case(
                    root=root,
                    family=family,
                    case=case,
                    expected_default_fallback=expected_default_fallbacks[family],
                )
                rows.append(row)
                print(
                    json.dumps(
                        {
                            "caseId": case.case_id,
                            "family": family,
                            "status": row["status"],
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
        replay_checks = _replay_checks(rows)
        passed = all(row["status"] == "pass" for row in rows) and all(
            check["passed"] for check in replay_checks
        )
        report = {
            "schemaVersion": 1,
            "reportVersion": "closy.z1.parameter_range_surface_repair.v1",
            "scope": "three_previously_rejected_families_declared_parameter_domain",
            "closySha": args.closy_sha,
            "preFixWitnesses": args.pre_fix_witnesses.name,
            "thresholdProfile": "closy.surface_equivalence.z1.v1",
            "executionBudget": {
                "strategyClass": "Z1-S2-SEAM-AWARE-LOCAL-VERTEX-SPLIT",
                "maximumStrategiesPerFamily": 3,
                "maximumTrialsPerStrategy": 4,
            },
            "declaredBounds": {family: declared_parameter_bounds(family) for family in FAMILIES},
            "caseCount": len(rows),
            "passedCaseCount": sum(row["status"] == "pass" for row in rows),
            "failedCaseCount": sum(row["status"] != "pass" for row in rows),
            "canonicalAuthorityMutationCount": sum(
                not row.get("canonicalAuthorityPreserved", False) for row in rows
            ),
            "fallbackLossCount": sum(not row.get("fallbackPreserved", False) for row in rows),
            "priorCollapseReplayChecks": replay_checks,
            "cases": rows,
            "status": "pass" if passed else "partial",
            "elapsedWallNanoseconds": time.perf_counter_ns() - started,
            "limitations": [
                "project-authored synthetic garment families",
                "CPU deterministic reference generation",
                "parameter topology regression is not human visual review",
                "physical cloth acceptance remains PHY1",
            ],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_canonical_json(args.output, report)
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "status": report["status"],
                    "passed": report["passedCaseCount"],
                    "failed": report["failedCaseCount"],
                },
                sort_keys=True,
            )
        )
        return 0 if passed else 1
    finally:
        cleanup_managed_staging(
            root,
            allowed_root=requested_root.parent,
            purpose="z1-parameter-regression",
        )


def _execute_case(
    *,
    root: Path,
    family: AffectedFamily,
    case: ParameterRegressionCase,
    expected_default_fallback: str,
) -> dict[str, Any]:
    package = root / family / f"{case.case_id}.closygarment"
    package.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter_ns()
    try:
        result: LongSleevedBuildResult | ButtonShirtBuildResult | JacketOuterwearBuildResult
        if family == "long_sleeved_top":
            if not isinstance(case.parameters, LongSleevedTopParameters):
                raise TypeError("long-sleeved case has the wrong parameter type")
            result = build_demo_long_sleeved_package(
                package,
                params=case.parameters,
                force=True,
            )
        elif family == "button_shirt":
            if not isinstance(case.parameters, ButtonShirtParameters):
                raise TypeError("button-shirt case has the wrong parameter type")
            result = build_demo_button_shirt_package(
                package,
                params=case.parameters,
                force=True,
            )
        else:
            if not isinstance(case.parameters, JacketOuterwearParameters):
                raise TypeError("jacket case has the wrong parameter type")
            result = build_demo_jacket_outerwear_package(
                package,
                params=case.parameters,
                force=True,
            )
        validation = validate_package(package)
        processing = inspect_processing_surface(package)
        surface_report = read_json(package / PROCESSING_REPORT_PATH)
        surface_manifest = read_json(package / PROCESSING_MANIFEST_PATH)
        fallback_hash = sha256_file(package / "render/fallback.glb")
        canonical_preserved = bool(
            surface_report["canonicalAuthority"]["allNonZeroOnePackageHashesPreserved"]
        )
        expected_matches = case.case_id != "default" or fallback_hash == expected_default_fallback
        fallback_preserved = (package / "render/fallback.glb").is_file() and canonical_preserved
        passed = (
            result.validation["status"] == "passed"
            and validation["status"] == "passed"
            and processing["status"] == "valid"
            and surface_report["status"] == "pass"
            and canonical_preserved
            and expected_matches
        )
        return {
            **case.to_json(),
            "family": family,
            "status": "pass" if passed else "fail",
            "packageDigest": result.manifest["packageDigest"],
            "fallbackSha256": fallback_hash,
            "expectedDefaultFallbackSha256": (
                expected_default_fallback if case.case_id == "default" else None
            ),
            "fallbackPreserved": fallback_preserved,
            "defaultFallbackMatchesPreFix": (
                expected_matches if case.case_id == "default" else None
            ),
            "canonicalAuthorityPreserved": canonical_preserved,
            "packageValidation": validation,
            "processingAudit": processing,
            "processingTopologyHash": surface_manifest["topologyHash"],
            "processingContentHash": surface_manifest["contentHash"],
            "processingCounts": surface_manifest["counts"],
            "repairRegions": surface_report["repairRegions"],
            "topologyAudit": surface_report["topologyAudit"],
            "surfaceDistance": surface_report["surfaceDistance"],
            "elapsedWallNanoseconds": time.perf_counter_ns() - started,
        }
    except Exception as exc:
        return {
            **case.to_json(),
            "family": family,
            "status": "fail",
            "reason": f"{type(exc).__name__}:{exc}",
            "fallbackPreserved": False,
            "canonicalAuthorityPreserved": False,
            "elapsedWallNanoseconds": time.perf_counter_ns() - started,
        }


def _replay_checks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    checks = []
    for family in FAMILIES:
        default = next(
            row for row in rows if row["family"] == family and row["caseId"] == "default"
        )
        replay = next(
            row
            for row in rows
            if row["family"] == family and row["caseId"] == "prior_default_collapse"
        )
        passed = all(
            default.get(field) == replay.get(field)
            for field in (
                "packageDigest",
                "fallbackSha256",
                "processingTopologyHash",
                "processingContentHash",
            )
        )
        checks.append(
            {
                "family": family,
                "defaultCaseId": "default",
                "replayCaseId": "prior_default_collapse",
                "passed": passed,
            }
        )
    return checks


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
        raise RuntimeError("evidence source checkout must be clean")
    if subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=repository, check=False
    ).returncode:
        raise RuntimeError("evidence source checkout must have no staged changes")


if __name__ == "__main__":
    raise SystemExit(main())
