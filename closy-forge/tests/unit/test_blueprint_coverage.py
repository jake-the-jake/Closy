from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FORGE_ROOT = REPO_ROOT / "closy-forge"
COVERAGE_PATH = FORGE_ROOT / "docs" / "blueprint_coverage.json"
LEDGER_PATH = FORGE_ROOT / "docs" / "MASTER_BLUEPRINT_PROGRESS.md"
ACTIVE_RESUME_PATH = FORGE_ROOT / "docs" / "ACTIVE_BLUEPRINT_RESUME.md"

STATUS_VOCABULARY = {
    "not_started",
    "scaffold",
    "partial",
    "implemented_unverified",
    "complete",
    "discovery_pending",
    "blocked_external",
    "not_applicable",
}
IMPLEMENTED_STATUSES = {
    "scaffold",
    "partial",
    "implemented_unverified",
    "complete",
}
NON_IMPLEMENTED_STATUSES = {
    "not_started",
    "discovery_pending",
    "blocked_external",
    "not_applicable",
}


def _coverage() -> dict:
    return json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))


def _rows() -> list[dict]:
    return _coverage()["rows"]


def test_blueprint_coverage_export_has_required_structure() -> None:
    payload = _coverage()

    assert payload["version"] == "phase6-d0-binding-c3-self-collision-pr7-implementation-v1"
    assert (
        payload["generatedBy"]
        == "Phase 6 scoped D0 binding C3 and self-collision PR #7 implementation evidence"
    )
    assert set(payload["statusVocabulary"]) == STATUS_VOCABULARY
    assert payload["blueprintSha256"] == (
        "AD8ED0088776BEFFE8F1CAB75B7EDEA9C2497FC80146FB74E1686D0C41896A6D"
    )

    rows = _rows()
    ids = [row["id"] for row in rows]
    assert len(ids) == len(set(ids))
    assert len(rows) >= 90

    for row in rows:
        assert row["status"] in STATUS_VOCABULARY
        assert row["sourceSection"]
        assert row["summary"]
        assert row["limitations"]
        assert row["nextAction"]


def test_blueprint_coverage_maps_required_sections() -> None:
    ids = {row["id"] for row in _rows()}

    required_ids = {
        "BP-05-01-PATTERN-FIRST",
        "BP-05-05-TRUTHFUL-EVIDENCE-TIERS",
        "BP-46-STITCHED-SHELL-OUTPUT",
        "BP-47-INSPECTION-ARTIFACTS",
        "BP-48-PERSISTED-FRAMES-TANGENTS",
        "BP-49-RASTER-INGESTION-PRIVACY",
        "BP-50-PIXEL-PARSING-CORRECTIONS",
        "BP-51-MULTIVIEW-CAPTURE-FUSION",
        "BP-52-IMAGE-CONDITIONED-FITTING",
        "BP-53-SOURCE-TEXTURE-PBR-RECOVERY",
        "REPO-HYGIENE-GITLINKS",
        "REPO-HYGIENE-CI-DIAGNOSTICS",
        *(f"BP-07-MODE-{mode}" for mode in "ABCDE"),
        *(
            f"BP-08-{stage}"
            for stage in [
                "A-INGESTION",
                "B-NORMALISATION-QC",
                "C-SEGMENTATION",
                "D-CAMERA-BODY",
                "E-MULTIVIEW-FUSION",
                "F-SEMANTIC-GRAPH",
                "G-PATTERN-REPRESENTATION",
                "H-PATTERN-INFERENCE",
                "I-GEOMETRY-PROVIDERS",
                "J-SIM-MESH-CONSTRUCTION",
                "K-CLOTH-SIMULATION",
                "L-FIT-REFINEMENT",
                "M-MESH-ANALYSIS",
                "N-GARMENT-RETOPOLOGY",
                "O-UV-STRATEGY",
                "P-TEXTURE-PBR",
                "Q-MATERIAL-INFERENCE",
                "R-SIM-TO-RENDER-BINDING",
                "S-LAYERING-ANIMATION",
                "T-HUMAN-CORRECTION",
                "U-QUALITY-PROVENANCE",
            ]
        ),
        *(f"BP-09-Z{index}" for index in range(1, 9)),
        *(f"BP-17-PHASE-{index:02d}" for index in range(15)),
        "BP-18-GATE-C1",
        "BP-18-GATE-C2",
        "BP-18-GATE-C3",
        "BP-18-GATE-Z1",
        "BP-18-GATE-Z2",
        "BP-18-GATE-P1",
        *(f"BP-19-RISK-{index:02d}" for index in range(1, 15)),
        "BP-20-RESEARCH-PROTOTYPE",
        "BP-20-ALPHA",
        "BP-20-BETA",
        "BP-20-PRODUCTION",
        "BP-21-LOCKED-DECISIONS",
    }

    assert required_ids <= ids


