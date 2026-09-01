from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from closy_forge.disjoint_confirmation_v2.evaluator import aggregate_result
from closy_forge.disjoint_confirmation_v2.protocol import (
    APPEARANCE_ORDINALS,
    BENCHMARK_VERSION,
    FIXTURE_ROOT,
    FULL_COMPILE_ROUTES,
    PRIMARY_ROUTE,
    ROUTES,
    load_protocol,
    validate_implementation,
    validate_protocol,
)
from closy_forge.package_io.canonical_json import read_json

ROOT = Path(__file__).resolve().parents[2]


def _mapping(path: Path) -> dict[str, object]:
    value = read_json(path)
    assert isinstance(value, dict)
    return value


def test_lock_has_exact_denominators_and_no_fresh_cohort() -> None:
    protocol = load_protocol(ROOT)
    assert protocol["benchmarkVersion"] == BENCHMARK_VERSION
    assert tuple(protocol["routes"]) == ROUTES
    assert tuple(protocol["fullCompileRoutes"]) == FULL_COMPILE_ROUTES
    assert protocol["primaryRoute"] == PRIMARY_ROUTE
    assert tuple(protocol["appearanceOrdinals"]) == APPEARANCE_ORDINALS
    assert protocol["predictionDenominator"] == 64
    assert protocol["fullCompileDenominator"] == 48
    assert protocol["primaryCompileRepeatDenominator"] == 16
    assert protocol["appearanceDenominator"] == 24
    assert protocol["primaryAppearanceRepeatDenominator"] == 8
    assert protocol["freshEvaluatorIdentitiesRealized"] is False
    assert protocol["freshEvaluatorTargetsRealized"] is False
    assert not (ROOT / FIXTURE_ROOT / "official_attempt").exists()
    assert validate_protocol(protocol) == []
    assert validate_implementation(ROOT, protocol) == []


def test_protocol_mutations_fail_closed() -> None:
    protocol = load_protocol(ROOT)
    mutated = deepcopy(protocol)
    mutated["predictionDenominator"] = 63
    assert "protocol_field_invalid:predictionDenominator" in validate_protocol(mutated)
    assert "protocol_lock_hash_mismatch" in validate_protocol(mutated)
    mutated = deepcopy(protocol)
    mutated["perIdentityRouteSelectionAllowed"] = True
    assert "protocol_false_field_invalid:perIdentityRouteSelectionAllowed" in validate_protocol(
        mutated
    )


def test_development_proof_is_contaminated_and_complete() -> None:
    proof = _mapping(ROOT / FIXTURE_ROOT / "development_proof.json")
    assert proof["classification"] == "revealed_unit_g_v1_contaminated_harness_diagnostic_only"
    assert proof["mayCloseResearchPrototypeRows"] is False
    assert proof["listTranscriptLoaded"] is True
    assert proof["mappingArtifactsLoaded"] is True
    assert proof["predictionCount"] == 64
    assert proof["fullCompileCount"] == 48
    assert proof["fullCompileSuccessCount"] == 45
    assert proof["primaryCompileRepeatCount"] == 16
    assert proof["appearanceEvaluationCount"] == 24
    assert proof["primaryAppearanceRepeatCount"] == 8
    assert proof["allGateFamiliesExecuted"] is True
    assert proof["contributionDerived"] is True


def test_prior_inventory_covers_disjointness_classes() -> None:
    inventory = _mapping(ROOT / FIXTURE_ROOT / "prior_inventory.json")
    assert inventory["identityValues"]
    assert inventory["parameterRecords"]
    assert inventory["parameterHashes"]
    assert inventory["pixelHashes"]
    assert inventory["geometryHashes"]
    assert inventory["targetFeatureHashes"]
    assert len(str(inventory["inventoryDigest"])) == 64


def test_authority_workflow_is_one_shot_and_exact_head() -> None:
    workflow = (ROOT.parent / ".github/workflows/closy-forge-unit-m-authority.yml").read_text(
        encoding="utf-8"
    )
    official = ROOT / FIXTURE_ROOT / "official_attempt"
    assert "workflow_dispatch" not in workflow
    if official.exists():
        assert "sealed_post_attempt" in workflow
        assert "run_d0_disjoint_confirmation_v2_authority.py" not in workflow
    else:
        assert 'test "$GITHUB_RUN_ATTEMPT" = "1"' in workflow
        assert "github.event.pull_request.head.sha" in workflow
        assert "prior_count" in workflow
    assert "--network" in (
        ROOT / "src/closy_forge/disjoint_confirmation_v2/isolation.py"
    ).read_text(encoding="utf-8")


def test_predraw_failure_allows_only_the_recorded_artifact_free_replacement() -> None:
    lifecycle = _mapping(ROOT / FIXTURE_ROOT / "authority_lifecycle.json")
    events = lifecycle["events"]
    assert isinstance(events, list) and len(events) == 1
    event = events[0]
    assert isinstance(event, dict)
    assert event["runId"] == "33530331133"
    assert event["jobId"] == "99931572124"
    assert event["classification"] == "failed_before_seed_or_commitment"
    assert event["seedOrCommitmentCreated"] is False
    assert event["publishedAttempt"] is False
    assert event["artifactCount"] == 0
    assert lifecycle["acceptedAttemptCount"] == 0
    assert lifecycle["maximumReplacementRunsAfterPreDrawInfrastructureFailure"] == 1
    assert lifecycle["nextAuthorityRunPermitted"] is True


def test_aggregate_rejects_incomplete_denominators() -> None:
    protocol = load_protocol(ROOT)
    with pytest.raises(ValueError, match="confirmation_v2_record_list_required"):
        aggregate_result(
            protocol=protocol,
            primary={"records": None},
            repeat={"records": []},
            predictions={"predictions": []},
            targets={"identities": []},
            isolation_summary={"qualifiesD0Rp04": False},
        )


def test_lock_report_requires_external_authority_next() -> None:
    report = _mapping(ROOT / FIXTURE_ROOT / "lock_report.json")
    assert report["freshEvaluatorIdentitiesRealized"] is False
    assert report["freshEvaluatorTargetsRealized"] is False
    assert report["officialAttemptState"] == "not_started"
    assert report["nextAction"] == "external_seed_authority_once_at_exact_lock_commit"
