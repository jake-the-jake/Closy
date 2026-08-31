from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from shutil import copytree
from typing import Any

import pytest

from closy_forge.binding.binary_format import read_binding, write_binding
from closy_forge.evidence_integrity_v4 import (
    AuthorityAuditError,
    MatrixV3Error,
    append_attempt,
    audit_candidate_package,
    audit_raster_semantics_v4,
    evaluate_phy1_trajectory_diagnostic_v4,
    evaluate_research_matrix_v3,
    validate_attempt_registry,
    validate_execution_authority,
)
from closy_forge.evidence_integrity_v4.matrix_v3 import (
    ATTEMPT_REGISTRY_VERSION,
    canonical_artifact_sha256,
    document_hash,
)
from closy_forge.evidence_integrity_v4.phy_evaluator_v4 import evaluate_phy_microfixtures_v4
from closy_forge.fitting.exact_d0_candidate import inventory_digest
from closy_forge.geometry.glb_io import read_glb_meshset, write_glb
from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.package_io.canonical_json import read_json, write_canonical_json
from closy_forge.package_io.hashing import (
    geometry_content_hash,
    sha256_bytes,
    sha256_file,
    topology_hash,
)
from scripts.generate_d0_evidence_integrity_v4 import generate

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/d0_evidence_integrity_v4"
PACKAGE = ROOT / "docs/evidence/d0_fitting_pbr_fidelity_v2/predictions/candidate_package"


def _object(path: Path) -> dict[str, Any]:
    value = read_json(path)
    assert isinstance(value, dict)
    return value


def _digest(label: str) -> str:
    return sha256_bytes(label.encode())


def _profile() -> dict[str, Any]:
    return {
        "schemaVersion": 3,
        "registryId": "fixture.v3",
        "rows": [
            {
                "rowId": "D0-RP-07",
                "scope": "exact_fixture_candidate",
                "requirement": "failed texture fixture",
                "decisionGroup": "research_prototype_core",
                "summaryClass": "core",
                "requiredForResearchPrototype": True,
                "thresholdRegistryRef": "fixture.threshold",
                "requiredEvidenceIds": ["failed"],
            }
        ],
        "scopedAuthorities": [{"scope": "exact_fixture_candidate", "authority": "fixture"}],
    }


def _context(label: str = "candidate") -> dict[str, str]:
    return {
        "candidateId": f"candidate.{label}",
        "packageDigest": _digest(f"package-{label}"),
        "avatarContractHash": _digest(f"avatar-{label}"),
        "garmentId": "garment.fixture",
        "patternHash": _digest(f"pattern-{label}"),
        "simulationTopologyHash": _digest(f"sim-{label}"),
        "renderTopologyHash": _digest(f"render-{label}"),
        "bindingHash": _digest(f"binding-{label}"),
    }


def _registry(context_hash: str, state: str = "attempted_fail") -> dict[str, Any]:
    value: dict[str, Any] = {
        "schemaVersion": 3,
        "registryVersion": ATTEMPT_REGISTRY_VERSION,
        "appendOnly": True,
        "records": [],
        "recordCount": 0,
        "headHash": "0" * 64,
    }
    append_attempt(
        value,
        attempt_id="attempt.fixture.1",
        lineage_id="lineage.fixture",
        row_id="D0-RP-07",
        scope="exact_fixture_candidate",
        candidate_identity_hash=context_hash,
        attempt_state=state,  # type: ignore[arg-type]
        reason_code="historical_failure",
        evidence_ids=["failed"],
    )
    return value


def _binding(path: Path) -> dict[str, Any]:
    return {
        "classification": "public_fixture",
        "path": path.name,
        "sha256": canonical_artifact_sha256(path),
        "predicates": [
            {
                "predicateId": "must_pass",
                "pointer": "/status",
                "operation": "equals",
                "expected": "pass",
            }
        ],
    }


def _evaluate(tmp_path: Path, registry: dict[str, Any], binding: dict[str, Any]) -> dict[str, Any]:
    context = _context()
    return evaluate_research_matrix_v3(
        tmp_path,
        profile=_profile(),
        bindings={"failed": binding},
        attempt_registry=registry,
        selected_context=context,
        evidence_source_anchor_sha="a" * 40,
        externally_attested_head_sha="b" * 40,
    )


