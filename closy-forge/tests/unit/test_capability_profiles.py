from __future__ import annotations

from copy import deepcopy

import pytest

from closy_forge.capabilities.profiles import (
    C3_BINDING_D0_PROFILE_ID,
    PHY1_SINGLE_LAYER_D0_PROFILE_ID,
    CapabilityProfileError,
    load_capability_profile,
    validate_capability_profile,
    validate_profile_package_inputs,
)
from tests.helpers import build_demo


def test_c3_and_phy1_profiles_are_distinct_hashed_authorities() -> None:
    c3 = load_capability_profile(C3_BINDING_D0_PROFILE_ID)
    phy1 = load_capability_profile(PHY1_SINGLE_LAYER_D0_PROFILE_ID)

    assert c3["axes"]["gateScope"] == "binding"
    assert phy1["axes"]["gateScope"] == "physical"
    assert c3["literalGate"]["physicalCollisionQualityRequired"] is False
    assert phy1["trajectoryEvidencePolicy"]["generatedTrajectoriesAreTargetGoldens"] is False
    assert phy1["layerCollision"]["enabled"] is False
    assert len(phy1["scenarioDefinitions"]) == 11


def test_profile_hash_and_numeric_budget_drift_fail_closed() -> None:
    profile = deepcopy(load_capability_profile(PHY1_SINGLE_LAYER_D0_PROFILE_ID))
    profile["solverProfile"]["maximumIterationsPerSubstep"] = 25

    with pytest.raises(CapabilityProfileError, match="capability_profile_hash_mismatch"):
        validate_capability_profile(profile)


def test_frozen_profile_inputs_match_canonical_demo(tmp_path) -> None:  # type: ignore[no-untyped-def]
    package = build_demo(tmp_path)

    assert validate_profile_package_inputs(
        load_capability_profile(C3_BINDING_D0_PROFILE_ID), package
    ) == []
    assert validate_profile_package_inputs(
        load_capability_profile(PHY1_SINGLE_LAYER_D0_PROFILE_ID), package
    ) == []
