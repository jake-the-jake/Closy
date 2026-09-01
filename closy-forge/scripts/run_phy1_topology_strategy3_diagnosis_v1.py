from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import (
    canonical_dumps,
    read_json,
    write_canonical_json,
)
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.phy1_topology_strategy3_diagnosis_v1.diagnosis import (
    run_bounded_diagnosis,
)
from closy_forge.phy1_topology_strategy3_diagnosis_v1.protocol import (
    AUTHORITY_PATH,
    EVIDENCE_ROOT,
    LOCK_PATH,
    OUTCOME_PATH,
    validate_lock,
)

REVISION_PATHS = {
    1: EVIDENCE_ROOT / "revision_1.json",
    2: EVIDENCE_ROOT / "revision_2.json",
}
DIAGNOSIS_REPORT_PATH = EVIDENCE_ROOT / "diagnosis_report.json"
EVIDENCE_MANIFEST_PATH = EVIDENCE_ROOT / "evidence_manifest.json"
REPORT_PATH = EVIDENCE_ROOT / "REPORT.md"


def build(root: Path) -> tuple[dict[Path, dict[str, Any]], str]:
    lock = read_json(root / LOCK_PATH)
    issues = validate_lock(root, lock)
    if issues:
        raise ValueError(f"unit_o_lock_invalid:{','.join(issues)}")
    outcome = run_bounded_diagnosis(root, lock)
    revisions = outcome["revisions"]
    authority = read_json(root / AUTHORITY_PATH)
    diagnosis_report = {
        "schemaVersion": 1,
        "unit": "O",
        "scope": "candidate-independent final-topology transfer diagnosis",
        "repository": "jake-the-jake/Closy",
        "branch": "codex/closy-forge-phy1-topology-strategy3-diagnosis-v1",
        "pullRequest": "pending_external_attestation",
        "baseBranch": "codex/closy-forge-d0-strict-c3-confirmation-v5",
        "baseSha": "e062a30ba295ed27334622916ddb449fd76e2166",
        "mergeBase": "e062a30ba295ed27334622916ddb449fd76e2166",
        "sourceEvidenceAnchorSha": authority["sourceEvidenceAnchorSha"],
        "authorityDigest": authority["integrity"]["authorityDigest"],
        "diagnosisLockDigest": lock["integrity"]["lockDigest"],
        "outcome": outcome["outcomeClass"],
        "attemptState": outcome["attemptState"],
        "coverageState": outcome["coverageState"],
        "firstUnmetPredicate": outcome["firstUnmetPredicate"],
        "revisionsConsumed": outcome["revisionCount"],
        "admittedStrategyClass": outcome["admittedStrategyClass"],
        "candidateCreated": False,
        "candidateAttemptConsumed": False,
        "finalStrategyConsumed": False,
        "runtimeSelected": "runtime_v1",
        "runtimeSelectionReason": "unit_o_is_candidate_independent_and_cannot_select_runtime",
        "unitPEligible": outcome["unitPEligible"],
        "unitQEligible": False,
        "unitREligible": False,
        "budgetsBefore": outcome["budgetsBefore"],
        "budgetsAfter": outcome["budgetsAfter"],
        "unsupportedEvidenceClasses": sorted(
            key for key, supported in outcome["unsupportedClaims"].items() if not supported
        ),
        "platform": "deterministic CPU/source development fixtures",
        "toolchain": ["CPython 3.11", "CPython 3.12 via exact-head Forge"],
        "externalAttestation": "pending_external_attestation",
    }
    documents: dict[Path, dict[str, Any]] = {
        REVISION_PATHS[1]: revisions[0],
        REVISION_PATHS[2]: revisions[1],
        OUTCOME_PATH: outcome,
        DIAGNOSIS_REPORT_PATH: diagnosis_report,
    }
    manifest_records = [
        {
            "path": path.as_posix(),
            "sha256": sha256_bytes(canonical_dumps(document).encode("utf-8")),
        }
        for path, document in sorted(documents.items(), key=lambda item: item[0].as_posix())
    ]
    documents[EVIDENCE_MANIFEST_PATH] = {
        "schemaVersion": 1,
        "manifestVersion": "closy.phy1.topology_strategy3.diagnosis_evidence.v1",
        "records": manifest_records,
        "candidateFiles": [],
        "confirmationSeedFiles": [],
        "manifestDigest": sha256_bytes(canonical_dumps(manifest_records).encode("utf-8")),
    }
    markdown = _markdown_report(diagnosis_report, revisions)
    return documents, markdown


def write(root: Path, documents: dict[Path, dict[str, Any]], markdown: str) -> None:
    if (root / OUTCOME_PATH).exists():
        raise ValueError("unit_o_diagnosis_attempt_already_recorded_use_check_only")
    for path, document in documents.items():
        write_canonical_json(root / path, document)
    report_path = root / REPORT_PATH
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(markdown, encoding="utf-8", newline="\n")


def check(root: Path, documents: dict[Path, dict[str, Any]], markdown: str) -> None:
    for path, document in documents.items():
        if read_json(root / path) != document:
            raise ValueError(f"unit_o_diagnosis_regeneration_drift:{path.as_posix()}")
    if (root / REPORT_PATH).read_text(encoding="utf-8") != markdown:
        raise ValueError("unit_o_diagnosis_regeneration_drift:REPORT.md")
    manifest = documents[EVIDENCE_MANIFEST_PATH]
    for record in manifest["records"]:
        if sha256_file(root / record["path"]) != record["sha256"]:
            raise ValueError(f"unit_o_evidence_hash_mismatch:{record['path']}")


def _markdown_report(report: dict[str, Any], revisions: list[dict[str, Any]]) -> str:
    lines = [
        "# Unit O - final-topology transfer diagnosis",
        "",
        "This is candidate-independent development evidence. It does not qualify a physical",
        "garment, consume the final topology strategy, or consume the remaining candidate attempt.",
        "",
        f"- Literal outcome: `{report['outcome']}`",
        f"- Revisions executed: `{report['revisionsConsumed']}/2`",
        f"- Admitted strategy class: `{report['admittedStrategyClass']}`",
        f"- First unmet predicate: `{report['firstUnmetPredicate']}`",
        f"- Unit P eligible: `{str(report['unitPEligible']).lower()}`",
        "- Runtime remains: `runtime_v1`",
        "- Candidate created / attempt consumed / strategy consumed: `false / false / false`",
        "",
        "## Revision results",
        "",
    ]
    for revision in revisions:
        lines.append(
            f"- Revision {revision['revision']} `{revision['strategyClass']}`: "
            f"{revision['fixturePassCount']}/{revision['fixtureCount']} fixtures passed; "
            f"admitted=`{str(revision['admitted']).lower()}`; "
            f"first unmet=`{revision['firstUnmetPredicate']}`."
        )
    lines.extend(
        [
            "",
            "The fixtures use the production distance/support/body-collision kernels, preserve the",
            "frozen finite-compliance law, and are regenerated across the Forge Python 3.11/3.12",
            "matrix. They are discrimination fixtures only, not held-out qualification instances.",
            "The separately frozen Unit P confirmation generator has no realised seed or",
            "instances.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute or verify bounded Unit O diagnosis.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    documents, markdown = build(root)
    if args.check:
        check(root, documents, markdown)
    else:
        write(root, documents, markdown)
    outcome = documents[OUTCOME_PATH]
    print(
        f"unit_o_outcome={outcome['outcomeClass']} "
        f"revisions={outcome['revisionCount']} candidate_created=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
