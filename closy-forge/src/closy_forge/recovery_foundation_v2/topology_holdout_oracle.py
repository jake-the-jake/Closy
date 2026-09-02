from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes


def derive_invariants(fixture: Mapping[str, Any]) -> dict[str, Any]:
    fixture_type = str(fixture.get("fixtureType", ""))
    parameters = _mapping(fixture.get("parameters"))
    seam_count = int(parameters.get("semanticSeamCount", 1))
    sample_count = int(parameters.get("seamSampleCount", 4))
    opening_count = int(parameters.get("openingCount", 0))
    expected_sequences = {
        f"seam.{ordinal}": [f"seam.{ordinal}.sample.{sample}" for sample in range(sample_count)]
        for ordinal in range(seam_count)
    }
    intervals = {
        seam: [[index, index + 1] for index in range(len(sequence) - 1)]
        for seam, sequence in expected_sequences.items()
    }
    document = {
        "oracleVersion": "closy.phy1.strategy3_holdout_oracle.v2",
        "fixtureId": fixture.get("fixtureId"),
        "fixtureType": fixture_type,
        "expectedSeamSequences": expected_sequences,
        "expectedIntervalCoverage": intervals,
        "expectedOpeningCount": opening_count,
        "expectedQuotientComponentCount": int(parameters.get("quotientComponentCount", 1)),
        "massIntervalKg": [
            float(parameters.get("massKg", 0.2)) - 1e-12,
            float(parameters.get("massKg", 0.2)) + 1e-12,
        ],
        "maximumEnergyJoules": float(parameters.get("maximumEnergyJoules", 1.0)),
        "requiredAttributeClasses": [
            "mass",
            "uv",
            "material",
            "source_coordinates",
            "semantic_ids",
            "binding_ancestry",
        ],
    }
    document["oracleDigest"] = sha256_bytes(canonical_dumps(document).encode("utf-8"))
    return document


def validate_candidate_report(
    fixture: Mapping[str, Any], oracle: Mapping[str, Any], report: Mapping[str, Any]
) -> list[str]:
    issues: list[str] = []
    if report.get("fixtureId") != fixture.get("fixtureId"):
        issues.append("topology_report_fixture_identity_invalid")
    if report.get("semanticSeamSequences") != oracle.get("expectedSeamSequences"):
        issues.append("topology_report_semantic_sequence_invalid")
    if report.get("intervalCoverage") != oracle.get("expectedIntervalCoverage"):
        issues.append("topology_report_interval_coverage_invalid")
    if report.get("openingCount") != oracle.get("expectedOpeningCount"):
        issues.append("topology_report_opening_count_invalid")
    required = set(oracle.get("requiredAttributeClasses", ()))
    actual = set(report.get("transferredAttributeClasses", ()))
    if actual != required:
        issues.append("topology_report_attribute_transfer_incomplete")
    if report.get("productionPathEvidence") in (None, {}, []):
        issues.append("topology_report_production_path_evidence_missing")
    if any(key.endswith("Pass") and value is True for key, value in report.items()):
        issues.append("topology_report_self_declared_pass_boolean_forbidden")
    return sorted(set(issues))


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
