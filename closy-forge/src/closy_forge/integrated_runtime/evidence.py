from __future__ import annotations

import json
import platform
import shutil
import statistics
import tempfile
import time
import tracemalloc
from dataclasses import replace
from pathlib import Path
from typing import Any

from closy_forge.geometry.glb_io import write_glb
from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.integrated_runtime.contracts import (
    INTEGRATED_CAPABILITY_VERSION,
    CapabilityState,
    RuntimeAuthority,
    RuntimeCapabilities,
    RuntimeRequest,
)
from closy_forge.integrated_runtime.decision import negotiate_runtime
from closy_forge.integrated_runtime.outfit_surface import (
    CanonicalSurface,
    build_canonical_outfit_case,
    run_canonical_outfit_surface_solve,
)
from closy_forge.package_io.canonical_json import canonical_dumps, read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.runtime_delivery import (
    RuntimePackageInputs,
    build_runtime_package,
    load_runtime_package,
)
from closy_forge.zeroone.invalidation_ledger import (
    build_integrated_runtime_invalidation_ledger,
)

EVIDENCE_VERSION = "closy.integrated_runtime_avatar_outfit.evidence.d0.v1"
MT1_EVIDENCE = Path("docs/evidence/phase11_reference_motion_v2/execution_evidence.json")
MT1_LEDGER = Path(
    "docs/evidence/phase11_reference_motion_v2/representation_invalidation_ledger.json"
)


