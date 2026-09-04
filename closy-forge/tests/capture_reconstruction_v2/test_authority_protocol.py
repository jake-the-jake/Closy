from __future__ import annotations

import json
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from closy_forge.capture_reconstruction_v2.blueprint_authority import (
    APPROVED_COMMIT,
    APPROVED_TREE,
    build_blueprint_authority,
    read_git_blob,
    verify_blueprint_authority,
)
from closy_forge.capture_reconstruction_v2.blueprint_parser import (
    build_requirement_inventory,
    parse_source_blocks,
    validate_inventory,
)
from closy_forge.capture_reconstruction_v2.common import canonical_digest, sha256_bytes
from closy_forge.capture_reconstruction_v2.evaluation import _evaluate_threshold_registry
from closy_forge.capture_reconstruction_v2.evidence_authority import (
    REQUIRED_BINDINGS,
    verify_evidence_eligibility,
)
from closy_forge.capture_reconstruction_v2.protocol import (
    CONTROL_NAMES,
    FAMILIES,
    MODES,
    STRATA,
    build_protocol,
    validate_protocol,
)
from closy_forge.capture_reconstruction_v2.publication import verify_source_freeze
from closy_forge.capture_reconstruction_v2.status_inventory import (
    build_pr63_inventory,
    validate_decorated_inventory,
)
from closy_forge.capture_reconstruction_v2.y2_forensic import derive_y2_terminal_state

REPOSITORY = Path(__file__).resolve().parents[3]


def test_protocol_freezes_exact_denominators_strata_controls_and_execution_registry() -> None:
    protocol = build_protocol()
    assert validate_protocol(protocol) == []
    assert len(protocol["sessionPlan"]) == 90
    locked = [row for row in protocol["sessionPlan"] if row["partition"] == "locked"]
    assert len(locked) == 30
    assert len(CONTROL_NAMES) == 5
    for mode in MODES:
        for family in FAMILIES:
            cell = [row for row in locked if row["mode"] == mode and row["family"] == family]
            assert len(cell) == 2
            assert {row["stratum"] for row in cell} == set(STRATA)
    registry = protocol["executionRegistry"]
    assert len(registry["thresholds"]) == len(protocol["thresholdRegistry"]) == 26
    assert {row["id"] for row in registry["denominators"]} == set(protocol["denominators"])
    assert {row["id"] for row in registry["stoppingRules"]} == set(protocol["candidateBudget"])


def test_v2_protocol_manifest_result_and_disclosure_schemas_are_versioned() -> None:
    root = REPOSITORY / "closy-forge" / "schemas" / "v2"
    names = (
        "capture-reconstruction-protocol.schema.json",
        "capture-reconstruction-observable-manifest.schema.json",
        "capture-reconstruction-result.schema.json",
        "capture-reconstruction-synthetic-disclosure.schema.json",
    )
    for name in names:
        schema = json.loads((root / name).read_text(encoding="utf-8"))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["$id"].startswith("https://closy.local/schemas/v2/")
        assert "schemaVersion" in schema["required"]


def test_checked_in_source_freeze_rejects_post_freeze_drift_when_present() -> None:
    path = (
        REPOSITORY / "closy-forge" / "fixtures" / "capture_reconstruction_v2" / "source_freeze.json"
    )
    if not path.exists():
        return
    freeze = json.loads(path.read_text(encoding="utf-8"))
    assert verify_source_freeze(REPOSITORY, freeze) == []
    changed = deepcopy(freeze)
    changed["implementationInventory"][0]["sha256"] = "0" * 64
    changed["implementationInventoryDigest"] = canonical_digest(changed["implementationInventory"])
    changed["freezeDigest"] = canonical_digest(changed, "freezeDigest")
    assert "capture_v2_frozen_implementation_digest_changed" in verify_source_freeze(
        REPOSITORY, changed
    )


@pytest.mark.parametrize("registry_name", ["thresholds", "denominators", "stoppingRules"])
def test_protocol_rejects_declared_execution_registry_drift(registry_name: str) -> None:
    protocol = build_protocol()
    protocol["executionRegistry"][registry_name].pop()
    protocol["protocolDigest"] = canonical_digest(protocol, "protocolDigest")
    assert any("execution_registry_mismatch" in row for row in validate_protocol(protocol))


def test_evaluator_rejects_declared_but_unused_and_evaluated_but_undeclared_metrics() -> None:
    protocol = build_protocol()
    metrics = {str(row["metric"]): 0.0 for row in protocol["thresholdRegistry"]}
    assert len(_evaluate_threshold_registry(protocol, metrics)) == 26
    with pytest.raises(ValueError, match="evaluated_or_declared_metric_mismatch"):
        _evaluate_threshold_registry(protocol, {**metrics, "undeclared.metric": 1.0})
    metrics.pop(next(iter(metrics)))
    with pytest.raises(ValueError, match="evaluated_or_declared_metric_mismatch"):
        _evaluate_threshold_registry(protocol, metrics)