def test_implemented_coverage_rows_have_paths_evidence_tests_and_commits() -> None:
    for row in _rows():
        if row["status"] in IMPLEMENTED_STATUSES:
            assert row["implementationPaths"], row["id"]
            assert row["executableEvidence"], row["id"]
            assert row["tests"], row["id"]
            assert row["commitSha"], row["id"]
        elif row["status"] in NON_IMPLEMENTED_STATUSES:
            assert row["implementationPaths"] is None, row["id"]
            assert row["executableEvidence"] is None, row["id"]
            assert row["tests"] is None, row["id"]
            assert row["commitSha"] is None, row["id"]


def test_coverage_commit_references_exist() -> None:
    commit_refs = {commit for row in _rows() for commit in (row["commitSha"] or [])}

    for commit in sorted(commit_refs):
        subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            cwd=REPO_ROOT,
            check=True,
        )


def test_phase_completion_is_not_overclaimed() -> None:
    rows_by_id = {row["id"]: row for row in _rows()}

    assert rows_by_id["BP-17-PHASE-00"]["status"] == "complete"
    for index in range(1, 7):
        assert rows_by_id[f"BP-17-PHASE-{index:02d}"]["status"] == "partial"
    for index in range(7, 10):
        assert rows_by_id[f"BP-17-PHASE-{index:02d}"]["status"] == "not_started"
    for index in (10, 11):
        assert rows_by_id[f"BP-17-PHASE-{index:02d}"]["status"] == "discovery_pending"


