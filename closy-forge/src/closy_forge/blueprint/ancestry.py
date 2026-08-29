from __future__ import annotations

from copy import deepcopy
from typing import Any

ANCESTRY_CLASSES = {
    "in_tree",
    "external_source_pr",
    "historical_superseded",
    "not_present",
}
CURRENT_REPOSITORY = "jake-the-jake/Closy"
CURRENT_AUTHORITY_PR = 35
CURRENT_AUTHORITY_SHA = "461436c22f8c5cd1948e0f6906961d0c512dcc34"

_EXTERNAL_ROW_SOURCES: dict[str, tuple[int, str, str]] = {
    "BP-09-Z2": (
        34,
        "960662d237e187cd8ecbcc9ebe9192367f194317",
        (
            "compiled pairing executed on PR #34 but failed the independent dense "
            "self-intersection oracle"
        ),
    ),
    "BP-17-PHASE-12": (
        29,
        "62464db2a91e4b24b808cfcd99ee95578fc95f32",
        "Phase 12 runtime preparation is a source-only sibling until replayed on Closy D",
    ),
    "BP-17-PHASE-13": (
        30,
        "1cf7ecff18bd0bbd37820638c0af2029d7a928ac",
        "synthetic avatar fit is a source-only sibling until replayed on Closy D",
    ),
    "BP-08-S-LAYERING-ANIMATION": (
        32,
        "386effb254d4ba15499399dfd7fd94c70a0e0fc5",
        "LayerCollision-D0 is an external radial-shell source and is not canonical "
        "garment-surface layering",
    ),
    "BP-18-GATE-Z2": (
        34,
        "960662d237e187cd8ecbcc9ebe9192367f194317",
        "Z2 is an external executed failure source and was not integrated into Closy E",
    ),
}

_HISTORICAL_ROWS = {
    "BP-18-GATE-C3",
    "BP-08-K-CLOTH-SIMULATION",
    "BP-17-PHASE-06",
}


def apply_ancestry_metadata(coverage: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(coverage)
    for row in result["rows"]:
        row_id = str(row["id"])
        status = str(row["status"])
        external = _EXTERNAL_ROW_SOURCES.get(row_id)
        if external is not None:
            source_pr, source_sha, limitation = external
            primary = _source(
                ancestry_class="external_source_pr",
                source_pr=source_pr,
                source_sha=source_sha,
                incorporated=False,
                incorporation_commit=None,
                evidence_tier="external_source_exact_head",
                limitations=limitation,
            )
        elif status in {"not_started", "discovery_pending", "blocked_external"}:
            primary = _source(
                ancestry_class="not_present",
                source_pr=None,
                source_sha=None,
                incorporated=False,
                incorporation_commit=None,
                evidence_tier="none",
                limitations=str(row["limitations"]),
            )
        else:
            primary = _source(
                ancestry_class="in_tree",
                source_pr=CURRENT_AUTHORITY_PR,
                source_sha=CURRENT_AUTHORITY_SHA,
                incorporated=True,
                incorporation_commit=CURRENT_AUTHORITY_SHA,
                evidence_tier=str(row.get("evidenceTier") or "in_tree_committed_evidence"),
                limitations=str(row["limitations"]),
            )

        supplemental: list[dict[str, Any]] = []
        if row_id in _HISTORICAL_ROWS:
            supplemental.append(
                _source(
                    ancestry_class="historical_superseded",
                    source_pr=25,
                    source_sha="f9f1ff86089f6b43157431bdd3ccdc83cbc8b974",
                    incorporated=True,
                    incorporation_commit="f64c4ff2225141aa3fa04405e77fef0af360e050",
                    evidence_tier="superseded_source_replayed_into_pr28",
                    limitations=(
                        "PR #25 exact-head CI was red; only mapped business commits were replayed "
                        "into PR #28"
                    ),
                )
            )
        row.update(primary)
        row["evidenceSources"] = [primary, *supplemental]
        row["evidenceTier"] = primary["evidenceTier"]
    result["ancestryAuthority"] = {
        "repository": CURRENT_REPOSITORY,
        "pullRequest": CURRENT_AUTHORITY_PR,
        "headSha": CURRENT_AUTHORITY_SHA,
        "classificationVersion": "closy.coverage_ancestry.v1",
    }
    result["integratedImplementationRowCount"] = sum(
        row["ancestryClass"] == "in_tree" for row in result["rows"]
    )
    result["externalSourceRowCount"] = sum(
        row["ancestryClass"] == "external_source_pr" for row in result["rows"]
    )
    return result


def validate_ancestry_metadata(coverage: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for row in coverage.get("rows", []):
        row_id = str(row.get("id"))
        ancestry_class = row.get("ancestryClass")
        if ancestry_class not in ANCESTRY_CLASSES:
            issues.append(f"coverage_ancestry_class_invalid:{row_id}")
        required = {
            "sourceRepository",
            "sourcePr",
            "sourceSha",
            "incorporated",
            "incorporationCommit",
            "evidenceTier",
            "limitations",
            "evidenceSources",
        }
        if not required.issubset(row):
            issues.append(f"coverage_ancestry_fields_missing:{row_id}")
            continue
        if ancestry_class == "in_tree":
            if row["incorporated"] is not True or not row["incorporationCommit"]:
                issues.append(f"coverage_in_tree_not_incorporated:{row_id}")
        elif row["incorporated"] is True:
            issues.append(f"coverage_external_marked_incorporated:{row_id}")
        if ancestry_class == "external_source_pr" and row["sourcePr"] not in {29, 30, 32, 34}:
            issues.append(f"coverage_external_source_unrecognised:{row_id}")
        if ancestry_class == "not_present" and row["sourceSha"] is not None:
            issues.append(f"coverage_absent_has_source_sha:{row_id}")
    return sorted(set(issues))


def _source(
    *,
    ancestry_class: str,
    source_pr: int | None,
    source_sha: str | None,
    incorporated: bool,
    incorporation_commit: str | None,
    evidence_tier: str,
    limitations: str,
) -> dict[str, Any]:
    return {
        "ancestryClass": ancestry_class,
        "sourceRepository": CURRENT_REPOSITORY if source_sha else None,
        "sourcePr": source_pr,
        "sourceSha": source_sha,
        "incorporated": incorporated,
        "incorporationCommit": incorporation_commit,
        "evidenceTier": evidence_tier,
        "limitations": limitations,
    }