def test_blueprint_authority_is_the_exact_git_blob_not_checkout_bytes() -> None:
    oid, payload = read_git_blob(REPOSITORY)
    authority = build_blueprint_authority(REPOSITORY)
    assert authority["commit"] == APPROVED_COMMIT
    assert authority["tree"] == APPROVED_TREE
    assert authority["gitBlobOid"] == oid
    assert authority["gitBlobSha256"] == sha256_bytes(payload)
    assert authority["gitBlobSha256"] == (
        "ad8ed0088776beffe8f1cab75b7edea9c2497fc80146fb74e1686d0c41896a6d"
    )
    assert authority["byteLength"] == len(payload) == 96153
    assert verify_blueprint_authority(REPOSITORY, authority) == []


@pytest.mark.parametrize("autocrlf", ["false", "input", "true"])
def test_git_blob_authority_survives_checkout_newline_modes(tmp_path: Path, autocrlf: str) -> None:
    _oid, canonical = read_git_blob(REPOSITORY)
    repository = tmp_path / autocrlf
    repository.mkdir()

    def git(*args: str, input_bytes: bytes | None = None, strip: bool = True) -> bytes:
        output = subprocess.check_output(
            ["git", *args], cwd=repository, input=input_bytes, stderr=subprocess.STDOUT
        )
        return output.strip() if strip else output

    git("init", "-q")
    git("config", "user.name", "Capture V2 Authority Test")
    git("config", "user.email", "capture-v2-authority@invalid.local")
    blob = git("hash-object", "-w", "--stdin", input_bytes=canonical).decode("ascii")
    git("update-index", "--add", "--cacheinfo", "100644", blob, "blueprint.md")
    tree = git("write-tree").decode("ascii")
    commit = git("commit-tree", tree, "-m", "canonical blueprint").decode("ascii")
    git("update-ref", "refs/heads/main", commit)
    git("symbolic-ref", "HEAD", "refs/heads/main")
    git("config", "core.autocrlf", autocrlf)
    git("reset", "--hard", "-q", "HEAD")

    checked_out = (repository / "blueprint.md").read_bytes()
    assert git("show", "HEAD:blueprint.md", strip=False) == canonical
    if autocrlf == "true":
        assert b"\r\n" in checked_out
    else:
        assert b"\r\n" not in checked_out

    (repository / "blueprint.md").write_bytes(checked_out + b"\n")
    assert sha256_bytes((repository / "blueprint.md").read_bytes()) != sha256_bytes(canonical)
    assert sha256_bytes(git("show", "HEAD:blueprint.md", strip=False)) == sha256_bytes(canonical)


def test_blueprint_parser_covers_every_source_block_without_ambiguity() -> None:
    oid, payload = read_git_blob(REPOSITORY)
    inventory = build_requirement_inventory(payload.decode("utf-8"), source_blob_oid=oid)
    assert inventory["sourceBlockCount"] == len(inventory["blocks"])
    assert inventory["mappedNormativeBlockCount"] == len(inventory["requirements"])
    assert inventory["sourceBlockCounts"]["ambiguous"] == 0
    assert inventory["sourceBlockCounts"]["unclassified"] == 0
    assert inventory["unmappedNormativeBlockCount"] == 0
    assert validate_inventory(inventory) == []


def test_blueprint_parser_mutations_add_remove_reword_duplicate_and_relocate() -> None:
    source = "# Phase 2\n\n- Must preserve canonical garment truth.\n- Record evidence digests.\n"
    baseline = build_requirement_inventory(source, source_blob_oid="a" * 40)
    added = build_requirement_inventory(
        source + "- Validate every retained package.\n", source_blob_oid="a" * 40
    )
    removed = build_requirement_inventory(
        source.replace("- Record evidence digests.\n", ""), source_blob_oid="a" * 40
    )
    reworded = build_requirement_inventory(
        source.replace("canonical garment truth", "canonical pattern truth"),
        source_blob_oid="a" * 40,
    )
    relocated = build_requirement_inventory(
        source.replace("# Phase 2", "# Appendix\n\n## Phase 2"), source_blob_oid="a" * 40
    )
    assert len(added["requirements"]) == len(baseline["requirements"]) + 1
    assert len(removed["requirements"]) == len(baseline["requirements"]) - 1
    assert reworded["requirementSetDigest"] != baseline["requirementSetDigest"]
    assert relocated["requirementSetDigest"] == baseline["requirementSetDigest"]
    assert relocated["requirements"][0]["headingPath"] != baseline["requirements"][0]["headingPath"]
    with pytest.raises(ValueError, match="duplicate_normalized_requirement"):
        build_requirement_inventory(
            source + "- Must preserve canonical garment truth.\n", source_blob_oid="a" * 40
        )


