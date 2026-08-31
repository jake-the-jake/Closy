from __future__ import annotations

from typing import Literal

from closy_forge.integrated_runtime.contracts import (
    INTEGRATED_CANDIDATE_CAPABILITY_VERSION,
    INTEGRATED_CAPABILITY_VERSION,
    INTEGRATED_RUNTIME_CANDIDATE_VERSION,
    INTEGRATED_RUNTIME_VERSION,
    CandidateRuntimeDecision,
    CandidateRuntimeRequest,
    CapabilityState,
    ExecutionAuthority,
    PackageAuthority,
    RuntimeAuthority,
    RuntimeCapabilities,
    RuntimeDecision,
    RuntimeRequest,
)


def negotiate_candidate_runtime(
    package_authority: PackageAuthority,
    request: CandidateRuntimeRequest,
    execution_authority: ExecutionAuthority | None = None,
) -> CandidateRuntimeDecision:
    """Join validated package bytes to actual execution without descriptor self-admission."""

    package_authority.validate()
    reasons: list[str] = []
    admitted: list[str] = []
    version_matches = request.capability_version == INTEGRATED_CANDIDATE_CAPABILITY_VERSION
    if not version_matches:
        reasons.append("unsupported_candidate_capability_version")

    execution_matches = False
    if execution_authority is not None:
        execution_authority.validate()
        execution_matches = _execution_matches(package_authority, execution_authority)
        if not execution_matches:
            reasons.append("execution_authority_stale_or_cross_package")

    static_admitted = (
        version_matches
        and request.supports_zeroone_static_payload
        and execution_authority is not None
        and execution_matches
        and execution_authority.static_payload_opened
    )
    dynamic_admitted = (
        version_matches
        and request.supports_zeroone_dynamic_payload
        and static_admitted
        and execution_authority is not None
        and execution_authority.dynamic_payload_opened
    )
    if static_admitted:
        admitted.append("candidate_static_zeroone_payload")
    else:
        reasons.append("zeroone_static_descriptor_not_payload")
    if dynamic_admitted:
        admitted.append("candidate_dynamic_zeroone_payload")
    else:
        reasons.append("zeroone_dynamic_descriptor_not_payload")

    return CandidateRuntimeDecision(
        runtime_version=INTEGRATED_RUNTIME_CANDIDATE_VERSION,
        package_valid=True,
        render_source=(
            "external_zeroone_static_payload" if static_admitted else "conventional_garment_glb"
        ),
        motion_source=(
            "external_zeroone_dynamic_payload" if dynamic_admitted else "prebaked_static_pose"
        ),
        descriptor_only=not static_admitted and not dynamic_admitted,
        optional_capabilities_admitted=tuple(admitted),
        fallback_reasons=tuple(dict.fromkeys(reasons)),
        package_authority=package_authority,
        execution_authority_joined=execution_matches,
    )


def _execution_matches(package: PackageAuthority, execution: ExecutionAuthority) -> bool:
    return (
        execution.candidate_runtime_package_digest == package.runtime_package_digest
        and execution.static_descriptor_identity == package.zeroone_static_descriptor_identity
        and execution.executable_sha256 == package.expected_zeroone_binary_identity
        and execution.static_input_surface_identity == package.static_input_surface_identity
        and execution.mechanical_reference_surface_identity
        == package.mechanical_reference_surface_identity
        and execution.simulation_topology_hash == package.simulation_topology_hash
        and execution.render_topology_hash == package.render_topology_hash
        and execution.binding_hash == package.binding_hash
        and execution.dynamic_request_identity != execution.dynamic_output_inventory_identity
        and execution.static_request_identity != execution.static_output_inventory_identity
    )


