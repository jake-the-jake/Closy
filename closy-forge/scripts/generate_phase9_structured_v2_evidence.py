from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from closy_forge.bounded_models.integrated_evaluation_v2 import (
    build_integrated_phase14_evaluation,
)
from closy_forge.package_io.canonical_json import canonical_dumps, read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.package_io.managed_output import (
    cleanup_managed_staging,
    create_managed_staging,
    publish_managed_staging,
)
from closy_forge.pattern_inference.correction_surface_v1 import (
    apply_correction,
    export_correction_record,
    start_correction_surface,
)
from closy_forge.pattern_inference.raster_evaluation_v4 import evaluate_raster_model_v4
from closy_forge.pattern_inference.raster_execution_v4 import execute_raster_downstream_v4
from closy_forge.pattern_inference.raster_foundation_v3 import build_raster_foundation_v3
from closy_forge.pattern_inference.structured_decoder_v1 import (
    build_structured_dataset_v1,
    evaluate_structured_decoder_v1,
    train_structured_decoder_v1,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate Phase 9 v2 and integrated Phase 14 evidence."
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    forge_root = Path(__file__).resolve().parents[1]
    output = args.output.resolve(strict=False)
    if args.check:
        with tempfile.TemporaryDirectory(prefix="closy-phase9-v2-check-") as temporary:
            generated = Path(temporary) / "evidence"
            summary = _generate(generated, forge_root)
            differences = _compare(output, generated)
        if differences:
            raise RuntimeError("phase9_structured_evidence_mismatch:" + ";".join(differences))
        print(json.dumps({"status": "match", **summary}, sort_keys=True))
        return 0
    staging = create_managed_staging(
        output, allowed_root=output.parent, purpose="phase9-structured-v2"
    )
    try:
        summary = _generate(staging, forge_root)
        publish_managed_staging(
            staging,
            output,
            allowed_root=output.parent,
            purpose="phase9-structured-v2",
            force=args.force,
        )
    finally:
        cleanup_managed_staging(staging, allowed_root=output.parent, purpose="phase9-structured-v2")
    print(json.dumps(summary, sort_keys=True))
    return 0


def _generate(output: Path, forge_root: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    source_map = (
        forge_root / "docs" / "evidence" / "phase9_structured_v2" / "source_replay_map.json"
    )
    if source_map.is_file():
        write_canonical_json(output / "source_replay_map.json", read_json(source_map))
    thresholds = read_json(forge_root / "docs" / "phase9_structured_threshold_registry_v2.json")
    e1_foundation = build_raster_foundation_v3()
    e1_evaluation = evaluate_raster_model_v4(
        e1_foundation["model"], e1_foundation["dataset"], e1_foundation["split"], thresholds
    )
    e1_foundation["evaluationV4"] = e1_evaluation
    e1_execution = execute_raster_downstream_v4(e1_foundation, thresholds)
    e2_bundle = build_structured_dataset_v1()
    e2_model = train_structured_decoder_v1(e2_bundle)
    e2_evaluation = evaluate_structured_decoder_v1(e2_model, e2_bundle, thresholds)
    correction = _correction_evidence(e2_bundle)
    source_context = {
        "z1": {
            "status": "failed_all_family_breadth",
            "acceptedFamilies": 6,
            "rejectedFamilies": 3,
            "source": "frozen_Closy_A_evidence",
        },
        "c3": {"status": "scoped_pass_global_partial", "bindingStatesPassed": 11},
        "phy1": {"status": "failed", "physicalStatesPassed": 0, "physicalStateCount": 11},
        "phase11To13": "omitted_dependency_blocked_on_unaccepted_z2",
        "phase9": {
            "e1Status": e1_execution["E1"]["status"],
            "e2Status": e2_evaluation["acceptance"]["status"],
        },
    }
    phase14 = build_integrated_phase14_evaluation(
        e1=e1_execution, e2=e2_evaluation, source_context=source_context
    )
    source_tree = _source_tree_attestation(forge_root)
    dataset_manifest = {
        "datasetVersion": e2_bundle["dataset"]["datasetVersion"],
        "datasetHash": sha256_bytes(canonical_dumps(e2_bundle["dataset"]).encode("utf-8")),
        "splitHash": sha256_bytes(canonical_dumps(e2_bundle["split"]).encode("utf-8")),
        "counts": {
            name: len(e2_bundle["split"]["groups"][name])
            for name in ("train", "validation", "test")
        },
        "heldoutStructuralCompositionGroups": e2_bundle["split"][
            "heldoutStructuralCompositionGroups"
        ],
        "containsPrivateData": False,
        "externalDatasets": [],
    }
    attestation = {
        "schemaVersion": 1,
        "attestationVersion": "closy.phase9.exact_source_attestation.v2",
        "sourceTree": source_tree,
        "trainingConfigHash": sha256_bytes(
            canonical_dumps(e1_foundation["trainingConfig"]).encode("utf-8")
        ),
        "e1CorpusHash": e1_foundation["hashes"]["dataset"],
        "e1SplitHash": e1_foundation["hashes"]["split"],
        "e1ModelHash": e1_foundation["model"]["integrity"]["modelHash"],
        "e1WeightsHash": e1_foundation["model"]["integrity"]["weightsHash"],
        "e1EvaluationHash": sha256_bytes(canonical_dumps(e1_evaluation).encode("utf-8")),
        "e2DatasetHash": dataset_manifest["datasetHash"],
        "e2SplitHash": dataset_manifest["splitHash"],
        "e2ModelHash": e2_model["integrity"]["modelHash"],
        "e2EvaluationHash": sha256_bytes(
            canonical_dumps(_without_runtime(e2_evaluation)).encode("utf-8")
        ),
        "exactHeadWorkflow": {
            "workflow": "Closy Forge Phase 9 Raster Canonical",
            "trigger": "pull_request",
            "runIdAuthority": "draft_pr_body_and_final_handoff_after_exact_head_run",
        },
        "commitSelfReferenceUsed": False,
    }
    documents = {
        "e1_evaluation.json": e1_evaluation,
        "e1_execution.json": e1_execution,
        "e2_dataset_manifest.json": dataset_manifest,
        "e2_model.json": e2_model,
        "e2_evaluation.json": e2_evaluation,
        "correction_surface.json": correction,
        "phase14_integrated_evaluation.json": phase14,
        "attestation.json": attestation,
    }
    for name, document in documents.items():
        write_canonical_json(output / name, document)
    summary = {
        "schemaVersion": 1,
        "evidenceVersion": "closy.phase9_structured_and_phase14.synthetic_d0.v2",
        "sourceTreeHash": source_tree["hash"],
        "E1": e1_execution["E1"],
        "E2": e2_evaluation["acceptance"],
        "phase14": {
            "materialTopOne": phase14["evaluation"]["material"]["topOneAccuracy"],
            "failureMacroF1": phase14["evaluation"]["failureAndQuality"]["macroF1"],
            "brier": phase14["evaluation"]["calibration"]["brierScore"],
        },
        "humanReviewStatus": "not_run",
        "privateUserEvidence": False,
        "globalPhase9": "partial",
        "globalPhase14": "partial",
    }
    write_canonical_json(output / "execution_summary.json", summary)
    return summary


def _correction_evidence(bundle: dict[str, Any]) -> dict[str, Any]:
    program = bundle["dataset"]["records"][0]["program"]
    session = start_correction_surface(program, session_id="correction.structured.automated.001")
    session = apply_correction(
        session,
        expected_source_hash=session["sourceProgramHash"],
        field="decision",
        value="defer",
        reason="automated_serialization_fixture_not_human_review",
    )
    return export_correction_record(session)


def _source_tree_attestation(forge_root: Path) -> dict[str, Any]:
    repository = forge_root.parent
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=repository, check=True, capture_output=True
    ).stdout.split(b"\0")
    paths = sorted(
        item.decode("utf-8")
        for item in tracked
        if item
        and (
            item.startswith(b"closy-forge/src/closy_forge/pattern_inference/")
            or item.startswith(b"closy-forge/src/closy_forge/bounded_models/")
            or item == b"closy-forge/scripts/generate_phase9_structured_v2_evidence.py"
            or item == b"closy-forge/docs/phase9_structured_threshold_registry_v2.json"
            or item == b".github/workflows/closy-forge-phase9-raster.yml"
        )
    )
    blobs = []
    for path in paths:
        blob = subprocess.run(
            ["git", "rev-parse", f"HEAD:{path}"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        blobs.append({"path": path, "blob": blob})
    return {
        "algorithm": "sha256_of_canonical_git_path_blob_inventory",
        "fileCount": len(blobs),
        "hash": sha256_bytes(canonical_dumps(blobs).encode("utf-8")),
        "portableRawPathsIncluded": False,
    }


def _compare(expected: Path, actual: Path) -> list[str]:
    expected_names = sorted(
        path.name for path in expected.glob("*.json") if path.name != "source_replay_map.json"
    )
    actual_names = sorted(
        path.name for path in actual.glob("*.json") if path.name != "source_replay_map.json"
    )
    differences = []
    if expected_names != actual_names:
        differences.append("file_inventory")
    for name in sorted(set(expected_names) & set(actual_names)):
        left = _without_runtime(read_json(expected / name))
        right = _without_runtime(read_json(actual / name))
        if canonical_dumps(left) != canonical_dumps(right):
            differences.append(f"semantic:{name}")
    return differences


def _without_runtime(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _without_runtime(child) for key, child in value.items() if key != "runtime"}
    if isinstance(value, list):
        return [_without_runtime(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