def test_bp46_checkpoint_is_partial_and_evidenced() -> None:
    rows_by_id = {row["id"]: row for row in _rows()}
    bp46 = rows_by_id["BP-46-STITCHED-SHELL-OUTPUT"]

    assert bp46["status"] == "partial"
    assert "62443b685604bc4afe9a8fac9f926db78814d5a9" in bp46["commitSha"]
    assert "997232e" in bp46["commitSha"]
    assert "meshStitchOrWeldExecutionRun=true" in bp46["executableEvidence"]
    assert not any(item == "meshStitchOrWeldProven=false" for item in bp46["executableEvidence"])
    assert not any(item == "executedTopologyAuditCount=5" for item in bp46["executableEvidence"])
    assert any("meshStitchOrWeldProven=true" in item for item in bp46["executableEvidence"])
    assert any("status=stitched_shell_proven" in item for item in bp46["executableEvidence"])
    assert any("vertexCount=81" in item for item in bp46["executableEvidence"])
    assert any("triangleCount=120" in item for item in bp46["executableEvidence"])
    assert any("boundaryLoopCount=4" in item for item in bp46["executableEvidence"])
    assert any("simpleBoundaryCycleCount=4" in item for item in bp46["executableEvidence"])
    assert any("nonManifoldEdgeCount=0" in item for item in bp46["executableEvidence"])
    assert any("nonManifoldVertexCount=0" in item for item in bp46["executableEvidence"])
    assert any("boundaryBranchVertexCount=0" in item for item in bp46["executableEvidence"])
    assert any("executedTopologyAuditCount=6" in item for item in bp46["executableEvidence"])
    assert any("surfaceTopologyStatus=pass" in item for item in bp46["executableEvidence"])
    assert any("eulerCharacteristic=-2" in item for item in bp46["executableEvidence"])
    assert any("genus=0" in item for item in bp46["executableEvidence"])
    assert any("vertexLinkStatus=pass" in item for item in bp46["executableEvidence"])
    assert any(
        "semanticOpeningAssignmentStatus=pass" in item for item in bp46["executableEvidence"]
    )
    assert any(
        "opening.neck" in item and "opening.hem" in item and "opening.cuff.left" in item
        for item in bp46["executableEvidence"]
    )
    assert any("bindingCoverage=1.0" in item for item in bp46["executableEvidence"])
    assert any("bindingReconstructionStatus=pass" in item for item in bp46["executableEvidence"])
    assert any(
        "5e5904ad7be00434e8b366823dec4e559da3525feb9e57088f563b7cd713caab" in item
        for item in bp46["executableEvidence"]
    )
    assert any(
        "d22b3d4392ce599ceeff6714eec39bf3d6c543cbeb7ff1a6953a363672b80cb5" in item
        for item in bp46["executableEvidence"]
    )
    assert any("89 physical files" in item for item in bp46["executableEvidence"])
    assert any("85 manifest-inventoried files" in item for item in bp46["executableEvidence"])
    assert any(
        "single_shell_stitch_weld_proof now passes" in item for item in bp46["executableEvidence"]
    )
    assert any("mesh_stitch_or_weld_not_proven" in item for item in bp46["executableEvidence"])
    assert any(
        "remote opening-provenance Actions run 32802914666" in item
        for item in bp46["executableEvidence"]
    )
    assert any("remote Actions run 32777652602" in item for item in bp46["executableEvidence"])
    assert "topology/opening proof now passes" in bp46["limitations"]
    assert "clean/canonical acceptance remains false" in bp46["limitations"]
    assert "production stitched-shell sim-to-render binding" in bp46["limitations"]
    assert "missing panel-edge provenance" not in bp46["limitations"]
    assert "pre-stitch distances still exceed" not in bp46["limitations"]
    assert "non-manifold edges" not in bp46["limitations"]
    assert "failed semantic opening" not in bp46["limitations"]
    assert "winding/normal/self-intersection audit failures" not in bp46["limitations"]
    assert "pre-stitch distance reduction" not in bp46["nextAction"]
    assert "freeze PR #5" in bp46["nextAction"]
    assert "Phase 5 provider branch" in bp46["nextAction"]
    assert "Phase 6 branch" in bp46["nextAction"]


