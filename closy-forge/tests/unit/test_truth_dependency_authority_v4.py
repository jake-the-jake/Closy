from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path

import pytest
from PIL import Image

from closy_forge.package_io.hashing import sha256_file
from closy_forge.truth_dependency_authority_v4.artifact_evaluator import (
    evaluate_artifact_attempts,
)
from closy_forge.truth_dependency_authority_v4.identity_inventory import audit_identity_splits
from closy_forge.truth_dependency_authority_v4.isolation import (
    PINNED_BASE_IMAGE,
    contestant_container_command,
    scrub_authority_environment,
)
from closy_forge.truth_dependency_authority_v4.pixel_causality import evaluate_pixel_causality
from closy_forge.truth_dependency_authority_v4.scheduler import (
    build_coverage_scheduler,
    validate_coverage_inventory,
    validate_scheduler,
)
from closy_forge.truth_dependency_authority_v4.secure_collector import (
    AuthorityOwnedOutput,
    SecureCollectionError,
    collect_owned_outputs,
    validate_file_metadata,
)
from closy_forge.truth_dependency_authority_v4.start_attestation import (
    validate_start_attestation,
)
from closy_forge.truth_dependency_authority_v4.unit_t_semantics import (
    derive_attempt_semantics,
)
from closy_forge.truth_dependency_authority_v4.y2_protocol_audit import (
    AUTHORIZATION_ID,
    TERMINAL_OUTCOME,
    audit_frozen_y2_protocol,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
FORGE_ROOT = REPO_ROOT / "closy-forge"


def test_unit_t_literal_failures_are_not_reclassified_as_abstentions() -> None:
    predictions = json.loads(
        (
            FORGE_ROOT
            / "fixtures/d0_disjoint_tshirt_confirmation_v3/official_attempt/predictions.json"
        ).read_text(encoding="utf-8")
    )
    result = derive_attempt_semantics(predictions["attemptRows"])

    assert result["predictionFailureCount"] == 4
    assert result["explicitAbstentionCount"] == 0
    assert result["statusCounts"]["failed"] == 4
    assert result["predictionArtifactProducedCount"] == 60


@pytest.mark.parametrize("state", ["failed", "abstained", "missing", "corrupt", "not_run"])
def test_unit_t_status_vocabulary_remains_distinct(state: str) -> None:
    result = derive_attempt_semantics([{"status": state, "predictionArtifact": None}])
    expected_key = {
        "failed": "predictionFailureCount",
        "abstained": "explicitAbstentionCount",
        "missing": "missingCount",
        "corrupt": "corruptCount",
        "not_run": "notRunCount",
    }[state]
    assert result[expected_key] == 1


def test_artifact_evaluator_reopens_bytes_and_derives_every_predicate(tmp_path: Path) -> None:
    attempt = _artifact_attempt(tmp_path)
    protocol = {
        "attemptDenominator": 1,
        "requiredObservables": ["seam", "mass"],
        "maximumAbsoluteErrorByObservable": {"seam": 0.01, "mass": 0.02},
    }

    result = evaluate_artifact_attempts(
        tmp_path,
        protocol,
        [attempt],
        compiler_validator=lambda path, value: (
            [] if path.is_file() and value else ["compile_failed"]
        ),
    )

    assert result["mandatoryIntegrityPass"] is True
    assert result["scientificCapabilityClaim"] is False
    assert all(result["predicateResults"].values())

    compiler_path = tmp_path / "compiler.json"
    compiler = json.loads(compiler_path.read_text(encoding="utf-8"))
    del compiler["observables"]["mass"]
    compiler["pass"] = True
    compiler_path.write_text(json.dumps(compiler), encoding="utf-8")
    attempt["compiler"]["sha256"] = sha256_file(compiler_path)
    mutated = evaluate_artifact_attempts(
        tmp_path,
        protocol,
        [attempt],
        compiler_validator=lambda _path, _value: [],
    )
    assert mutated["mandatoryIntegrityPass"] is False
    assert mutated["predicateResults"]["allRequiredObservablesPresent"] is False
    assert mutated["predicateResults"]["allFrozenThresholdsSatisfied"] is False


def test_pixel_causality_requires_task_relevant_interventions() -> None:
    base = {
        "sourceSha256": "1" * 64,
        "decoder": "Pillow",
        "decoderVersion": "11.1.0",
        "pixelReadTraceSha256": "2" * 64,
        "normalizedTensorSha256": "3" * 64,
        "contestantInputManifestSha256": "4" * 64,
        "baselineOutputSha256": "5" * 64,
        "interventions": [
            {
                "kind": kind,
                "intervenedTensorSha256": f"{index + 6:x}" * 64,
                "outputSha256": f"{index + 11:x}" * 64,
                "outputChanged": True,
                "groundTruthPerformanceDegraded": True,
            }
            for index, kind in enumerate(
                ["zeroed", "shuffled", "localized_occlusion", "role_swapped", "label_preserving"]
            )
        ],
    }
    assert evaluate_pixel_causality(base)["causalityPass"] is True
    unverified = deepcopy(base)
    unverified["interventions"][2]["groundTruthPerformanceDegraded"] = False
    assert evaluate_pixel_causality(unverified)["trustedEvidenceClass"] == "unverified"


def test_identity_inventory_normalizes_aliases_units_and_derivative_groups(tmp_path: Path) -> None:
    left_image = tmp_path / "left.png"
    right_image = tmp_path / "right.png"
    Image.new("RGB", (12, 12), (50, 80, 110)).save(left_image)
    Image.new("RGB", (12, 12), (50, 80, 110)).save(right_image)
    common = {
        "avatarIdentity": "Avatar 1",
        "garmentIdentity": "Garment 1",
        "garmentFamily": "T-Shirt",
        "appearanceIdentity": "Blue",
        "captureSession": "Session A",
        "rendererCameraFamily": "Renderer 1",
        "physicalMaterialPreset": "Cotton",
        "meshSignature": [1.0, 2.0, 3.0],
    }
    rows = [
        {
            **common,
            "split": "train",
            "rasterPath": str(left_image),
            "parameters": {"height": {"value": 175, "unit": "cm"}},
        },
        {
            **common,
            "garmentFamily": "tee",
            "split": "test",
            "rasterPath": str(right_image),
            "parameters": {"height": {"value": 1.75, "unit": "m"}},
        },
    ]
    audit = audit_identity_splits(
        rows,
        numeric_fields=["height"],
        normalized_distance_threshold=1e-8,
        raster_hamming_threshold=0,
    )
    assert audit["disjoint"] is False
    assert audit["exactCrossSplitCollisions"]
    assert audit["normalizedNearestCollisions"]
    assert audit["perceptualCrossSplitCollisions"]
    assert audit["meshTopologyCrossSplitCollisions"]


def test_secure_collector_emits_portable_records_and_quarantines_races() -> None:
    with AuthorityOwnedOutput() as owned:
        (owned.path / "report.json").write_text("{}", encoding="utf-8")
        records = collect_owned_outputs(owned, allowed_names=frozenset({"report.json"}))
        assert list(records[0]) == ["path", "byteLength", "sha256"]
        assert "inode" not in records[0] and "device" not in records[0]

        (owned.path / "report.json").write_text("before", encoding="utf-8")

        def replace(path: Path) -> None:
            replacement = path.with_suffix(".replacement")
            replacement.write_text("after", encoding="utf-8")
            os.replace(replacement, path)

        with pytest.raises(SecureCollectionError, match="collector_replacement_race"):
            collect_owned_outputs(
                owned,
                allowed_names=frozenset({"report.json"}),
                after_lstat=replace,
            )
        assert not list(owned.path.iterdir())


def test_secure_collector_rejects_symlink_or_hardlink_when_supported() -> None:
    with AuthorityOwnedOutput() as owned:
        source = owned.owner / "source"
        source.write_text("secret", encoding="utf-8")
        link = owned.path / "report.json"
        try:
            link.symlink_to(source)
        except OSError:
            pytest.skip("symlink creation unavailable")
        with pytest.raises(SecureCollectionError, match="collector_symlink_or_reparse_forbidden"):
            collect_owned_outputs(owned, allowed_names=frozenset({"report.json"}))


@pytest.mark.parametrize(
    ("mode", "links", "attributes", "expected"),
    [
        (0o120777, 1, 0, "collector_symlink_or_reparse_forbidden"),
        (0o100600, 1, 0x400, "collector_symlink_or_reparse_forbidden"),
        (0o010600, 1, 0, "collector_nonregular_forbidden"),
        (0o140600, 1, 0, "collector_nonregular_forbidden"),
        (0o020600, 1, 0, "collector_nonregular_forbidden"),
        (0o100600, 2, 0, "collector_hardlink_forbidden"),
    ],
)
def test_secure_collector_rejects_portable_adversarial_metadata(
    mode: int, links: int, attributes: int, expected: str
) -> None:
    assert validate_file_metadata(mode, links, 10, 100, file_attributes=attributes) == expected


def test_scheduler_covers_dynamic_inventory_and_exposes_real_ready_work() -> None:
    coverage = json.loads((FORGE_ROOT / "docs/blueprint_coverage.json").read_text(encoding="utf-8"))
    scheduler = build_coverage_scheduler(
        coverage,
        blueprint_path=FORGE_ROOT
        / "docs/Closy_AI_3D_Garment_and_ZeroOne_Integration_Master_Blueprint.md",
    )
    assert scheduler["dynamicRequirementCount"] == len(coverage["rows"])
    assert scheduler["unmappedRequirementCount"] == 0
    assert not validate_scheduler(scheduler)
    for row_id in ["BP-07-MODE-A", "BP-07-MODE-B", "BP-07-MODE-D", "BP-07-MODE-E"]:
        assert row_id in scheduler["readyRows"]
    assert "BP-09-Z3" in scheduler["readyRows"]
    assert "BP-17-PHASE-12" in scheduler["readyRows"]


def test_start_attestation_reopens_git_history_and_exact_counts() -> None:
    start = json.loads(
        (FORGE_ROOT / "fixtures/truth_dependency_authority_v4/start_state.json").read_text(
            encoding="utf-8"
        )
    )
    assert not validate_start_attestation(REPO_ROOT, start)


def test_scheduler_rejects_unknown_dependency_duplicate_and_cycle() -> None:
    rows = [
        {"id": "BP-A", "status": "partial", "dependencies": ["BP-B"], "sourceSection": "x"},
        {"id": "BP-B", "status": "partial", "dependencies": ["BP-A"], "sourceSection": "x"},
    ]
    assert "scheduler_dependency_cycle" in validate_coverage_inventory(rows)
    rows[1]["id"] = "BP-A"
    assert "scheduler_duplicate_row_id" in validate_coverage_inventory(rows)
    rows[1]["id"] = "BP-B"
    rows[1]["dependencies"] = ["UNKNOWN"]
    assert "scheduler_dependency_reference_missing" in validate_coverage_inventory(rows)


def test_frozen_y2_protocol_fails_closed_before_seed_or_tag() -> None:
    audit = audit_frozen_y2_protocol(FORGE_ROOT)
    assert audit["authorizationId"] == AUTHORIZATION_ID
    assert audit["scientificProtocolValidForY2"] is False
    assert audit["terminalOutcome"] == TERMINAL_OUTCOME
    assert audit["authorityTagCreated"] is False
    assert audit["seedCreated"] is False
    assert audit["scientificAttemptConsumed"] is False
    assert audit["candidateBudgetConsumed"] is False
    assert len(audit["findings"]) >= 4


def test_authority_environment_scrubs_tokens_and_git_indirection(tmp_path: Path) -> None:
    clean = scrub_authority_environment(
        {
            "PATH": "safe",
            "GH_TOKEN": "secret",
            "GITHUB_TOKEN": "secret",
            "GIT_DIR": "elsewhere",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "include.path",
            "GIT_CONFIG_VALUE_0": "secret",
        }
    )
    assert clean == {"PATH": "safe"}
    inputs = tmp_path / "inputs"
    outputs = tmp_path / "outputs"
    inputs.mkdir()
    outputs.mkdir()
    command = contestant_container_command(
        PINNED_BASE_IMAGE, input_path=inputs, output_path=outputs
    )
    command_text = " ".join(command)
    for required in (
        "--network none",
        "--read-only",
        "--cap-drop ALL",
        "no-new-privileges",
        "--memory 768m",
        "--cpus 2",
        "--pids-limit 128",
    ):
        assert required in command_text


def _artifact_attempt(root: Path) -> dict[str, object]:
    attempt_id = "attempt-01"
    candidate_path = root / "candidate.json"
    candidate_path.write_text(json.dumps({"attemptId": attempt_id, "mesh": [0, 1, 2]}))
    candidate_digest = sha256_file(candidate_path)
    values = {
        "prediction": {"attemptId": attempt_id, "prediction": "ok", "pass": True},
        "compiler": {
            "attemptId": attempt_id,
            "candidateSha256": candidate_digest,
            "observables": {"seam": 0.005, "mass": 0.01},
            "pass": True,
        },
        "appearance": {"attemptId": attempt_id, "candidateSha256": candidate_digest},
        "package": {"attemptId": attempt_id, "candidateSha256": candidate_digest},
        "lineage": {"attemptId": attempt_id, "candidateSha256": candidate_digest},
    }
    references: dict[str, object] = {
        "candidate": {"path": candidate_path.name, "sha256": candidate_digest}
    }
    for role, value in values.items():
        path = root / f"{role}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        references[role] = {"path": path.name, "sha256": sha256_file(path)}
    return {"attemptId": attempt_id, "fixtureKind": "real_output", **references}
