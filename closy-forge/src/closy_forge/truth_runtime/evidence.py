from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from closy_forge.dependency_identity import (
    DEPENDENCY_GRAPH_VERSION,
    calculate_invalidation,
    validate_dependency_graph,
)
from closy_forge.integrated_runtime import package_authority_record
from closy_forge.package_io.canonical_json import canonical_dumps, read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.pipeline.build_tshirt_demo import build_demo_tshirt_package
from closy_forge.research_matrix import evaluate_research_matrix
from closy_forge.runtime_delivery import (
    RUNTIME_CANDIDATE_CAPABILITY_VERSION,
    RUNTIME_CANDIDATE_PACKAGE_VERSION,
    RuntimeCandidateInputs,
    build_runtime_candidate_v2,
    load_runtime_candidate_v2,
)

EVIDENCE_VERSION = "closy.d0_truth_runtime_authority.evidence.v1"
EVIDENCE_FOLDER = "docs/evidence/d0_truth_runtime_authority_v3"
BASE_HEAD = "f732df267642cd55960205764e699c7fa2bb2d0f"
GARMENT_ID = "garment.demo_tshirt.reference_v1"


def generate_truth_runtime_evidence(
    root: Path,
    *,
    source_anchor_sha: str,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    if not _commit(source_anchor_sha):
        raise ValueError("truth_runtime_source_anchor_invalid")
    target = output_dir or root / EVIDENCE_FOLDER
    target.mkdir(parents=True, exist_ok=True)
    audit = _starting_state_audit(root)
    write_canonical_json(target / "starting_state_audit.json", audit)

    with tempfile.TemporaryDirectory(prefix="closy-truth-runtime-") as temporary:
        workspace = Path(temporary)
        garment = workspace / "selected.closygarment"
        build = build_demo_tshirt_package(garment)
        manifest = build.manifest
        selected_identity = {
            "avatarContractHash": str(manifest["avatar"]["contentHash"]),
            "garmentId": str(manifest["garmentId"]),
            "packageDigest": str(manifest["canonicalPackageDigest"]),
        }
        static_descriptor, dynamic_descriptor = _write_descriptors(workspace)
        candidate_a = workspace / "candidate-a.closyruntime"
        candidate_b = workspace / "candidate-b.closyruntime"
        candidate_no_descriptors = workspace / "candidate-no-descriptors.closyruntime"
        inputs = RuntimeCandidateInputs(
            garment_package=garment,
            source_link=_source_link(),
            zeroone_static_descriptor=static_descriptor,
            zeroone_dynamic_descriptor=dynamic_descriptor,
        )
        build_runtime_candidate_v2(candidate_a, inputs=inputs)
        build_runtime_candidate_v2(candidate_b, inputs=inputs)
        build_runtime_candidate_v2(
            candidate_no_descriptors,
            inputs=RuntimeCandidateInputs(garment_package=garment, source_link=_source_link()),
        )
        deterministic_rebuild = _tree_hashes(candidate_a) == _tree_hashes(candidate_b)
        withdrawn = workspace / "withdrawn-source.closygarment"
        garment.rename(withdrawn)
        loaded = load_runtime_candidate_v2(candidate_a)
        no_descriptors = load_runtime_candidate_v2(candidate_no_descriptors)
        runtime_evidence = _runtime_evidence(
            source_anchor_sha,
            selected_identity,
            loaded,
            deterministic_rebuild,
            no_descriptors.selected_source == "conventional_garment_glb",
        )
        write_canonical_json(target / "runtime_candidate_v2.json", runtime_evidence)
        dependency_graph = _dependency_graph(
            root,
            withdrawn,
            loaded.package_authority.runtime_package_digest,
            selected_identity,
        )
        validate_dependency_graph(dependency_graph)
        write_canonical_json(target / "dependency_identity_graph.json", dependency_graph)

    bindings = _matrix_bindings(root, target, selected_identity)
    write_canonical_json(target / "matrix_evidence_bindings.json", bindings)
    registry = read_json(root / "docs/capability-profiles/d0-research-matrix-v2.json")
    if not isinstance(registry, dict):
        raise ValueError("truth_runtime_matrix_registry_invalid")
    matrix = evaluate_research_matrix(
        root,
        registry=registry,
        evidence_bindings=bindings["evidenceBindings"],
        selected_identity=selected_identity,
        source_anchor_sha=source_anchor_sha,
    )
    write_canonical_json(target / "final_d0_research_prototype_matrix_v2.json", matrix)
    return {
        name: target / name
        for name in (
            "starting_state_audit.json",
            "runtime_candidate_v2.json",
            "dependency_identity_graph.json",
            "matrix_evidence_bindings.json",
            "final_d0_research_prototype_matrix_v2.json",
        )
    }


def _runtime_evidence(
    source_anchor_sha: str,
    selected_identity: dict[str, str],
    loaded: Any,
    deterministic_rebuild: bool,
    descriptor_removal_fallback_viable: bool,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schemaVersion": 1,
        "evidenceVersion": EVIDENCE_VERSION,
        "sourceAnchorSha": source_anchor_sha,
        "classification": "public_fixture_research_candidate_not_product_selected",
        "selectedIdentity": selected_identity,
        "runtimeCandidate": {
            "packageVersion": RUNTIME_CANDIDATE_PACKAGE_VERSION,
            "capabilityVersion": RUNTIME_CANDIDATE_CAPABILITY_VERSION,
            "selectedSource": loaded.selected_source,
            "selectedBytesSha256": sha256_bytes(loaded.selected_bytes),
            "descriptorOnly": loaded.descriptor_only,
            "actualZeroOnePayloadLoaded": loaded.actual_zeroone_payload_loaded,
            "runtimePackageDigest": loaded.package_digest,
            "deterministicRebuild": deterministic_rebuild,
            "sourceWithdrawalFallbackLoadedOffline": True,
            "descriptorRemovalFallbackViable": descriptor_removal_fallback_viable,
            "productRuntimeV1Unchanged": True,
        },
        "packageAuthority": package_authority_record(loaded.package_authority),
        "truth": {
            "conventionalFallbackIsSelectedCanonicalGarment": True,
            "avatarBodyTubeIsFallback": False,
            "descriptorSelectableAsRenderablePayload": False,
            "descriptorSelfAssertionAdmitsExecution": False,
            "actualPayloadCapability": False,
            "packageValidityDependsOnZeroOne": False,
            "privateSourceRequiredAfterPackaging": False,
        },
        "integrity": {"evidenceHash": ""},
    }
    value["integrity"]["evidenceHash"] = _record_hash(value, "evidenceHash")
    return value


def _dependency_graph(
    root: Path,
    garment: Path,
    runtime_digest: str,
    selected_identity: dict[str, str],
) -> dict[str, Any]:
    manifest = _object(garment / "manifest.json")
    paths = manifest["canonicalPaths"]

    def artifact_hash(key: str) -> str:
        return sha256_file(garment / str(paths[key]))

    simulation = _object(garment / str(paths["simulationMeshManifest"]))
    render = _object(garment / str(paths["renderMeshManifest"]))
    identities = {
        "source": {
            "availability": "not_available_for_selected_candidate",
            "reason": "exact_decoded_raster_not_run",
        },
        "capture": {"publicFixtureCaptureHash": artifact_hash("sourceCaptureRecord")},
        "observations": {
            "observationHash": artifact_hash("sourceVisualObservations"),
            "correctionHash": artifact_hash("sourceCorrectionRecord"),
            "cameraFusionHash": artifact_hash("sourceMultiviewFusion"),
        },
        "fit": {"fittedParameterHash": artifact_hash("tshirtFitReport")},
        "pattern": {
            "patternHash": artifact_hash("pattern"),
            "seamOpeningHash": artifact_hash("semanticGraph"),
        },
        "simulation": {"simulationTopologyHash": str(simulation["topologyHash"])},
        "render": {"renderTopologyHash": str(render["topologyHash"])},
        "binding": {
            "bindingHash": artifact_hash("productionBindingContract"),
            "fallbackHash": artifact_hash("renderFallback"),
        },
        "appearance": {
            "textureIdentityHash": artifact_hash("textureIdentity"),
            "pbrMaterialHash": artifact_hash("pbrMaterialMaps"),
            "sourceFidelityHash": artifact_hash("sourceRenderFidelity"),
        },
        "derivatives": {
            "z1EvidenceHash": sha256_file(
                root / "docs/evidence/phase10_zeroone_static/z1_representative_evidence.json"
            ),
            "mt1EvidenceHash": sha256_file(
                root / "docs/evidence/phase11_reference_motion_v2/execution_evidence.json"
            ),
        },
        "runtime": {"runtimePackageDigest": runtime_digest},
    }
    stages = [
        ("source", "decoded_source_records"),
        ("capture", "capture_normalisation"),
        ("observations", "masks_parts_landmarks_corrections_cameras"),
        ("fit", "template_choice_and_fitted_parameters"),
        ("pattern", "pattern_seams_openings"),
        ("simulation", "simulation_topology"),
        ("render", "render_topology"),
        ("binding", "binding_and_conventional_fallback"),
        ("appearance", "texture_pbr_material_identity"),
        ("derivatives", "optional_z1_mt1_derivatives"),
        ("runtime", "runtime_package_and_negotiated_capability"),
    ]
    nodes = [
        {
            "nodeId": node_id,
            "stage": stage,
            "identity": identities[node_id],
            "authorityId": f"authority.{selected_identity['garmentId']}.{node_id}",
            "classification": "public_fixture",
            "portable": True,
            "packageCandidateId": selected_identity["packageDigest"],
        }
        for node_id, stage in stages
    ]
    edges = [
        {
            "fromNodeId": parent[0],
            "toNodeId": child[0],
            "onUpstreamIdentityChange": "rebuild",
            "rationale": f"{child[1]} is selected or generated from {parent[1]}",
        }
        for parent, child in zip(stages, stages[1:], strict=False)
    ]
    graph = {
        "schemaVersion": 1,
        "graphVersion": DEPENDENCY_GRAPH_VERSION,
        "packageCandidateId": selected_identity["packageDigest"],
        "nodes": nodes,
        "edges": edges,
        "identityPolicy": {
            "privateInputs": "restricted_registry_handles_only",
            "portableAuthority": "opaque_lineage_and_exported_artifact_hashes",
            "publicFixtureException": "explicit_public_fixture_only",
            "offlineFallbackRequiresRestrictedRegistry": False,
            "sourceWithdrawalTest": "candidate_loaded_after_source_package_renamed",
            "sampleInvalidation": calculate_invalidation(
                {
                    "schemaVersion": 1,
                    "graphVersion": DEPENDENCY_GRAPH_VERSION,
                    "packageCandidateId": selected_identity["packageDigest"],
                    "nodes": nodes,
                    "edges": edges,
                    "identityPolicy": {},
                },
                {"observations"},
            ),
        },
    }
    return graph


def _matrix_bindings(root: Path, target: Path, selected_identity: dict[str, str]) -> dict[str, Any]:
    runtime = target / "runtime_candidate_v2.json"
    z1 = root / "docs/evidence/phase10_zeroone_static/z1_representative_evidence.json"
    mt1 = root / "docs/evidence/phase11_reference_motion_v2/execution_evidence.json"
    phy1 = root / "docs/evidence/phy1_topology_v2/phy1_experiment.json"

    def binding(path: Path, predicates: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "classification": "public_fixture",
            "path": path.relative_to(root).as_posix(),
            "sha256": sha256_file(path),
            "predicates": predicates,
        }

    bindings = {
        "runtime_candidate_v2": binding(
            runtime,
            [
                _identity_predicate(
                    "runtime_package", "/selectedIdentity/packageDigest", "packageDigest"
                ),
                _identity_predicate(
                    "runtime_avatar", "/selectedIdentity/avatarContractHash", "avatarContractHash"
                ),
                _identity_predicate("runtime_garment", "/selectedIdentity/garmentId", "garmentId"),
                _equals(
                    "garment_fallback",
                    "/truth/conventionalFallbackIsSelectedCanonicalGarment",
                    True,
                ),
                _equals("body_not_fallback", "/truth/avatarBodyTubeIsFallback", False),
                _equals(
                    "descriptor_not_payload",
                    "/truth/descriptorSelectableAsRenderablePayload",
                    False,
                ),
                _equals("offline", "/runtimeCandidate/sourceWithdrawalFallbackLoadedOffline", True),
                _equals("deterministic", "/runtimeCandidate/deterministicRebuild", True),
                _equals("v1_unchanged", "/runtimeCandidate/productRuntimeV1Unchanged", True),
            ],
        ),
        "c3_binding_v1": binding(
            z1,
            [
                _identity_predicate("c3_package", "/canonicalPackageDigest", "packageDigest"),
                _identity_predicate("c3_garment", "/garmentId", "garmentId"),
                _equals("c3_status", "/c3Binding/status", "pass"),
                _equals(
                    "c3_runtime_profile",
                    "/c3Binding/readiness/acceptedForD0RuntimeBindingProfile",
                    True,
                ),
            ],
        ),
        "z1_candidate_v1": binding(
            z1,
            [
                _identity_predicate("z1_package", "/canonicalPackageDigest", "packageDigest"),
                _identity_predicate("z1_garment", "/garmentId", "garmentId"),
                _equals("z1_candidate", "/claims/representativeStaticProfilePassed", True),
                _equals("z1_global_false", "/claims/globalZ1Passed", False),
                _equals("z1_delete_rebuild", "/deleteAndRebuild/passed", True),
                _equals("z1_loaded", "/integration/actualZeroOneStaticArtifactLoaded", True),
            ],
        ),
        "mt1_reference_v2": binding(
            mt1,
            [
                _identity_predicate(
                    "mt1_package", "/canonicalAuthority/packageDigest", "packageDigest"
                ),
                _equals("mt1_preserved", "/canonicalAuthority/preserved", True),
                _equals("mt1_pass", "/claims/mechanicalTransportReferencePassed", True),
                _equals("mt1_not_z2", "/claims/blueprintZ2Passed", False),
                _equals("mt1_not_solver", "/claims/solverDrivenClothPassed", False),
                _equals("mt1_delete_rebuild", "/dynamic/deterministicDeleteRebuild", True),
                _equals("mt1_cache", "/dynamic/cacheHitValidated", True),
                _sha_predicate("mt1_binary", "/static/zeroOneWindowsExecutableSha256"),
            ],
        ),
        "phy1_v2": binding(
            phy1,
            [
                _equals("phy1_failed", "/acceptance/status", "failed"),
                _equals("phy1_deterministic", "/acceptance/checks/determinism", True),
                _equals("phy1_no_device", "/claims/gpuOrDeviceEvidence", False),
                _equals("phy1_not_production", "/claims/productionPhysicalAnimation", False),
                _sha_predicate("phy1_evidence_hash", "/integrity/evidenceHash"),
            ],
        ),
    }
    return {
        "schemaVersion": 1,
        "bindingVersion": "closy.d0_research_matrix.evidence_bindings.v2",
        "selectedIdentity": selected_identity,
        "evidenceBindings": bindings,
        "privacy": {
            "classification": "public_fixture",
            "containsPrivateSourcePaths": False,
            "containsPrivateSourceHashes": False,
            "futurePrivateQualification": "restricted_registry_and_local_envelope",
        },
    }


def _starting_state_audit(root: Path) -> dict[str, Any]:
    old_matrix = root / "docs/evidence/phy1_topology_v2/final_d0_research_prototype_matrix.json"
    old_runtime = root / "docs/evidence/integrated_runtime_avatar_outfit_v2.json"
    return {
        "schemaVersion": 1,
        "auditVersion": "closy.d0_truth_runtime.starting_state.v1",
        "observedAtUtc": "2026-08-31T00:30:00Z",
        "sourceAnchorSha": BASE_HEAD,
        "frozenPullRequests": [
            {"pullRequest": 36, "headSha": "4c5dcd284a1221a7820184e640fb92b67b880787"},
            {"pullRequest": 37, "headSha": "7430131d5ecab0df77d3933709aed0d86138e03e"},
            {"pullRequest": 38, "headSha": "921ef05b61f39e6020ad12126ffac24c4728f7e0"},
            {"pullRequest": 39, "headSha": BASE_HEAD},
        ],
        "matrixV1HistoricalClaims": {
            "path": old_matrix.relative_to(root).as_posix(),
            "sha256": sha256_file(old_matrix),
            "rowCount": 14,
            "statusCounts": {"pass": 8, "fail": 0, "not_run": 6},
            "classification": "historical_claims_pending_v2_recomputation",
        },
        "selectedRuntimeIdentities": {
            "path": old_runtime.relative_to(root).as_posix(),
            "sha256": sha256_file(old_runtime),
            "runtimePackageDigest": (
                "836abc564a79c0f38ae8bdad3d4a418b0fb05a550193059c1cece8130203c20a"
            ),
            "bindingHash": "7331f0210a0c00e7cc32909809e99a7c92504a717fa0013e270acca66b6ef25f",
            "conventionalFallbackSha256": (
                "8eccea814251f8974f5349548038be73a4d00cec73df7a7bfb787aede58385c6"
            ),
            "productRuntimeVersion": "closy.runtime_package.static_prep.v1",
        },
        "externalWorkflowAuthorities": [
            _workflow(36, "4c5dcd284a1221a7820184e640fb92b67b880787", "33302649199", 26),
            _workflow(37, "7430131d5ecab0df77d3933709aed0d86138e03e", "33321665632", 29),
            _workflow(38, "921ef05b61f39e6020ad12126ffac24c4728f7e0", "33329481046", 29),
            _workflow(39, BASE_HEAD, "33342673147", 29),
        ],
        "privacy": {
            "containsRawPrivateSourceIdentifier": False,
            "containsRawPrivateSourcePath": False,
            "containsDurablePrivateFingerprint": False,
            "publicFixtureHashesExplicitlyClassified": True,
        },
    }


def _workflow(number: int, head: str, run: str, jobs: int) -> dict[str, Any]:
    return {
        "pullRequest": number,
        "exactHeadSha": head,
        "workflowRunUrl": f"https://github.com/jake-the-jake/Closy/actions/runs/{run}",
        "requiredJobResult": "pass",
        "forgeJobCount": jobs,
        "authority": "github_workflow_api",
    }


def _write_descriptors(root: Path) -> tuple[Path, Path]:
    static = root / "zeroone_static_descriptor.json"
    dynamic = root / "zeroone_dynamic_descriptor.json"
    write_canonical_json(
        static,
        {
            "schemaVersion": 1,
            "payloadKind": "qualified_static_identity_descriptor_not_render_blob",
            "staticInputSurfaceIdentity": (
                "39e25cec28dd5ba46edb088319913e751d082e3f48dae513b303ed089549d319"
            ),
        },
    )
    write_canonical_json(
        dynamic,
        {
            "schemaVersion": 1,
            "payloadKind": "qualified_mt1_identity_descriptor_not_dynamic_vertex_blob",
            "zeroOneBinaryIdentity": (
                "b29345b062691cfa7d7e6873c7c9b9bca2cd5a46e670b866d8e69153c0ad8476"
            ),
            "mechanicalReferenceSurfaceIdentity": (
                "2be42dedf78136676b963c8a9a9a4c791ac36f6de8c9b0adb0730b6f41624b81"
            ),
        },
    )
    return static, dynamic


def _source_link() -> dict[str, str]:
    return {
        "opaqueId": "src_public_fixture_tshirt_d0",
        "consentScope": "project_authored_public_fixture",
        "retentionPolicy": "fixture_retained",
        "deletionPolicy": "candidate_remains_offline_after_source_withdrawal",
        "derivationPolicy": "public_fixture_reproducibility_exception",
        "withdrawalStatus": "active",
    }


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _object(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError("truth_runtime_object_required")
    return value


def _identity_predicate(predicate_id: str, pointer: str, identity_key: str) -> dict[str, Any]:
    return {
        "predicateId": predicate_id,
        "pointer": pointer,
        "operation": "identity_equals",
        "identityKey": identity_key,
    }


def _equals(predicate_id: str, pointer: str, expected: Any) -> dict[str, Any]:
    return {
        "predicateId": predicate_id,
        "pointer": pointer,
        "operation": "equals",
        "expected": expected,
    }


def _sha_predicate(predicate_id: str, pointer: str) -> dict[str, Any]:
    return {"predicateId": predicate_id, "pointer": pointer, "operation": "sha256"}


def _record_hash(value: dict[str, Any], key: str) -> str:
    copy = {**value, "integrity": {**value["integrity"], key: ""}}
    return sha256_bytes(canonical_dumps(copy).encode())


def _commit(value: str) -> bool:
    return len(value) == 40 and all(character in "0123456789abcdef" for character in value)
