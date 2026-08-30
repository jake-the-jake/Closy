from __future__ import annotations

import argparse
import json
import platform
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from closy_forge.bounded_models.integrated_evaluation_v3 import (
    build_integrated_phase14_evaluation_v3,
)
from closy_forge.package_io.canonical_json import canonical_dumps, read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.package_io.managed_output import (
    cleanup_managed_staging,
    create_managed_staging,
    publish_managed_staging,
)
from closy_forge.pattern_inference.correction_surface_v2 import (
    apply_typed_correction_v2,
    export_typed_correction_v2,
    start_typed_correction_v2,
)
from closy_forge.pattern_inference.e1_evaluation_v5 import evaluate_e1_v5
from closy_forge.pattern_inference.e1_kernel_v3 import (
    reload_e1_model_v3,
    train_e1_kernel_v3,
    validate_e1_model_v3,
)
from closy_forge.pattern_inference.multiview_corpus_v5 import (
    build_multiview_corpus_v5,
    compact_corpus_manifest_v5,
    validate_multiview_corpus_v5,
)
from closy_forge.pattern_inference.structured_decoder_v2 import (
    evaluate_structured_decoder_v2,
    reload_structured_model_v2,
    train_structured_decoder_v2,
    validate_structured_model_v2,
)
from closy_forge.pattern_inference.typed_program_v2 import (
    build_typed_dataset_v2,
    compact_typed_dataset_manifest_v2,
    validate_typed_dataset_v2,
)

EVIDENCE_VERSION = "closy.phase9_structured_and_phase14.synthetic_d0.v3"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate or validate Phase 9 v3 evidence.")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--validate-committed", action="store_true")
    args = parser.parse_args()
    forge_root = Path(__file__).resolve().parents[1]
    if args.smoke:
        print(json.dumps(_smoke(forge_root), sort_keys=True))
        return 0
    if args.output is None:
        parser.error("--output is required except with --smoke")
    output = args.output.resolve(strict=False)
    if args.validate_committed:
        print(json.dumps(_validate_committed(output, forge_root), sort_keys=True))
        return 0
    if args.check:
        with tempfile.TemporaryDirectory(prefix="closy-phase9-v3-check-") as temporary:
            generated = Path(temporary) / "evidence"
            summary = _generate(generated, forge_root)
            differences = _compare(output, generated)
        if differences:
            raise RuntimeError("phase9_structured_v3_evidence_mismatch:" + ";".join(differences))
        print(json.dumps({"status": "match", **summary}, sort_keys=True))
        return 0
    staging = create_managed_staging(
        output, allowed_root=output.parent, purpose="phase9-structured-v3"
    )
    try:
        summary = _generate(staging, forge_root)
        publish_managed_staging(
            staging,
            output,
            allowed_root=output.parent,
            purpose="phase9-structured-v3",
            force=args.force,
        )
    finally:
        cleanup_managed_staging(staging, allowed_root=output.parent, purpose="phase9-structured-v3")
    print(json.dumps(summary, sort_keys=True))
    return 0


