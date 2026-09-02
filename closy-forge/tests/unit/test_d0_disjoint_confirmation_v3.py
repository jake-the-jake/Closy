from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from closy_forge.disjoint_confirmation_v3.authority import SOURCE_ROLE_SCHEDULE
from closy_forge.disjoint_confirmation_v3.evaluator import validate_result
from closy_forge.disjoint_confirmation_v3.protocol import (
    APPEARANCE_ORDINALS,
    FIXTURE_ROOT,
    FULL_COMPILE_ROUTES,
    OUTCOMES,
    PRIMARY_ROUTE,
    ROUTES,
    load_protocol,
    validate_implementation,
    validate_protocol,
)

ROOT = Path(__file__).resolve().parents[2]


def test_preseed_protocol_is_exact_complete_and_contains_no_official_data() -> None:
    protocol = load_protocol(ROOT)
    assert validate_protocol(protocol) == []
    assert validate_implementation(ROOT, protocol) == []
    assert tuple(protocol["routes"]) == ROUTES
    assert tuple(protocol["fullCompileRoutes"]) == FULL_COMPILE_ROUTES
    assert protocol["primaryRoute"] == PRIMARY_ROUTE
    assert tuple(protocol["appearanceOrdinals"]) == APPEARANCE_ORDINALS
    assert protocol["outcomeVocabulary"] == list(OUTCOMES)
    assert protocol["denominators"] == {
        "identity": 16,
        "attempt": 64,
        "fullCompile": 48,
        "primaryCompileRepeat": 16,
        "appearance": 24,
        "primaryAppearanceRepeat": 8,
    }
    assert all(
        protocol[field] is False
        for field in (
            "officialV3IdentityPresent",
            "officialV3TargetPresent",
            "officialV3TargetHashPresent",
            "officialV3NoncePresent",
            "officialV3RawSeedPresent",
            "officialV3PredictionPresent",
            "officialV3ResultPresent",
        )
    )


def test_lock_development_proof_is_nonqualifying_and_mutations_are_detected() -> None:
    proof = json.loads((ROOT / FIXTURE_ROOT / "development_proof.json").read_text(encoding="utf-8"))
    assert proof["qualificationEligible"] is False
    assert proof["officialSeedCreated"] is False
    assert proof["officialIdentityCreated"] is False
    assert proof["allEvaluatorMutationsDetected"] is True
    assert proof["allPixelCausalControlsPass"] is True


def test_role_schedule_varies_image_availability_without_changing_denominator() -> None:
    assert set(SOURCE_ROLE_SCHEDULE) == set(range(16))
    assert SOURCE_ROLE_SCHEDULE[6] == ["front_png"]
    assert SOURCE_ROLE_SCHEDULE[14] == ["front_png"]
    assert sum("rear_png" in roles for roles in SOURCE_ROLE_SCHEDULE.values()) == 14


def test_protocol_mutations_fail_closed() -> None:
    protocol = load_protocol(ROOT)
    for field, value in (
        ("primaryRoute", ROUTES[2]),
        ("repeatReserveReassignable", True),
        ("officialV3RawSeedPresent", True),
    ):
        mutated = deepcopy(protocol)
        mutated[field] = value
        assert validate_protocol(mutated)


def test_result_validator_rejects_denominator_and_hash_mutations() -> None:
    result = {
        "outcome": OUTCOMES[1],
        "predictionDenominator": 64,
        "predictionCount": 64,
        "fullCompileDenominator": 48,
        "fullCompileCount": 48,
        "primaryCompileRepeatDenominator": 16,
        "primaryCompileRepeatCount": 16,
        "appearanceDenominator": 24,
        "appearanceEvaluationCount": 24,
        "primaryAppearanceRepeatDenominator": 8,
        "primaryAppearanceRepeatCount": 8,
        "rowDecisions": {
            "D0-RP-03": "fail",
            "D0-RP-04": "pass",
            "D0-RP-06": "fail",
            "D0-RP-07": "fail",
        },
        "failuresRetainedInDenominator": True,
        "routePromotion": {"perIdentityMosaicUsed": False},
        "resultHash": "deliberately-invalid",
    }
    assert "d0_v3_result_hash_invalid" in validate_result(result)
    result["predictionCount"] = 63
    assert "d0_v3_result_denominator_invalid:predictionCount" in validate_result(result)
