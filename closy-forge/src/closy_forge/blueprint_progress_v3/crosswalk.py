"""Lossless migration records, without importing old statuses as current acceptance."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


def build_migration_crosswalk(
    current: Mapping[str, Any],
    *,
    historical_239: Mapping[str, Any],
    historical_101: Mapping[str, Any],
) -> dict[str, Any]:
    requirements = current["requirements"]
    by_text: dict[str, list[dict[str, Any]]] = {}
    for row in requirements:
        by_text.setdefault(row["normalizedTextDigest"], []).append(row)
    retained: set[str] = set()
    source_rows = []
    for old in historical_239["requirements"]:
        candidates = by_text.get(old["normalizedTextDigest"], [])
        same_heading = [row for row in candidates if row["headingPath"] == old["headingPath"]]
        matches = same_heading or candidates
        retained.update(row["id"] for row in matches)
        exact = len(matches) == 1
        source_matches = [
            block
            for block in current["blocks"]
            if block["normalizedTextDigest"] == old["normalizedTextDigest"]
            and block["headingPath"] == old["headingPath"]
        ]
        source_rows.append(
            {
                "historicalId": old["id"],
                "historicalPhase": old.get("phase"),
                "historicalStatus": old.get("status"),
                "historicalNormalizedText": old.get("normalizedText"),
                "historicalSourceLines": [old["sourceLineStart"], old["sourceLineEnd"]],
                "currentSourceBlocks": [
                    {
                        "blockId": block["blockId"],
                        "classification": block["classification"],
                        "classificationReason": block["classificationReason"],
                    }
                    for block in source_matches
                ],
                "currentIds": [row["id"] for row in matches],
                "currentRoadmapPhases": sorted(
                    {phase for row in matches for phase in row["roadmapPhases"]}
                ),
                "currentSourceSections": sorted(
                    {row["sourceSection"] for row in matches if row["sourceSection"] is not None}
                ),
                "currentStatuses": sorted({row["status"] for row in matches}),
                "matchKind": "exact_text" if exact else "review_required",
                "reason": (
                    "location and roadmap mapping recomputed; historical status not inherited"
                    if exact
                    else "split, reclassified, repeated or changed source; inspect anchors"
                ),
            }
        )
    grouped_rows = []
    for old in historical_101["rows"]:
        # Only these IDs explicitly name a roadmap phase; other legacy ID digits are not phases.
        match = re.fullmatch(r"BP-17-PHASE-(\d{2})", old["id"])
        phase = int(match.group(1)) if match else None
        targets = [row["id"] for row in requirements if row["roadmapPhase"] == phase]
        if phase is None or phase not in range(15):
            targets = []
        grouped_rows.append(
            {
                "historicalId": old["id"],
                "historicalStatus": old.get("status"),
                "historicalSummary": old.get("summary"),
                "roadmapPhase": phase,
                "currentIds": targets,
                "matchKind": "roadmap_group_to_deliverables" if targets else "review_required",
                "reason": "grouped historical assessment is not atomic requirement acceptance",
            }
        )
    additions = [
        {
            "id": row["id"],
            "sourceAnchor": row["sourceAnchor"],
            "normalizedText": row["normalizedText"],
            "roadmapPhase": row["roadmapPhase"],
            "classificationReason": row["classificationReason"],
            "status": row["status"],
        }
        for row in requirements
        if row["id"] not in retained
    ]
    return {
        "crosswalkVersion": "closy.blueprint_progress_migration.v3",
        "historical239ParserVersion": historical_239.get("parserVersion"),
        "historical239SourceGitBlobOid": historical_239.get("sourceGitBlobOid"),
        "historical101Version": historical_101.get("version"),
        "counts": {
            "historicalSourceRows": len(source_rows),
            "historicalGroupedRows": len(grouped_rows),
            "currentRequirements": len(requirements),
            "newlyIncludedRequirements": len(additions),
            "historicalSourceRowsNeedingReview": sum(
                row["matchKind"] == "review_required" for row in source_rows
            ),
            "historicalGroupedRowsNeedingReview": sum(
                row["matchKind"] == "review_required" for row in grouped_rows
            ),
        },
        "historical239": source_rows,
        "historical101": grouped_rows,
        "newlyIncludedRequirements": additions,
        "statusPolicy": (
            "Historical statuses remain verbatim. Current unassessed means no row-specific review, "
            "not lost implementation. Consult the inspected phase overview separately. "
            "Counts belong to different inventory versions and are not completion percentages."
        ),
    }
