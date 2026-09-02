from __future__ import annotations

import json
import subprocess
from pathlib import Path

from closy_forge.strategy3_blob_authority_v3.authority import write_public_failure
from closy_forge.strategy3_blob_authority_v3.git_blobs import GitBlobReader, git_blob_oid
from closy_forge.strategy3_blob_authority_v3.inventory import build_inventory
from closy_forge.strategy3_blob_authority_v3.materializer import materialized_context
from closy_forge.strategy3_blob_authority_v3.preflight import (
    compare_portability_reports,
    preflight_mutation_report,
)
from closy_forge.strategy3_blob_authority_v3.protocol import (
    OUTCOMES,
    SCIENTIFIC_SOURCE_COMMIT,
    build_lock,
    validate_lock,
)

FORGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = FORGE_ROOT.parent


def _head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_repository_blob_inventory_closes_execution_surface() -> None:
    reader = GitBlobReader(REPO_ROOT)
    inventory = build_inventory(
        reader,
        scientific_commit=SCIENTIFIC_SOURCE_COMMIT,
        wrapper_commit=_head(),
    )
    rows = inventory["rows"]
    assert inventory["blobCount"] == len(rows)
    assert inventory["executionImageBlobCount"] >= 50
    assert [row["repositoryPath"] for row in rows] == sorted(row["repositoryPath"] for row in rows)
    assert all(row["objectType"] == "blob" for row in rows)
    assert all(row["gitMode"] in {"100644", "100755"} for row in rows)
    assert inventory["baseImageDigest"].startswith("sha256:")
    assert inventory["dockerCopyInputs"]
    assert {row["action"] for row in inventory["actions"]} == {
        "actions/checkout",
        "actions/download-artifact",
        "actions/setup-python",
        "actions/upload-artifact",
    }
    generator_rows = [row for row in rows if row["declaredRole"] in {"generator", "oracle"}]
    assert generator_rows
    assert all(row["entersExecutionImage"] is False for row in generator_rows)


def test_blob_payload_identity_is_independent_of_checkout_materialization() -> None:
    reader = GitBlobReader(REPO_ROOT)
    path = "closy-forge/src/closy_forge/recovery_foundation_v2/topology_holdout.py"
    identity = reader.identity(SCIENTIFIC_SOURCE_COMMIT, path)
    payload = reader.blob(identity.blob_oid)
    assert git_blob_oid(payload) == identity.blob_oid
    assert payload.replace(b"\n", b"\r\n") != payload
    assert reader.identity(SCIENTIFIC_SOURCE_COMMIT, path) == identity


def test_lock_preserves_strategy_and_materializes_only_declared_blobs() -> None:
    lock = build_lock(REPO_ROOT, wrapper_source_commit=_head())
    assert validate_lock(REPO_ROOT, lock, verify_objects=True) == []
    assert lock["outcomeVocabulary"] == list(OUTCOMES)
    assert lock["strategyAlgorithmChanged"] is False
    assert lock["topologyStrategyBudgetRestored"] is False
    assert lock["newStrategyIntroduced"] is False
    assert lock["v2MigrationClassification"] == {
        "rawBlobExact": 20,
        "lfToCrlfOnly": 4,
        "unexplained": 0,
    }
    with materialized_context(REPO_ROOT, lock) as (context, manifest):
        files = sorted(
            path.relative_to(context).as_posix() for path in context.rglob("*") if path.is_file()
        )
        assert files == sorted(row["path"] for row in manifest["rows"])
        assert manifest["fileCount"] == lock["executionImageBlobCount"]
        assert not (context / ".git").exists()
    assert not context.exists()


def test_all_declared_mutation_classes_fail_closed() -> None:
    lock = build_lock(REPO_ROOT, wrapper_source_commit=_head())
    report = preflight_mutation_report(REPO_ROOT, lock)
    assert report
    assert all(report.values()), json.dumps(report, sort_keys=True)


def test_portability_aggregation_requires_five_matching_lanes() -> None:
    template = {
        "status": "pass",
        "lockDigest": "a",
        "inventoryDigest": "b",
        "materializedBuildContextDigest": "c",
        "scientificSourceCommit": SCIENTIFIC_SOURCE_COMMIT,
        "authorityWrapperSourceCommit": _head(),
    }
    reports = [
        {**template, "checkoutMode": "normal"},
        {**template, "checkoutMode": "normal"},
        {**template, "checkoutMode": "autocrlf_true"},
        {**template, "checkoutMode": "autocrlf_false"},
        {**template, "checkoutMode": "autocrlf_false"},
    ]
    assert compare_portability_reports(reports)["pass"] is True
    reports[-1] = {**reports[-1], "inventoryDigest": "changed"}
    assert compare_portability_reports(reports)["pass"] is False


def test_workflow_separates_precommit_contestant_and_evaluator_jobs() -> None:
    workflow = (
        REPO_ROOT / ".github/workflows/forge-unit-y1-strategy3-blob-authority-v3.yml"
    ).read_text(encoding="utf-8")
    assert "authority-precommit:" in workflow
    assert "authority-contestant:" in workflow
    assert "authority-evaluator:" in workflow
    assert workflow.index("authority-precommit:") < workflow.index("authority-contestant:")
    assert workflow.index("authority-contestant:") < workflow.index("authority-evaluator:")
    assert "--network\n            none" not in workflow
    assert "--network" in (
        FORGE_ROOT / "src/closy_forge/strategy3_blob_authority_v3/authority.py"
    ).read_text(encoding="utf-8")


def test_public_failure_is_bounded_and_never_contains_private_authority_data(
    tmp_path: Path,
) -> None:
    failure = write_public_failure(
        tmp_path / "failure",
        seed_created=False,
        stage="preflight",
        error=ValueError("x" * 1000),
        workflow_run_id="generic-test",
    )
    assert failure["literalOutcome"] == OUTCOMES[3]
    assert failure["privateArtifactsIncluded"] is False
    assert len(failure["sanitizedDiagnostic"]) == 500
    assert "rawSeed" not in failure
    assert "oracle" not in failure
