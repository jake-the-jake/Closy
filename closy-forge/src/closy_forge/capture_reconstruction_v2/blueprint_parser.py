from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

PARSER_VERSION = "closy.blueprint_source_block_parser.v2"
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
BULLET = re.compile(r"^\s*[-*+]\s+(.+?)\s*$")
NUMBERED = re.compile(r"^\s*\d+[.)]\s+(.+?)\s*$")
TABLE_SEPARATOR = re.compile(r"^\s*\|?(?:\s*:?-+:?\s*\|)+\s*$")
NORMATIVE_WORDS = re.compile(
    r"\b(must|shall|required|requires|should|need(?:s)? to|do not|never|may not|cannot|"
    r"acceptance|gate|invariant|mandatory)\b",
    re.IGNORECASE,
)
IMPERATIVE_START = re.compile(
    r"^(add|avoid|build|create|define|document|ensure|evaluate|expose|freeze|implement|"
    r"include|keep|maintain|measure|persist|prepare|preserve|provide|record|reject|report|"
    r"require|retain|run|score|separate|store|support|test|track|use|validate|verify)\b",
    re.IGNORECASE,
)


def normalize_text(value: str) -> str:
    value = re.sub(r"[`*_>#]", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def parse_source_blocks(text: str) -> list[dict[str, Any]]:
    if text.startswith("\ufeff"):
        raise ValueError("blueprint_utf8_bom_forbidden")
    lines = text.splitlines()
    blocks: list[dict[str, Any]] = []
    headings: list[str] = []
    index = 0
    while index < len(lines):
        raw = lines[index]
        if not raw.strip():
            index += 1
            continue
        heading_match = HEADING.match(raw)
        if heading_match:
            level = len(heading_match.group(1))
            title = normalize_text(heading_match.group(2))
            headings = headings[: level - 1] + [title]
            blocks.append(_block("heading", index + 1, index + 1, raw, headings))
            index += 1
            continue
        if raw.strip().startswith("```"):
            start = index
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                index += 1
            if index >= len(lines):
                raise ValueError("blueprint_unclosed_code_fence")
            index += 1
            blocks.append(
                _block("code_fence", start + 1, index, "\n".join(lines[start:index]), headings)
            )
            continue
        if raw.strip() == "---":
            blocks.append(_block("separator", index + 1, index + 1, raw, headings))
            index += 1
            continue
        if "|" in raw and index + 1 < len(lines) and TABLE_SEPARATOR.match(lines[index + 1]):
            blocks.append(_block("table_header", index + 1, index + 1, raw, headings))
            blocks.append(
                _block("table_separator", index + 2, index + 2, lines[index + 1], headings)
            )
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                blocks.append(_block("table_row", index + 1, index + 1, lines[index], headings))
                index += 1
            continue
        bullet = BULLET.match(raw)
        numbered = NUMBERED.match(raw)
        if bullet or numbered:
            kind = "bullet" if bullet else "numbered_item"
            start = index
            collected = [raw]
            index += 1
            while (
                index < len(lines)
                and lines[index].strip()
                and not HEADING.match(lines[index])
                and not BULLET.match(lines[index])
                and not NUMBERED.match(lines[index])
                and not lines[index].strip().startswith("```")
                and lines[index].strip() != "---"
            ):
                collected.append(lines[index])
                index += 1
            blocks.append(_block(kind, start + 1, index, "\n".join(collected), headings))
            continue
        start = index
        collected = [raw]
        index += 1
        while (
            index < len(lines)
            and lines[index].strip()
            and not HEADING.match(lines[index])
            and not BULLET.match(lines[index])
            and not NUMBERED.match(lines[index])
            and not lines[index].strip().startswith("```")
            and lines[index].strip() != "---"
            and not (
                "|" in lines[index]
                and index + 1 < len(lines)
                and TABLE_SEPARATOR.match(lines[index + 1])
            )
        ):
            collected.append(lines[index])
            index += 1
        blocks.append(_block("paragraph", start + 1, index, "\n".join(collected), headings))
    return blocks


def build_requirement_inventory(
    text: str,
    *,
    source_blob_oid: str,
    status_overrides: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    blocks = parse_source_blocks(text)
    requirements: list[dict[str, Any]] = []
    seen_text: dict[str, str] = {}
    overrides = status_overrides or {}
    for block in blocks:
        classification, reason = _classify(block)
        block["classification"] = classification
        block["classificationReason"] = reason
        if classification != "normative":
            continue
        normalized = str(block["normalizedText"])
        normalized_digest = hashlib.sha256(normalized.casefold().encode()).hexdigest()
        if normalized_digest in seen_text:
            raise ValueError("blueprint_duplicate_normalized_requirement")
        requirement_id = f"BP-SRC-{normalized_digest[:16].upper()}"
        seen_text[normalized_digest] = requirement_id
        override = dict(overrides.get(requirement_id, {}))
        status = str(override.get("status", "not_started"))
        evidence = list(override.get("evidenceAnchors", []))
        if status != "not_started" and not evidence:
            raise ValueError("blueprint_nondefault_status_requires_verifier_evidence")
        requirements.append(
            {
                "id": requirement_id,
                "headingPath": block["headingPath"],
                "sourceLineStart": block["lineStart"],
                "sourceLineEnd": block["lineEnd"],
                "normalizedText": normalized,
                "normalizedTextDigest": normalized_digest,
                "sourceGitBlobOid": source_blob_oid,
                "phase": _phase(block["headingPath"]),
                "gate": _gate(normalized),
                "dependencies": list(override.get("dependencies", [])),
                "requiredEvidenceClass": _evidence_class(normalized),
                "externalInputDependency": _external_dependency(normalized),
                "status": status,
                "evidenceAnchors": evidence,
                "reason": override.get("reason", "source_derived_not_yet_verified"),
            }
        )
    _validate_requirements(requirements)
    counts = Counter(str(block["classification"]) for block in blocks)
    inventory: dict[str, Any] = {
        "schemaVersion": 1,
        "parserVersion": PARSER_VERSION,
        "sourceGitBlobOid": source_blob_oid,
        "sourceBlockCount": len(blocks),
        "sourceBlockCounts": {
            "normative": counts["normative"],
            "nonNormative": counts["non_normative"],
            "ambiguous": counts["ambiguous"],
            "unclassified": counts["unclassified"],
        },
        "mappedNormativeBlockCount": len(requirements),
        "unmappedNormativeBlockCount": 0,
        "blocks": blocks,
        "requirements": requirements,
    }
    inventory["requirementSetDigest"] = canonical_digest_for_requirements(requirements)
    return inventory


def canonical_digest_for_requirements(requirements: Sequence[Mapping[str, Any]]) -> str:
    rows = [
        {"id": row["id"], "normalizedTextDigest": row["normalizedTextDigest"]}
        for row in sorted(requirements, key=lambda item: str(item["id"]))
    ]
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def validate_inventory(inventory: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    counts = inventory.get("sourceBlockCounts", {})
    if not isinstance(counts, Mapping):
        return ["blueprint_source_block_counts_missing"]
    if int(counts.get("ambiguous", -1)) != 0:
        issues.append("blueprint_ambiguous_source_blocks")
    if int(counts.get("unclassified", -1)) != 0:
        issues.append("blueprint_unclassified_source_blocks")
    if int(inventory.get("unmappedNormativeBlockCount", -1)) != 0:
        issues.append("blueprint_unmapped_normative_blocks")
    requirements = inventory.get("requirements")
    if not isinstance(requirements, list):
        return issues + ["blueprint_requirements_missing"]
    try:
        _validate_requirements([dict(row) for row in requirements if isinstance(row, Mapping)])
    except ValueError as error:
        issues.append(str(error))
    return sorted(set(issues))


def _block(kind: str, start: int, end: int, text: str, headings: Sequence[str]) -> dict[str, Any]:
    normalized = normalize_text(text)
    return {
        "blockId": f"BLOCK-{start:04d}-{end:04d}",
        "kind": kind,
        "lineStart": start,
        "lineEnd": end,
        "headingPath": list(headings),
        "normalizedText": normalized,
        "normalizedTextDigest": hashlib.sha256(normalized.encode()).hexdigest(),
    }


def _classify(block: Mapping[str, Any]) -> tuple[str, str]:
    kind = str(block["kind"])
    text = str(block["normalizedText"])
    if kind in {"heading", "separator", "table_header", "table_separator", "code_fence"}:
        return "non_normative", f"{kind}_structural_or_example"
    cleaned = re.sub(r"^\d+[.)]\s+|^[-*+]\s+", "", text)
    if cleaned.casefold() in {"record:", "require:", "acceptance:", "gates:"}:
        return "non_normative", "structural_list_introducer"
    if NORMATIVE_WORDS.search(cleaned) or IMPERATIVE_START.search(cleaned):
        return "normative", "explicit_modal_or_imperative"
    return "non_normative", "descriptive_context_without_normative_grammar"


def _phase(headings: Sequence[str]) -> str:
    for heading in headings:
        match = re.match(r"(?:Phase\s+)?(\d{1,2})(?:\.|\s|$)", heading, re.IGNORECASE)
        if match:
            return match.group(1)
    return "cross_cutting"


def _gate(text: str) -> str:
    lowered = text.casefold()
    if "acceptance" in lowered or "gate" in lowered or "must" in lowered:
        return "acceptance_or_invariant"
    return "implementation_requirement"


def _evidence_class(text: str) -> str:
    lowered = text.casefold()
    if any(word in lowered for word in ("real garment", "real fabric", "user photograph")):
        return "authorised_real_external_evidence"
    if any(word in lowered for word in ("mobile", "device", "thermal", "battery")):
        return "measured_physical_device_evidence"
    if any(word in lowered for word in ("human review", "perceptual", "expert")):
        return "independent_human_review"
    return "executed_project_engineering_evidence"


def _external_dependency(text: str) -> str | None:
    lowered = text.casefold()
    if any(word in lowered for word in ("private", "consent", "user photograph", "body estimate")):
        return "consent_privacy_custody_authority"
    if any(word in lowered for word in ("physical device", "thermal", "battery")):
        return "physical_target_device"
    if any(word in lowered for word in ("real fabric", "fabric coupon")):
        return "measured_fabric_coupon"
    if any(word in lowered for word in ("licensed", "provider weights")):
        return "approved_licence_or_provider"
    return None


def _validate_requirements(requirements: Sequence[Mapping[str, Any]]) -> None:
    ids = [str(row.get("id", "")) for row in requirements]
    digests = [str(row.get("normalizedTextDigest", "")) for row in requirements]
    if not ids or "" in ids:
        raise ValueError("blueprint_requirement_id_missing")
    if len(ids) != len(set(ids)):
        raise ValueError("blueprint_duplicate_requirement_id")
    if len(digests) != len(set(digests)):
        raise ValueError("blueprint_duplicate_normalized_requirement")
    known = set(ids)
    for row in requirements:
        dependencies = row.get("dependencies")
        if not isinstance(dependencies, list):
            raise ValueError("blueprint_dependency_list_required")
        if any(str(dependency) not in known for dependency in dependencies):
            raise ValueError("blueprint_dangling_dependency")
        if row.get("status") == "complete" and not row.get("evidenceAnchors"):
            raise ValueError("blueprint_complete_without_evidence")
    if _has_cycle(requirements):
        raise ValueError("blueprint_dependency_cycle")


def _has_cycle(requirements: Sequence[Mapping[str, Any]]) -> bool:
    graph = {str(row["id"]): [str(value) for value in row["dependencies"]] for row in requirements}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(dependency) for dependency in graph[node]):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)
