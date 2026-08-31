from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

INTEGRATED_RUNTIME_VERSION = "closy.integrated_runtime.headless_d0.v1"
INTEGRATED_CAPABILITY_VERSION = "closy.integrated_runtime.capabilities_d0.v1"
INTEGRATED_RUNTIME_CANDIDATE_VERSION = "closy.integrated_runtime.research_candidate.v2"
INTEGRATED_CANDIDATE_CAPABILITY_VERSION = "closy.integrated_runtime.capabilities_d0.v2"


@dataclass(frozen=True)
class RuntimeAuthority:
    package_digest: str
    conventional_fallback_sha256: str
    garment_topology_hash: str
    binding_hash: str
    static_derivative_identity: str
    dynamic_request_identity: str
    dynamic_output_identity: str
    zeroone_binary_identity: str
    avatar_authority_hash: str
    avatar_fit_digest: str
    layer_profile_identity: str
    outfit_surface_identity: str

    def validate(self) -> None:
        for field, value in self.__dict__.items():
            if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                raise ValueError(f"runtime_authority_digest_invalid:{field}")


@dataclass(frozen=True)
class PackageAuthority:
    runtime_package_digest: str
    garment_package_digest: str
    garment_id: str
    avatar_contract_hash: str
    pattern_hash: str
    seam_opening_hash: str
    simulation_topology_hash: str
    render_topology_hash: str
    binding_hash: str
    conventional_garment_fallback_sha256: str
    source_fidelity_identity: str
    material_identity: str
    zeroone_static_descriptor_identity: str | None
    zeroone_dynamic_descriptor_identity: str | None
    expected_zeroone_binary_identity: str | None
    static_input_surface_identity: str | None
    mechanical_reference_surface_identity: str | None

    def validate(self) -> None:
        if not self.garment_id.startswith("garment."):
            raise ValueError("package_authority_garment_id_invalid")
        for field, value in self.__dict__.items():
            if field == "garment_id" or value is None:
                continue
            if not _is_sha256(value):
                raise ValueError(f"package_authority_digest_invalid:{field}")


@dataclass(frozen=True)
class ExecutionAuthority:
    platform: str
    architecture: str
    zeroone_commit: str
    executable_sha256: str
    processor_contract_identity: str
    candidate_runtime_package_digest: str
    static_descriptor_identity: str
    static_input_surface_identity: str
    static_request_identity: str
    static_output_inventory_identity: str
    mechanical_reference_surface_identity: str
    simulation_topology_hash: str
    render_topology_hash: str
    binding_hash: str
    dynamic_request_identity: str
    dynamic_output_inventory_identity: str
    execution_attestation_identity: str
    static_payload_opened: bool
    dynamic_payload_opened: bool

    def validate(self) -> None:
        if not self.platform or not self.architecture:
            raise ValueError("execution_authority_platform_invalid")
        if len(self.zeroone_commit) != 40 or any(
            character not in "0123456789abcdef" for character in self.zeroone_commit
        ):
            raise ValueError("execution_authority_commit_invalid")
        for field, value in self.__dict__.items():
            if field in {
                "platform",
                "architecture",
                "zeroone_commit",
                "static_payload_opened",
                "dynamic_payload_opened",
            }:
                continue
            if not _is_sha256(value):
                raise ValueError(f"execution_authority_digest_invalid:{field}")


@dataclass(frozen=True)
class CandidateRuntimeRequest:
    supports_zeroone_static_payload: bool = False
    supports_zeroone_dynamic_payload: bool = False
    capability_version: str = INTEGRATED_CANDIDATE_CAPABILITY_VERSION


@dataclass(frozen=True)
class CandidateRuntimeDecision:
    runtime_version: str
    package_valid: bool
    render_source: Literal["conventional_garment_glb", "external_zeroone_static_payload"]
    motion_source: Literal["external_zeroone_dynamic_payload", "prebaked_static_pose"]
    descriptor_only: bool
    optional_capabilities_admitted: tuple[str, ...]
    fallback_reasons: tuple[str, ...]
    package_authority: PackageAuthority
    execution_authority_joined: bool

    def to_record(self) -> dict[str, object]:
        return {
            "runtimeVersion": self.runtime_version,
            "packageValid": self.package_valid,
            "renderSource": self.render_source,
            "motionSource": self.motion_source,
            "descriptorOnly": self.descriptor_only,
            "optionalCapabilitiesAdmitted": list(self.optional_capabilities_admitted),
            "fallbackReasons": list(self.fallback_reasons),
            "executionAuthorityJoined": self.execution_authority_joined,
            "packageAuthority": package_authority_record(self.package_authority),
        }


