from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from closy_forge.geometry.glb_io import write_glb
from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.integrated_runtime import (
    CandidateRuntimeRequest,
    ExecutionAuthority,
    negotiate_candidate_runtime,
)
from closy_forge.package_io.canonical_json import write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.runtime_delivery import (
    RuntimeCandidateInputs,
    RuntimePackageError,
    build_runtime_candidate_v2,
    load_runtime_candidate_v2,
)


def _digest(label: str) -> str:
    return sha256_bytes(label.encode())


def _source_link() -> dict[str, str]:
    return {
        "opaqueId": "src_public_runtime_v2_fixture",
        "consentScope": "project-authored-public-fixture",
        "retentionPolicy": "fixture-lifetime",
        "deletionPolicy": "managed-withdrawal",
        "derivationPolicy": "portable-authority-projection",
        "withdrawalStatus": "active",
    }


def _write_source_package(root: Path, *, body: bool = False) -> Path:
    package = root / "garment.closygarment"
    files = {
        "avatar/avatar_contract.json": {"contractId": "avatar.fixture"},
        "pattern/pattern.json": {"panels": ["front", "rear"]},
        "semantic/garment_graph.json": {"seams": ["side"], "openings": ["neck"]},
        "simulation/mesh_manifest.json": {
            "coordinateConvention": {"up": "+Y", "front": "+Z"},
            "topologyHash": _digest("simulation-topology"),
        },
        "render/mesh_manifest.json": {
            "coordinateConvention": {"up": "+Y", "front": "+Z"},
            "topologyHash": _digest("render-topology"),
        },
        "binding/production_binding_contract.json": {"records": [0, 1, 2]},
        "textures/pbr_material_maps.json": {"material": "cotton"},
        "reports/fidelity/source_render_fidelity.json": {"status": "fixture"},
    }
    for relative, value in files.items():
        write_canonical_json(package / relative, value)
    panel_id = "avatar.synthetic.body" if body else "panel.front"
    material_id = "material.synthetic_avatar_neutral_d0" if body else "material.cotton"
    mesh = Mesh(
        name="body" if body else "tshirt-front",
        panel_id=panel_id,
        vertices=[(-0.2, 0.8, 0.0), (0.2, 0.8, 0.0), (0.0, 1.2, 0.0)],
        panel_uvs=[(0.0, 0.0), (1.0, 0.0), (0.5, 1.0)],
        triangles=[(0, 1, 2)],
        material_id=material_id,
    )
    write_glb(
        package / "render/fallback.glb",
        MeshSet([mesh]),
        "fixture",
        (0.2, 0.3, 0.4, 1.0),
    )
    canonical_paths = {
        "renderFallback": "render/fallback.glb",
        "pattern": "pattern/pattern.json",
        "semanticGraph": "semantic/garment_graph.json",
        "simulationMeshManifest": "simulation/mesh_manifest.json",
        "renderMeshManifest": "render/mesh_manifest.json",
        "productionBindingContract": "binding/production_binding_contract.json",
        "pbrMaterialMaps": "textures/pbr_material_maps.json",
        "sourceRenderFidelity": "reports/fidelity/source_render_fidelity.json",
    }
    write_canonical_json(
        package / "manifest.json",
        {
            "garmentId": "garment.fixture_tshirt",
            "canonicalPackageDigest": _digest("garment-package"),
            "coordinateConvention": {"up": "+Y", "front": "+Z"},
            "avatar": {
                "path": "avatar/avatar_contract.json",
                "contentHash": sha256_file(package / "avatar/avatar_contract.json"),
            },
            "canonicalPaths": canonical_paths,
            "hashes": {},
        },
    )
    return package


def _write_descriptors(root: Path) -> tuple[Path, Path]:
    static = root / "static.json"
    dynamic = root / "dynamic.json"
    write_canonical_json(
        static,
        {
            "schemaVersion": 2,
            "payloadKind": "qualified_static_identity_descriptor_not_render_blob",
            "staticInputSurfaceIdentity": _digest("static-input"),
        },
    )
    write_canonical_json(
        dynamic,
        {
            "schemaVersion": 2,
            "payloadKind": "qualified_mt1_identity_descriptor_not_dynamic_vertex_blob",
            "zeroOneBinaryIdentity": _digest("binary"),
            "mechanicalReferenceSurfaceIdentity": _digest("mechanical-surface"),
        },
    )
    return static, dynamic


def _build(tmp_path: Path) -> Path:
    static, dynamic = _write_descriptors(tmp_path)
    return build_runtime_candidate_v2(
        tmp_path / "candidate.closyruntime",
        inputs=RuntimeCandidateInputs(
            garment_package=_write_source_package(tmp_path),
            source_link=_source_link(),
            zeroone_static_descriptor=static,
            zeroone_dynamic_descriptor=dynamic,
        ),
    )


