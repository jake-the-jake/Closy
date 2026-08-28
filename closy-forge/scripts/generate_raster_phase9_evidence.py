from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps, read_json, write_canonical_json
from closy_forge.package_io.managed_output import (
    cleanup_managed_staging,
    create_managed_staging,
    publish_managed_staging,
)
from closy_forge.pattern_inference.correction_session_v2 import (
    record_correction,
    start_correction_session,
)
from closy_forge.pattern_inference.execution_evidence_v2 import process_memory_snapshot
from closy_forge.pattern_inference.raster_execution_v3 import execute_raster_downstream_v3
from closy_forge.pattern_inference.raster_foundation_v3 import write_raster_foundation_v3


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate or verify Phase 9 raster-derived synthetic D0 evidence."
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--closy-sha", required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    forge_root = Path(__file__).resolve().parents[1]
    repository_root = forge_root.parent
    _require_git_head(repository_root, args.closy_sha)
    if _content_dirty(repository_root):
        raise RuntimeError("raster_evidence_source_checkout_must_be_clean")
    if args.check:
        if not args.output.is_dir():
            raise RuntimeError("committed_raster_evidence_missing")
        with tempfile.TemporaryDirectory(prefix="closy-phase9-raster-check-") as temporary:
            generated = Path(temporary) / "evidence"
            _generate(generated, closy_sha=args.closy_sha)
            differences = _compare_evidence(args.output, generated)
        if differences:
            raise RuntimeError("raster_evidence_mismatch:" + ";".join(differences))
        print(json.dumps({"status": "match", "output": args.output.as_posix()}))
        return 0

    output = args.output.resolve(strict=False)
    staging = create_managed_staging(
        output,
        allowed_root=output.parent,
        purpose="phase9-raster-evidence",
    )
    try:
        summary = _generate(staging, closy_sha=args.closy_sha)
        publish_managed_staging(
            staging,
            output,
            allowed_root=output.parent,
            purpose="phase9-raster-evidence",
            force=args.force,
        )
    finally:
        cleanup_managed_staging(
            staging,
            allowed_root=output.parent,
            purpose="phase9-raster-evidence",
        )
    print(json.dumps(summary, sort_keys=True))
    return 0


def _generate(output: Path, *, closy_sha: str) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    wall_start = time.perf_counter_ns()
    cpu_start = time.process_time_ns()
    foundation = write_raster_foundation_v3(output)
    downstream = execute_raster_downstream_v3(foundation)
    write_canonical_json(output / "downstream_execution.json", downstream)
    correction = _simulated_correction_evidence(foundation)
    write_canonical_json(output / "correction_session.json", correction)
    summary = {
        "schemaVersion": 1,
        "evidenceVersion": "closy.phase9_raster_synthetic_d0.execution.v1",
        "closySha": closy_sha,
        "scope": "project_authored_synthetic_raster_unassisted_host_cpu_d0",
        "corpusHash": foundation["hashes"]["dataset"],
        "modelHash": foundation["model"]["integrity"]["modelHash"],
        "weightsHash": foundation["model"]["integrity"]["weightsHash"],
        "E1": downstream["E1"],
        "E2": downstream["E2"],
        "humanCorrectionStatus": "not_run",
        "privateUserEvidence": False,
        "realPhotoEvidence": False,
        "globalPhase9": "partial",
        "runtime": {
            "wallMilliseconds": round((time.perf_counter_ns() - wall_start) / 1_000_000, 6),
            "cpuMilliseconds": round((time.process_time_ns() - cpu_start) / 1_000_000, 6),
            "memory": process_memory_snapshot(),
        },
    }
    write_canonical_json(output / "execution_summary.json", summary)
    return summary


def _simulated_correction_evidence(bundle: dict[str, Any]) -> dict[str, Any]:
    sample = bundle["dataset"]["samples"][-1]
    session = start_correction_session(
        bundle["model"],
        sample["input"],
        session_id="correction.raster.synthetic.001",
        seed=39_971,
    )
    session = record_correction(
        session,
        field="easeNormalized",
        value=0.28,
        accepted=False,
        reason_code="simulated_reject_excess_drape",
    )
    session = record_correction(
        session,
        field="widthScale",
        value=1.02,
        accepted=True,
        reason_code="simulated_accept_width_adjustment",
    )
    return {
        "schemaVersion": 1,
        "workflowVersion": "closy.raster_correction_review.synthetic_d0.v1",
        "display": {
            "decodedViewLabels": sample["captureAudit"]["viewLabels"],
            "decodedPixelHashes": sample["captureAudit"]["pixelHashes"],
            "maskSource": "unassisted_border_mode_colour_distance",
            "landmarkSource": "pixel_boundary_observables_only",
            "proposedGrammarProgramVisible": True,
        },
        "supportedActions": ["accept", "reject", "defer", "edit_length", "edit_width", "edit_ease"],
        "session": session,
        "rebuildDeterministic": session["deterministicRebuildVerified"],
        "provenanceRecorded": True,
        "unexpectedUploadPossible": False,
        "automatedInteraction": True,
        "humanReviewStatus": "not_run",
    }


def _compare_evidence(expected: Path, actual: Path) -> list[str]:
    names = (
        "raster_dataset.json",
        "split.json",
        "corpus_manifest.json",
        "model.json",
        "evaluation.json",
        "dataset_card.json",
        "model_card.json",
        "training_config.json",
        "training_curve.json",
        "reproducibility.json",
        "licence_provenance.json",
        "correction_session.json",
    )
    differences = []
    for name in names:
        left = expected / name
        right = actual / name
        if not left.is_file() or not right.is_file():
            differences.append(f"missing:{name}")
        elif left.read_bytes() != right.read_bytes():
            differences.append(f"content:{name}")
    for name in ("downstream_execution.json", "execution_summary.json"):
        left = _without_runtime(read_json(expected / name))
        right = _without_runtime(read_json(actual / name))
        if canonical_dumps(left) != canonical_dumps(right):
            differences.append(f"semantic:{name}")
    return differences


def _without_runtime(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_runtime(child)
            for key, child in value.items()
            if key not in {"runtime", "wallMilliseconds", "cpuMilliseconds", "memory"}
        }
    if isinstance(value, list):
        return [_without_runtime(item) for item in value]
    return value


def _require_git_head(repository: Path, expected: str) -> None:
    actual = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if actual != expected:
        raise RuntimeError(f"closy_head_mismatch:{actual}")


def _content_dirty(repository: Path) -> bool:
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return bool(status.strip())


if __name__ == "__main__":
    raise SystemExit(main())
