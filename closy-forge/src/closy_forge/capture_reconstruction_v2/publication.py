from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .blueprint_authority import (
    build_blueprint_authority,
    read_git_blob,
    verify_blueprint_authority,
)
from .common import canonical_digest, sha256_bytes, write_json
from .independent_checker import check_locked_publication
from .protocol import build_protocol
from .status_inventory import (
    build_inventory_transition,
    build_pr62_baseline_inventory,
    build_pr63_inventory,
    validate_decorated_inventory,
)
from .truth_reconciliation import build_truth_reconciliation, render_truth_markdown
from .y2_forensic import derive_y2_terminal_state

PR62_FINAL_HEAD = "0189d2f969ff9a17cdfec8c1843b26981ffa388a"
PR62_FINAL_TREE = "76d361483b551bbd2542bdbf0efb0786fa904ee5"
PR62_FINAL_RUN = "33826899350"


def prepare_source_artifacts(repository: Path) -> dict[str, Any]:
    forge = repository / "closy-forge"
    fixture_root = forge / "fixtures" / "capture_reconstruction_v2"
    evidence_root = forge / "docs" / "evidence" / "capture_reconstruction_v2"
    authority = build_blueprint_authority(repository)
    blob_oid, blob = read_git_blob(repository)
    text = blob.decode("utf-8")
    baseline = build_pr62_baseline_inventory(text, blob_oid)
    current = build_pr63_inventory(text, blob_oid, result_digest=None)
    truth = build_truth_reconciliation(PR62_FINAL_HEAD, PR62_FINAL_RUN)
    protocol = build_protocol()
    y2 = derive_y2_terminal_state(repository)
    fixture_root.mkdir(parents=True, exist_ok=True)
    evidence_root.mkdir(parents=True, exist_ok=True)
    write_json(fixture_root / "protocol.json", protocol)
    write_json(evidence_root / "blueprint_authority.json", authority)
    write_json(evidence_root / "pr62_baseline_inventory.json", baseline)
    write_json(evidence_root / "source_inventory.json", current)
    write_json(evidence_root / "truth_reconciliation.json", truth)
    (evidence_root / "TRUTH_RECONCILIATION.md").write_text(
        render_truth_markdown(truth), encoding="utf-8", newline="\n"
    )
    write_json(evidence_root / "y2_forensic.json", y2)
    summary: dict[str, Any] = {
        "schemaVersion": 2,
        "preparationVersion": "closy.capture_reconstruction_v2_source_preparation.v2",
        "protocolDigest": protocol["protocolDigest"],
        "blueprintAuthorityDigest": authority["authorityDigest"],
        "blueprintBlobSha256": authority["gitBlobSha256"],
        "parentInventoryDigest": baseline["inventoryDigest"],
        "sourceInventoryDigest": current["inventoryDigest"],
        "truthReconciliationDigest": truth["reconciliationDigest"],
        "y2ForensicDigest": y2["forensicDigest"],
    }
    summary["preparationDigest"] = canonical_digest(summary)
    write_json(evidence_root / "source_preparation.json", summary)
    return summary


def build_source_freeze(repository: Path, source_commit: str, source_tree: str) -> dict[str, Any]:
    _verify_git_identity(repository, source_commit, source_tree)
    forge = repository / "closy-forge"
    protocol = _read(forge / "fixtures" / "capture_reconstruction_v2" / "protocol.json")
    source_files = _implementation_paths(repository)
    inventory = [
        {
            "path": path.relative_to(repository).as_posix(),
            "byteLength": path.stat().st_size,
            "sha256": sha256_bytes(path.read_bytes()),
        }
        for path in source_files
    ]
    groups = {
        "generator": ("corpus.py", "producer_in_model.py", "producer_cross.py", "video_mjpeg.py"),
        "contestant": ("contestant.py", "camera_estimation.py", "fitter.py", "appearance.py"),
        "evaluator": ("evaluation.py", "evaluator_renderer.py"),
        "checker": ("independent_checker.py",),
    }
    group_digests = {
        name: canonical_digest(
            [row for row in inventory if Path(str(row["path"])).name in filenames]
        )
        for name, filenames in groups.items()
    }
    freeze: dict[str, Any] = {
        "schemaVersion": 2,
        "freezeVersion": "closy.capture_reconstruction_v2_source_freeze.v2",
        "sourceCommit": source_commit,
        "sourceTree": source_tree,
        "parentCommit": PR62_FINAL_HEAD,
        "parentTree": PR62_FINAL_TREE,
        "protocolDigest": protocol["protocolDigest"],
        "thresholdRegistryDigest": canonical_digest(protocol["thresholdRegistry"]),
        "implementationInventory": inventory,
        "implementationInventoryDigest": canonical_digest(inventory),
        "generatorImplementationDigest": group_digests["generator"],
        "contestantImplementationDigest": group_digests["contestant"],
        "evaluatorImplementationDigest": group_digests["evaluator"],
        "checkerImplementationDigest": group_digests["checker"],
        "candidateBudget": protocol["candidateBudget"],
        "singleUseLockedEvaluation": True,
        "postObservationSourceChangesAllowed": False,
        "canonicalD0CandidateBudgetConsumed": False,
        "y2BudgetConsumed": False,
    }
    freeze["freezeDigest"] = canonical_digest(freeze)
    write_json(forge / "fixtures" / "capture_reconstruction_v2" / "source_freeze.json", freeze)
    return freeze