def negotiate_runtime(
    authoritative: RuntimeAuthority,
    capabilities: RuntimeCapabilities,
    request: RuntimeRequest,
) -> RuntimeDecision:
    """Admit optional runtime paths only when capability and exact identity both match."""

    authoritative.validate()
    request.authority.validate()
    if not capabilities.package.admissible:
        raise ValueError("integrated_runtime_package_invalid")

    reasons: list[str] = []
    admitted: list[str] = []
    version_matches = (
        capabilities.capability_version == INTEGRATED_CAPABILITY_VERSION
        and request.capability_version == INTEGRATED_CAPABILITY_VERSION
    )
    if not version_matches:
        reasons.append("unsupported_capability_version")

    static_matches = _matches(
        authoritative,
        request.authority,
        ("package_digest", "conventional_fallback_sha256", "static_derivative_identity"),
    )
    static_admitted = (
        version_matches
        and request.supports_zeroone_static
        and capabilities.zeroone_static.admissible
        and static_matches
    )
    static_source: Literal["zeroone_static", "conventional_glb"]
    if static_admitted:
        static_source = "zeroone_static"
        admitted.append("candidate_static_zeroone")
    else:
        static_source = "conventional_glb"
        reasons.append(
            _fallback_reason("zeroone_static", capabilities.zeroone_static, static_matches)
        )

    mt1_matches = _matches(
        authoritative,
        request.authority,
        (
            "garment_topology_hash",
            "static_derivative_identity",
            "dynamic_request_identity",
            "dynamic_output_identity",
            "zeroone_binary_identity",
        ),
    )
    mt1_admitted = (
        version_matches
        and static_admitted
        and request.supports_mt1_reference_motion
        and capabilities.mt1_reference_motion.admissible
        and mt1_matches
    )
    c3_matches = _matches(
        authoritative,
        request.authority,
        ("garment_topology_hash", "binding_hash"),
    )
    c3_admitted = (
        version_matches
        and request.supports_conventional_deformation
        and capabilities.conventional_deformation.admissible
        and c3_matches
    )
    motion_source: Literal[
        "zeroone_mt1_reference_motion",
        "conventional_deformation",
        "prebaked_static_pose",
    ]
    if mt1_admitted:
        motion_source = "zeroone_mt1_reference_motion"
        admitted.append("mt1_reference_motion_d0")
    elif c3_admitted:
        motion_source = "conventional_deformation"
        admitted.append("conventional_c3_deformation")
        reasons.append(
            _fallback_reason("mt1_reference_motion", capabilities.mt1_reference_motion, mt1_matches)
        )
    else:
        motion_source = "prebaked_static_pose"
        reasons.extend(
            (
                _fallback_reason(
                    "mt1_reference_motion", capabilities.mt1_reference_motion, mt1_matches
                ),
                _fallback_reason(
                    "conventional_deformation", capabilities.conventional_deformation, c3_matches
                ),
            )
        )

    avatar_matches = _matches(
        authoritative,
        request.authority,
        ("avatar_authority_hash", "avatar_fit_digest"),
    )
    avatar_admitted = (
        version_matches
        and request.supports_synthetic_avatar
        and capabilities.synthetic_avatar.admissible
        and avatar_matches
    )
    avatar_source: Literal["synthetic_avatar_d0", "fixed_reference_avatar"]
    if avatar_admitted:
        avatar_source = "synthetic_avatar_d0"
        admitted.append("synthetic_avatar_exact_authority")
    else:
        avatar_source = "fixed_reference_avatar"
        reasons.append(
            _fallback_reason("synthetic_avatar", capabilities.synthetic_avatar, avatar_matches)
        )

    layer_matches = _matches(
        authoritative,
        request.authority,
        (
            "garment_topology_hash",
            "avatar_authority_hash",
            "avatar_fit_digest",
            "layer_profile_identity",
            "outfit_surface_identity",
        ),
    )
    layer_admitted = (
        version_matches
        and avatar_admitted
        and request.supports_layer_collision
        and capabilities.layer_collision.admissible
        and layer_matches
    )
    layer_source: Literal["canonical_surface_layer_d0", "single_garment_only"]
    if layer_admitted:
        layer_source = "canonical_surface_layer_d0"
        admitted.append("geometric_layer_collision_d0")
    else:
        layer_source = "single_garment_only"
        reasons.append(
            _fallback_reason("layer_collision", capabilities.layer_collision, layer_matches)
        )

    return RuntimeDecision(
        runtime_version=INTEGRATED_RUNTIME_VERSION,
        package_valid=True,
        static_source=static_source,
        motion_source=motion_source,
        avatar_source=avatar_source,
        layer_source=layer_source,
        optional_capabilities_admitted=tuple(admitted),
        fallback_reasons=tuple(dict.fromkeys(reasons)),
        authority=authoritative,
    )


def _matches(
    expected: RuntimeAuthority, requested: RuntimeAuthority, fields: tuple[str, ...]
) -> bool:
    return all(getattr(expected, field) == getattr(requested, field) for field in fields)


def _fallback_reason(name: str, state: CapabilityState, identity_matches: bool) -> str:
    if not state.available:
        return f"{name}_unavailable"
    if not state.integrity_valid:
        return f"{name}_corrupt"
    if not state.version_supported:
        return f"{name}_unsupported"
    if not identity_matches:
        return f"{name}_stale_identity"
    return f"{name}_not_requested"
