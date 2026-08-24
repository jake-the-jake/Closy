from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FORGE_ROOT = REPO_ROOT / "closy-forge"
COVERAGE_PATH = FORGE_ROOT / "docs" / "blueprint_coverage.json"
LEDGER_PATH = FORGE_ROOT / "docs" / "MASTER_BLUEPRINT_PROGRESS.md"

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

    assert payload["version"] == "bp46-logical-binding-audit-local-v1"
    assert payload["generatedBy"] == "BP-46 logical binding audit local evidence"
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
    assert "81fb02c" in bp46["commitSha"]
    assert "d0801291ecdaeda4d04ab5897327abcbf9e95ad1" in bp46["commitSha"]
    assert "de35156de35831f467c7809fea727195a548ddce" in bp46["commitSha"]
    assert "eef64ef1ead7adbe7db4132043e388856ed9b513" in bp46["commitSha"]
    assert "0ced19b3efdf69a7ba55cb330c66e8da44a68669" in bp46["commitSha"]
    assert "meshStitchOrWeldExecutionRun=true" in bp46["executableEvidence"]
    assert "meshStitchOrWeldProven=false" in bp46["executableEvidence"]
    assert "executedTopologyAuditCount=5" in bp46["executableEvidence"]
    assert any(
        "winding, normal-inversion and self-intersection" in item
        for item in bp46["executableEvidence"]
    )
    assert any(
        "semanticOpeningAssignmentStatus=fail" in item for item in bp46["executableEvidence"]
    )
    assert any("panelEdgeProvenanceStatus=fail" in item for item in bp46["executableEvidence"])
    assert any(
        "36d766f3b2d3099f54490b3adcc3f34cafb437356bdc1d622ac8bcd486f796c9" in item
        for item in bp46["executableEvidence"]
    )
    assert any("bindingCoverage=1.0" in item for item in bp46["executableEvidence"])
    assert any("bindingReconstructionStatus=pass" in item for item in bp46["executableEvidence"])
    assert any(
        "d808a67ed829388cae96cdf6bdd69b1587a3c59c1bd7a89fc9e3d5efc267ecbb" in item
        for item in bp46["executableEvidence"]
    )
    assert any("193 collected Forge tests" in item for item in bp46["executableEvidence"])
    assert any("89 files each" in item for item in bp46["executableEvidence"])
    assert any("remote Actions run 32761608825" in item for item in bp46["executableEvidence"])
    assert any("97541503765" in item for item in bp46["executableEvidence"])
    assert any("97541503927" in item for item in bp46["executableEvidence"])
    assert "non-manifold edges" in bp46["limitations"]
    assert "not-run topology audits" not in bp46["limitations"]
    assert "incomplete binding coverage" not in bp46["limitations"]
    assert "semantic opening proof" in bp46["nextAction"]


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
    assert "BP-48" in bp47["nextAction"]


def test_bp48_checkpoint_is_partial_and_evidenced() -> None:
    rows_by_id = {row["id"]: row for row in _rows()}
    bp48 = rows_by_id["BP-48-PERSISTED-FRAMES-TANGENTS"]

    assert bp48["status"] == "partial"
    assert "0e743bb" in bp48["commitSha"]
    assert "render/fallback.glb contains VEC4 TANGENT accessors" in bp48["executableEvidence"]
    assert "poseSuiteBindingEvidenceAvailable=true" in bp48["executableEvidence"]
    assert "acceptedForCleanProposal=false" in bp48["executableEvidence"]
    assert "BP-49" in bp48["nextAction"]


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
    assert "BP-52" in phase2["nextAction"]


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
    assert any("remote Actions run 32728354755" in item for item in bp52["executableEvidence"])
    assert "settled-render or drape comparison" in bp52["limitations"]
    assert "BP-53" in bp52["nextAction"]

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


def test_markdown_ledger_matches_foundation_proof_checkpoint_state() -> None:
    ledger = LEDGER_PATH.read_text(encoding="utf-8")

    assert "Latest completed implementation commit when last updated: `0ced19b`" in ledger
    assert "executedTopologyAuditCount=5" in ledger
    assert "semanticOpeningAssignmentStatus=fail" in ledger
    assert "boundaryComponentCount=3" in ledger
    assert "bindingCoverage=1.0" in ledger
    assert "bindingReconstructionStatus=pass" in ledger
    assert "d808a67ed829388cae96cdf6bdd69b1587a3c59c1bd7a89fc9e3d5efc267ecbb" in ledger
    assert (
        "Current active increment: `FOUNDATION-PROOF-CLOSEOUT-BP46-LOGICAL-BINDING-AUDIT`" in ledger
    )
    assert "Next dependency-ready increment: continue `FOUNDATION-PROOF-CLOSEOUT`" in ledger
    assert "| BP-46-STITCHED-SHELL-OUTPUT | partial |" in ledger
    assert "| BP-47-INSPECTION-ARTIFACTS | partial |" in ledger
    assert "| BP-48-PERSISTED-FRAMES-TANGENTS | partial |" in ledger
    assert "| BP-49-RASTER-INGESTION-PRIVACY | partial |" in ledger
    assert "| BP-50-PIXEL-PARSING-CORRECTIONS | partial |" in ledger
    assert "| BP-51-MULTIVIEW-CAPTURE-FUSION | partial |" in ledger
    assert "| BP-52-IMAGE-CONDITIONED-FITTING | partial |" in ledger
    assert "| BP-53-SOURCE-TEXTURE-PBR-RECOVERY | partial |" in ledger
    assert "| REPO-HYGIENE-GITLINKS | complete |" in ledger
    assert "| REPO-HYGIENE-CI-DIAGNOSTICS | complete |" in ledger
    assert "| BP-08-H-PATTERN-INFERENCE | partial |" in ledger
    assert "| BP-08-K-CLOTH-SIMULATION | partial |" in ledger
    assert "| BP-08-R-SIM-TO-RENDER-BINDING | partial |" in ledger


def test_ledger_table_statuses_use_bp46_vocabulary() -> None:
    ledger = LEDGER_PATH.read_text(encoding="utf-8")
    table_statuses = {
        match.group(1)
        for match in re.finditer(r"^\| BP-[^|]+ \| ([^|]+) \|", ledger, flags=re.MULTILINE)
    }

    assert table_statuses <= STATUS_VOCABULARY
    assert "in_progress" not in table_statuses
