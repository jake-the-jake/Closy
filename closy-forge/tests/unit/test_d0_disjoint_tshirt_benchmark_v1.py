from __future__ import annotations

import json
from pathlib import Path

import pytest

from closy_forge.disjoint_benchmark_v1.compiler import compile_structural_candidate
from closy_forge.disjoint_benchmark_v1.contender_cli import ROUTES
from closy_forge.disjoint_benchmark_v1.corpus import (
    default_prior,
    realize_identities,
    verify_target_commitment,
)
from closy_forge.disjoint_benchmark_v1.development import (
    build_source_evidence,
    contestant_input,
)
from closy_forge.disjoint_benchmark_v1.evaluator import derive_evaluator_seed
from closy_forge.disjoint_benchmark_v1.isolation import execute_isolated_contender
from closy_forge.disjoint_benchmark_v1.metrics import observable_parameter_errors
from closy_forge.disjoint_benchmark_v1.protocol import (
    BENCHMARK_VERSION,
    normalized_distance,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def development_identities():
    identities, transcript = realize_identities(
        seed_hex="unit-test-development-seed",
        count=8,
        role="development",
        minimum_prior_distance=0.15,
        references=[default_prior()],
        maximum_attempts=4096,
    )
    return identities, transcript


def test_protocol_lock_precedes_all_evaluator_identities() -> None:
    protocol = json.loads(
        (ROOT / "fixtures/d0_disjoint_tshirt_benchmark_v1/protocol_lock.json").read_text()
    )
    assert protocol["benchmarkVersion"] == BENCHMARK_VERSION
    assert protocol["developmentIdentityCount"] == 8
    assert protocol["evaluatorIdentityCount"] == 16
    assert protocol["evaluatorIdentitiesRealized"] is False
    assert protocol["targetContentsMounted"] is False
    assert not (ROOT / "fixtures/d0_disjoint_tshirt_benchmark_v1/evaluator").exists()


def test_identity_draws_are_opaque_disjoint_and_committed(development_identities) -> None:
    identities, transcript = development_identities
    assert len(identities) == 8
    assert len({item.opaque_id for item in identities}) == 8
    assert all(item.opaque_id.startswith("garment_") for item in identities)
    assert all(verify_target_commitment(item.target_record()) for item in identities)
    assert all(item.target_commitment in json.dumps(transcript) for item in identities)
    assert all(normalized_distance(item.parameters, default_prior()) >= 0.15 for item in identities)


def test_evaluator_seed_uses_exact_authority_tuple() -> None:
    lock_sha = "1" * 40
    seed = derive_evaluator_seed(lock_sha, 12345, 67890)
    assert len(seed) == 64
    assert seed != derive_evaluator_seed(lock_sha, 12345, 67891)
    with pytest.raises(ValueError, match="seed_authority_invalid"):
        derive_evaluator_seed("short", 1, 2)


def test_source_and_target_renderers_produce_nonblank_distinct_roles(
    development_identities,
) -> None:
    identity = development_identities[0][0]
    source = build_source_evidence(identity)
    assert source["front"]["maskPixelCount"] > 0
    assert source["rear"]["maskPixelCount"] > 0
    assert source["png"]["front"] != source["png"]["rear"]


def test_structural_compiler_never_executes_physics(development_identities) -> None:
    compiled = compile_structural_candidate(development_identities[0][0].parameters)
    assert compiled.report["finite"] is True
    assert compiled.report["solverExecuted"] is False
    assert compiled.report["physicsClaimed"] is False
    assert compiled.report["openingIds"] == [
        "opening.cuff.left",
        "opening.cuff.right",
        "opening.hem",
        "opening.neck",
    ]


def test_contender_runs_in_stripped_audited_subprocess(development_identities) -> None:
    identity = development_identities[0][0]
    source = build_source_evidence(identity)
    prior = default_prior()
    config = {
        "metadataPrior": prior,
        "noPixelPrior": prior,
        "sourceFitterBodyEase": 0.045,
        "developmentMaskCoverageMedian": source["front"]["maskCoverage"],
        "appearancePrior": source["appearanceFeatures"],
    }
    prediction, report = execute_isolated_contender(
        executable=ROOT / "src/closy_forge/disjoint_benchmark_v1/contender_cli.py",
        route="deterministic_masks_landmarks",
        input_payload=contestant_input(identity.opaque_id, source, "deterministic_masks_landmarks"),
        config=config,
    )
    assert prediction["routeId"] == "deterministic_masks_landmarks"
    assert report["allOpenedPathsAllowed"] is True
    assert report["withdrawalExecutionFailedClosed"] is True
    assert report["repositoryRootMounted"] is False
    assert report["operatingSystemSandboxClaimed"] is False
    assert (
        observable_parameter_errors(prediction["parameters"], identity.parameters)[
            "macroNormalizedError"
        ]
        < 0.10
    )


def test_contender_routes_are_distinct_and_fixed() -> None:
    assert ROUTES == (
        "metadata_category_prior",
        "no_pixel_template_prior",
        "deterministic_masks_landmarks",
        "image_conditioned_iterative",
    )
