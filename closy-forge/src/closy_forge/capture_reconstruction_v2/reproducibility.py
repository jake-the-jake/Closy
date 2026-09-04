from __future__ import annotations

import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from .common import canonical_digest, sha256_bytes, write_json
from .corpus import _generate_session, build_development_seed_authority
from .evaluation import _aggregate_metrics, _evaluate_session, run_contestant
from .protocol import FAMILIES, MODES, STRATA


def run_development_canary_twice(protocol: dict[str, Any], report_path: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="closy-capture-v2-canary-a-") as first_root:
        first = _run_once(protocol, Path(first_root))
    with tempfile.TemporaryDirectory(prefix="closy-capture-v2-canary-b-") as second_root:
        second = _run_once(protocol, Path(second_root))
    comparison_fields = (
        "observableManifestDigest",
        "contestantOutputDigest",
        "packageInventoryDigest",
        "evaluationDigest",
    )
    reproducible = all(first[field] == second[field] for field in comparison_fields)
    report: dict[str, Any] = {
        "schemaVersion": 2,
        "canaryVersion": "closy.capture_reconstruction_v2_development_canary.v2",
        "sessionCountPerRun": first["sessionCount"],
        "appearanceControlCountPerRun": first["appearanceControlCount"],
        "modeCounts": first["modeCounts"],
        "familyCounts": first["familyCounts"],
        "stratumCounts": first["stratumCounts"],
        "firstRun": first,
        "secondRun": second,
        "comparisonFields": list(comparison_fields),
        "canonicalDigestsReproducible": reproducible,
        "developmentIdentitiesPermanentlyExcludedFromLockedUse": True,
        "privatePathsPersisted": False,
        "terminalOutcome": "passed" if reproducible else "failed",
    }
    report["canaryDigest"] = canonical_digest(report)
    write_json(report_path, report)
    return report


def _run_once(protocol: dict[str, Any], root: Path) -> dict[str, Any]:
    sessions = _canary_sessions(protocol)
    seeds = build_development_seed_authority(protocol)
    source_root = root / "sources"
    source_root.mkdir(parents=True)
    public_rows: list[dict[str, Any]] = []
    truth_by_id: dict[str, dict[str, Any]] = {}
    source_payloads: dict[str, bytes] = {}
    for session in sessions:
        session_id = str(session["sessionId"])
        public, truth, sources = _generate_session(
            session,
            protocol,
            frozen_source_commit="development-canary-source",
            hidden_seed=seeds[session_id],
        )
        public_rows.append(public)
        truth_by_id[session_id] = truth
        for suffix, payload in sources:
            source_payloads.setdefault(f"{sha256_bytes(payload)}.{suffix}", payload)
    for name, payload in sorted(source_payloads.items()):
        (source_root / name).write_bytes(payload)
    manifest: dict[str, Any] = {
        "schemaVersion": 2,
        "manifestVersion": "closy.capture_reconstruction.development_canary.v2",
        "protocolId": protocol["protocolId"],
        "protocolDigest": protocol["protocolDigest"],
        "partition": "development_canary",
        "frozenSourceCommit": "development-canary-source",
        "frozenSourceTree": "development-canary-tree",
        "sessionCount": len(public_rows),
        "sourceReferenceCount": sum(len(row["sources"]) for row in public_rows),
        "uniqueSourceFileCount": len(source_payloads),
        "retainedBytes": sum(len(payload) for payload in source_payloads.values()),
        "contentAddressedDeduplication": True,
        "sessions": public_rows,
    }
    manifest["observableManifestDigest"] = canonical_digest(manifest)
    output = run_contestant(
        manifest,
        source_root,
        root / "packages",
        output_path=root / "contestant.json",
    )
    output_by_id = {str(row["sessionId"]): row for row in output["rows"]}
    evaluated = [
        _evaluate_session(output_by_id[str(row["sessionId"])], truth_by_id[str(row["sessionId"])])
        for row in public_rows
    ]
    evaluation = {
        "rows": evaluated,
        "metrics": _aggregate_metrics(evaluated),
    }
    return {
        "sessionCount": len(public_rows),
        "appearanceControlCount": output["appearanceControlCount"],
        "observableManifestDigest": manifest["observableManifestDigest"],
        "contestantOutputDigest": output["contestantOutputDigest"],
        "packageInventoryDigest": output["packageInventory"]["inventoryDigest"],
        "evaluationDigest": canonical_digest(evaluation),
        "modeCounts": dict(sorted(Counter(str(row["mode"]) for row in sessions).items())),
        "familyCounts": dict(sorted(Counter(str(row["family"]) for row in sessions).items())),
        "stratumCounts": dict(sorted(Counter(str(row["stratum"]) for row in sessions).items())),
    }


def _canary_sessions(protocol: dict[str, Any]) -> list[dict[str, Any]]:
    development = [row for row in protocol["sessionPlan"] if row["partition"] == "development"]
    selected: list[dict[str, Any]] = []
    for mode_index, mode in enumerate(MODES):
        for stratum_index, stratum in enumerate(STRATA):
            family = FAMILIES[(mode_index + stratum_index) % len(FAMILIES)]
            selected.append(
                next(
                    row
                    for row in development
                    if row["mode"] == mode and row["family"] == family and row["stratum"] == stratum
                )
            )
    return selected