def test_committed_unit_e_evidence_regenerates_byte_identically() -> None:
    before = {
        path.relative_to(ROOT).as_posix(): sha256_file(path)
        for path in EVIDENCE.rglob("*")
        if path.is_file()
    }
    generate(ROOT)
    after = {
        path.relative_to(ROOT).as_posix(): sha256_file(path)
        for path in EVIDENCE.rglob("*")
        if path.is_file()
    }
    assert before == after


def test_v3_matrix_separates_core_supplemental_and_resets_disputed_claims() -> None:
    matrix = _object(EVIDENCE / "final_d0_research_prototype_matrix_v3.json")
    by_id = {row["rowId"]: row for row in matrix["rows"]}
    assert matrix["summaries"]["core"]["rowCount"] == 11
    assert matrix["summaries"]["supplemental"]["rowCount"] == 4
    assert by_id["D0-RP-03"]["attemptState"] == "attempted_fail"
    assert by_id["D0-RP-04"]["attemptState"] == "attempted_integrity_error"
    assert by_id["D0-RP-06"]["resultStatus"] == "pass"
    assert by_id["D0-RP-07"]["resultStatus"] == "fail"
    assert by_id["D0-RP-12"]["requiredEvidenceIds"] == ["delete_rebuild"]
    assert by_id["D0-RP-13"]["requiredEvidenceIds"] == [
        "package_authority",
        "external_authority",
    ]
    assert by_id["D0-RP-15"]["resultStatus"] == "fail"


def test_attempt_history_is_hash_chained_monotonic_and_cannot_be_erased() -> None:
    registry = _object(EVIDENCE / "attempt_registry_v3.json")
    validate_attempt_registry(registry)
    corrupt = deepcopy(registry)
    del corrupt["records"][5]
    corrupt["recordCount"] -= 1
    with pytest.raises(MatrixV3Error):
        validate_attempt_registry(corrupt)
    corrupt = deepcopy(registry)
    corrupt["records"][0]["attemptState"] = "never_attempted"
    with pytest.raises(MatrixV3Error):
        validate_attempt_registry(corrupt)


def test_tombstone_is_append_only_and_rejects_unknown_or_duplicate_target() -> None:
    context_hash = document_hash(_context())
    registry = _registry(context_hash)
    append_attempt(
        registry,
        attempt_id="attempt.fixture.tombstone",
        lineage_id="lineage.fixture",
        row_id="D0-RP-07",
        scope="exact_fixture_candidate",
        candidate_identity_hash=context_hash,
        attempt_state="attempted_integrity_error",
        reason_code="artifact_invalidated",
        evidence_ids=["failed"],
        invalidates_attempt_id="attempt.fixture.1",
    )
    validate_attempt_registry(registry)
    registry["records"][-1]["invalidatesAttemptId"] = "missing"
    registry["records"][-1]["recordHash"] = document_hash(
        {**registry["records"][-1], "recordHash": ""}
    )
    registry["headHash"] = registry["records"][-1]["recordHash"]
    with pytest.raises(MatrixV3Error, match="tombstone"):
        validate_attempt_registry(registry)


def test_deleted_failed_evidence_stays_fail_instead_of_improving_to_not_run(tmp_path: Path) -> None:
    evidence = tmp_path / "failed.json"
    write_canonical_json(evidence, {"status": "fail"})
    binding = _binding(evidence)
    registry = _registry(document_hash(_context()))
    evidence.unlink()
    matrix = _evaluate(tmp_path, registry, binding)
    row = matrix["rows"][0]
    assert row["resultStatus"] == "fail"
    assert row["openedArtifactInventory"][0]["openAttempted"] is True
    assert "evidence_artifact_missing:failed" in row["reasonCodes"]


def test_mutating_failed_summary_to_pass_without_reauthoring_bytes_is_rejected(
    tmp_path: Path,
) -> None:
    evidence = tmp_path / "failed.json"
    write_canonical_json(evidence, {"status": "fail", "underlyingMetric": 1.0})
    binding = _binding(evidence)
    write_canonical_json(evidence, {"status": "pass", "underlyingMetric": 1.0})
    matrix = _evaluate(tmp_path, _registry(document_hash(_context())), binding)
    row = matrix["rows"][0]
    assert row["resultStatus"] == "fail"
    assert "evidence_artifact_hash_mismatch:failed" in row["reasonCodes"]


