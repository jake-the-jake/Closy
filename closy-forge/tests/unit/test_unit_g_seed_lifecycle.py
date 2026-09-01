from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from closy_forge.disjoint_benchmark_v1.lifecycle import (
    SeedLifecycleState,
    inspect_seed_lifecycle,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures/d0_disjoint_tshirt_benchmark_v1"
BASE_FILES = (
    "protocol_lock.json",
    "development_lock.json",
    "development_summary.json",
)
AUTHORITY_FILES = (
    "evaluator/seed_authority.json",
    "evaluator/raw_draw_rejection_transcript.json",
    "evaluator/commitments.json",
)
SEALED_FILES = (
    "evaluator/predictions.json",
    "evaluator/isolation_report.json",
    "evaluator/prediction_freeze.json",
    "evaluator/target_reveal.json",
    "evaluator/evaluation_attempt_failure.json",
    "evaluator/benchmark_result.json",
)
CHRONOLOGY_FILES = (
    "evaluator/seed_authority.json",
    "evaluator/commitments.json",
    "evaluator/predictions.json",
    "evaluator/prediction_freeze.json",
    "evaluator/target_reveal.json",
    "evaluator/evaluation_attempt_failure.json",
    "evaluator/benchmark_result.json",
)


def test_committed_unit_g_state_is_sealed_read_only() -> None:
    report = inspect_seed_lifecycle(FIXTURE)
    assert report.state == SeedLifecycleState.SEALED_POST_EVALUATOR
    assert report.issues == ()
    assert report.authority_run_id == 33467062432
    assert report.authority_job_id == 99729005374
    assert report.sealed_verification_only is True


def test_pre_authority_and_frozen_pre_evaluator_states_are_derived(tmp_path: Path) -> None:
    pre = tmp_path / "pre"
    _copy_files(pre, BASE_FILES)
    assert inspect_seed_lifecycle(pre).state == SeedLifecycleState.PRE_AUTHORITY

    frozen = tmp_path / "frozen"
    _copy_files(frozen, (*BASE_FILES, *AUTHORITY_FILES))
    report = inspect_seed_lifecycle(frozen)
    assert report.state == SeedLifecycleState.AUTHORITY_FROZEN_PRE_EVALUATOR
    assert report.authority_run_id == 33467062432


def test_every_authority_and_chronology_field_mutation_is_rejected(tmp_path: Path) -> None:
    for relative in CHRONOLOGY_FILES:
        original = json.loads((FIXTURE / relative).read_text(encoding="utf-8"))
        assert isinstance(original, dict)
        for key in original:
            mutated = tmp_path / relative.replace("/", "_") / key
            _copy_files(mutated, (*BASE_FILES, *AUTHORITY_FILES, *SEALED_FILES))
            payload = json.loads((mutated / relative).read_text(encoding="utf-8"))
            payload[key] = _different_value(payload[key])
            (mutated / relative).write_text(
                json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            report = inspect_seed_lifecycle(mutated)
            assert report.state == SeedLifecycleState.INVALID, (relative, key)


def test_second_authority_and_reordered_inventory_fail_closed(tmp_path: Path) -> None:
    second = tmp_path / "second"
    _copy_files(second, (*BASE_FILES, *AUTHORITY_FILES, *SEALED_FILES))
    shutil.copyfile(
        second / "evaluator/seed_authority.json",
        second / "evaluator/seed_authority_second.json",
    )
    assert inspect_seed_lifecycle(second).state == SeedLifecycleState.INVALID

    reordered = tmp_path / "reordered"
    _copy_files(reordered, (*BASE_FILES, *AUTHORITY_FILES, *SEALED_FILES))
    (reordered / "evaluator/target_reveal.json").unlink()
    assert inspect_seed_lifecycle(reordered).state == SeedLifecycleState.INVALID


def test_workflow_has_no_seed_derivation_or_evaluator_dispatch_path() -> None:
    workflow = (ROOT.parent / ".github/workflows/closy-forge-unit-g-seed.yml").read_text(
        encoding="utf-8"
    )
    assert "validate_unit_g_seed_lifecycle.py" in workflow
    assert "realize_evaluator_commitments" not in workflow
    assert "derive_evaluator_seed" not in workflow
    assert "reveal_and_evaluate" not in workflow
    assert "upload-artifact" not in workflow


def _copy_files(target: Path, relatives: tuple[str, ...]) -> None:
    for relative in relatives:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FIXTURE / relative, destination)


def _different_value(value: Any) -> Any:
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, float):
        return value + 1.0
    if isinstance(value, str):
        return value + "-mutation"
    if isinstance(value, list):
        return [*value, "mutation"]
    if isinstance(value, dict):
        return {**value, "mutation": True}
    if value is None:
        return "mutation"
    raise AssertionError(f"unsupported mutation type: {type(value)!r}")
