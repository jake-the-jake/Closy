from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from closy_forge.capture_reconstruction_v2.common import read_json
from closy_forge.capture_reconstruction_v2.corpus import (
    build_development_seed_authority,
    create_locked_seed_authority,
    generate_corpus,
)
from closy_forge.capture_reconstruction_v2.evaluation import (
    run_contestant,
    run_locked_evaluation_once,
)
from closy_forge.capture_reconstruction_v2.independent_checker import check_publication_paths
from closy_forge.capture_reconstruction_v2.publication import (
    build_final_status_artifacts,
    build_source_freeze,
    prepare_source_artifacts,
    verify_source_freeze,
)
from closy_forge.capture_reconstruction_v2.reproducibility import run_development_canary_twice


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=(
            "prepare-source",
            "freeze",
            "canary",
            "development",
            "generate-locked",
            "evaluate",
            "check",
        ),
    )
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--custody-root", type=Path)
    args = parser.parse_args()
    repository = args.repository.resolve()
    forge = repository / "closy-forge"
    fixtures = forge / "fixtures" / "capture_reconstruction_v2"
    evidence = forge / "docs" / "evidence" / "capture_reconstruction_v2"
    protocol_path = fixtures / "protocol.json"
    if args.command == "prepare-source":
        print(json.dumps(prepare_source_artifacts(repository), sort_keys=True))
        return 0
    protocol = read_json(protocol_path)
    if args.command == "canary":
        report = run_development_canary_twice(
            protocol,
            evidence / "development_canary_reproducibility.json",
        )
        print(json.dumps(report, sort_keys=True))
        return 0 if report["terminalOutcome"] == "passed" else 1
    if args.command == "freeze":
        head = _git(repository, "rev-parse", "HEAD")
        tree = _git(repository, "rev-parse", "HEAD^{tree}")
        print(json.dumps(build_source_freeze(repository, head, tree), sort_keys=True))
        return 0
    freeze = read_json(fixtures / "source_freeze.json")
    freeze_failures = verify_source_freeze(repository, freeze)
    if freeze_failures:
        raise SystemExit(";".join(freeze_failures))
    if args.command == "development":
        root = forge / ".tmp" / "capture_v2_development"
        (root / "truth").mkdir(parents=True, exist_ok=True)
        result = generate_corpus(
            protocol,
            partition="development",
            public_root=root / "sources",
            evaluator_root=root / "truth",
            frozen_source_commit=freeze["sourceCommit"],
            frozen_source_tree=freeze["sourceTree"],
            seed_authority=build_development_seed_authority(protocol),
        )
        print(json.dumps({"manifestDigest": result["manifest"]["observableManifestDigest"]}))
        return 0
    custody = _required_custody(args.custody_root)
    public_root = fixtures / "locked_sources"
    truth_root = custody / "truth"
    if args.command == "generate-locked":
        truth_root.mkdir(parents=True, exist_ok=True)
        result = generate_corpus(
            protocol,
            partition="locked",
            public_root=public_root,
            evaluator_root=truth_root,
            frozen_source_commit=freeze["sourceCommit"],
            frozen_source_tree=freeze["sourceTree"],
            seed_authority=create_locked_seed_authority(protocol),
        )
        print(json.dumps({"manifestDigest": result["manifest"]["observableManifestDigest"]}))
        return 0
    manifest = read_json(fixtures / "locked_observable_manifest.json")
    commitments = read_json(fixtures / "locked_truth_commitments.json")
    output_path = evidence / "contestant_outputs.json"
    envelope_path = evidence / "canonical_result_envelope.json"
    disclosure_path = evidence / "synthetic_truth_disclosure.json"
    if args.command == "evaluate":
        output = run_contestant(
            manifest, public_root, fixtures / "locked_packages", output_path=output_path
        )
        publication = run_locked_evaluation_once(
            protocol,
            manifest,
            commitments,
            output,
            truth_root,
            frozen_source_commit=freeze["sourceCommit"],
            frozen_source_tree=freeze["sourceTree"],
            result_commit_intent="next_append_only_publication_commit",
            envelope_path=envelope_path,
            disclosure_path=disclosure_path,
        )
        payload = build_final_status_artifacts(
            repository,
            transition_commit="next_append_only_publication_commit",
            envelope=publication["envelope"],
            disclosure=publication["disclosure"],
            contestant_output=output,
            manifest=manifest,
            commitments=commitments,
        )
        print(json.dumps(payload, sort_keys=True))
        return 0
    checker = check_publication_paths(
        protocol_path,
        fixtures / "locked_observable_manifest.json",
        fixtures / "locked_truth_commitments.json",
        output_path,
        envelope_path,
        disclosure_path,
    )
    print(json.dumps(checker, sort_keys=True))
    return 0 if checker["terminalOutcome"] == "passed" else 1


def _required_custody(value: Path | None) -> Path:
    if value is None:
        raise SystemExit("--custody-root is required for locked operations")
    return value.resolve()


def _git(repository: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repository, text=True).strip()


if __name__ == "__main__":
    raise SystemExit(main())
