from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

KNOWN_ATTEMPT_STATES = frozenset({"pass", "failed", "abstained", "missing", "corrupt", "not_run"})


def derive_attempt_semantics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    states = Counter(str(row.get("status", "missing")) for row in rows)
    unknown = sorted(set(states) - KNOWN_ATTEMPT_STATES)
    if unknown:
        raise ValueError("unit_t_unknown_attempt_state")
    executed = states["pass"] + states["failed"] + states["abstained"] + states["corrupt"]
    return {
        "attemptCount": len(rows),
        "attemptsExecutedCount": executed,
        "predictionArtifactProducedCount": sum(
            row.get("status") == "pass" and isinstance(row.get("predictionArtifact"), str)
            for row in rows
        ),
        "predictionFailureCount": states["failed"],
        "explicitAbstentionCount": states["abstained"],
        "missingCount": states["missing"],
        "corruptCount": states["corrupt"],
        "notRunCount": states["not_run"],
        "statusCounts": {state: states[state] for state in sorted(KNOWN_ATTEMPT_STATES)},
        "semanticRule": "literal_status_values_are_not_reinterpreted",
    }