def test_attempted_pass_with_current_failed_predicate_fails_closed(tmp_path: Path) -> None:
    evidence = tmp_path / "failed.json"
    write_canonical_json(evidence, {"status": "fail"})
    matrix = _evaluate(
        tmp_path,
        _registry(document_hash(_context()), "attempted_pass"),
        _binding(evidence),
    )
    assert matrix["rows"][0]["resultStatus"] == "fail"
    assert matrix["rows"][0]["firstUnmetPredicate"] == "must_pass"


def test_changing_candidate_identity_requires_a_new_attempt_lineage(tmp_path: Path) -> None:
    evidence = tmp_path / "failed.json"
    write_canonical_json(evidence, {"status": "fail"})
    registry = _registry(document_hash(_context("predecessor")))
    with pytest.raises(MatrixV3Error, match="lineage_missing"):
        _evaluate(tmp_path, registry, _binding(evidence))


def test_exact_candidate_package_opens_every_authority_and_recomputes_digest() -> None:
    audit = audit_candidate_package(PACKAGE)
    assert audit["status"] == "pass"
    assert audit["inventoryDigestRecomputedFromOpenedBytes"] is True
    assert all(audit["semanticAuthorities"].values())
    assert audit["fallback"]["panelIds"] == [
        "panel.back",
        "panel.front",
        "panel.neck_band",
        "panel.sleeve.left",
        "panel.sleeve.right",
    ]


@pytest.mark.parametrize(
    ("relative", "expected"),
    [
        ("pattern/pattern.json", "candidate_inventory_hash_mismatch"),
        ("simulation/constraints.json", "candidate_inventory_hash_mismatch"),
        ("simulation/topology_manifest.json", "candidate_inventory_hash_mismatch"),
        ("simulation/rest_mesh.glb", "candidate_inventory_hash_mismatch"),
        ("render/render_mesh.glb", "candidate_inventory_hash_mismatch"),
        ("binding/sim_to_render.bin", "candidate_inventory_hash_mismatch"),
        ("textures/bitmap_pbr_report.json", "candidate_inventory_hash_mismatch"),
    ],
)
def test_swapped_canonical_authority_bytes_fail_closed(
    tmp_path: Path, relative: str, expected: str
) -> None:
    package = tmp_path / "candidate"
    copytree(PACKAGE, package)
    path = package / relative
    path.write_bytes(path.read_bytes() + b"corrupt")
    with pytest.raises(AuthorityAuditError, match=expected):
        audit_candidate_package(package)


def test_forged_package_digest_and_wrong_hash_table_entry_are_rejected(tmp_path: Path) -> None:
    package = tmp_path / "candidate"
    copytree(PACKAGE, package)
    manifest = _object(package / "candidate_manifest.json")
    manifest["packageDigest"] = _digest("forged")
    write_canonical_json(package / "candidate_manifest.json", manifest)
    with pytest.raises(AuthorityAuditError, match="package_digest"):
        audit_candidate_package(package)

    package = tmp_path / "candidate-hash"
    copytree(PACKAGE, package)
    manifest = _object(package / "candidate_manifest.json")
    manifest["inventory"][0]["sha256"] = _digest("wrong")
    write_canonical_json(package / "candidate_manifest.json", manifest)
    with pytest.raises(AuthorityAuditError, match="inventory_hash"):
        audit_candidate_package(package)


def test_avatar_body_fallback_is_rejected_even_when_inventory_is_reauthorised(
    tmp_path: Path,
) -> None:
    package = tmp_path / "candidate"
    copytree(PACKAGE, package)
    mesh = Mesh(
        name="body",
        panel_id="avatar.synthetic.body",
        vertices=[(-0.2, 0.8, 0.0), (0.2, 0.8, 0.0), (0.0, 1.4, 0.1)],
        panel_uvs=[(0.0, 0.0), (1.0, 0.0), (0.5, 1.0)],
        triangles=[(0, 1, 2)],
        material_id="material.synthetic_avatar",
    )
    write_glb(package / "render/render_mesh.glb", MeshSet([mesh]), "body", (0.5, 0.5, 0.5, 1.0))
    _reauthor_render(package)
    with pytest.raises(AuthorityAuditError, match="fallback_not_garment"):
        audit_candidate_package(package)