def _generate(output: Path, forge_root: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    thresholds = read_json(forge_root / "docs" / "phase9_structured_threshold_registry_v3.json")
    corpus, split = build_multiview_corpus_v5()
    e1_model = reload_e1_model_v3(train_e1_kernel_v3(corpus, split))
    e1_evaluation = evaluate_e1_v5(e1_model, corpus, split, thresholds)
    typed_dataset = build_typed_dataset_v2()
    e2_model = reload_structured_model_v2(train_structured_decoder_v2(typed_dataset))
    e2_evaluation = evaluate_structured_decoder_v2(
        e2_model, typed_dataset, thresholds, e1_model=e1_model
    )
    correction = _correction_evidence(typed_dataset)
    source_context = {
        "z1": {
            "status": "scoped_default_family_pass_global_partial",
            "defaultFamilies": {"passed": 9, "total": 9},
            "parameterBreadth": {"passed": 6, "total": 25},
            "humanReview": "not_run",
        },
        "c3": {"status": "scoped_pass_global_partial", "bindingStatesPassed": 11},
        "phy1": {"status": "failed", "physicalStatesPassed": 0, "physicalStateCount": 11},
        "phase11": "partial_mechanical_reference_is_not_solver_driven_cloth",
        "phase9": {
            "e1Status": e1_evaluation["acceptance"]["status"],
            "e2Status": e2_evaluation["acceptance"]["status"],
        },
    }
    phase14 = build_integrated_phase14_evaluation_v3(
        e1=e1_evaluation,
        e2=e2_evaluation,
        source_context=source_context,
        thresholds=thresholds,
    )
    source_tree = _source_tree_attestation(forge_root)
    corpus_manifest = compact_corpus_manifest_v5(corpus, split)
    typed_manifest = compact_typed_dataset_manifest_v2(typed_dataset)
    summary = {
        "schemaVersion": 1,
        "evidenceVersion": EVIDENCE_VERSION,
        "sourceTreeHash": source_tree["hash"],
        "E1": e1_evaluation["acceptance"],
        "E2": e2_evaluation["acceptance"],
        "phase14": phase14["acceptance"],
        "humanReviewStatus": "not_run",
        "privateUserEvidence": False,
        "realPhotoEvidence": False,
        "physicalDrapeEvidence": False,
        "globalPhase9": "partial",
        "globalPhase14": "partial",
    }
    documents: dict[str, Any] = {
        "corpus_manifest.json": corpus_manifest,
        "e1_model.json": e1_model,
        "e1_evaluation.json": e1_evaluation,
        "e2_dataset_manifest.json": typed_manifest,
        "e2_model.json": e2_model,
        "e2_evaluation.json": e2_evaluation,
        "correction_surface.json": correction,
        "phase14_integrated_evaluation.json": phase14,
        "model_card.json": _model_card(e1_evaluation, e2_evaluation, phase14),
        "licence_provenance.json": _licence_provenance(),
        "execution_summary.json": summary,
    }
    replay_map = (
        forge_root / "docs" / "evidence" / "phase9_structured_v2" / "source_replay_map.json"
    )
    if replay_map.is_file():
        documents["source_replay_map.json"] = read_json(replay_map)
    document_hashes = {
        name: sha256_bytes(canonical_dumps(_without_runtime(value)).encode("utf-8"))
        for name, value in documents.items()
    }
    attestation = {
        "schemaVersion": 1,
        "attestationVersion": "closy.phase9.exact_source_attestation.v3",
        "sourceTree": source_tree,
        "generatorExecutableBlob": _git_blob(
            forge_root.parent, "closy-forge/scripts/generate_phase9_structured_v3_evidence.py"
        ),
        "thresholdRegistryHash": sha256_bytes(canonical_dumps(thresholds).encode("utf-8")),
        "e1CorpusManifestHash": corpus_manifest["manifestHash"],
        "e1ModelHash": e1_model["integrity"]["modelHash"],
        "e1WeightsHash": e1_model["integrity"]["weightsHash"],
        "e2DatasetManifestHash": typed_manifest["manifestHash"],
        "e2ModelHash": e2_model["integrity"]["modelHash"],
        "e2WeightsHash": e2_model["integrity"]["weightsHash"],
        "documentHashesWithoutRuntime": document_hashes,
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "cpuOnly": True,
            "threadCount": 1,
            "seeded": True,
        },
        "exactHeadWorkflow": {
            "workflow": "Closy Forge Phase 9 Structured v3",
            "runIdAuthority": "draft_pr_body_and_final_handoff_after_exact_head_run",
        },
        "commitSelfReferenceUsed": False,
        "rawRasterOrFeatureCacheCommitted": False,
    }
    documents["attestation.json"] = attestation
    for name, document in documents.items():
        write_canonical_json(output / name, document)
    return summary


def _smoke(forge_root: Path) -> dict[str, Any]:
    thresholds = read_json(forge_root / "docs" / "phase9_structured_threshold_registry_v3.json")
    corpus, split = build_multiview_corpus_v5(programs_per_family=4, captures_per_program=1)
    e1_model = reload_e1_model_v3(train_e1_kernel_v3(corpus, split, seed=91_338))
    typed = build_typed_dataset_v2(seed=72_120)
    e2_model = reload_structured_model_v2(train_structured_decoder_v2(typed, seed=63_018))
    e2_evaluation = evaluate_structured_decoder_v2(e2_model, typed, thresholds, e1_model=e1_model)
    if validate_multiview_corpus_v5(corpus, split):
        raise RuntimeError("phase9_v3_smoke_multiview_invalid")
    if validate_e1_model_v3(e1_model):
        raise RuntimeError("phase9_v3_smoke_e1_invalid")
    if validate_typed_dataset_v2(typed):
        raise RuntimeError("phase9_v3_smoke_typed_invalid")
    if validate_structured_model_v2(e2_model):
        raise RuntimeError("phase9_v3_smoke_e2_invalid")
    return {
        "status": "pass",
        "profile": "deterministic_ci_smoke_not_full_evidence",
        "e1Programmes": len(corpus["programs"]),
        "e1DecodedImages": corpus["renderer"]["decodedImageCount"],
        "e2TestProgrammes": e2_evaluation["execution"]["testProgramCount"],
        "e2Reference3dAttempts": e2_evaluation["execution"]["actualReference3dAttempts"],
        "capabilityOutcomePromoted": False,
    }