@dataclass(frozen=True)
class CapabilityState:
    available: bool
    integrity_valid: bool
    version_supported: bool = True

    @property
    def admissible(self) -> bool:
        return self.available and self.integrity_valid and self.version_supported


@dataclass(frozen=True)
class RuntimeCapabilities:
    package: CapabilityState
    zeroone_static: CapabilityState
    mt1_reference_motion: CapabilityState
    conventional_deformation: CapabilityState
    synthetic_avatar: CapabilityState
    layer_collision: CapabilityState
    capability_version: str = INTEGRATED_CAPABILITY_VERSION


@dataclass(frozen=True)
class RuntimeRequest:
    authority: RuntimeAuthority
    supports_zeroone_static: bool = True
    supports_mt1_reference_motion: bool = True
    supports_conventional_deformation: bool = True
    supports_synthetic_avatar: bool = True
    supports_layer_collision: bool = True
    capability_version: str = INTEGRATED_CAPABILITY_VERSION


@dataclass(frozen=True)
class RuntimeDecision:
    runtime_version: str
    package_valid: bool
    static_source: Literal["zeroone_static", "conventional_glb"]
    motion_source: Literal[
        "zeroone_mt1_reference_motion",
        "conventional_deformation",
        "prebaked_static_pose",
    ]
    avatar_source: Literal["synthetic_avatar_d0", "fixed_reference_avatar"]
    layer_source: Literal["canonical_surface_layer_d0", "single_garment_only"]
    optional_capabilities_admitted: tuple[str, ...]
    fallback_reasons: tuple[str, ...]
    authority: RuntimeAuthority

    def to_record(self) -> dict[str, object]:
        return {
            "runtimeVersion": self.runtime_version,
            "packageValid": self.package_valid,
            "staticSource": self.static_source,
            "motionSource": self.motion_source,
            "avatarSource": self.avatar_source,
            "layerSource": self.layer_source,
            "optionalCapabilitiesAdmitted": list(self.optional_capabilities_admitted),
            "fallbackReasons": list(self.fallback_reasons),
            "authority": {
                "packageDigest": self.authority.package_digest,
                "conventionalFallbackSha256": self.authority.conventional_fallback_sha256,
                "garmentTopologyHash": self.authority.garment_topology_hash,
                "bindingHash": self.authority.binding_hash,
                "staticDerivativeIdentity": self.authority.static_derivative_identity,
                "dynamicRequestIdentity": self.authority.dynamic_request_identity,
                "dynamicOutputIdentity": self.authority.dynamic_output_identity,
                "zeroOneBinaryIdentity": self.authority.zeroone_binary_identity,
                "avatarAuthorityHash": self.authority.avatar_authority_hash,
                "avatarFitDigest": self.authority.avatar_fit_digest,
                "layerProfileIdentity": self.authority.layer_profile_identity,
                "outfitSurfaceIdentity": self.authority.outfit_surface_identity,
            },
        }


def package_authority_record(authority: PackageAuthority) -> dict[str, object]:
    return {
        "runtimePackageDigest": authority.runtime_package_digest,
        "garmentPackageDigest": authority.garment_package_digest,
        "garmentId": authority.garment_id,
        "avatarContractHash": authority.avatar_contract_hash,
        "patternHash": authority.pattern_hash,
        "seamOpeningHash": authority.seam_opening_hash,
        "simulationTopologyHash": authority.simulation_topology_hash,
        "renderTopologyHash": authority.render_topology_hash,
        "bindingHash": authority.binding_hash,
        "conventionalGarmentFallbackSha256": (authority.conventional_garment_fallback_sha256),
        "sourceFidelityIdentity": authority.source_fidelity_identity,
        "materialIdentity": authority.material_identity,
        "zeroOneStaticDescriptorIdentity": authority.zeroone_static_descriptor_identity,
        "zeroOneDynamicDescriptorIdentity": authority.zeroone_dynamic_descriptor_identity,
        "expectedZeroOneBinaryIdentity": authority.expected_zeroone_binary_identity,
        "staticInputSurfaceIdentity": authority.static_input_surface_identity,
        "mechanicalReferenceSurfaceIdentity": authority.mechanical_reference_surface_identity,
    }


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
