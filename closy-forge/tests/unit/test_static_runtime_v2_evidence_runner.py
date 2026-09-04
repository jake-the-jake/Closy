from __future__ import annotations

import runpy
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

RUNNER = runpy.run_path(
    str(
        Path(__file__).resolve().parents[2]
        / "scripts/generate_static_zeroone_runtime_v2_evidence.py"
    )
)
TERMINAL_OUTCOME = cast(Callable[[str], str], RUNNER["_integration_terminal_outcome"])
AGGREGATE_STAGES = cast(
    Callable[[list[dict[str, Any]]], dict[str, dict[str, Any]]],
    RUNNER["_aggregate_stage_outcomes"],
)


def test_static_runtime_runner_preserves_processor_failure_for_conventional_fallback() -> None:
    assert TERMINAL_OUTCOME("valid") == "passed"
    assert TERMINAL_OUTCOME("unavailable") == "unsupported"
    assert TERMINAL_OUTCOME("derivative_corrupt") == "corrupt_or_invalid"
    assert TERMINAL_OUTCOME("process_failed") == "failed"


def test_static_runtime_runner_conserves_pass_not_run_and_blocked_stage_rows() -> None:
    passing = {
        "terminalOutcome": "passed",
        "stageAudit": {
            "stages": {
                stage: {"status": "not_run" if stage in {"Z3", "Z7"} else "passed"}
                for stage in ("Z3", "Z4", "Z5", "Z6", "Z7", "Z8")
            }
        },
    }
    failed = {"terminalOutcome": "failed", "stageAudit": None}

    aggregate = AGGREGATE_STAGES([passing, failed])

    assert aggregate["Z3"] == {
        "planned": 2,
        "passed": 0,
        "failed": 0,
        "not_run": 1,
        "dependency_blocked": 1,
        "corrupt_or_invalid": 0,
        "terminalConservation": True,
    }
    assert aggregate["Z4"]["passed"] == 1
    assert aggregate["Z4"]["dependency_blocked"] == 1
    assert aggregate["Z4"]["terminalConservation"] is True