def verify_source_freeze(repository: Path, freeze: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    try:
        _verify_git_identity(
            repository, str(freeze.get("sourceCommit", "")), str(freeze.get("sourceTree", ""))
        )
    except (subprocess.CalledProcessError, ValueError):
        failures.append("capture_v2_frozen_git_identity_invalid")
    expected_rows = freeze.get("implementationInventory", [])
    expected = {str(row.get("path")): row for row in expected_rows}
    current_paths = _implementation_paths(repository)
    current_names = {path.relative_to(repository).as_posix() for path in current_paths}
    if set(expected) != current_names:
        failures.append("capture_v2_frozen_implementation_path_set_changed")
    for relative, row in expected.items():
        path = repository / relative
        if not path.is_file():
            failures.append("capture_v2_frozen_implementation_missing")
            continue
        payload = path.read_bytes()
        if len(payload) != int(row.get("byteLength", -1)) or sha256_bytes(payload) != row.get(
            "sha256"
        ):
            failures.append("capture_v2_frozen_implementation_digest_changed")
    if freeze.get("implementationInventoryDigest") != canonical_digest(expected_rows):
        failures.append("capture_v2_frozen_inventory_digest_invalid")
    protocol = _read(
        repository / "closy-forge" / "fixtures" / "capture_reconstruction_v2" / "protocol.json"
    )
    if protocol.get("protocolDigest") != freeze.get("protocolDigest"):
        failures.append("capture_v2_frozen_protocol_digest_changed")
    if freeze.get("freezeDigest") != canonical_digest(freeze, "freezeDigest"):
        failures.append("capture_v2_freeze_digest_invalid")
    return sorted(set(failures))


def build_final_status_artifacts(
    repository: Path,
    *,
    transition_commit: str,
    envelope: dict[str, Any],
    disclosure: dict[str, Any],
    contestant_output: dict[str, Any],
    manifest: dict[str, Any],
    commitments: dict[str, Any],
) -> dict[str, Any]:
    forge = repository / "closy-forge"
    evidence = forge / "docs" / "evidence" / "capture_reconstruction_v2"
    authority = _read(evidence / "blueprint_authority.json")
    blob_oid, blob = read_git_blob(repository)
    parent = _read(evidence / "pr62_baseline_inventory.json")
    result = envelope["result"]
    child = build_pr63_inventory(
        blob.decode("utf-8"), blob_oid, result_digest=str(result["resultDigest"])
    )
    transition = build_inventory_transition(parent, child, transition_commit)
    checker = check_locked_publication(
        _read(forge / "fixtures" / "capture_reconstruction_v2" / "protocol.json"),
        manifest,
        commitments,
        contestant_output,
        envelope,
        disclosure,
    )
    if checker["terminalOutcome"] != "passed":
        raise ValueError("capture_v2_independent_checker_failed")
    write_json(evidence / "blueprint_inventory.json", child)
    write_json(evidence / "inventory_transition.json", transition)
    write_json(evidence / "independent_checker_receipt.json", checker)
    payload: dict[str, Any] = {
        "schemaVersion": 2,
        "payloadVersion": "closy.capture_reconstruction_v2_pr_body_payload.v2",
        "pullRequest": 63,
        "branch": "codex/closy-forge-synthetic-capture-reconstruction-v2",
        "parentCommit": PR62_FINAL_HEAD,
        "sourceCommit": manifest["frozenSourceCommit"],
        "sourceTree": manifest["frozenSourceTree"],
        "resultCommitIntent": result["resultCommitIntent"],
        "resultDigest": result["resultDigest"],
        "result": result["terminalOutcome"],
        "firstUnmetPredicate": result["firstUnmetPredicate"],
        "protocolDigest": result["protocolDigest"],
        "observableManifestDigest": result["observableManifestDigest"],
        "contestantOutputDigest": result["contestantOutputDigest"],
        "publicationDigest": envelope["publicationDigest"],
        "disclosureDigest": disclosure["disclosureDigest"],
        "checkerDigest": checker["checkerDigest"],
        "blueprintAuthorityDigest": authority["authorityDigest"],
        "blueprintInventoryDigest": child["inventoryDigest"],
        "blueprintStatusCounts": child["statusCounts"],
        "denominators": result["denominators"],
        "evidenceClass": result["evidenceClass"],
        "unsupportedEvidenceTiers": result["unsupportedEvidenceTiers"],
        "workflowAttestation": "external_after_exact_head_ci",
    }
    payload["payloadDigest"] = canonical_digest(payload)
    write_json(evidence / "pr_body_payload.json", payload)
    write_json(evidence / "resume.json", _resume(payload, child))
    write_json(evidence / "stack_manifest.json", _stack(payload))
    _write_report(evidence / "REPORT.md", payload)
    return payload


def check_generated_freshness(repository: Path) -> list[str]:
    forge = repository / "closy-forge"
    fixtures = forge / "fixtures" / "capture_reconstruction_v2"
    evidence = forge / "docs" / "evidence" / "capture_reconstruction_v2"
    failures: list[str] = []
    protocol = _read(fixtures / "protocol.json")
    if protocol != build_protocol():
        failures.append("capture_v2_protocol_stale")
    authority = _read(evidence / "blueprint_authority.json")
    failures.extend(verify_blueprint_authority(repository, authority))
    blob_oid, blob = read_git_blob(repository)
    blueprint_text = blob.decode("utf-8")
    baseline = _read(evidence / "pr62_baseline_inventory.json")
    expected_baseline = build_pr62_baseline_inventory(blueprint_text, blob_oid)
    if baseline != expected_baseline:
        failures.append("capture_v2_pr62_baseline_inventory_stale")
    failures.extend(validate_decorated_inventory(repository, baseline))
    source_inventory = _read(evidence / "source_inventory.json")
    expected_source = build_pr63_inventory(blueprint_text, blob_oid, result_digest=None)
    if source_inventory != expected_source:
        failures.append("capture_v2_source_inventory_stale")
    failures.extend(validate_decorated_inventory(repository, source_inventory))
    truth = _read(evidence / "truth_reconciliation.json")
    if truth != build_truth_reconciliation(PR62_FINAL_HEAD, PR62_FINAL_RUN):
        failures.append("capture_v2_truth_reconciliation_stale")
    if (evidence / "TRUTH_RECONCILIATION.md").read_text(encoding="utf-8") != render_truth_markdown(
        truth
    ):
        failures.append("capture_v2_truth_markdown_stale")
    y2 = _read(evidence / "y2_forensic.json")
    if y2 != derive_y2_terminal_state(repository):
        failures.append("capture_v2_y2_forensic_stale")
    preparation = _read(evidence / "source_preparation.json")
    expected_preparation: dict[str, Any] = {
        "schemaVersion": 2,
        "preparationVersion": "closy.capture_reconstruction_v2_source_preparation.v2",
        "protocolDigest": protocol["protocolDigest"],
        "blueprintAuthorityDigest": authority["authorityDigest"],
        "blueprintBlobSha256": authority["gitBlobSha256"],
        "parentInventoryDigest": baseline["inventoryDigest"],
        "sourceInventoryDigest": source_inventory["inventoryDigest"],
        "truthReconciliationDigest": truth["reconciliationDigest"],
        "y2ForensicDigest": y2["forensicDigest"],
    }
    expected_preparation["preparationDigest"] = canonical_digest(expected_preparation)
    if preparation != expected_preparation:
        failures.append("capture_v2_source_preparation_stale")
    canary_path = evidence / "development_canary_reproducibility.json"
    if canary_path.exists():
        canary = _read(canary_path)
        if (
            canary.get("canaryDigest") != canonical_digest(canary, "canaryDigest")
            or canary.get("terminalOutcome") != "passed"
            or canary.get("canonicalDigestsReproducible") is not True
        ):
            failures.append("capture_v2_development_canary_invalid")
    final_inventory_path = evidence / "blueprint_inventory.json"
    if final_inventory_path.exists():
        envelope = _read(evidence / "canonical_result_envelope.json")
        result = envelope["result"]
        final_inventory = _read(final_inventory_path)
        expected_final = build_pr63_inventory(
            blueprint_text, blob_oid, result_digest=str(result["resultDigest"])
        )
        if final_inventory != expected_final:
            failures.append("capture_v2_final_inventory_stale")
        failures.extend(validate_decorated_inventory(repository, final_inventory))
        transition = _read(evidence / "inventory_transition.json")
        expected_transition = build_inventory_transition(
            baseline, final_inventory, str(transition.get("transitionCommit", ""))
        )
        if transition != expected_transition:
            failures.append("capture_v2_inventory_transition_stale")
    for name, field in (
        ("blueprint_inventory.json", "inventoryDigest"),
        ("pr_body_payload.json", "payloadDigest"),
        ("resume.json", "resumeDigest"),
        ("stack_manifest.json", "stackDigest"),
    ):
        path = evidence / name
        if path.exists():
            value = _read(path)
            if value.get(field) != canonical_digest(value, field):
                failures.append(f"capture_v2_{name}_digest_invalid")
    payload_path = evidence / "pr_body_payload.json"
    if payload_path.exists() and final_inventory_path.exists():
        payload = _read(payload_path)
        final_inventory = _read(final_inventory_path)
        if _read(evidence / "resume.json") != _resume(payload, final_inventory):
            failures.append("capture_v2_resume_stale")
        if _read(evidence / "stack_manifest.json") != _stack(payload):
            failures.append("capture_v2_stack_manifest_stale")
        if (evidence / "REPORT.md").read_text(encoding="utf-8") != _report_text(payload):
            failures.append("capture_v2_report_stale")
    return sorted(failures)


def _resume(payload: Mapping[str, Any], inventory: Mapping[str, Any]) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schemaVersion": 2,
        "resumeVersion": "closy.capture_reconstruction_v2_resume.v2",
        "branch": payload["branch"],
        "parentCommit": payload["parentCommit"],
        "sourceCommit": payload["sourceCommit"],
        "resultDigest": payload["resultDigest"],
        "result": payload["result"],
        "firstUnmetPredicate": payload["firstUnmetPredicate"],
        "blueprintInventoryDigest": inventory["inventoryDigest"],
        "workflowUrlsExcluded": True,
        "privatePathsAndSeedsExcluded": True,
        "nextAction": "continue_PR64_from_exact_final_PR63_head",
    }
    value["resumeDigest"] = canonical_digest(value)
    return value


