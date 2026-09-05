from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path
from typing import Any

import pytest

from closy_forge.blueprint_progress_v3 import build_requirement_inventory, parse_source_blocks
from closy_forge.blueprint_progress_v3.checkpoint import (
    BLUEPRINT_PATH,
    phase_overview,
    render_phase_table,
)
from closy_forge.blueprint_progress_v3.crosswalk import build_migration_crosswalk

ROOT = Path(__file__).resolve().parents[2]


def inventory(text: str, **kwargs: Any) -> dict[str, Any]:
    return build_requirement_inventory(text, source_blob_oid="fixture-blob", **kwargs)


@pytest.mark.parametrize("phase", range(15))
def test_phase_is_nearest_explicit_heading_not_outer_section(phase: int) -> None:
    row = inventory(
        f"# Blueprint\n## 17. Roadmap\n### Phase {phase} - Topic\n"
        "##### Deep subheading\nDeliver:\n\n- simulation mesh;\n"
    )["requirements"][0]
    assert row["roadmapPhase"] == phase
    assert row["sourceSection"] == "17"
    assert row["roadmapPhases"] == [phase]


def test_nearest_phase_wins_and_sibling_heading_resets_scope() -> None:
    rows = inventory(
        "## 17. Roadmap\n### Phase 8 - Families\n#### Phase 6 - Binding\n"
        "- Must retain offsets.\n## 8. Other section\n- Must preserve semantics."
    )["requirements"]
    assert rows[0]["roadmapPhase"] == 6
    assert rows[1]["roadmapPhase"] is None
    assert rows[1]["sourceSection"] == "8"
    assert rows[1]["mappingKind"] == "cross_cutting"


@pytest.mark.parametrize(
    "label",
    [
        "Deliver:",
        "**Required:**",
        "Requirements:",
        "Acceptance criteria:",
        "Required before high-res animation:",
        "Record:",
        "The output should include:",
        "The package must retain the following.",
        "The subsystem processes garments. It owns:",
        "Only after the prerequisites have passed:",
    ],
)
def test_noun_bullets_inherit_requirement_introducer(label: str) -> None:
    rows = inventory(f"## Phase 13 - Outfits\n{label}\n\n- multiple garment collision layers;")
    noun = next(row for row in rows["requirements"] if "collision layers" in row["rawText"])
    assert noun["classificationReason"] == "inherited_requirement_context"
    assert noun["contextBlockId"] is not None
    assert noun["roadmapPhase"] == 13


@pytest.mark.parametrize("heading", ["Acceptance criteria", "18.2 Acceptance criteria", "Required"])
def test_noun_bullets_under_acceptance_heading(heading: str) -> None:
    rows = inventory(f"## {heading}\n### Geometry\n- positive triangle area;")["requirements"]
    assert len(rows) == 1
    assert rows[0]["contextHeading"] == heading


def test_governing_prose_after_family_list_is_not_lost() -> None:
    rows = inventory(
        "## 17. Roadmap\n### Phase 8 - Additional families\nRecommended order:\n\n"
        "1. sleeveless tops;\n2. jackets/outerwear;\n\n"
        "Each family requires templates, semantics, capture tests and simulation validation."
    )["requirements"]
    assert len(rows) == 3
    assert all(row["roadmapPhase"] == 8 for row in rows)
    assert rows[0]["contextBlockId"] == rows[2]["blockId"]


def test_context_does_not_leak_across_prose_or_heading() -> None:
    blocks = parse_source_blocks(
        "## Phase 1\nDeliver:\n- simulation mesh;\n"
        "This is historical background.\n\n- uncertain noun;\n"
        "### New section\n- another uncertain noun;\n"
    )
    items = [block for block in blocks if block["kind"] == "list_item"]
    assert [block["classification"] for block in items] == ["normative", "ambiguous", "ambiguous"]


def test_nested_list_governor_does_not_apply_to_siblings() -> None:
    blocks = parse_source_blocks(
        "# Notes\n- Required:\n  - finite positions;\n- uncertain sibling;"
    )
    assert blocks[2]["classification"] == "normative"
    assert blocks[3]["classification"] == "ambiguous"


def test_fenced_examples_and_explicit_example_lists_do_not_become_requirements() -> None:
    result = inventory(
        "## Acceptance\nFor example:\n- simulation mesh;\n\n"
        "~~~~text\n# Phase 9\n- must train;\n```\n~~~~\n"
        "### Phase 3\nDeliver:\n- fitted garment;"
    )
    assert len(result["requirements"]) == 1
    assert result["requirements"][0]["roadmapPhase"] == 3


def test_multiline_noun_and_normative_continuation_preserve_source_anchor() -> None:
    text = "# Notes\n- binding offsets\n  must be finite.\n"
    row = inventory(text)["requirements"][0]
    assert row["sourceLineStart"] == 2
    assert row["sourceLineEnd"] == 3
    assert row["sourceAnchor"] == "L2-L3"
    assert row["rawText"] == "\n".join(text.splitlines()[1:3])


