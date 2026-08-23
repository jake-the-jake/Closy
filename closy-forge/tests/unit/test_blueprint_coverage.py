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

    assert payload["version"] == "bp46-closeout-proof-invariants-v1"
    assert payload["generatedBy"] == "BP-46 closeout ledger and proof invariant pass"
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
    assert "meshStitchOrWeldExecutionRun=true" in bp46["executableEvidence"]
    assert "meshStitchOrWeldProven=false" in bp46["executableEvidence"]
    assert "non-manifold edges" in bp46["limitations"]
    assert "BP-47" in bp46["nextAction"]


def test_markdown_ledger_matches_bp46_checkpoint_state() -> None:
    ledger = LEDGER_PATH.read_text(encoding="utf-8")

    assert "Latest completed implementation commit when last updated: `81fb02c`" in ledger
    assert "Current active increment: `BP-47-INSPECTION-ARTIFACTS`" in ledger
    assert "Next dependency-ready increment: `BP-47-INSPECTION-ARTIFACTS`" in ledger
    assert "| BP-46-STITCHED-SHELL-OUTPUT | partial |" in ledger
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
