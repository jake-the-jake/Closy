from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from closy_forge.solver_material_v2.common import read_json, write_json
from closy_forge.solver_material_v2.contestant import run_contestant
from closy_forge.solver_material_v2.corpus import generate_partition
from closy_forge.solver_material_v2.development_studies import prepare_source_artifacts
from closy_forge.solver_material_v2.evaluation import run_locked_evaluation_once
from closy_forge.solver_material_v2.independent_checker import check_publication_paths
from closy_forge.solver_material_v2.publication import (
    build_seed_authority,
    build_source_freeze,
    derive_private_seed,
    verify_source_freeze,
)
from closy_forge.solver_material_v2.real_coupon import empty_real_coupon_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Solver/material V2 source-guarded evidence tool")
    parser.add_argument(
        "command",
        choices=(
            "prepare-source",
            "development",
            "freeze",
            "generate-locked",
            "evaluate",
            "check",
            "real-coupon-empty",
        ),
    )
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--custody-root", type=Path)
    parser.add_argument("--exact-head-run-id")
    args = parser.parse_args()
    repository = args.repository.resolve()
    forge = repository / "closy-forge"
    fixture = forge / "fixtures" / "solver_material_v2"
    evidence = forge / "docs" / "evidence" / "solver_material_v2"
    protocol_path = fixture / "protocol.json"
    if args.command == "prepare-source":
        print(json.dumps(prepare_source_artifacts(repository), sort_keys=True))
        return 0
    protocol = read_json(protocol_path)
    if args.command == "development":
        root = forge / ".tmp" / "solver_material_v2_development"
        result = generate_partition(
            protocol,
            partition="development",
            secret="development-identities-exposed-not-evaluation-eligible",
            public_root=root / "public",
            private_root=root / "private",
            source_commit=_git(repository, "rev-parse", "HEAD"),
            source_tree=_git(repository, "rev-parse", "HEAD^{tree}"),
        )
        summary = {
            "schemaVersion": 2,
            "evidenceClass": "project_authored_synthetic_development",
            "tupleCount": result["manifest"]["tupleCount"],
            "manifestDigest": result["manifest"]["manifestDigest"],
            "eligibleForLockedEvaluation": False,
        }
        write_json(evidence / "development_corpus_summary.json", summary)
        print(json.dumps(summary, sort_keys=True))
        return 0
    if args.command == "freeze":
        head = _git(repository, "rev-parse", "HEAD")
        tree = _git(repository, "rev-parse", "HEAD^{tree}")
        print(json.dumps(build_source_freeze(repository, head, tree), sort_keys=True))
        return 0
    freeze = read_json(fixture / "source_freeze.json")
    failures = verify_source_freeze(repository, freeze)
    if failures:
        raise SystemExit(";".join(failures))
    if args.command == "real-coupon-empty":
        report = empty_real_coupon_report()
        write_json(evidence / "real_coupon_report.json", report)
        print(json.dumps(report, sort_keys=True))
        return 0
    run_id = _required(args.exact_head_run_id, "--exact-head-run-id")
    authority = build_seed_authority(freeze, run_id)
    if args.command == "generate-locked":
        custody = _required_path(args.custody_root)
        write_json(fixture / "seed_authority.json", authority)
        result = generate_partition(
            protocol,
            partition="locked",
            secret=derive_private_seed(freeze, run_id),
            public_root=fixture / "locked_public",
            private_root=custody,
            source_commit=str(freeze["sourceCommit"]),
            source_tree=str(freeze["sourceTree"]),
        )
        print(json.dumps({"manifestDigest": result["manifest"]["manifestDigest"]}))
        return 0
    custody = _required_path(args.custody_root)
    public_root = fixture / "locked_public"
    contestant_path = evidence / "contestant_output.json"
    envelope_path = evidence / "canonical_result_envelope.json"
    disclosure_path = evidence / "synthetic_truth_disclosure.json"
    if args.command == "evaluate":
        if authority != read_json(fixture / "seed_authority.json"):
            raise SystemExit("seed_authority_substitution")
        contestant = run_contestant(public_root, contestant_path)
        publication = run_locked_evaluation_once(
            protocol,
            public_root,
            custody,
            contestant,
            envelope_path=envelope_path,
            disclosure_path=disclosure_path,
            source_freeze=freeze,
            development_studies=read_json(evidence / "development_studies.json"),
        )
        print(json.dumps({"resultDigest": publication["envelope"]["resultDigest"]}))
        return 0
    checker = check_publication_paths(
        protocol_path,
        public_root,
        contestant_path,
        envelope_path,
        disclosure_path,
        evidence / "development_studies.json",
    )
    write_json(evidence / "independent_checker.json", checker)
    print(json.dumps(checker, sort_keys=True))
    return 0 if checker["terminalOutcome"] == "passed" else 1


def _required(value: str | None, name: str) -> str:
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def _required_path(value: Path | None) -> Path:
    if value is None:
        raise SystemExit("--custody-root is required")
    value = value.resolve()
    value.mkdir(parents=True, exist_ok=True)
    return value


def _git(repository: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repository, text=True).strip()


if __name__ == "__main__":
    raise SystemExit(main())