def test_required_table_rows_and_unknown_tables_are_kept() -> None:
    result = inventory(
        "# Notes\nRequired:\n\n| Asset | Budget |\n|---|---|\n| Mesh | 8 MiB |\n\n"
        "Background:\n\n| Thing | Value |\n|---|---|\n| Other | unknown |"
    )
    assert len(result["requirements"]) == 1
    assert len(result["reviewRequiredBlocks"]) == 1


def test_repeated_requirements_keep_distinct_anchors_and_stable_ids() -> None:
    source = "## Phase 1\nDeliver:\n- mesh;\n- mesh;\n## Phase 8\nDeliver:\n- mesh;"
    original = inventory(source)["requirements"]
    shifted = inventory("\n\n" + source)["requirements"]
    assert len({row["id"] for row in original}) == 3
    assert [row["id"] for row in original] == [row["id"] for row in shifted]


def test_sections_crosslink_explicitly_and_gate_z2_is_not_processing_stage_z2() -> None:
    rows = inventory(
        "## 8. Foundry\n### 8.18 Binding\nRequired:\n- frame offsets;\n"
        "## 9. Backend\n### 9.5 Stages\n#### Z2 - Dense geometry analysis\n"
        "- Must analyse geometry.\n## 18. Gates\n### Gate Z2 - Dynamic readiness\n"
        "Required:\n- deformation compute;\n## 21. Architecture\n- Never replace panels."
    )["requirements"]
    assert [row["sourceSection"] for row in rows] == ["8.18", "9.5", "18", "21"]
    assert [row["roadmapPhases"] for row in rows] == [[6], [10], [11], []]
    assert all(row["roadmapPhase"] is None for row in rows)


def test_out_of_range_phase_is_flagged_not_invented() -> None:
    result = inventory("## Phase 17\n- Must retain geometry.")
    assert result["requirements"][0]["mappingKind"] == "review_required"
    assert result["reviewRequiredBlocks"]
    assert len(result["phaseSummaries"]) == 15


@pytest.mark.parametrize("source", ["\ufeff# Source", "```\nUnclosed"])
def test_invalid_source_rejected(source: str) -> None:
    with pytest.raises(ValueError):
        inventory(source)


def test_no_override_does_not_mean_no_implementation() -> None:
    row = inventory("## Phase 0\nDeliver:\n- package reader;")["requirements"][0]
    assert row["status"] == "unassessed"
    assert row["implementationStatus"] == "unassessed"
    assert row["evidenceStatus"] == "not_reviewed"


def test_reviewed_code_and_failed_evidence_are_separate() -> None:
    text = "## Phase 6\nDeliver:\n- binding;"
    key = inventory(text)["requirements"][0]["id"]
    assessment = {
        "status": "partial",
        "implementationStatus": "implemented",
        "evidenceStatus": "failed",
        "implementationAnchors": ["binding.py"],
        "evidenceAnchors": ["rest_error.json"],
        "scope": "manual dense shell",
        "reason": "Rest error exceeds 0.008 m.",
    }
    row = inventory(text, assessments={key: assessment})["requirements"][0]
    assert row["status"] == "partial"
    assert row["implementationStatus"] == "implemented"
    assert row["evidenceStatus"] == "failed"
    with pytest.raises(ValueError, match="scoped_acceptance"):
        inventory(text, assessments={key: {**assessment, "status": "complete"}})


@pytest.mark.parametrize(
    "assessment",
    [
        {"status": "not_started"},
        {"status": "complete", "evidenceAnchors": ["test.py"]},
        {"status": "dependency_blocked"},
        {"implementationStatus": "implemented"},
        {"evidenceStatus": "passed"},
        {"status": "typo"},
        {"dependencies": "not a list"},
    ],
)
def test_unsupported_status_claims_are_rejected(assessment: dict[str, Any]) -> None:
    text = "- Must keep a fallback."
    key = inventory(text)["requirements"][0]["id"]
    with pytest.raises(ValueError):
        inventory(text, assessments={key: {"scope": "fixture", "reason": "review", **assessment}})


def test_unknown_assessment_ids_are_rejected() -> None:
    with pytest.raises(ValueError, match="id_not_in_inventory"):
        inventory("- Must keep a fallback.", assessments={"stale-id": {}})


def test_scoped_acceptance_requires_review_even_with_passing_evidence() -> None:
    source = "Deliver:\n- a mesh;"
    key = inventory(source)["requirements"][0]["id"]
    assessment = {
        "status": "complete",
        "implementationStatus": "implemented",
        "evidenceStatus": "passed",
        "implementationAnchors": ["mesh.py"],
        "evidenceAnchors": ["mesh-report.json"],
        "scope": "one fixture",
        "reason": "All scoped acceptance predicates reviewed.",
    }
    with pytest.raises(ValueError, match="scoped_acceptance"):
        inventory(source, assessments={key: assessment})
    assert (
        inventory(
            source,
            assessments={
                key: {
                    **assessment,
                    "acceptanceReviewed": True,
                }
            },
        )["requirements"][0]["status"]
        == "complete"
    )