def _validate_committed(output: Path, forge_root: Path) -> dict[str, Any]:
    required = {
        "attestation.json",
        "corpus_manifest.json",
        "e1_model.json",
        "e1_evaluation.json",
        "e2_dataset_manifest.json",
        "e2_model.json",
        "e2_evaluation.json",
        "correction_surface.json",
        "phase14_integrated_evaluation.json",
        "model_card.json",
        "licence_provenance.json",
        "execution_summary.json",
    }
    names = {path.name for path in output.glob("*.json")}
    missing = sorted(required - names)
    if missing:
        raise RuntimeError("phase9_v3_committed_evidence_missing:" + ";".join(missing))
    attestation = read_json(output / "attestation.json")
    current_tree = _source_tree_attestation(forge_root)
    if attestation["sourceTree"]["hash"] != current_tree["hash"]:
        raise RuntimeError("phase9_v3_source_tree_attestation_stale")
    for name, expected in attestation["documentHashesWithoutRuntime"].items():
        actual = sha256_bytes(
            canonical_dumps(_without_runtime(read_json(output / name))).encode("utf-8")
        )
        if actual != expected:
            raise RuntimeError(f"phase9_v3_document_hash_mismatch:{name}")
    if validate_e1_model_v3(read_json(output / "e1_model.json")):
        raise RuntimeError("phase9_v3_committed_e1_model_invalid")
    if validate_structured_model_v2(read_json(output / "e2_model.json")):
        raise RuntimeError("phase9_v3_committed_e2_model_invalid")
    return {
        "status": "pass",
        "profile": "committed_full_evidence_integrity_and_exact_source_validation",
        "fileCount": len(names),
        "sourceTreeHash": current_tree["hash"],
    }


def _correction_evidence(dataset: dict[str, Any]) -> dict[str, Any]:
    proposal = dataset["records"][0]["target"]["program"]
    session: dict[str, Any] = start_typed_correction_v2(
        proposal, session_id="correction.typed.synthetic.001"
    )
    session = apply_typed_correction_v2(
        session,
        expected_proposal_hash=session["currentProposalHash"],
        section="parameters",
        field="length",
        value=0.61,
        reason="scripted_synthetic_compile_fixture_not_human_review",
    )
    return export_typed_correction_v2(session)


def _model_card(e1: dict[str, Any], e2: dict[str, Any], phase14: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "modelCardVersion": "closy.phase9_phase14.synthetic_d0.model_card.v3",
        "intendedUse": "bounded_garment_specific_research_proposals_and_advisory_ranking",
        "prohibitedUse": [
            "canonical_geometry_without_validation",
            "real_photo_generalisation_claim",
            "physical_cloth_certification",
            "private_user_or_production_decisions",
        ],
        "E1": e1["acceptance"],
        "E2": e2["acceptance"],
        "phase14": phase14["acceptance"],
        "limitations": [
            "project_authored_synthetic_reference_assembly_only",
            "no_human_review",
            "no_real_photos_or_fabrics",
            "no_solver_backed_phase14_replacement_corpus",
            "losing_models_not_default",
        ],
    }


def _licence_provenance() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "provenanceVersion": "closy.phase9.synthetic_provenance.v3",
        "source": "project_authored_deterministic_programmes_and_cpu_renders",
        "privateData": False,
        "externalDataset": None,
        "externalCheckpoint": None,
        "networkDownload": False,
        "licence": "internal Closy project test and development use",
        "rawRastersPersisted": False,
    }


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
            or item == b"closy-forge/scripts/generate_phase9_structured_v3_evidence.py"
            or item == b"closy-forge/docs/phase9_structured_threshold_registry_v3.json"
            or item == b".github/workflows/closy-forge-phase9-raster.yml"
        )
    )
    blobs = [{"path": path, "blob": _git_blob(repository, path)} for path in paths]
    return {
        "algorithm": "sha256_of_canonical_git_path_blob_inventory",
        "fileCount": len(blobs),
        "hash": sha256_bytes(canonical_dumps(blobs).encode("utf-8")),
        "portableRawPathsIncluded": False,
    }


def _git_blob(repository: Path, path: str) -> str:
    return subprocess.run(
        ["git", "rev-parse", f"HEAD:{path}"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _compare(expected: Path, actual: Path) -> list[str]:
    ignored = {".closy-forge-owned.json"}
    expected_names = sorted(
        path.name for path in expected.glob("*.json") if path.name not in ignored
    )
    actual_names = sorted(path.name for path in actual.glob("*.json") if path.name not in ignored)
    differences = []
    if expected_names != actual_names:
        differences.append("file_inventory")
    for name in sorted(set(expected_names) & set(actual_names)):
        if canonical_dumps(_without_runtime(read_json(expected / name))) != canonical_dumps(
            _without_runtime(read_json(actual / name))
        ):
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