def test_phase5_provider_checkpoint_is_partial_and_evidenced() -> None:
    rows_by_id = {row["id"]: row for row in _rows()}
    phase5 = rows_by_id["BP-17-PHASE-05"]
    providers = rows_by_id["BP-08-I-GEOMETRY-PROVIDERS"]
    model_strategy = rows_by_id["BP-12-MODEL-STRATEGY"]
    licensing = rows_by_id["BP-15-LICENSING"]
    derivative_policy = rows_by_id["BP-05-03-PROVIDER-DERIVATIVE-ONLY"]

    assert phase5["status"] == "partial"
    assert "12322a1eb23e5f0cd8361ecc01be419bbc175364" in phase5["commitSha"]
    assert any(
        "closy.provider_contract.garment_avatar_only.v1" in item
        for item in phase5["executableEvidence"]
    )
    assert any(
        "reports/provider_bakeoff.json status=completed_d0_contract_only_clean_rejected" in item
        for item in phase5["executableEvidence"]
    )
    assert any("providerCount=3" in item for item in phase5["executableEvidence"])
    assert any("executedProviderCount=1" in item for item in phase5["executableEvidence"])
    assert any("notRunProviderCount=2" in item for item in phase5["executableEvidence"])
    assert any("canonicalAcceptedProviderCount=0" in item for item in phase5["executableEvidence"])
    assert any(
        "not_run_missing_runtime_or_weights" in item for item in phase5["executableEvidence"]
    )
    assert any("210 collected Forge tests" in item for item in phase5["executableEvidence"])
    assert any(
        "12b3f768a1916c593574514bb5f5d25a9456415acfddb5e57aadb32381a9bc95" in item
        for item in phase5["executableEvidence"]
    )
    assert "no authorised local/open-model execution" in phase5["limitations"]
    assert "Push and remote-validate" in phase5["nextAction"]
    assert "Phase 6 binding/crack branch" in phase5["nextAction"]

    assert providers["status"] == "partial"
    assert "12322a1eb23e5f0cd8361ecc01be419bbc175364" in providers["commitSha"]
    assert any(
        "closy.geometry_provider_registry.phase5_contract_v2" in item
        for item in providers["executableEvidence"]
    )
    assert any(
        "closy.provider_contract.garment_avatar_only.v1" in item
        for item in providers["executableEvidence"]
    )
    assert any(
        "completed_d0_contract_only_clean_rejected" in item
        for item in providers["executableEvidence"]
    )
    assert any(
        "closy.local_open_model_geometry_adapter.v1" in item
        for item in providers["executableEvidence"]
    )
    assert "No authorised AI/open-model provider execution" in providers["limitations"]
    assert any(
        path.endswith("provider-bakeoff.schema.json") for path in providers["implementationPaths"]
    )
    assert "tests/integration/test_cli_and_package.py" in providers["tests"]

    assert "12322a1eb23e5f0cd8361ecc01be419bbc175364" in model_strategy["commitSha"]
    assert any(
        "provider bakeoff report records no canonical authority" in item
        for item in model_strategy["executableEvidence"]
    )
    assert "No authorised model weights/checkpoint" in model_strategy["limitations"]

    assert "12322a1eb23e5f0cd8361ecc01be419bbc175364" in licensing["commitSha"]
    assert any(
        "license/commercial status not reviewed" in item for item in licensing["executableEvidence"]
    )
    assert "license/SBOM evidence" in licensing["limitations"]

    assert "12322a1eb23e5f0cd8361ecc01be419bbc175364" in derivative_policy["commitSha"]
    assert any(
        "canonicalAcceptedProviderCount=0" in item
        for item in derivative_policy["executableEvidence"]
    )
    assert "does not grant canonical authority" in derivative_policy["limitations"]


def test_repository_gitlink_hygiene_checkpoint_is_complete() -> None:
    rows_by_id = {row["id"]: row for row in _rows()}
    hygiene = rows_by_id["REPO-HYGIENE-GITLINKS"]

    assert hygiene["status"] == "complete"
    assert "e02b85a5f6f2e165c7a0dec2777ff10531048d1b" in hygiene["commitSha"]
    assert "no generated engine _deps/*-src gitlinks" in hygiene["executableEvidence"]
    assert ".gitignore" in hygiene["implementationPaths"]
    assert "tests/unit/test_repository_hygiene.py" in hygiene["tests"]


def test_repository_ci_diagnostics_checkpoint_is_complete() -> None:
    rows_by_id = {row["id"]: row for row in _rows()}
    diagnostics = rows_by_id["REPO-HYGIENE-CI-DIAGNOSTICS"]

    assert diagnostics["status"] == "complete"
    assert "eb4c6113a921037db4f39778f2fa224869fd7d99" in diagnostics["commitSha"]
    assert "closy-forge ci diagnostics command" in diagnostics["executableEvidence"]
    assert ".github/workflows/closy-forge.yml" in diagnostics["implementationPaths"]
    assert "tests/unit/test_ci_sanitized_diagnostics.py" in diagnostics["tests"]


def test_bp47_checkpoint_is_partial_and_evidenced() -> None:
    rows_by_id = {row["id"]: row for row in _rows()}
    bp47 = rows_by_id["BP-47-INSPECTION-ARTIFACTS"]

    assert bp47["status"] == "partial"
    assert "aac1c06" in bp47["commitSha"]
    assert "12 deterministic SVG inspection artifacts" in bp47["executableEvidence"]
    assert "acceptedForVisualFidelity=false" in bp47["executableEvidence"]
    assert (
        "provider/source/human visual fidelity tiers remain not_run" in bp47["executableEvidence"]
    )
    assert "D0-fidelity branch" in bp47["nextAction"]


