from __future__ import annotations

from dataclasses import replace

import pytest

from closy_forge.integrated_runtime import (
    CapabilityState,
    RuntimeAuthority,
    RuntimeCapabilities,
    RuntimeRequest,
    build_canonical_outfit_case,
    negotiate_runtime,
    run_canonical_outfit_surface_solve,
)
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.zeroone.invalidation_ledger import (
    INTEGRATED_IDENTITY_KEYS,
    build_integrated_runtime_invalidation_ledger,
    validate_integrated_runtime_invalidation_ledger,
)


def _digest(label: str) -> str:
    return sha256_bytes(label.encode())


def _authority() -> RuntimeAuthority:
    return RuntimeAuthority(
        package_digest=_digest("package"),
        conventional_fallback_sha256=_digest("fallback"),
        garment_topology_hash=_digest("topology"),
        binding_hash=_digest("binding"),
        static_derivative_identity=_digest("static"),
        dynamic_request_identity=_digest("request"),
        dynamic_output_identity=_digest("output"),
        zeroone_binary_identity=_digest("binary"),
        avatar_authority_hash=_digest("avatar"),
        avatar_fit_digest=_digest("fit"),
        layer_profile_identity=_digest("layer-profile"),
        outfit_surface_identity=_digest("outfit-surface"),
    )


def _capabilities() -> RuntimeCapabilities:
    valid = CapabilityState(True, True)
    return RuntimeCapabilities(
        package=valid,
        zeroone_static=valid,
        mt1_reference_motion=valid,
        conventional_deformation=valid,
        synthetic_avatar=valid,
        layer_collision=valid,
    )


def test_exact_authority_admits_every_current_d0_capability() -> None:
    authority = _authority()
    decision = negotiate_runtime(authority, _capabilities(), RuntimeRequest(authority))

    assert decision.package_valid is True
    assert decision.static_source == "zeroone_static"
    assert decision.motion_source == "zeroone_mt1_reference_motion"
    assert decision.avatar_source == "synthetic_avatar_d0"
    assert decision.layer_source == "canonical_surface_layer_d0"
    assert decision.fallback_reasons == ()


def test_zeroone_is_optional_and_conventional_package_remains_valid() -> None:
    authority = _authority()
    unavailable = CapabilityState(False, False)
    capabilities = replace(
        _capabilities(),
        zeroone_static=unavailable,
        mt1_reference_motion=unavailable,
    )
    decision = negotiate_runtime(authority, capabilities, RuntimeRequest(authority))

    assert decision.package_valid is True
    assert decision.static_source == "conventional_glb"
    assert decision.motion_source == "conventional_deformation"
    assert "zeroone_static_unavailable" in decision.fallback_reasons
    assert "mt1_reference_motion_unavailable" in decision.fallback_reasons


@pytest.mark.parametrize(
    ("field", "expected_source", "expected_reason"),
    [
        ("static_derivative_identity", "conventional_glb", "zeroone_static_stale_identity"),
        (
            "dynamic_output_identity",
            "zeroone_static",
            "mt1_reference_motion_stale_identity",
        ),
        ("avatar_fit_digest", "zeroone_static", "synthetic_avatar_stale_identity"),
        ("outfit_surface_identity", "zeroone_static", "layer_collision_stale_identity"),
    ],
)
def test_stale_optional_identity_fails_closed(
    field: str, expected_source: str, expected_reason: str
) -> None:
    authority = _authority()
    stale = replace(authority, **{field: _digest(f"stale-{field}")})
    decision = negotiate_runtime(authority, _capabilities(), RuntimeRequest(stale))

    assert decision.static_source == expected_source
    assert expected_reason in decision.fallback_reasons
    if field == "avatar_fit_digest":
        assert decision.avatar_source == "fixed_reference_avatar"
        assert decision.layer_source == "single_garment_only"


def test_corrupt_or_unsupported_capability_fails_closed() -> None:
    authority = _authority()
    capabilities = replace(
        _capabilities(),
        zeroone_static=CapabilityState(True, False),
        synthetic_avatar=CapabilityState(True, True, False),
    )
    decision = negotiate_runtime(authority, capabilities, RuntimeRequest(authority))

    assert decision.static_source == "conventional_glb"
    assert decision.avatar_source == "fixed_reference_avatar"
    assert decision.layer_source == "single_garment_only"
    assert "zeroone_static_corrupt" in decision.fallback_reasons
    assert "synthetic_avatar_unsupported" in decision.fallback_reasons


def test_invalid_base_package_is_rejected_even_when_optional_capabilities_exist() -> None:
    authority = _authority()
    capabilities = replace(_capabilities(), package=CapabilityState(True, False))

    with pytest.raises(ValueError, match="integrated_runtime_package_invalid"):
        negotiate_runtime(authority, capabilities, RuntimeRequest(authority))


def test_canonical_surface_outfit_executes_real_triangle_clearance_solve() -> None:
    case = build_canonical_outfit_case()
    report = run_canonical_outfit_surface_solve(case)

    assert report["surfaceExecution"]["actualIndexedTriangleSurfaces"] is True
    assert report["surfaceExecution"]["metadataOnly"] is False
    assert report["initial"]["contactCount"] > 0
    assert report["intersectionAudit"]["initialIntersections"] > 0
    assert report["final"]["unresolvedContactCount"] == 0
    assert report["final"]["orderingInversionCount"] == 0
    assert report["intersectionAudit"]["finalIntersections"] == 0
    assert min(report["final"]["minimumClearanceBySemanticRegionMeters"].values()) >= 0.002
    assert report["openingAccessibility"] == {"neck": True, "hem": True}
    assert report["seamOpeningPreservation"]["seamsOrOpeningsRewritten"] is False
    assert report["truth"]["physicalSimulation"] is False


def test_canonical_surface_outfit_is_deterministic() -> None:
    first = run_canonical_outfit_surface_solve(build_canonical_outfit_case())
    second = run_canonical_outfit_surface_solve(build_canonical_outfit_case())

    assert first == second


def test_representation_ledger_calculates_targeted_runtime_invalidation() -> None:
    baseline = {key: _digest(key) for key in INTEGRATED_IDENTITY_KEYS}
    current = {**baseline, "simulationTopologyHash": _digest("topology-v2")}
    ledger = build_integrated_runtime_invalidation_ledger(baseline, current)
    invalidated = ledger["calculatedInvalidation"]["invalidatedCapabilities"]

    assert invalidated == [
        "conventional_c3_deformation",
        "geometric_layer_collision_d0",
        "mt1_reference_motion_d0",
    ]
    assert (
        "conventional_static_fallback"
        in ledger["calculatedInvalidation"]["retainedByExactIdentity"]
    )
    assert validate_integrated_runtime_invalidation_ledger(ledger, current) == []


def test_representation_ledger_rejects_stale_current_identity() -> None:
    baseline = {key: _digest(key) for key in INTEGRATED_IDENTITY_KEYS}
    ledger = build_integrated_runtime_invalidation_ledger(baseline, baseline)
    changed = {**baseline, "avatarFitDigest": _digest("new-avatar-fit")}

    assert validate_integrated_runtime_invalidation_ledger(ledger, changed) == [
        "integrated_invalidation_current_identity_stale",
        "integrated_invalidation_not_recalculated",
    ]