def _stack(payload: Mapping[str, Any]) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schemaVersion": 2,
        "stackVersion": "closy.capture_reconstruction_v2_stack.v2",
        "mainObservedAtStart": "859d4ee9a8a3386e95ec8c29043aa9ecc246769a",
        "parent": {"pullRequest": 62, "commit": payload["parentCommit"]},
        "current": {
            "pullRequest": 63,
            "branch": payload["branch"],
            "sourceCommit": payload["sourceCommit"],
            "state": "draft_open_unmerged",
        },
        "mainModifiedByExecutor": False,
        "forcePushRebaseMergeCloseReadyRetargetPerformed": False,
    }
    value["stackDigest"] = canonical_digest(value)
    return value


def _write_report(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(_report_text(payload), encoding="utf-8", newline="\n")


def _report_text(payload: Mapping[str, Any]) -> str:
    return f"""# Capture Reconstruction V2

Literal result: `{payload['result']}`.

- Evidence class: `{payload['evidenceClass']}`
- First unmet predicate: `{payload['firstUnmetPredicate']}`
- Result digest: `{payload['resultDigest']}`
- Protocol digest: `{payload['protocolDigest']}`
- Locked sessions: `{payload['denominators']['attemptedSessions']}`
- Appearance controls: `{payload['denominators']['appearanceControlOutcomes']}`
- Real capture: `not_run`
- Private-user evidence: `not_run`
- D0 qualification: `not_run`
- Product acceptance: `false`

This is source-guarded project-authored synthetic engineering. It is not real-photo,
physical-fabric, private-user, mobile-device, provider, human-review, Alpha, Beta,
or Production evidence.
"""


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("capture_v2_json_mapping_required")
    return value


def _verify_git_identity(repository: Path, commit: str, tree: str) -> None:
    observed = subprocess.check_output(
        ["git", "rev-parse", f"{commit}^{{tree}}"], cwd=repository, text=True
    ).strip()
    if observed != tree:
        raise ValueError("capture_v2_source_tree_mismatch")


def _implementation_paths(repository: Path) -> list[Path]:
    forge = repository / "closy-forge"
    module = forge / "src" / "closy_forge" / "capture_reconstruction_v2"
    tests = forge / "tests" / "capture_reconstruction_v2"
    schemas = forge / "schemas" / "v2"
    return sorted(
        [
            *module.glob("*.py"),
            *tests.glob("*.py"),
            *schemas.glob("capture-reconstruction-*.schema.json"),
            forge / "scripts" / "capture_reconstruction_v2.py",
            forge / "fixtures" / "capture_reconstruction_v2" / "protocol.json",
            forge / "src" / "closy_forge" / "ci" / "test_shards.py",
            forge / "pyproject.toml",
            forge / "requirements-dev.lock",
            repository / ".github" / "workflows" / "closy-forge.yml",
        ],
        key=lambda path: path.as_posix(),
    )