def test_bp48_checkpoint_is_partial_and_evidenced() -> None:
    rows_by_id = {row["id"]: row for row in _rows()}
    bp48 = rows_by_id["BP-48-PERSISTED-FRAMES-TANGENTS"]

    assert bp48["status"] == "partial"
    assert "0e743bb" in bp48["commitSha"]
    assert "render/fallback.glb contains VEC4 TANGENT accessors" in bp48["executableEvidence"]
    assert "poseSuiteBindingEvidenceAvailable=true" in bp48["executableEvidence"]
    assert "acceptedForCleanProposal=false" in bp48["executableEvidence"]
    assert "Phase 6 branch" in bp48["nextAction"]


def test_bp49_checkpoint_is_partial_and_evidenced() -> None:
    rows_by_id = {row["id"]: row for row in _rows()}
    bp49 = rows_by_id["BP-49-RASTER-INGESTION-PRIVACY"]

    assert bp49["status"] == "partial"
    assert "0db14ee" in bp49["commitSha"]
    assert "fcf64dce8a2117c78df7d1a01f3cefad118b5093" in bp49["commitSha"]
    assert "fixture-only synthetic_fixture_raster_v1 profile" in bp49["executableEvidence"]
    assert (
        "pixel-derived PNG exposure/sharpness/alpha/resolution/framing quality"
        in bp49["executableEvidence"]
    )
    assert any("remote Actions run 32700668662" in item for item in bp49["executableEvidence"])
    assert "tests/unit/test_raster_sources.py" in bp49["tests"]
    assert "BP-51" in bp49["nextAction"]


def test_bp50_checkpoint_is_partial_and_evidenced() -> None:
    rows_by_id = {row["id"]: row for row in _rows()}
    bp50 = rows_by_id["BP-50-PIXEL-PARSING-CORRECTIONS"]
    segmentation = rows_by_id["BP-08-C-SEGMENTATION"]
    correction = rows_by_id["BP-08-T-HUMAN-CORRECTION"]
    phase2 = rows_by_id["BP-17-PHASE-02"]

    assert bp50["status"] == "partial"
    assert "e90a38e" in bp50["commitSha"]
    assert "0da8cea" in bp50["commitSha"]
    assert any("target garment, person/body proxy" in item for item in bp50["executableEvidence"])
    assert any("structured correction replay" in item for item in bp50["executableEvidence"])
    assert any("remote Actions run 32710390547" in item for item in bp50["executableEvidence"])
    assert "tests/unit/test_visual_understanding.py" in bp50["tests"]
    assert "BP-51" in bp50["nextAction"]

    assert "e90a38e" in segmentation["commitSha"]
    assert (
        "closy-forge/src/closy_forge/visual_understanding/raster_parser.py"
        in segmentation["implementationPaths"]
    )
    assert any("16 decoded-pixel masks" in item for item in segmentation["executableEvidence"])
    assert "e90a38e" in correction["commitSha"]
    assert any(
        "non-empty structured correction replay" in item
        for item in correction["executableEvidence"]
    )
    assert "e90a38e" in phase2["commitSha"]
    assert "34023a0" in phase2["commitSha"]
    assert "77bea09" in phase2["commitSha"]
    assert any("BP51 D0 multiview pairing" in item for item in phase2["executableEvidence"])
    assert any("remote Actions run 32719446390" in item for item in phase2["executableEvidence"])
    assert "already consumed by BP52/BP53" in phase2["nextAction"]


