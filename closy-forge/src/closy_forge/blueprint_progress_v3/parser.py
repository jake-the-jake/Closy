"""A bounded Markdown inventory, not a Markdown renderer or acceptance evaluator.

V2 is the historical design reference, not an import dependency. V3 retains uncertain
list items for review and separates document location, roadmap mapping and evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

PARSER_VERSION = "closy.blueprint_progress.v3"
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
ITEM = re.compile(r"^([ \t]*)(?:[-*+]|\d+[.)])[ \t]+([^\n]+)")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")
PHASE = re.compile(r"^Phase\s+(\d+)\b", re.IGNORECASE)
SECTION = re.compile(r"^(\d+(?:\.\d+)*)(?:\.\s|\s)")
MODAL = re.compile(
    r"\b(must|shall|required|requires|should|needs? to|do not|never|may not|cannot|"
    r"mandatory|acceptance|invariant|success means)\b",
    re.IGNORECASE,
)
IMPERATIVE = re.compile(
    r"^(add|avoid|build|create|define|document|ensure|evaluate|expose|freeze|implement|"
    r"include|keep|maintain|measure|persist|prepare|preserve|provide|record|reject|report|"
    r"require|retain|run|score|separate|store|support|test|track|use|validate|verify|"
    r"train|fine-tune|compare|optimise|optimize|estimate|begin)\b",
    re.IGNORECASE,
)
CONTEXT_LABEL = re.compile(
    r"^(deliver(?:ables)?|required|requirements?|acceptance(?: criteria)?|gates?|"
    r"record|success criteria)\b",
    re.IGNORECASE,
)
EXAMPLE = re.compile(r"^(?:for example|examples?|illustration|possible adapters)\b", re.I)
GOVERNING = re.compile(r"^(?:each|every)\b.*\b(?:requires|must|shall|should)\b", re.I)

# An editorial crosswalk of specific blueprint sections, NOT arithmetic on section numbers.
# Unlisted architecture, rights, risk and evaluation sections remain cross-cutting.
SECTION_PHASE_LINKS: dict[str, tuple[int, ...]] = {
    "7": (2,),
    "8.1": (2,),
    "8.2": (2,),
    "8.3": (2,),
    "8.4": (2, 13),
    "8.5": (2, 3),
    "8.6": (1, 8),
    "8.7": (0, 1, 8),
    "8.8": (3, 9),
    "8.9": (5,),
    "8.10": (1, 8),
    "8.11": (1, 7, 8, 13),
    "8.12": (3,),
    "8.13": (5,),
    "8.14": (5, 6),
    "8.15": (4,),
    "8.16": (4,),
    "8.17": (7,),
    "8.18": (6,),
    "8.19": (13,),
    "8.20": (2, 3, 9, 13),
    "9.1": (10, 11),
    "9.2": (10,),
    "9.3": (10,),
    "9.4": (10,),
    "9.5": (10,),
    "9.6": (10,),
    "9.7": (10, 11, 12),
    "9.8": (11,),
    "9.9": (11,),
    "9.10": (11,),
    "9.11": (0, 10, 11),
    "10": (0, 12),
    "13": (9, 14),
    "22": (0, 1),
    "23": (2, 3),
}
GATE_PHASE_LINKS: dict[str, tuple[int, ...]] = {
    "C1": (0, 1),
    "C2": (5,),
    "C3": (6,),
    "Z1": (10,),
    "Z2": (11,),
    "P1": (),
}


def normalize_text(value: str) -> str:
    """Keep V2 text normalization for exact historical-text matching only."""
    return re.sub(r"\s+", " ", re.sub(r"[`*_>#]", "", value)).strip()


def _clean(raw: str) -> str:
    return normalize_text(ITEM.sub(r"\2", raw, count=1))


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _location(headings: Sequence[str]) -> dict[str, Any]:
    section = None
    for title in reversed(headings):
        match = SECTION.match(title)
        if match:
            section = match.group(1)
            break
    for title in reversed(headings):
        match = PHASE.match(title)
        if match:
            number = int(match.group(1))
            valid = 0 <= number <= 14
            return {
                "sourceSection": section,
                "roadmapPhase": number if valid else None,
                "roadmapPhases": [number] if valid else [],
                "mappingKind": "explicit_phase_heading" if valid else "review_required",
                "mappingReason": title if valid else f"phase_out_of_range:{number}",
            }
    for title in reversed(headings):
        gate = re.match(r"^Gate\s+(C[123]|Z[12]|P1)\b", title, re.I)
        if gate and section == "18":
            phases = GATE_PHASE_LINKS[gate.group(1).upper()]
            return {
                "sourceSection": section,
                "roadmapPhase": None,
                "roadmapPhases": list(phases),
                "mappingKind": "explicit_gate_crosswalk" if phases else "cross_cutting",
                "mappingReason": title,
            }
    key = section or ""
    while key:
        if key in SECTION_PHASE_LINKS:
            return {
                "sourceSection": section,
                "roadmapPhase": None,
                "roadmapPhases": list(SECTION_PHASE_LINKS[key]),
                "mappingKind": "explicit_section_crosswalk",
                "mappingReason": f"SECTION_PHASE_LINKS[{key}]",
            }
        key = key.rpartition(".")[0]
    return {
        "sourceSection": section,
        "roadmapPhase": None,
        "roadmapPhases": [],
        "mappingKind": "cross_cutting",
        "mappingReason": "no_explicit_roadmap_assignment",
    }


def parse_source_blocks(text: str) -> list[dict[str, Any]]:
    if text.startswith("\ufeff"):
        raise ValueError("blueprint_utf8_bom_forbidden")
    lines = text.splitlines()
    blocks: list[dict[str, Any]] = []
    headings: list[tuple[int, str]] = []
    index = 0

    def append(kind: str, start: int, end: int) -> None:
        raw = "\n".join(lines[start:end])
        path = [title for _, title in headings]
        normalized = normalize_text(raw)
        blocks.append(
            {
                "blockId": f"BLOCK-{start + 1:04d}-{end:04d}",
                "kind": kind,
                "lineStart": start + 1,
                "lineEnd": end,
                "rawText": raw,
                "headingPath": path,
                "normalizedText": normalized,
                "normalizedTextDigest": hashlib.sha256(normalized.casefold().encode()).hexdigest(),
                **_location(path),
            }
        )

    while index < len(lines):
        raw = lines[index]
        if not raw.strip():
            index += 1
            continue
        start = index
        heading = HEADING.match(raw)
        fence = FENCE.match(raw)
        if heading:
            level = len(heading.group(1))
            headings = [(depth, title) for depth, title in headings if depth < level]
            headings.append((level, normalize_text(heading.group(2))))
            index += 1
            append("heading", start, index)
        elif fence:
            marker = fence.group(1)
            index += 1
            close = re.compile(r"^\s*" + re.escape(marker[0]) + "{" + str(len(marker)) + r",}\s*$")
            while index < len(lines) and not close.match(lines[index]):
                index += 1
            if index == len(lines):
                raise ValueError("blueprint_unclosed_code_fence")
            index += 1
            append("code_fence", start, index)
        elif raw.strip() in {"---", "***", "___"}:
            index += 1
            append("separator", start, index)
        elif index + 1 < len(lines) and "|" in raw and TABLE_RULE.match(lines[index + 1]):
            append("table_header", index, index + 1)
            append("table_separator", index + 1, index + 2)
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                append("table_row", index, index + 1)
                index += 1
        else:
            item = ITEM.match(raw)
            kind = "list_item" if item else "paragraph"
            indent = len(item.group(1)) if item else 0
            index += 1
            while index < len(lines) and lines[index].strip():
                current = lines[index]
                if HEADING.match(current) or ITEM.match(current) or FENCE.match(current):
                    break
                if current.strip() in {"---", "***", "___"}:
                    break
                if index + 1 < len(lines) and TABLE_RULE.match(lines[index + 1]):
                    break
                # Unindented prose after a list must not become part of its final item.
                if item and len(current) - len(current.lstrip()) <= indent:
                    break
                index += 1
            append(kind, start, index)
    _classify_blocks(blocks)
    return blocks


def _context(text: str) -> str | None:
    if EXAMPLE.match(text):
        return "example"
    if re.search(r"\bowns:$|\bis responsible for:$|^Only after\b.*:$", text, re.I):
        return "requirement"
    if CONTEXT_LABEL.match(text) or (
        text.endswith(":") and (MODAL.search(text) or IMPERATIVE.match(text))
    ):
        return "requirement"
    if MODAL.search(text) and re.search(r"\b(include|retain|contain|following)\b", text, re.I):
        return "requirement"
    return None


def _classify_blocks(blocks: list[dict[str, Any]]) -> None:
    # Governing prose can follow a list (notably the Phase 8 family inventory).
    governors = {
        tuple(block["headingPath"]): block
        for block in blocks
        if block["kind"] == "paragraph" and GOVERNING.match(_clean(block["rawText"]))
    }
    context: dict[str, Any] | None = None
    parents: list[tuple[int, dict[str, Any]]] = []
    for block in blocks:
        kind = block["kind"]
        cleaned = _clean(block["rawText"])
        heading_context = next(
            (
                title
                for title in reversed(block["headingPath"])
                if CONTEXT_LABEL.match(SECTION.sub("", title, count=1))
            ),
            None,
        )
        if kind in {"heading", "separator", "code_fence"}:
            context = None
            parents = []
        inherited = context
        if kind == "list_item":
            match = ITEM.match(block["rawText"])
            assert match is not None
            indent = len(match.group(1))
            parents = [(depth, parent) for depth, parent in parents if depth < indent]
            if parents:
                inherited = parents[-1][1]
        mode = _context(_clean(inherited["rawText"])) if inherited else None
        governor = governors.get(tuple(block["headingPath"]))
        block["contextBlockId"] = inherited["blockId"] if inherited else None
        if kind in {"heading", "separator", "code_fence", "table_header", "table_separator"}:
            classification, reason = "non_normative", "structural_or_example"
        elif kind in {"list_item", "table_row"} and mode == "example":
            classification, reason = "non_normative", "explicit_example_context"
        elif kind in {"list_item", "table_row"} and (
            mode == "requirement" or heading_context or governor
        ):
            classification, reason = "normative", "inherited_requirement_context"
            if not inherited and governor:
                block["contextBlockId"] = governor["blockId"]
            block["contextHeading"] = heading_context
        elif kind == "paragraph" and CONTEXT_LABEL.match(cleaned) and cleaned.endswith(":"):
            classification, reason = "non_normative", "requirement_list_introducer"
        elif MODAL.search(cleaned) or IMPERATIVE.match(cleaned):
            classification, reason = "normative", "explicit_modal_or_imperative"
        elif kind in {"list_item", "table_row"}:
            classification, reason = "ambiguous", "list_without_clear_governing_context"
        else:
            classification, reason = "non_normative", "descriptive_prose"
        block["classification"] = classification
        block["classificationReason"] = reason
        if kind == "paragraph":
            context = block if _context(cleaned) else None
            parents = []
        elif kind == "list_item" and _context(cleaned):
            parents.append((indent, block))


def _assessment(override: Mapping[str, Any]) -> dict[str, Any]:
    value: dict[str, Any] = {
        "status": "unassessed",
        "implementationStatus": "unassessed",
        "evidenceStatus": "not_reviewed",
        "implementationAnchors": [],
        "evidenceAnchors": [],
        "dependencies": [],
        "scope": "",
        "reason": "no_requirement_level_review; not an assertion that code is absent",
        "acceptanceReviewed": False,
    }
    if set(override) - set(value):
        raise ValueError("blueprint_unknown_assessment_field")
    value.update(override)
    if value["status"] not in {
        "unassessed",
        "not_started",
        "partial",
        "implemented_unverified",
        "complete",
        "dependency_blocked",
        "not_run",
    }:
        raise ValueError("blueprint_unknown_status")
    if value["implementationStatus"] not in {"unassessed", "absent", "partial", "implemented"}:
        raise ValueError("blueprint_unknown_implementation_status")
    if value["evidenceStatus"] not in {"not_reviewed", "not_run", "passed", "failed", "partial"}:
        raise ValueError("blueprint_unknown_evidence_status")
    for key in ("implementationAnchors", "evidenceAnchors", "dependencies"):
        if not isinstance(value[key], list) or any(
            not isinstance(item, str) or not item.strip() for item in value[key]
        ):
            raise ValueError("blueprint_assessment_list_required")
    if override and any(
        not isinstance(value[key], str) or not value[key].strip() for key in ("scope", "reason")
    ):
        raise ValueError("blueprint_assessment_scope_and_reason_required")
    if override and "reason" not in override:
        raise ValueError("blueprint_assessment_scope_and_reason_required")
    if value["implementationStatus"] != "unassessed" and not value["implementationAnchors"]:
        raise ValueError("blueprint_implementation_inspection_required")
    if value["evidenceStatus"] in {"passed", "failed", "partial"} and not value["evidenceAnchors"]:
        raise ValueError("blueprint_verifier_evidence_required")
    if value["status"] == "not_started" and value["implementationStatus"] != "absent":
        raise ValueError("blueprint_not_started_requires_inspected_absence")
    if value["status"] == "dependency_blocked" and not value["dependencies"]:
        raise ValueError("blueprint_blocked_requires_dependency")
    if value["status"] == "complete" and not (
        value["implementationStatus"] == "implemented"
        and value["evidenceStatus"] == "passed"
        and value["acceptanceReviewed"] is True
    ):
        raise ValueError("blueprint_complete_requires_scoped_acceptance_review")
    return value


def build_requirement_inventory(
    text: str,
    *,
    source_blob_oid: str,
    assessments: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    blocks = parse_source_blocks(text)
    requirements: list[dict[str, Any]] = []
    occurrences: Counter[str] = Counter()
    overrides = assessments or {}
    for block in blocks:
        if block["classification"] != "normative":
            continue
        identity = _digest([block["headingPath"], block["kind"], block["normalizedText"]])
        occurrences[identity] += 1
        requirement_id = f"BPV3-{identity[:16].upper()}-{occurrences[identity]}"
        requirements.append(
            {
                **block,
                "id": requirement_id,
                "sourceGitBlobOid": source_blob_oid,
                "sourceLineStart": block["lineStart"],
                "sourceLineEnd": block["lineEnd"],
                "sourceAnchor": f"L{block['lineStart']}-L{block['lineEnd']}",
                **_assessment(overrides.get(requirement_id, {})),
            }
        )
    if set(overrides) - {row["id"] for row in requirements}:
        raise ValueError("blueprint_assessment_id_not_in_inventory")
    counts = Counter(block["classification"] for block in blocks)
    return {
        "schemaVersion": 3,
        "parserVersion": PARSER_VERSION,
        "sourceGitBlobOid": source_blob_oid,
        "sourceTextSha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "sourceBlockCount": len(blocks),
        "sourceBlockCounts": dict(sorted(counts.items())),
        "requirementCount": len(requirements),
        "requirements": requirements,
        "blocks": blocks,
        "requirementSetDigest": _digest(
            [[row["id"], row["normalizedTextDigest"]] for row in requirements]
        ),
        "statusCounts": dict(sorted(Counter(row["status"] for row in requirements).items())),
        "reviewRequiredBlocks": [
            block
            for block in blocks
            if (block["classification"] == "ambiguous" or block["mappingKind"] == "review_required")
        ],
        "coverageClaim": "classified_source_blocks_only; ambiguous blocks require human review",
        "phaseSummaries": [
            {
                "roadmapPhase": phase,
                "directRequirementCount": sum(row["roadmapPhase"] == phase for row in requirements),
                "crossLinkedRequirementCount": sum(
                    row["roadmapPhase"] is None and phase in row["roadmapPhases"]
                    for row in requirements
                ),
            }
            for phase in range(15)
        ],
        "crossCuttingRequirementCount": sum(
            row["mappingKind"] == "cross_cutting" for row in requirements
        ),
    }