def _execution(package: Path) -> ExecutionAuthority:
    loaded = load_runtime_candidate_v2(package)
    authority = loaded.package_authority
    assert authority.zeroone_static_descriptor_identity is not None
    assert authority.static_input_surface_identity is not None
    assert authority.mechanical_reference_surface_identity is not None
    return ExecutionAuthority(
        platform="windows",
        architecture="amd64",
        zeroone_commit="a" * 40,
        executable_sha256=_digest("binary"),
        processor_contract_identity=_digest("processor-contract"),
        candidate_runtime_package_digest=authority.runtime_package_digest,
        static_descriptor_identity=authority.zeroone_static_descriptor_identity,
        static_input_surface_identity=authority.static_input_surface_identity,
        static_request_identity=_digest("static-request"),
        static_output_inventory_identity=_digest("static-output"),
        mechanical_reference_surface_identity=authority.mechanical_reference_surface_identity,
        simulation_topology_hash=authority.simulation_topology_hash,
        render_topology_hash=authority.render_topology_hash,
        binding_hash=authority.binding_hash,
        dynamic_request_identity=_digest("dynamic-request"),
        dynamic_output_inventory_identity=_digest("dynamic-output"),
        execution_attestation_identity=_digest("attestation"),
        static_payload_opened=True,
        dynamic_payload_opened=True,
    )


def test_candidate_loader_derives_authority_and_selects_garment_fallback(
    tmp_path: Path,
) -> None:
    package = _build(tmp_path)
    loaded = load_runtime_candidate_v2(package)

    assert loaded.selected_source == "conventional_garment_glb"
    assert loaded.selected_bytes[:4] == b"glTF"
    assert loaded.descriptor_only is True
    assert loaded.actual_zeroone_payload_loaded is False
    assert loaded.package_authority.garment_id == "garment.fixture_tshirt"
    assert loaded.package_authority.binding_hash == sha256_file(
        package / "canonical/binding_contract.json"
    )


def test_descriptor_only_candidate_cannot_self_admit_zeroone_payload(tmp_path: Path) -> None:
    loaded = load_runtime_candidate_v2(_build(tmp_path))
    decision = negotiate_candidate_runtime(
        loaded.package_authority,
        CandidateRuntimeRequest(
            supports_zeroone_static_payload=True,
            supports_zeroone_dynamic_payload=True,
        ),
    )

    assert decision.render_source == "conventional_garment_glb"
    assert decision.motion_source == "prebaked_static_pose"
    assert decision.optional_capabilities_admitted == ()
    assert decision.descriptor_only is True


def test_actual_joined_execution_can_admit_external_payload(tmp_path: Path) -> None:
    package = _build(tmp_path)
    loaded = load_runtime_candidate_v2(package)
    decision = negotiate_candidate_runtime(
        loaded.package_authority,
        CandidateRuntimeRequest(True, True),
        _execution(package),
    )

    assert decision.render_source == "external_zeroone_static_payload"
    assert decision.motion_source == "external_zeroone_dynamic_payload"
    assert decision.execution_authority_joined is True


@pytest.mark.parametrize(
    "field",
    [
        "candidate_runtime_package_digest",
        "static_descriptor_identity",
        "static_input_surface_identity",
        "mechanical_reference_surface_identity",
        "simulation_topology_hash",
        "render_topology_hash",
        "binding_hash",
        "executable_sha256",
    ],
)
def test_stale_or_cross_package_execution_authority_fails_closed(
    tmp_path: Path, field: str
) -> None:
    package = _build(tmp_path)
    loaded = load_runtime_candidate_v2(package)
    execution = replace(_execution(package), **{field: _digest(f"stale-{field}")})
    decision = negotiate_candidate_runtime(
        loaded.package_authority,
        CandidateRuntimeRequest(True, True),
        execution,
    )

    assert decision.render_source == "conventional_garment_glb"
    assert decision.execution_authority_joined is False
    assert "execution_authority_stale_or_cross_package" in decision.fallback_reasons


def test_modified_fallback_or_authority_artifact_is_rejected(tmp_path: Path) -> None:
    package = _build(tmp_path)
    (package / "assets/conventional_garment.glb").write_bytes(b"changed")
    with pytest.raises(RuntimePackageError, match="runtime_inventory_hash_mismatch"):
        load_runtime_candidate_v2(package)

    other = _build(tmp_path / "other")
    (other / "canonical/pattern.json").write_text('{"changed":true}\n', encoding="utf-8")
    with pytest.raises(RuntimePackageError, match="runtime_inventory_hash_mismatch"):
        load_runtime_candidate_v2(other)


def test_avatar_body_tube_cannot_be_packaged_as_garment_fallback(tmp_path: Path) -> None:
    static, dynamic = _write_descriptors(tmp_path)
    with pytest.raises(RuntimePackageError, match="runtime_fallback_not_canonical_garment"):
        build_runtime_candidate_v2(
            tmp_path / "invalid.closyruntime",
            inputs=RuntimeCandidateInputs(
                garment_package=_write_source_package(tmp_path, body=True),
                source_link=_source_link(),
                zeroone_static_descriptor=static,
                zeroone_dynamic_descriptor=dynamic,
            ),
        )


def test_descriptor_json_masquerading_as_payload_is_rejected(tmp_path: Path) -> None:
    static, dynamic = _write_descriptors(tmp_path)
    static.write_bytes(b"glTF" + b"\x00" * 32)
    with pytest.raises(RuntimePackageError, match="runtime_static_descriptor_invalid"):
        build_runtime_candidate_v2(
            tmp_path / "invalid.closyruntime",
            inputs=RuntimeCandidateInputs(
                garment_package=_write_source_package(tmp_path),
                source_link=_source_link(),
                zeroone_static_descriptor=static,
                zeroone_dynamic_descriptor=dynamic,
            ),
        )
