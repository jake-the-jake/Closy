from __future__ import annotations

import argparse
import platform
import subprocess
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from closy_forge.family_integration_v1.appearance import capture_roundtrip
from closy_forge.family_integration_v1.compiler import compile_family, validate_family
from closy_forge.family_integration_v1.registry import FAMILIES, FamilyInputError
from closy_forge.family_integration_v1.settling import DEFAULT_SETTINGS
from closy_forge.package_io.canonical_json import canonical_dumps, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file


def run(root: Path) -> dict[str, Any]:
    if root.exists():
        raise ValueError("evaluation_output_must_be_fresh")
    root.mkdir(parents=True)
    forge = Path(__file__).resolve().parents[1]
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=forge, text=True).strip()
    source_files = sorted((forge / "src").rglob("*.py"))
    source = {p.relative_to(forge).as_posix(): sha256_file(p) for p in source_files}
    cases: list[dict[str, Any]] = [
        {"caseId": f"{spec.name}/{label}", "family": spec.name, "changes": change}
        for spec in FAMILIES
        for label, change in zip(
            ("nominal", "variation1", "variation2"), ({}, *spec.variations), strict=True
        )
    ]
    protocol = {
        "version": "family_integration_development_v1",
        "cases": cases,
        "buildCount": 54,
        "cleanRoots": 2,
        "areaThresholdM2": 1e-12,
        "bindingFloat32ToleranceM": 2e-6,
        "classification": "exposed_development",
        "parameterRanges": "unchanged_family_parameters.validate",
        "scientificCampaign": False,
        "settlingSettings": asdict(DEFAULT_SETTINGS),
    }
    write_canonical_json(root / "protocol.json", protocol)
    write_canonical_json(root / "source_inventory.json", {"head": head, "files": source})
    rows: list[dict[str, Any]] = []
    captures = []
    started = time.perf_counter()
    for repeat in (1, 2):
        for case in cases:
            target = root / f"build{repeat}" / case["caseId"]
            begin = time.perf_counter()
            write_canonical_json(
                root / "checkpoint.json",
                {
                    "rows": rows,
                    "active": {"repeat": repeat, **case},
                    "nextBuild": len(rows) + 1,
                },
            )
            try:
                compiled = compile_family(case["family"], target, changes=case["changes"])
                decoded = validate_family(target)
                row = {
                    "repeat": repeat,
                    **case,
                    "terminal": "passed",
                    "audit": decoded,
                    "packageIdentity": compiled["packageIdentity"],
                }
            except Exception as error:
                row = {
                    "repeat": repeat,
                    **case,
                    "terminal": "failed",
                    "error": f"{type(error).__name__}:{error}",
                }
            row["wallSeconds"] = time.perf_counter() - begin
            rows.append(row)
            write_canonical_json(
                root / "checkpoint.json", {"rows": rows, "nextBuild": len(rows) + 1}
            )
            print(f"{len(rows)}/54 {case['caseId']} {row['terminal']}", flush=True)
    for spec in FAMILIES:
        try:
            captures.append(
                capture_roundtrip(
                    root / "build1" / spec.name / "nominal", root / "captures" / spec.name
                )
            )
        except Exception as error:
            captures.append({"family": spec.name, "passed": False, "error": str(error)})
    negatives = []
    for spec in FAMILIES:
        for value in (float("nan"), -100):
            field = next(iter(spec.parameters().to_json()))
            try:
                spec.parameters({field: value})
            except FamilyInputError as error:
                negatives.append(
                    {
                        "family": spec.name,
                        "input": str(value),
                        "rejected": True,
                        "reason": str(error),
                    }
                )
            else:
                negatives.append({"family": spec.name, "input": str(value), "rejected": False})
    deterministic = all(
        a.get("packageIdentity") is not None
        and a.get("packageIdentity") == b.get("packageIdentity")
        for a, b in zip(rows[:27], rows[27:], strict=True)
    )
    result = {
        "version": "closy.family_integration.result.v1",
        "sourceHead": head,
        "sourceInventoryDigest": sha256_bytes(canonical_dumps(source).encode()),
        "protocolDigest": sha256_file(root / "protocol.json"),
        "host": platform.platform(),
        "classification": "exposed_development_host_cpu",
        "rows": rows,
        "buildDenominator": 54,
        "passedBuilds": sum(r["terminal"] == "passed" for r in rows),
        "deterministicTwoRoots": deterministic,
        "captures": captures,
        "negatives": negatives,
        "elapsedWallSeconds": time.perf_counter() - started,
        "physicalQualification": False,
        "globalPhase8Complete": False,
    }
    write_canonical_json(root / "result.json", result)
    index = [
        {
            "family": row["family"],
            "caseId": row["caseId"],
            "terminal": row["terminal"],
            "packageIdentity": row.get("packageIdentity"),
            "audit": row.get("audit"),
        }
        for row in rows
        if row["repeat"] == 1
    ]
    write_canonical_json(root / "family_index.json", index)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = run(args.output)
    return int(result["passedBuilds"] != 54 or not result["deterministicTwoRoots"])


if __name__ == "__main__":
    raise SystemExit(main())