def test_bp51_checkpoint_is_partial_and_evidenced() -> None:
    rows_by_id = {row["id"]: row for row in _rows()}
    bp51 = rows_by_id["BP-51-MULTIVIEW-CAPTURE-FUSION"]
    multiview = rows_by_id["BP-08-E-MULTIVIEW-FUSION"]
    correction = rows_by_id["BP-08-T-HUMAN-CORRECTION"]

    assert bp51["status"] == "partial"
    assert "34023a0" in bp51["commitSha"]
    assert "77bea09" in bp51["commitSha"]
    assert any("front/rear required pairing" in item for item in bp51["executableEvidence"])
    assert any("cross-view garment identity" in item for item in bp51["executableEvidence"])
    assert any("fail-closed Phase-2 quality gate" in item for item in bp51["executableEvidence"])
    assert any("fused correction replay" in item for item in bp51["executableEvidence"])
    assert any("185 collected Forge tests" in item for item in bp51["executableEvidence"])
    assert any("remote Actions run 32719446390" in item for item in bp51["executableEvidence"])
    assert (
        "closy-forge/src/closy_forge/visual_understanding/multiview_fusion.py"
        in bp51["implementationPaths"]
    )
    assert "tests/integration/test_cli_and_package.py" in bp51["tests"]
    assert "BP52 fitting" in bp51["nextAction"]

    assert "34023a0" in multiview["commitSha"]
    assert any("D0 anchor/bbox registration" in item for item in multiview["executableEvidence"])
    assert "learned geometric/depth fusion" in multiview["limitations"]
    assert "34023a0" in correction["commitSha"]
    assert any("before/after fusion hashes" in item for item in correction["executableEvidence"])


def test_bp52_checkpoint_is_partial_and_evidenced() -> None:
    rows_by_id = {row["id"]: row for row in _rows()}
    bp52 = rows_by_id["BP-52-IMAGE-CONDITIONED-FITTING"]
    phase3 = rows_by_id["BP-17-PHASE-03"]
    inference = rows_by_id["BP-08-H-PATTERN-INFERENCE"]
    refinement = rows_by_id["BP-08-L-FIT-REFINEMENT"]

    assert bp52["status"] == "partial"
    assert "e23820eddaf6d6599a3b125ee1a083dc97ef4acd" in bp52["commitSha"]
    assert any("hash-links visual observations" in item for item in bp52["executableEvidence"])
    assert any("multiview silhouette IoU 0.939980" in item for item in bp52["executableEvidence"])
    assert any("held-out rear view" in item for item in bp52["executableEvidence"])
    assert any("189 tests" in item for item in bp52["executableEvidence"])
    assert any("85 files each" in item for item in bp52["executableEvidence"])
    assert any(
        "final remote Actions run 32729539416" in item for item in bp52["executableEvidence"]
    )
    assert any("97438405296" in item for item in bp52["executableEvidence"])
    assert any("97438405597" in item for item in bp52["executableEvidence"])
    assert "settled-render or drape comparison" in bp52["limitations"]
    assert "D0-fidelity branch" in bp52["nextAction"]

    assert "e23820e" in phase3["commitSha"]
    assert any("BP52 image-conditioned D0 fitting" in item for item in phase3["executableEvidence"])
    assert "tests/unit/test_tshirt_fit.py" in phase3["tests"]
    assert "e23820e" in inference["commitSha"]
    assert any("priors separated" in item for item in inference["executableEvidence"])
    assert "e23820e" in refinement["commitSha"]
    assert any(
        "iterative D0 optimisation trace" in item for item in refinement["executableEvidence"]
    )