def test_out_of_frame_and_coordinate_axis_fallbacks_are_rejected(tmp_path: Path) -> None:
    for mode, expected in (("translate", "out_of_frame"), ("axis", "coordinate_convention")):
        package = tmp_path / mode
        copytree(PACKAGE, package)
        source = read_glb_meshset(package / "render/render_mesh.glb")
        meshes = []
        for mesh in source.meshes:
            vertices = [
                (x + 5.0, y, z) if mode == "translate" else (x, z + 1.0, y - 1.0)
                for x, y, z in mesh.vertices
            ]
            meshes.append(
                Mesh(
                    mesh.name,
                    mesh.panel_id,
                    vertices,
                    mesh.panel_uvs,
                    mesh.triangles,
                    mesh.material_id,
                )
            )
        write_glb(
            package / "render/render_mesh.glb", MeshSet(meshes), "corrupt", (0.2, 0.3, 0.4, 1.0)
        )
        _reauthor_render(package)
        with pytest.raises(AuthorityAuditError, match=expected):
            audit_candidate_package(package)


def test_wrong_material_slot_is_rejected_after_reauthorised_inventory(tmp_path: Path) -> None:
    package = tmp_path / "candidate"
    copytree(PACKAGE, package)
    report = _object(package / "textures/bitmap_pbr_report.json")
    report["maps"] = [item for item in report["maps"] if item["mapId"] != "normal"]
    write_canonical_json(package / "textures/bitmap_pbr_report.json", report)
    _reauthor_inventory(package)
    with pytest.raises(AuthorityAuditError, match="material_slot_missing"):
        audit_candidate_package(package)


@pytest.mark.parametrize(
    "field",
    [
        "platform",
        "architecture",
        "zeroOneCommit",
        "processorContractSha256",
        "executableSha256",
    ],
)
def test_wrong_externally_pinned_execution_identity_is_rejected(field: str) -> None:
    supplied, trusted, candidate = _execution()
    supplied[field] = "linux" if field in {"platform", "architecture"} else _digest(field)
    with pytest.raises(AuthorityAuditError, match="execution_authority_mismatch"):
        validate_execution_authority(supplied, trusted=trusted, candidate=candidate)


@pytest.mark.parametrize(
    "field",
    [
        "requestInventorySha256",
        "outputInventorySha256",
        "executionAttestationSha256",
        "candidatePackageDigest",
    ],
)
def test_wrong_execution_request_output_attestation_or_candidate_is_rejected(field: str) -> None:
    supplied, trusted, candidate = _execution()
    supplied[field] = _digest(f"wrong-{field}")
    expected = "candidate_mismatch" if field == "candidatePackageDigest" else "digest_invalid"
    if field != "candidatePackageDigest":
        supplied[field] = "not-a-digest"
    with pytest.raises(AuthorityAuditError, match=expected):
        validate_execution_authority(supplied, trusted=trusted, candidate=candidate)


def test_duplicate_execution_attestation_and_descriptor_only_state() -> None:
    supplied, trusted, candidate = _execution()
    seen: set[str] = set()
    assert (
        validate_execution_authority(
            supplied, trusted=trusted, candidate=candidate, seen_attestation_ids=seen
        )["status"]
        == "pass"
    )
    with pytest.raises(AuthorityAuditError, match="duplicate"):
        validate_execution_authority(
            supplied, trusted=trusted, candidate=candidate, seen_attestation_ids=seen
        )
    blocked = validate_execution_authority(None, trusted=trusted, candidate=candidate)
    assert blocked["status"] == "not_run"
    assert blocked["corePackageAuthorityValid"] is True


