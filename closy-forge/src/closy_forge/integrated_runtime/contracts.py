from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

INTEGRATED_RUNTIME_VERSION = "closy.integrated_runtime.headless_d0.v1"
INTEGRATED_CAPABILITY_VERSION = "closy.integrated_runtime.capabilities_d0.v1"


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