def test_bp53_checkpoint_is_partial_and_evidenced() -> None:
    rows_by_id = {row["id"]: row for row in _rows()}
    bp53 = rows_by_id["BP-53-SOURCE-TEXTURE-PBR-RECOVERY"]
    phase4 = rows_by_id["BP-17-PHASE-04"]
    texture = rows_by_id["BP-08-P-TEXTURE-PBR"]
    risk = rows_by_id["BP-19-RISK-04"]

    assert bp53["status"] == "partial"
    assert "9fc004d429d9187bfd427586ca43af65e54ec2f5" in bp53["commitSha"]
    assert "93f2e6587cc4f5f3237aba669870648a01118a09" in bp53["commitSha"]
    assert any("sourceTextureAvailable=true" in item for item in bp53["executableEvidence"])
    assert any("16 source projections" in item for item in bp53["executableEvidence"])
    assert any("89 files each" in item for item in bp53["executableEvidence"])
    assert any("remote Actions run 32742283522" in item for item in bp53["executableEvidence"])
    assert "private-user source textures" in bp53["limitations"]
    assert "foundation-proof closeout" in bp53["nextAction"]

    assert "9fc004d429d9187bfd427586ca43af65e54ec2f5" in phase4["commitSha"]
    assert any("BP53 D0 source texture identity" in item for item in phase4["executableEvidence"])
    assert "tests/unit/test_texture_identity.py" in phase4["tests"]
    assert "9fc004d429d9187bfd427586ca43af65e54ec2f5" in texture["commitSha"]
    assert any("textureProjectionRun=true" in item for item in texture["executableEvidence"])
    assert "hidden regions remain placeholders" in texture["limitations"]
    assert "9fc004d429d9187bfd427586ca43af65e54ec2f5" in risk["commitSha"]
    assert any("cannot overwrite visible evidence" in item for item in risk["executableEvidence"])


def test_markdown_ledger_matches_phase6_binding_checkpoint_state() -> None:
    ledger = LEDGER_PATH.read_text(encoding="utf-8")

    assert "Branch: `codex/closy-forge-phase-6-binding`" in ledger
    assert "Current active increment: " "`PHASE-6-D0-BINDING-C3-SELF-COLLISION-EVIDENCE`" in ledger
    assert (
        "Next dependency-ready increment: push this evidence-sync head, verify its "
        "Ubuntu/Windows CI if not already verified" in ledger
    )
    assert "a8a053a68d8f455134e5a2bfed0fe340467a039a" in ledger
    assert "PR #7 run `32863864318`" in ledger
    assert "Ubuntu job `97854194246`" in ledger
    assert "Windows job `97854193823`" in ledger
    assert "binding/production_binding_contract.json" in ledger
    assert "reports/production_binding_c3.json" in ledger
    assert "reports/self_collision_report.json" in ledger
    assert "complete_for_d0_fixed_avatar_tshirt_profile" in ledger
    assert "d0_fixed_avatar_tshirt_dense_fallback" in ledger
    assert "motionStateCount=11" in ledger
    assert "max reconstruction error `0.004996001`" in ledger
    assert "max seam crack `0.047774031`" in ledger
    assert "dense/fallback parity `0.0`" in ledger
    assert "global Phase 6/clean/canonical flags false" in ledger
    assert "3598 broad-phase candidate pairs" in ledger
    assert "36 contacts after correction" in ledger
    assert "unsupported_high_velocity_tunnelling" in ledger
    assert "self_collision_unresolved_contacts" in ledger
    assert "full `pytest -q` over 217 collected tests" in ledger
    assert "117 files" in ledger
    assert "92 source files" in ledger
    assert "93-file package trees" in ledger
    assert "e02b5b19450d72f5e74a30d117cbcd7ab45de1451823b22bfa834f3a548a0711" in ledger
    assert "global Phase 6, clean geometry or canonical geometry" in ledger
    assert "reports/provider_bakeoff.json" in ledger
    assert "closy.manual_local_glb_import.v1" in ledger
    assert "No authorised AI/open-model provider execution" in ledger
    assert "| BP-08-I-GEOMETRY-PROVIDERS | partial |" in ledger
    assert "| BP-12-MODEL-STRATEGY | partial |" in ledger
    assert "| BP-14-EVALUATION | partial |" in ledger
    assert "| BP-15-LICENSING | partial |" in ledger
    assert "| BP-17-PHASE-05 | partial |" in ledger
    assert "| BP-20-RESEARCH-PROTOTYPE | partial |" in ledger
    assert "| BP-47-INSPECTION-ARTIFACTS | partial |" in ledger
    assert "| BP-48-PERSISTED-FRAMES-TANGENTS | partial |" in ledger
    assert "| BP-49-RASTER-INGESTION-PRIVACY | partial |" in ledger
    assert "| BP-50-PIXEL-PARSING-CORRECTIONS | partial |" in ledger
    assert "| BP-51-MULTIVIEW-CAPTURE-FUSION | partial |" in ledger
    assert "| BP-52-IMAGE-CONDITIONED-FITTING | partial |" in ledger
    assert "| BP-53-SOURCE-TEXTURE-PBR-RECOVERY | partial |" in ledger
    assert "| BP-18-GATE-C3 | partial |" in ledger
    assert "| REPO-HYGIENE-GITLINKS | complete |" in ledger
    assert "| REPO-HYGIENE-CI-DIAGNOSTICS | complete |" in ledger
    assert "| BP-08-H-PATTERN-INFERENCE | partial |" in ledger
    assert "| BP-08-K-CLOTH-SIMULATION | partial |" in ledger
    assert "| BP-08-R-SIM-TO-RENDER-BINDING | partial |" in ledger


