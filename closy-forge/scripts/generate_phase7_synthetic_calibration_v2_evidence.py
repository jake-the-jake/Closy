from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.blueprint.continuation_dependency_graph import (
    build_continuation_dependency_graph,
)
from closy_forge.package_io.canonical_json import (
    canonical_dumps,
    read_json,
    write_canonical_json,
    write_canonical_text,
)
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.simulation.material_physics import build_material_preset_registry
from closy_forge.simulation.synthetic_mechanical_calibration import (
    run_synthetic_mechanical_calibration,
)

EVIDENCE_DIR = Path("docs/evidence/phase7_synthetic_mechanical_calibration_v2")
IMPLEMENTATION_BASE = "cfe3c1d5caebbb8f5de70f36abb254c896780906"


def build_evidence(forge_root: Path) -> dict[str, str]:
    docs = forge_root / "docs"
    strategy3_outcome = read_json(docs / "evidence/strategy3_blob_authority_v3/outcome_report.json")
    d0_v4_outcome = read_json(docs / "evidence/d0_v4_engineering/unit_ac_outcome.json")
    status = read_json(docs / "current_blueprint_status.json")
    calibration = run_synthetic_mechanical_calibration(build_material_preset_registry())
    graph = build_continuation_dependency_graph(
        strategy3_outcome=strategy3_outcome,
        d0_v4_outcome=d0_v4_outcome,
        synthetic_calibration_report=calibration,
        coverage_counts=status["coverage"]["counts"],
        phase_statuses=status["phases"],
    )
    calibration_bytes = canonical_dumps(calibration).encode("utf-8")
    graph_bytes = canonical_dumps(graph).encode("utf-8")
    outcome: dict[str, Any] = {
        "schemaVersion": 1,
        "evidenceClass": "unit_ae_phase7_synthetic_mechanical_calibration_v2",
        "unit": "AE",
        "implementationBase": IMPLEMENTATION_BASE,
        "literalOutcome": ("implemented_project_authored_synthetic_mechanical_calibration_v2"),
        "phase7Status": "partial",
        "calibration": {
            "calibrationVersion": calibration["calibrationVersion"],
            "reportHash": calibration["integrity"]["reportHash"],
            "presetCount": calibration["aggregate"]["presetCount"],
            "parameterRecordCount": calibration["aggregate"]["parameterRecordCount"],
            "calibrationObservationCount": calibration["corpus"]["calibrationObservationCount"],
            "holdoutObservationCount": calibration["corpus"]["holdoutObservationCount"],
            "worstNormalizedParameterError": calibration["aggregate"][
                "worstNormalizedParameterError"
            ],
            "worstHoldoutNormalizedRmse": calibration["aggregate"]["worstHoldoutNormalizedRmse"],
            "calibratedToBaselineErrorRatio": calibration["aggregate"][
                "calibratedToBaselineErrorRatio"
            ],
            "acceptedForProjectAuthoredSyntheticCalibration": calibration["readiness"][
                "acceptedForProjectAuthoredSyntheticCalibration"
            ],
        },
        "dependencyGraph": {
            "graphVersion": graph["graphVersion"],
            "graphHash": graph["integrity"]["graphHash"],
            "unitAD": graph["sourceOutcomes"]["unitAD"],
            "dependencyReadyImplementationUnitsRemaining": [],
            "exactNextAction": graph["remainingDependencyGraph"]["exactNextAction"],
        },
        "coverage": graph["coverageSnapshot"],
        "unsupportedEvidence": calibration["unsupportedEvidence"],
        "evidenceInventory": [
            {
                "path": (
                    "docs/evidence/phase7_synthetic_mechanical_calibration_v2/"
                    "synthetic_mechanical_calibration.json"
                ),
                "byteLength": len(calibration_bytes),
                "sha256": sha256_bytes(calibration_bytes),
            },
            {
                "path": (
                    "docs/evidence/phase7_synthetic_mechanical_calibration_v2/"
                    "continuation_dependency_graph.json"
                ),
                "byteLength": len(graph_bytes),
                "sha256": sha256_bytes(graph_bytes),
            },
        ],
        "integrity": {"outcomeHash": ""},
    }
    outcome["integrity"]["outcomeHash"] = _hash_outcome(outcome)
    report_markdown = _render_report(outcome)
    return {
        "synthetic_mechanical_calibration.json": canonical_dumps(calibration),
        "continuation_dependency_graph.json": canonical_dumps(graph),
        "unit_ae_outcome.json": canonical_dumps(outcome),
        "REPORT.md": report_markdown,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate or verify Unit AE Phase 7 synthetic calibration evidence."
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    forge_root = Path(__file__).resolve().parents[1]
    outputs = build_evidence(forge_root)
    output_dir = forge_root / EVIDENCE_DIR
    if args.check:
        mismatches = [
            name
            for name, expected in outputs.items()
            if not (output_dir / name).is_file()
            or (output_dir / name).read_text(encoding="utf-8") != expected
        ]
        if mismatches:
            raise SystemExit(f"stale Unit AE evidence: {', '.join(mismatches)}")
        print("Unit AE evidence is fresh")
        return 0
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, content in outputs.items():
        if name.endswith(".json"):
            write_canonical_json(output_dir / name, read_json_text(content))
        else:
            write_canonical_text(output_dir / name, content)
    print(f"Wrote {len(outputs)} Unit AE evidence files to {output_dir}")
    return 0


def read_json_text(content: str) -> Any:
    import json

    return json.loads(content)


def _hash_outcome(outcome: dict[str, Any]) -> str:
    payload = deepcopy(outcome)
    payload["integrity"]["outcomeHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _render_report(outcome: dict[str, Any]) -> str:
    calibration = outcome["calibration"]
    coverage = outcome["coverage"]
    counts = coverage["counts"]
    accepted = str(calibration["acceptedForProjectAuthoredSyntheticCalibration"]).lower()
    return f"""# Unit AE Phase 7 synthetic mechanical calibration v2

## Literal outcome

`{outcome['literalOutcome']}`

This unit executes inverse calibration against deterministic project-authored synthetic coupon
observations. It does not contain or claim measured real-fabric, learned, private-user, GPU,
mobile, physical-accuracy, Alpha, Beta, or Production evidence.

## Executed evidence

- Presets: {calibration['presetCount']}
- Recovered parameter records: {calibration['parameterRecordCount']}
- Calibration observations: {calibration['calibrationObservationCount']}
- Unseen synthetic holdout observations: {calibration['holdoutObservationCount']}
- Worst normalized parameter error: {calibration['worstNormalizedParameterError']}
- Worst holdout normalized RMSE: {calibration['worstHoldoutNormalizedRmse']}
- Calibrated/baseline error ratio: {calibration['calibratedToBaselineErrorRatio']}
- Synthetic calibration accepted: {accepted}
- Report hash: `{calibration['reportHash']}`

## Dependency truth

Unit Y1 ended before seed, so Z/AA/AB remain ineligible. AC failed its frozen public worst-error
margin, so AD and the image-conditioned sleeveless extension are not run. Phase 7 was the first
independent dependency-ready engineering unit and is implemented here. The regenerated graph has
no unexecuted dependency-ready implementation unit under this prompt.

The 101-row coverage counts remain complete={counts['complete']}, partial={counts['partial']},
not-started={counts['not_started']}, discovery-pending={counts['discovery_pending']}. Phase 7
remains `partial` because authored synthetic calibration cannot satisfy measured real-fabric or
production-motion requirements.

## Exact next action

`{outcome['dependencyGraph']['exactNextAction']}`
"""


if __name__ == "__main__":
    raise SystemExit(main())