def test_reclassified_introducer_keeps_migration_context_anchor() -> None:
    result = inventory("## Phase 6\nRequired before animation:\n- frame offsets;")
    intro = result["blocks"][1]
    legacy = {
        "requirements": [
            {
                "id": "legacy-intro",
                "headingPath": intro["headingPath"],
                "normalizedTextDigest": intro["normalizedTextDigest"],
                "sourceLineStart": 2,
                "sourceLineEnd": 2,
            }
        ]
    }
    migration = build_migration_crosswalk(
        result,
        historical_239=legacy,
        historical_101={"rows": []},
    )
    context = migration["historical239"][0]["currentSourceBlocks"][0]
    assert context["classificationReason"] == "requirement_list_introducer"
    assert context["blockId"] == result["requirements"][0]["contextBlockId"]


def test_read_only_generator_matches_saved_source_and_is_deterministic() -> None:
    script = runpy.run_path(str(ROOT / "scripts/generate_blueprint_progress_v3.py"))
    first = script["generate_report"](ROOT)
    second = script["generate_report"](ROOT)
    assert first == second
    assert first["sourceMatchesHistorical239"] is True
    assert first["inventory"]["sourceGitBlobOid"] == "b0b702ff940719a6c83a232487762077345090fd"
    assert first["phaseOverview"]["baselinePr"] == 66
    assert first["migration"]["counts"]["historicalSourceRows"] == 239


def test_crosswalk_preserves_unmatched_legacy_rows_and_statuses() -> None:
    result = inventory("## 17. Roadmap\n### Phase 1\nDeliver:\n- simulation mesh;")
    row = result["requirements"][0]
    legacy = {
        "requirements": [
            {
                "id": "old",
                "normalizedTextDigest": row["normalizedTextDigest"],
                "headingPath": row["headingPath"],
                "phase": "17",
                "status": "not_started",
                "sourceLineStart": 4,
                "sourceLineEnd": 4,
            },
            {
                "id": "unmatched",
                "normalizedTextDigest": "missing",
                "headingPath": [],
                "phase": "25",
                "status": "partial",
                "sourceLineStart": 10,
                "sourceLineEnd": 10,
            },
        ],
    }
    grouped = {"rows": [{"id": "BP-17-PHASE-01", "status": "complete"}, {"id": "BP-09-Z2"}]}
    migration = build_migration_crosswalk(result, historical_239=legacy, historical_101=grouped)
    assert migration["counts"]["historicalSourceRows"] == 2
    assert migration["historical239"][0]["historicalPhase"] == "17"
    assert migration["historical239"][0]["currentRoadmapPhases"] == [1]
    assert migration["historical239"][0]["currentStatuses"] == ["unassessed"]
    assert migration["historical239"][1]["matchKind"] == "review_required"
    assert migration["historical101"][0]["matchKind"] == "roadmap_group_to_deliverables"
    assert migration["historical101"][1]["roadmapPhase"] is None


def test_actual_blueprint_and_frozen_inputs_are_read_only() -> None:
    paths = [
        ROOT / BLUEPRINT_PATH,
        ROOT / "docs/blueprint_coverage.json",
        ROOT / "docs/evidence/static_zeroone_runtime_v2/blueprint_inventory.json",
        ROOT / "src/closy_forge/capture_reconstruction_v2/blueprint_parser.py",
    ]
    before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    result = inventory(paths[0].read_text(encoding="utf-8"))
    migration = build_migration_crosswalk(
        result,
        historical_239=json.loads(paths[2].read_text(encoding="utf-8")),
        historical_101=json.loads(paths[1].read_text(encoding="utf-8")),
    )
    assert migration["counts"]["historicalSourceRows"] == 239
    assert migration["counts"]["historicalGroupedRows"] == 101
    assert {row["roadmapPhase"] for row in result["requirements"]} >= set(range(15))
    assert any(
        "simulation mesh;" in row["rawText"] and row["roadmapPhase"] == 1
        for row in result["requirements"]
    )
    assert any(
        "multiple garment collision layers;" in row["rawText"] and row["roadmapPhase"] == 13
        for row in result["requirements"]
    )
    assert result["sourceBlockCounts"]["ambiguous"] > 0
    assert result["requirementCount"] > 239
    assert len(result["blocks"]) == sum(result["sourceBlockCounts"].values())
    assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths] == before


def test_phase_overview_links_exist_and_no_current_acceptance_is_invented() -> None:
    overview = phase_overview()
    assert overview["baselinePr"] == 66
    assert [row["roadmapPhase"] for row in overview["phases"]] == list(range(15))
    for row in overview["phases"]:
        assert row["acceptanceStatus"] != "complete"
        assert row["supportedScope"] and row["unmetGates"] and row["dependencies"]
        for anchor in row["implementationAnchors"] + row["evidenceAnchors"]:
            assert (ROOT / anchor).is_file()
    overview["phases"][0]["title"] = "mutation"
    assert phase_overview()["phases"][0]["title"] != "mutation"
    assert "| 14:" in render_phase_table()
