from __future__ import annotations

import math
import shutil
from pathlib import Path
from typing import Any

from .common import digest_value, read_json, validate_embedded_digest, write_json
from .corpus import load_locked_sources
from .package import build_provider_package


def _build_corpus(fixture_root: Path, output_root: Path) -> list[dict[str, Any]]:
    _, sources = load_locked_sources(fixture_root)
    if output_root.exists():
        raise ValueError("manual_provider_output_must_not_exist")
    output_root.mkdir(parents=True)
    return [build_provider_package(source, output_root / source.source_id) for source in sources]


def _metric_summary(packages: list[dict[str, Any]], deterministic: bool) -> dict[str, Any]:
    rows = [row for package in packages for row in package["rows"]]
    all_errors = [float(row["maximumErrorMeters"]) for row in rows]
    p95_errors = [float(row["p95ErrorMeters"]) for row in rows]
    return {
        "sourceCount": len(packages),
        "familyCount": len({package["family"] for package in packages}),
        "evaluationRowCount": len(rows),
        "motionStateCount": len({row["stateId"] for row in rows}),
        "cleanTopologyPassRate": math.fsum(
            package["cleanup"]["status"] == "pass" for package in packages
        )
        / max(1, len(packages)),
        "minimumSemanticConfidence": min(
            float(package["semantics"]["minimumAcceptedConfidence"]) for package in packages
        ),
        "minimumBindingCoverage": min(
            float(package["binding"]["coverage"]) for package in packages
        ),
        "maximumOutOfDomainCount": max(
            int(package["binding"]["outOfDomainCount"]) for package in packages
        ),
        "maximumRestErrorMeters": max(
            float(package["binding"]["restMaximumErrorMeters"]) for package in packages
        ),
        "maximumMotionErrorMeters": max(all_errors),
        "maximumP95MotionErrorMeters": max(p95_errors),
        "maximumSeamCrackDeltaMeters": max(
            float(row["maximumSeamCrackDeltaMeters"]) for row in rows
        ),
        "totalInvertedTriangleCount": sum(int(row["invertedTriangleCount"]) for row in rows),
        "openingsPreservedRate": math.fsum(bool(row["openingsPreserved"]) for row in rows)
        / max(1, len(rows)),
        "vec4TangentPackageRate": math.fsum(
            package["renderAudit"]["clean"]["hasVec4Tangents"]
            and package["renderAudit"]["fallback"]["hasVec4Tangents"]
            for package in packages
        )
        / max(1, len(packages)),
        "maximumPackageBytes": max(int(package["packageBytes"]) for package in packages),
        "deterministicTwoBuilds": deterministic,
    }


def evaluate_locked_manual_provider_corpus(
    fixture_root: Path,
    build_a_root: Path,
    build_b_root: Path,
    *,
    source_freeze_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    protocol = read_json(fixture_root / "protocol.json")
    validate_embedded_digest(protocol, "protocolDigest")
    source_freeze = read_json(source_freeze_path)
    validate_embedded_digest(source_freeze, "sourceFreezeDigest")
    packages_a = _build_corpus(fixture_root, build_a_root)
    packages_b = _build_corpus(fixture_root, build_b_root)
    digest_a = digest_value(
        [(package["sourceId"], package["packageDigest"]) for package in packages_a]
    )
    digest_b = digest_value(
        [(package["sourceId"], package["packageDigest"]) for package in packages_b]
    )
    metrics = _metric_summary(packages_a, digest_a == digest_b)
    gates = []
    for gate_id, definition in sorted(protocol["gates"].items()):
        metric = definition["metric"]
        value = metrics[metric]
        operator = definition["operator"]
        threshold = definition["threshold"]
        passed = (
            value >= threshold
            if operator == ">="
            else value <= threshold
            if operator == "<="
            else value == threshold
        )
        gates.append(
            {
                "gateId": gate_id,
                "metric": metric,
                "operator": operator,
                "threshold": threshold,
                "observed": value,
                "status": "pass" if passed else "fail",
            }
        )
    passed = all(gate["status"] == "pass" for gate in gates)
    first_unmet = next((gate["gateId"] for gate in gates if gate["status"] == "fail"), None)
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "resultVersion": "closy.manual_provider_c3_v1.result.v1",
        "scope": "manual_provider_scoped_C3_development",
        "literalResult": "manual_provider_scoped_C3_development_passed"
        if passed
        else "manual_provider_scoped_C3_development_failed",
        "sourceCommit": source_freeze["sourceCommit"],
        "sourceTree": source_freeze["sourceTree"],
        "sourceFreezeDigest": source_freeze["sourceFreezeDigest"],
        "protocolDigest": protocol["protocolDigest"],
        "rawSourceFreezeDigest": read_json(fixture_root / "raw_source_freeze.json")["freezeDigest"],
        "denominators": protocol["denominators"],
        "metrics": metrics,
        "gates": gates,
        "firstUnmetPredicate": first_unmet,
        "packageCorpusDigest": digest_a,
        "packageRecords": [
            {
                "sourceId": package["sourceId"],
                "family": package["family"],
                "packageId": package["packageId"],
                "packageDigest": package["packageDigest"],
                "packageBytes": package["packageBytes"],
            }
            for package in packages_a
        ],
        "optionalModelProvider": {
            "status": "not_run",
            "reason": "optional_model_or_provider_dependency_unavailable",
        },
        "claims": {
            "scopedDevelopmentC3Passed": passed,
            "globalC3Complete": False,
            "phase5Complete": False,
            "phase6Complete": False,
            "privateProviderEvidence": False,
            "realGarmentEvidence": False,
            "mobileRuntimeEvidence": False,
            "humanVisualAcceptance": False,
        },
        "limitations": [
            "nine project-authored public dense shells only",
            "independent dense deformation is synthetic and not cloth ground truth",
            "host CPU package and binding evidence only",
            "no private provider, real garment, mobile GPU, or human visual evidence",
            "does not complete blueprint Phase 5, Phase 6, or global C3",
        ],
        "execution": {
            "benchmarkRunCount": 1,
            "cleanBuildCount": 2,
            "secondBuildRetained": False,
        },
    }
    result["resultDigest"] = digest_value(result)
    return result, packages_a


def copy_first_build(source_root: Path, destination_root: Path) -> None:
    if destination_root.exists():
        raise ValueError("publication_package_root_must_not_exist")
    shutil.copytree(source_root, destination_root)


def write_result(path: Path, result: dict[str, Any]) -> None:
    write_json(path, result)