def test_blueprint_parser_rejects_bom_and_unclosed_fence() -> None:
    with pytest.raises(ValueError, match="utf8_bom_forbidden"):
        parse_source_blocks("\ufeff# Blueprint\n")
    with pytest.raises(ValueError, match="unclosed_code_fence"):
        parse_source_blocks("# Blueprint\n\n```text\nnot closed\n")


def _registry() -> dict[str, object]:
    value: dict[str, object] = {
        field: "a" * 64 if field.endswith("Digest") else "b" * 40 for field in REQUIRED_BINDINGS
    }
    value.update(
        {
            "authorityIdentity": "AUTH-1",
            "seedIdentity": "SEED-1",
            "allowedClaims": ["synthetic_capture_engineering"],
            "evidenceClass": "source_guarded_project_authored_synthetic_capture_engineering",
            "registeredFixtureKinds": [
                "canonical_result_receipt",
                "commitment_matching_synthetic_truth_disclosure",
            ],
            "freezeSequence": 10,
            "resultSequence": 20,
            "seedConsumed": True,
            "canonicalResultDigest": "c" * 64,
        }
    )
    return value


def _artifact(registry: dict[str, object]) -> dict[str, object]:
    value = {field: registry[field] for field in REQUIRED_BINDINGS}
    value.update(
        {
            "fixtureKind": "canonical_result_receipt",
            "requestedClaims": ["synthetic_capture_engineering"],
            "evidenceClass": registry["evidenceClass"],
            "seedConsumed": True,
        }
    )
    return value


def test_evidence_eligibility_is_registry_owned_and_rejects_substitution_replay_and_elevation() -> (
    None
):
    registry = _registry()
    artifact = _artifact(registry)
    assert verify_evidence_eligibility(artifact, registry, observation_sequence=20)["eligible"]
    for mutation, reason in (
        ({"fixtureKind": "producer_claimed_science"}, "unregistered_fixture_kind_rejected"),
        ({"candidateDigest": "d" * 64}, "evidence_candidateDigest_mismatch"),
        ({"protocolDigest": "e" * 64}, "evidence_protocolDigest_mismatch"),
        ({"requestedClaims": ["production"]}, "producer_claim_elevation_rejected"),
    ):
        changed = {**artifact, **mutation}
        report = verify_evidence_eligibility(changed, registry, observation_sequence=20)
        assert not report["eligible"]
        assert reason in report["reasonCodes"]
    post = verify_evidence_eligibility(artifact, registry, observation_sequence=21)
    assert "post_result_claim_elevation_rejected" in post["reasonCodes"]


def test_commitment_matching_disclosure_is_the_only_non_claiming_post_result_exception() -> None:
    registry = _registry()
    disclosure = _artifact(registry)
    disclosure.update(
        {
            "fixtureKind": "commitment_matching_synthetic_truth_disclosure",
            "requestedClaims": [],
            "canonicalResultDigest": registry["canonicalResultDigest"],
        }
    )
    assert verify_evidence_eligibility(disclosure, registry, observation_sequence=21)["eligible"]
    disclosure["canonicalResultDigest"] = "f" * 64
    assert not verify_evidence_eligibility(disclosure, registry, observation_sequence=21)[
        "eligible"
    ]


def test_y2_forensic_reproduces_terminal_preseed_state_without_arming_attempt() -> None:
    report = derive_y2_terminal_state(REPOSITORY)
    assert report["terminalOutcome"] == "preseed_scientific_protocol_invalid"
    assert report["matchingAuthorityRefs"] == []
    assert report["newAttemptArmed"] is False
    assert report["seedExists"] is False
    assert report["scientificAttemptConsumed"] is False


def test_authority_digest_mutation_is_detected() -> None:
    authority = build_blueprint_authority(REPOSITORY)
    changed = deepcopy(authority)
    changed["gitBlobSha256"] = "0" * 64
    changed["authorityDigest"] = canonical_digest(changed, "authorityDigest")
    assert "blueprint_authority_gitBlobSha256_mismatch" in verify_blueprint_authority(
        REPOSITORY, changed
    )


def test_decorated_inventory_rejects_stale_counts_phase_summary_and_missing_evidence() -> None:
    oid, payload = read_git_blob(REPOSITORY)
    inventory = build_pr63_inventory(payload.decode("utf-8"), oid, result_digest=None)
    assert validate_decorated_inventory(REPOSITORY, inventory) == []
    changed = deepcopy(inventory)
    changed["statusCounts"]["partial"] += 1
    changed["phaseSummaries"]["2"] = "complete"
    changed["requirements"][0]["status"] = "partial"
    changed["requirements"][0]["evidenceAnchors"] = ["../missing-private-evidence.json"]
    changed["inventoryDigest"] = canonical_digest(changed, "inventoryDigest")
    failures = validate_decorated_inventory(REPOSITORY, changed)
    assert "blueprint_status_counts_inconsistent" in failures
    assert "blueprint_phase_summary_inconsistent" in failures
    assert "blueprint_evidence_anchor_missing_or_unsafe" in failures
