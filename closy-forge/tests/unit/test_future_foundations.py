from __future__ import annotations

from closy_forge.future_foundations import build_future_foundations, validate_future_foundations


def test_phases_10_to_14_runnable_foundations_execute_without_overclaim() -> None:
    first = build_future_foundations()
    second = build_future_foundations()

    assert first == second
    assert validate_future_foundations(first) == []
    assert first["phase10"]["referenceExecutableExecuted"] is True
    assert first["phase10"]["actualZeroOneStaticCookExecutedThisInvocation"] is False
    assert first["phase10"]["fallbackPreserved"] is True
    assert first["phase11"]["dynamicLodHarness"]["actualZeroOneDynamicDeformationExecuted"] is False
    assert first["phase12"]["sourceHash"] == first["phase12"]["roundTripHash"]
    assert first["phase12"]["evidenceTier"]["deviceRun"] is False
    assert first["phase13"]["quality"]["unresolvedLayerContacts"] == 0
    assert first["phase14"]["training"]["actualTrainingRun"] is False


def test_future_foundation_corruption_and_overclaim_fail_closed() -> None:
    document = build_future_foundations()
    document["phase10"]["actualZeroOneStaticCookExecutedThisInvocation"] = True
    document["phase11"]["influenceClusters"][0]["weights"]["chest"] = 0.9
    document["phase12"]["roundTripHash"] = "0" * 64
    document["phase13"]["outfit"]["layers"][0]["collisionOrder"] = 30
    document["phase14"]["training"]["actualTrainingRun"] = True

    issues = validate_future_foundations(document)

    assert "zeroone_static_contract_invalid" in issues
    assert "zeroone_deformation_foundation_invalid" in issues
    assert "mobile_runtime_foundation_invalid" in issues
    assert "avatar_layering_foundation_invalid" in issues
    assert "native_model_foundation_overclaim" in issues
    assert "future_foundations_hash_mismatch" in issues