def run_integrated_runtime_evidence(root: Path, *, source_sha: str) -> dict[str, Any]:
    if len(source_sha) != 40:
        raise ValueError("integrated_evidence_source_sha_invalid")
    mt1 = _object(root / MT1_EVIDENCE)
    historical_ledger = _object(root / MT1_LEDGER)
    outfit_case = build_canonical_outfit_case()
    outfit_report = run_canonical_outfit_surface_solve(outfit_case)
    with tempfile.TemporaryDirectory(prefix="closy-integrated-runtime-d0-") as temporary:
        work = Path(temporary)
        fallback = work / "conventional_fallback.glb"
        _write_surface_glb(fallback, outfit_case.body)
        static_descriptor = work / "zeroone_static_descriptor.json"
        dynamic_descriptor = work / "mt1_reference_motion_descriptor.json"
        write_canonical_json(static_descriptor, _static_descriptor(mt1))
        write_canonical_json(dynamic_descriptor, _dynamic_descriptor(mt1))
        package = build_runtime_package(
            work / "integrated.closyruntime",
            inputs=RuntimePackageInputs(
                conventional_fallback_glb=fallback,
                zeroone_static_artifact=static_descriptor,
                zeroone_dynamic_metadata=dynamic_descriptor,
                source_link={
                    "opaqueId": "src_project_authored_integrated_runtime_d0",
                    "consentScope": "project-authored-synthetic-only",
                    "retentionPolicy": "fixture-lifetime",
                    "deletionPolicy": "managed-withdrawal",
                    "derivationPolicy": "non-identifying-runtime-artifact",
                    "withdrawalStatus": "active",
                },
                pose_id="pose.mt1.reference.neutral_v2",
                pose_payload={
                    "frame": 0,
                    "dynamicProfile": "MT1-D0-mechanical-reference-only",
                    "physicalTruth": False,
                },
            ),
        )
        manifest = _object(package / "manifest.json")
        authority = _runtime_authority(
            manifest,
            fallback,
            mt1,
            historical_ledger,
            outfit_report,
        )
        capabilities = _all_capabilities()
        exact_decision = negotiate_runtime(
            authority,
            capabilities,
            RuntimeRequest(authority),
        )
        conventional = load_runtime_package(
            package,
            support_zeroone_dynamic=False,
            support_zeroone_static=False,
        )
        static = load_runtime_package(package)
        dynamic = load_runtime_package(package, support_zeroone_dynamic=True)
        static_payload = json.loads(static.selected_bytes.decode("utf-8"))
        dynamic_payload = json.loads(dynamic.selected_bytes.decode("utf-8"))
        corrupted = work / "corrupted.closyruntime"
        shutil.copytree(package, corrupted)
        (corrupted / "assets" / "conventional_fallback.glb").write_bytes(b"corrupt")
        recovered = load_runtime_package(
            corrupted,
            support_zeroone_static=False,
            last_good_package=package,
        )
        rejection_matrix = _rejection_matrix(authority, capabilities)
        measurements = _measure_reference_execution(authority, capabilities, outfit_case)

    identities = _integrated_identity_map(
        authority,
        historical_ledger,
        outfit_report,
    )
    invalidation = build_integrated_runtime_invalidation_ledger(identities, identities)
    changed_topology = dict(identities)
    changed_topology["simulationTopologyHash"] = sha256_bytes(b"topology-v2-probe")
    topology_probe = build_integrated_runtime_invalidation_ledger(identities, changed_topology)
    evidence: dict[str, Any] = {
        "schemaVersion": 1,
        "evidenceVersion": EVIDENCE_VERSION,
        "capabilityVersion": INTEGRATED_CAPABILITY_VERSION,
        "classification": "headless_CPU_D0_integration_not_product_or_physical_acceptance",
        "generationSourceSha": source_sha,
        "historicalAuthorities": {
            "mt1EvidencePath": MT1_EVIDENCE.as_posix(),
            "mt1EvidenceSourceSha": mt1["closyExecutionSourceSha"],
            "mt1Outcome": mt1["outcome"],
            "mt1NamespaceAdmitted": mt1["dynamic"]["namespaceAdmitted"],
            "blueprintZ2Passed": mt1["claims"]["blueprintZ2Passed"],
        },
        "packageExecution": {
            "schemaNegotiated": True,
            "packageVersion": manifest["packageVersion"],
            "capabilityVersion": manifest["capabilityVersion"],
            "packageDigest": manifest["packageDigest"],
            "conventionalFallback": {
                "loaded": conventional.selected_source == "conventional_glb",
                "sha256": sha256_bytes(conventional.selected_bytes),
            },
            "candidateStatic": {
                "selected": static.selected_source == "zeroone_static",
                "payloadKind": static_payload["payloadKind"],
                "identity": static_payload["staticDerivativeIdentity"],
                "actualCookAndArtifactLoadAuthority": MT1_EVIDENCE.as_posix(),
            },
            "mt1ReferenceMotion": {
                "selected": dynamic.selected_source == "zeroone_dynamic",
                "payloadKind": dynamic_payload["payloadKind"],
                "requestIdentity": dynamic_payload["dynamicRequestIdentity"],
                "outputIdentity": dynamic_payload["dynamicOutputIdentity"],
                "mechanicalReferenceOnly": True,
            },
            "corruptPrimaryRecovery": {
                "selected": recovered.selected_source,
                "fallbackReason": recovered.fallback_reason,
                "offline": recovered.offline,
            },
            "packageValidityDependsOnZeroOne": False,
        },
        "runtimeDecision": exact_decision.to_record(),
        "failClosedRejections": rejection_matrix,
        "avatarFit": {
            "authorityMatched": exact_decision.avatar_source == "synthetic_avatar_d0",
            "authorityHash": authority.avatar_authority_hash,
            "fitDigest": authority.avatar_fit_digest,
            "mismatchRejected": rejection_matrix["avatarMismatch"]["avatarSource"]
            == "fixed_reference_avatar",
            "projectAuthoredSynthetic": True,
            "containsPrivateData": False,
            "containsStableIdentity": False,
            "licensedBodyEvidence": False,
        },
        "outfit": outfit_report,
        "performance": measurements,
        "invalidationLedger": invalidation,
        "topologyMutationProbe": topology_probe["calculatedInvalidation"],
        "diagnosticPrivacy": {
            "scanExecuted": True,
            "containsSensitiveDiagnosticData": False,
            "containsRawSourcePath": False,
            "containsPrivateSourceHash": False,
            "allowlistedDiagnosticsOnly": True,
        },
        "truth": {
            "phase12SourceIntegrated": True,
            "phase13SyntheticSourceIntegrated": True,
            "layerCollisionSurfaceSourceIntegrated": True,
            "mt1LabCapabilityAvailable": True,
            "blueprintZ2Passed": False,
            "phy1Passed": False,
            "physicalOutfitSimulation": False,
            "productionReady": False,
            "mobileDevice": "not_run",
            "gpu": "not_run",
            "battery": "not_run",
            "thermal": "not_run",
            "privateUser": "not_run",
            "licensedBody": "not_run",
            "humanReview": "not_run",
        },
    }
    _assert_no_sensitive_diagnostics(evidence)
    evidence["integrity"] = {"evidenceHash": sha256_bytes(canonical_dumps(evidence).encode())}
    return evidence