def test_active_resume_points_to_phase6_binding_publish_and_remote_validation() -> None:
    resume = ACTIVE_RESUME_PATH.read_text(encoding="utf-8")

    assert (
        "Active blueprint checkpoint: " "`PHASE-6-D0-BINDING-C3-SELF-COLLISION-EVIDENCE`" in resume
    )
    assert "Current branch: `codex/closy-forge-phase-6-binding`" in resume
    assert "Parent branch / PR target: `codex/closy-forge-phase-5-provider`" in resume
    assert "Phase 6 branch point: `97bf23ccff13e806132b732534d131d80b146467`" in resume
    assert "PR #6 passed GitHub Actions run `32848455025`" in resume
    assert "97803514100" in resume
    assert "97803513678" in resume
    assert "Phase 6 implementation commit: `a8a053a68d8f455134e5a2bfed0fe340467a039a`" in resume
    assert "PR #7 passed GitHub Actions run `32863864318`" in resume
    assert "97854194246" in resume
    assert "97854193823" in resume
    assert "binding/production_binding_contract.json" in resume
    assert "reports/production_binding_c3.json" in resume
    assert "reports/self_collision_report.json" in resume
    assert "complete_for_d0_fixed_avatar_tshirt_profile" in resume
    assert "d0_fixed_avatar_tshirt_dense_fallback" in resume
    assert "motionStateCount=11" in resume
    assert "0.004996001" in resume
    assert "0.047774031" in resume
    assert "3598 candidate pairs" in resume
    assert "36 unresolved D0 reference contacts" in resume
    assert "unsupported_high_velocity_tunnelling" in resume
    assert "217 Forge tests" in resume
    assert "93 physical files each" in resume
    assert "89 manifest-inventoried files" in resume
    assert "e02b5b19450d72f5e74a30d117cbcd7ab45de1451823b22bfa834f3a548a0711" in resume
    assert "12b3f768a1916c593574514bb5f5d25a9456415acfddb5e57aadb32381a9bc95" in resume
    assert "self_collision_not_run" in resume
    assert "self_collision_unresolved_contacts" in resume
    assert "opening-provenance remote-evidence truth-sync update" not in resume
    assert "Commit and push this opening-provenance remote-evidence truth-sync" not in resume
    assert (
        "continue BP-46 conforming stitched-shell topology and semantic opening proof first"
        not in resume
    )
    assert (
        "Remote Ubuntu/Windows CI has not yet run for this BP46 conforming-shell truth-sync update"
        not in resume
    )
    assert "Push this evidence-sync head" in resume
    assert "without creating another self-referential evidence-only commit" in resume


def test_ledger_table_statuses_use_bp46_vocabulary() -> None:
    ledger = LEDGER_PATH.read_text(encoding="utf-8")
    table_statuses = {
        match.group(1)
        for match in re.finditer(r"^\| BP-[^|]+ \| ([^|]+) \|", ledger, flags=re.MULTILINE)
    }

    assert table_statuses <= STATUS_VOCABULARY
    assert "in_progress" not in table_statuses
