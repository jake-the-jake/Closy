from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from closy_forge.blueprint.status import (
    build_status_model,
    render_status_summary,
    validate_status_model,
)
from closy_forge.truth_authority_integrity_v3.status_reconciliation import (
    build_resume,
    reconcile_coverage,
    reconcile_stack,
    render_master_checkpoint,
    render_resume,
)
from closy_forge.truth_authority_integrity_v3.truth_overlay import (
    build_integrity_report,
    build_truth_overlay,
    validate_truth_overlay,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FORGE_ROOT = REPO_ROOT / "closy-forge"
OUTPUT_ROOT = FORGE_ROOT / "docs/evidence/truth_authority_integrity_v3"
DOCS_ROOT = FORGE_ROOT / "docs"
PUBLICATION_CONTEXT = OUTPUT_ROOT / "publication_context.json"


def outputs(publication: dict[str, Any]) -> dict[Path, bytes]:
    integrity = build_integrity_report(REPO_ROOT)
    overlay = build_truth_overlay(REPO_ROOT, integrity)
    issues = validate_truth_overlay(overlay)
    if issues or integrity.get("allIntegrityPredicatesPass") is not True:
        raise ValueError(";".join([*issues, "unit_y0_integrity_predicate_failed"]))
    coverage = reconcile_coverage(
        REPO_ROOT,
        _load_json(DOCS_ROOT / "blueprint_coverage.json"),
        overlay,
    )
    stack = reconcile_stack(
        REPO_ROOT,
        _load_json(DOCS_ROOT / "pr_stack_manifest.json"),
        overlay,
    )
    status = build_status_model(
        coverage,
        stack,
        evidence_anchor_sha=publication["sourceEvidenceAnchor"],
        truth_overlay=overlay,
    )
    status_issues = validate_status_model(status, coverage, stack, truth_overlay=overlay)
    if status_issues:
        raise ValueError(";".join(status_issues))
    resume = build_resume(
        overlay,
        source_anchor=publication["sourceEvidenceAnchor"],
        branch=publication["branch"],
        pull_request=publication["pullRequest"],
    )
    return {
        PUBLICATION_CONTEXT: _json_bytes(publication),
        OUTPUT_ROOT / "integrity_report.json": _json_bytes(integrity),
        OUTPUT_ROOT / "v2_repository_blob_migration_audit.json": _json_bytes(
            integrity["migrationAudit"]
        ),
        OUTPUT_ROOT / "typed_record_inventory.json": _json_bytes(integrity["typedInventory"]),
        OUTPUT_ROOT / "truth_overlay.json": _json_bytes(overlay),
        OUTPUT_ROOT / "REPORT.md": _report(overlay, integrity).encode("utf-8"),
        DOCS_ROOT / "blueprint_coverage.json": _json_bytes(coverage),
        DOCS_ROOT / "pr_stack_manifest.json": _json_bytes(stack),
        DOCS_ROOT / "current_blueprint_status.json": _json_bytes(status),
        DOCS_ROOT / "BLUEPRINT_STATUS_SUMMARY.md": render_status_summary(status).encode("utf-8"),
        DOCS_ROOT / "ACTIVE_BLUEPRINT_RESUME.json": _json_bytes(resume),
        DOCS_ROOT / "ACTIVE_BLUEPRINT_RESUME.md": render_resume(resume).encode("utf-8"),
        DOCS_ROOT / "MASTER_BLUEPRINT_PROGRESS.md": render_master_checkpoint(
            (DOCS_ROOT / "MASTER_BLUEPRINT_PROGRESS.md").read_text(encoding="utf-8"),
            overlay,
            source_anchor=publication["sourceEvidenceAnchor"],
            branch=publication["branch"],
            pull_request=publication["pullRequest"],
        ).encode("utf-8"),
    }


def build(*, check: bool, publication: dict[str, Any]) -> bool:
    generated = outputs(publication)
    if check:
        return all(path.is_file() and path.read_bytes() == data for path, data in generated.items())
    for path, data in generated.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--pull-request", type=int)
    parser.add_argument("--source-anchor")
    parser.add_argument("--branch")
    args = parser.parse_args()
    publication = _publication_context(
        pull_request=args.pull_request,
        source_anchor=args.source_anchor,
        branch=args.branch,
    )
    stable = build(check=args.check, publication=publication)
    print(json.dumps({"status": "pass" if stable else "fail"}, sort_keys=True))
    return 0 if stable else 1


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected mapping at {path}")
    return value


def _publication_context(
    *, pull_request: int | None, source_anchor: str | None, branch: str | None
) -> dict[str, Any]:
    if pull_request is None and source_anchor is None and branch is None:
        if not PUBLICATION_CONTEXT.is_file():
            raise ValueError("publication context missing; provide --pull-request")
        return _load_json(PUBLICATION_CONTEXT)
    if pull_request is None:
        raise ValueError("--pull-request is required when creating publication context")
    resolved_anchor = source_anchor or _git("rev-parse", "HEAD")
    resolved_branch = branch or _git("branch", "--show-current")
    return {
        "schemaVersion": 1,
        "contextVersion": "closy.truth_authority_publication_context.v1",
        "branch": resolved_branch,
        "pullRequest": pull_request,
        "sourceEvidenceAnchor": resolved_anchor,
        "finalPublicationHead": None,
        "finalHeadAttestationAuthority": "exact_head_ci_and_draft_pr_body",
    }


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def _report(overlay: dict[str, Any], integrity: dict[str, Any]) -> str:
    unit_t = overlay["unitT"]
    unit_u = overlay["unitU"]
    supplemental = overlay["researchPrototype"]["supplemental"]
    return (
        "# Unit Y0 Truth and Authority Integrity\n\n"
        "This append-only successor report does not alter or rerun Units S, T, or U. "
        "It separates historical scientific outcomes from authority-integrity controls.\n\n"
        "## Unit T\n\n"
        f"Literal outcome: `{unit_t['literalOutcome']}`. Of "
        f"{unit_t['attemptsScheduledCount']} scheduled attempts, "
        f"{unit_t['attemptsExecutedCount']} executed and "
        f"{unit_t['predictionArtifactProducedCount']} produced prediction artifacts. "
        f"All {unit_t['compileRowsScheduledCount']} compile rows were evaluated, while the "
        f"legacy counter was {unit_t['legacyFullCompileSuccessCounter']} and strict complete "
        "pixel-route compile-valid candidates were "
        f"{unit_t['strictCompletePixelRouteCompileValidCount']}. "
        f"Only {unit_t['appearanceRowsActuallyEvaluatedCount']} of "
        f"{unit_t['appearanceRowsScheduledCount']} appearance rows executed and "
        f"{unit_t['appearanceGatePassCount']} passed. This remains a scientific failure.\n\n"
        "## Unit U\n\n"
        f"Literal outcome: `{unit_u['literalOutcome']}`. The official seed, untouched fixture, "
        "oracle reveal, scientific admission, and canonical candidate did not exist. The topology "
        "strategy budget remains exhausted and the canonical candidate attempt remains "
        "available.\n\n"
        "## Integrity\n\n"
        f"All successor integrity predicates pass: "
        f"`{str(integrity['allIntegrityPredicatesPass']).lower()}`. The migration audit proves "
        "24 locked paths: 20 raw Git-blob matches and four LF-to-CRLF-only captures. The exact "
        "immutable failure is required in its dedicated CI lane; no old authority is reopened.\n\n"
        "## Matrix Identity\n\n"
        f"Supplemental passes: {', '.join(supplemental['passes'])}. Supplemental not run: "
        f"{', '.join(supplemental['notRun'])}. Pre-topology C3, scoped static Z1, non-solver "
        "Z2 evidence, and global gates remain distinct.\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
