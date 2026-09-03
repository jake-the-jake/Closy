from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .common import canonical_digest, mapping

REQUIRED_INTERVENTIONS = frozenset(
    {"zeroed", "shuffled", "localized_occlusion", "role_swapped", "label_preserving"}
)


def evaluate_pixel_causality(record: Mapping[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    for key in (
        "sourceSha256",
        "decoder",
        "decoderVersion",
        "pixelReadTraceSha256",
        "normalizedTensorSha256",
        "contestantInputManifestSha256",
        "baselineOutputSha256",
    ):
        if not record.get(key):
            reasons.append(f"{key}_missing")
    interventions = [mapping(row) for row in _sequence(record.get("interventions"))]
    kinds = {str(row.get("kind", "")) for row in interventions}
    for missing in sorted(REQUIRED_INTERVENTIONS - kinds):
        reasons.append(f"intervention_{missing}_missing")
    for row in interventions:
        if row.get("outputChanged") is not True:
            reasons.append(f"{row.get('kind', 'unknown')}_output_unchanged")
        if row.get("groundTruthPerformanceDegraded") is not True:
            reasons.append(f"{row.get('kind', 'unknown')}_task_control_not_degraded")
        if not row.get("intervenedTensorSha256") or not row.get("outputSha256"):
            reasons.append(f"{row.get('kind', 'unknown')}_digest_missing")
    verified = not reasons
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "causalityVersion": "closy.pixel_causality.v1",
        "classification": "verified_pixel_causal" if verified else "unverified_pixel_causality",
        "trustedEvidenceClass": "source_conditioned_pixels" if verified else "unverified",
        "reasonCodes": sorted(set(reasons)),
        "interventionCount": len(interventions),
        "causalityPass": verified,
        "recordDigest": "",
    }
    result["recordDigest"] = canonical_digest(result, "recordDigest")
    return result


def _sequence(value: object) -> Sequence[object]:
    return value if isinstance(value, Sequence) and not isinstance(value, str | bytes) else []