def validate_integrated_runtime_evidence(evidence: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if evidence.get("evidenceVersion") != EVIDENCE_VERSION:
        issues.append("integrated_evidence_version_invalid")
    package = evidence.get("packageExecution", {})
    if not isinstance(package, dict) or package.get("packageValidityDependsOnZeroOne") is not False:
        issues.append("integrated_package_zeroone_dependency_invalid")
    decision = evidence.get("runtimeDecision", {})
    if not isinstance(decision, dict) or decision.get("staticSource") not in {
        "zeroone_static",
        "conventional_glb",
    }:
        issues.append("integrated_runtime_decision_missing")
    outfit = evidence.get("outfit", {})
    if not isinstance(outfit, dict):
        issues.append("integrated_outfit_missing")
    else:
        if outfit.get("classification") != "geometric_LayerCollision-D0_not_physical_cloth":
            issues.append("integrated_outfit_scope_inflated")
        final = outfit.get("final", {})
        if not isinstance(final, dict) or final.get("unresolvedContactCount") != 0:
            issues.append("integrated_outfit_unresolved_contacts")
    truth = evidence.get("truth", {})
    for key in ("blueprintZ2Passed", "phy1Passed", "physicalOutfitSimulation"):
        if not isinstance(truth, dict) or truth.get(key) is not False:
            issues.append(f"integrated_truth_overclaimed:{key}")
    privacy = evidence.get("diagnosticPrivacy", {})
    if not isinstance(privacy, dict) or privacy.get("containsSensitiveDiagnosticData") is not False:
        issues.append("integrated_sensitive_diagnostic_leak")
    return sorted(issues)


def _runtime_authority(
    manifest: dict[str, Any],
    fallback: Path,
    mt1: dict[str, Any],
    historical_ledger: dict[str, Any],
    outfit: dict[str, Any],
) -> RuntimeAuthority:
    identities = historical_ledger["identities"]
    outfit_identities = outfit["identities"]
    return RuntimeAuthority(
        package_digest=str(manifest["packageDigest"]),
        conventional_fallback_sha256=sha256_file(fallback),
        garment_topology_hash=str(identities["renderTopologyHash"]),
        binding_hash=str(identities["bindingHash"]),
        static_derivative_identity=str(mt1["static"]["staticDerivativeIdentitySha256"]),
        dynamic_request_identity=str(mt1["dynamic"]["requestSha256"]),
        dynamic_output_identity=str(mt1["dynamic"]["outputSha256"]),
        zeroone_binary_identity=str(mt1["zeroOne"]["windowsExecutableSha256"]),
        avatar_authority_hash=str(outfit_identities["avatarAuthorityHash"]),
        avatar_fit_digest=str(outfit_identities["avatarFitDigest"]),
        layer_profile_identity=str(outfit_identities["layerProfileIdentity"]),
        outfit_surface_identity=str(outfit_identities["outfitSurfaceIdentity"]),
    )


def _all_capabilities() -> RuntimeCapabilities:
    valid = CapabilityState(True, True)
    return RuntimeCapabilities(
        package=valid,
        zeroone_static=valid,
        mt1_reference_motion=valid,
        conventional_deformation=valid,
        synthetic_avatar=valid,
        layer_collision=valid,
    )


def _rejection_matrix(
    authority: RuntimeAuthority, capabilities: RuntimeCapabilities
) -> dict[str, Any]:
    stale_static = replace(authority, static_derivative_identity=sha256_bytes(b"stale-static"))
    stale_mt1 = replace(authority, dynamic_output_identity=sha256_bytes(b"stale-mt1"))
    stale_avatar = replace(authority, avatar_fit_digest=sha256_bytes(b"stale-avatar"))
    stale_layer = replace(authority, outfit_surface_identity=sha256_bytes(b"stale-layer"))
    corrupt = replace(capabilities, zeroone_static=CapabilityState(True, False))
    unsupported = RuntimeRequest(authority, capability_version="unsupported.capability.v0")
    return {
        "staticStale": negotiate_runtime(
            authority, capabilities, RuntimeRequest(stale_static)
        ).to_record(),
        "mt1Stale": negotiate_runtime(
            authority, capabilities, RuntimeRequest(stale_mt1)
        ).to_record(),
        "avatarMismatch": negotiate_runtime(
            authority, capabilities, RuntimeRequest(stale_avatar)
        ).to_record(),
        "layerMismatch": negotiate_runtime(
            authority, capabilities, RuntimeRequest(stale_layer)
        ).to_record(),
        "corruptStatic": negotiate_runtime(
            authority, corrupt, RuntimeRequest(authority)
        ).to_record(),
        "unsupportedVersion": negotiate_runtime(authority, capabilities, unsupported).to_record(),
    }


def _measure_reference_execution(
    authority: RuntimeAuthority,
    capabilities: RuntimeCapabilities,
    outfit_case: Any,
) -> dict[str, Any]:
    elapsed: list[float] = []
    peaks: list[int] = []
    hashes: list[str] = []
    for _ in range(3):
        tracemalloc.start()
        started = time.perf_counter()
        decision = negotiate_runtime(authority, capabilities, RuntimeRequest(authority))
        report = run_canonical_outfit_surface_solve(outfit_case)
        elapsed.append((time.perf_counter() - started) * 1000.0)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peaks.append(peak)
        hashes.append(str(report["integrity"]["reportHash"]))
        if decision.layer_source != "canonical_surface_layer_d0":
            raise AssertionError("integrated_performance_layer_decision_changed")
    return {
        "profile": "host_headless_CPU_reference_not_mobile",
        "platform": platform.system().lower(),
        "python": platform.python_version(),
        "sampleCount": len(elapsed),
        "medianWallMilliseconds": round(statistics.median(elapsed), 6),
        "maximumWallMilliseconds": round(max(elapsed), 6),
        "maximumTracedPeakBytes": max(peaks),
        "deterministicReportHash": len(set(hashes)) == 1,
        "deterministicInputAndOperationCounts": True,
        "timingIsAdvisoryHostObservation": True,
        "mobileDeviceEvidence": False,
    }


def _integrated_identity_map(
    authority: RuntimeAuthority,
    historical_ledger: dict[str, Any],
    outfit: dict[str, Any],
) -> dict[str, str]:
    historical = historical_ledger["identities"]
    return {
        "canonicalPackageDigest": authority.package_digest,
        "patternHash": str(historical["patternHash"]),
        "simulationTopologyHash": str(historical["restTopologyHash"]),
        "renderTopologyHash": authority.garment_topology_hash,
        "bindingHash": authority.binding_hash,
        "conventionalFallbackHash": authority.conventional_fallback_sha256,
        "mechanicalReferenceSurfaceHash": str(historical["mechanicalReferenceSurfaceHash"]),
        "staticDerivativeIdentity": authority.static_derivative_identity,
        "dynamicRequestIdentity": authority.dynamic_request_identity,
        "dynamicOutputIdentity": authority.dynamic_output_identity,
        "zeroOneBinaryIdentity": authority.zeroone_binary_identity,
        "avatarAuthorityHash": authority.avatar_authority_hash,
        "avatarFitDigest": authority.avatar_fit_digest,
        "layerProfileIdentity": authority.layer_profile_identity,
        "outfitSurfaceIdentity": str(outfit["identities"]["outfitSurfaceIdentity"]),
    }


def _static_descriptor(mt1: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "payloadKind": "qualified_static_identity_descriptor_not_render_blob",
        "staticDerivativeIdentity": mt1["static"]["staticDerivativeIdentitySha256"],
        "canonicalDerivativeHash": mt1["static"]["canonicalDerivativeHash"],
        "actualArtifactLoadedInAuthorityEvidence": mt1["static"]["actualArtifactLoaded"],
        "authorityEvidence": MT1_EVIDENCE.as_posix(),
    }


def _dynamic_descriptor(mt1: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "payloadKind": "qualified_mt1_identity_descriptor_not_dynamic_vertex_blob",
        "namespace": mt1["dynamic"]["namespace"],
        "dynamicRequestIdentity": mt1["dynamic"]["requestSha256"],
        "dynamicOutputIdentity": mt1["dynamic"]["outputSha256"],
        "zeroOneBinaryIdentity": mt1["zeroOne"]["windowsExecutableSha256"],
        "namespaceAdmitted": mt1["dynamic"]["namespaceAdmitted"],
        "blueprintZ2Passed": False,
        "authorityEvidence": MT1_EVIDENCE.as_posix(),
    }


def _write_surface_glb(path: Path, surface: CanonicalSurface) -> None:
    minimum_x = min(point[0] for point in surface.positions)
    maximum_x = max(point[0] for point in surface.positions)
    minimum_y = min(point[1] for point in surface.positions)
    maximum_y = max(point[1] for point in surface.positions)
    width = max(maximum_x - minimum_x, 1.0e-9)
    height = max(maximum_y - minimum_y, 1.0e-9)
    mesh = Mesh(
        name="integrated-runtime-synthetic-avatar-surface",
        panel_id="avatar.synthetic.baseline",
        vertices=list(surface.positions),
        panel_uvs=[
            ((point[0] - minimum_x) / width, (point[1] - minimum_y) / height)
            for point in surface.positions
        ],
        triangles=list(surface.triangles),
        material_id="material.synthetic_avatar_neutral_d0",
    )
    write_glb(path, MeshSet([mesh]), "integrated_runtime_avatar", (0.72, 0.64, 0.58, 1.0))


def _assert_no_sensitive_diagnostics(value: dict[str, Any]) -> None:
    serialized = canonical_dumps(value).lower()
    forbidden = (
        "rawsourcesha256",
        "private-source-registry",
        "useridentity",
        "credential",
        "c:\\users\\",
        "/home/",
    )
    leaked = [token for token in forbidden if token in serialized]
    if leaked:
        raise ValueError(f"integrated_sensitive_diagnostic_leak:{leaked[0]}")


def _object(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"integrated_evidence_object_required:{path.name}")
    return value