def test_raster_semantics_keep_raw_focus_distinct_and_generated_fill_score_neutral() -> None:
    report = audit_raster_semantics_v4(
        PACKAGE,
        exact_texture_evaluation=ROOT
        / "docs/evidence/d0_fitting_pbr_fidelity_v2/evaluation"
        / "exact_texture_rerender_evaluation.json",
        exact_reference_evaluation=ROOT
        / "docs/evidence/d0_fitting_pbr_fidelity_v2/evaluation/exact_reference_3d_evaluation.json",
    )
    assert report["status"] == "pass"
    assert report["scaleConfidence"]["status"] == "unavailable"
    assert report["sourceFidelityColor"]["generatedFillScoreDelta"] == 0.0
    assert report["sourceFidelityColor"]["generatedFillCannotImproveScore"] is True
    assert len(report["contributionProvenance"]["perView"]) == 2
    assert report["physicalPbrAccuracy"] == "not_measured"
    for view in report["sourceViewQuality"]:
        assert view["rawLaplacianVariance8BitSquared"] != view["normalizedFocus"]


def test_phy_v4_microfixtures_and_pr43_rescore_are_diagnostic_only() -> None:
    micro = evaluate_phy_microfixtures_v4()
    report = evaluate_phy1_trajectory_diagnostic_v4(ROOT)
    assert micro["status"] == "pass"
    assert report["historicalOutcomeAuthority"]["predecessorOutcomeUnchanged"] is True
    assert report["historicalOutcomeAuthority"]["physicalCandidateReran"] is False
    assert report["historicalOutcomeAuthority"]["budgetConsumed"] is False
    assert report["independentRepeat"]["status"] == "historical_only_not_re_evaluable"
    assert len(report["tailFrameMetrics"]) == 8
    assert report["collisionExclusions"]["stitchedNeighbourhoodExclusionRings"] == 1
    assert report["supports"]["status"] == "not_available"
    assert report["supportRelease"]["offByOneResolved"] is True


def test_external_exact_head_authority_has_full_linear_pr_dag_and_29_forge_jobs() -> None:
    authority = _object(EVIDENCE / "external_exact_head_authority.json")
    assert authority["evidenceSourceAnchor"] == "fe8f6d8a6d08e4c1b75a838728d66fea5d2c92c0"
    assert authority["finalPublishedHead"] == "6aee5ed3b2753ee99c95abdef6f5a24be39b3a7e"
    assert [record["pullRequest"] for record in authority["prDag"]] == [39, 40, 41, 42, 43]
    assert all(record["forgeJobCount"] == 29 for record in authority["prDag"])
    assert all(record["mergeBaseEqualsBase"] for record in authority["prDag"])


def _reauthor_render(package: Path) -> None:
    manifest = _object(package / "candidate_manifest.json")
    render = read_glb_meshset(package / "render/render_mesh.glb")
    manifest["identityGraph"]["renderTopologyHash"] = topology_hash(render)
    manifest["identityGraph"]["renderContentHash"] = geometry_content_hash(render)
    binding_path = package / "binding/sim_to_render.bin"
    binding = read_binding(binding_path)
    write_binding(
        binding_path,
        replace(binding, render_topology_hash=manifest["identityGraph"]["renderTopologyHash"]),
    )
    _reauthor_inventory(package, manifest)


def _reauthor_inventory(package: Path, manifest: dict[str, Any] | None = None) -> None:
    active = manifest or _object(package / "candidate_manifest.json")
    inventory = []
    for raw in active["inventory"]:
        path = package / raw["path"]
        inventory.append(
            {
                "path": raw["path"],
                "byteLength": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    active["inventory"] = inventory
    active["packageDigest"] = inventory_digest(inventory)
    active["identityGraph"]["packageDigest"] = active["packageDigest"]
    write_canonical_json(package / "candidate_manifest.json", active)


def _execution() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    trusted = {
        "platform": "windows",
        "architecture": "amd64",
        "zeroOneCommit": "a" * 40,
        "processorContractSha256": _digest("contract"),
        "executableSha256": _digest("executable"),
    }
    candidate = {"packageDigest": _digest("candidate")}
    supplied = {
        **trusted,
        "requestInventorySha256": _digest("request"),
        "outputInventorySha256": _digest("output"),
        "executionAttestationSha256": _digest("attestation"),
        "candidatePackageDigest": candidate["packageDigest"],
    }
    return supplied, trusted, candidate
