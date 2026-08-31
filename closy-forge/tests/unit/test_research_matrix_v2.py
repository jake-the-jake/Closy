from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from closy_forge.package_io.canonical_json import read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.research_matrix import canonical_artifact_sha256, evaluate_research_matrix


def _digest(label: str) -> str:
    return sha256_bytes(label.encode())


def _registry() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "registryId": "fixture.registry.v1",
        "rows": [
            {
                "rowId": "D0-RP-01",
                "requirement": "fixture evidence",
                "thresholdRef": "fixture.threshold.v1",
                "requiredEvidenceIds": ["fixture"],
                "decisionGroup": "research_prototype_core",
                "requiredForResearchPrototype": True,
            },
            {
                "rowId": "D0-RP-10",
                "requirement": "supplemental evidence",
                "thresholdRef": "fixture.supplemental.v1",
                "requiredEvidenceIds": ["supplemental"],
                "decisionGroup": "zeroone_supplemental",
                "requiredForResearchPrototype": False,
            },
        ],
        "traceability": [{"clauseId": "fixture_clause", "requiredRowIds": ["D0-RP-01"]}],
    }


def _identity() -> dict[str, str]:
    return {
        "avatarContractHash": _digest("avatar"),
        "garmentId": "garment.fixture",
        "packageDigest": _digest("package"),
    }


def _binding(path: Path, *, expected: bool = True) -> dict[str, object]:
    return {
        "classification": "public_fixture",
        "path": path.name,
        "sha256": canonical_artifact_sha256(path),
        "predicates": [
            {
                "predicateId": "executed",
                "pointer": "/executed",
                "operation": "equals",
                "expected": expected,
            },
            {
                "predicateId": "package_join",
                "pointer": "/packageDigest",
                "operation": "identity_equals",
                "identityKey": "packageDigest",
            },
        ],
    }


def test_matrix_derives_status_counts_and_ignores_supplemental_missing_row(
    tmp_path: Path,
) -> None:
    evidence = tmp_path / "evidence.json"
    write_canonical_json(
        evidence,
        {"executed": True, "declaredPass": False, "packageDigest": _digest("package")},
    )
    matrix = evaluate_research_matrix(
        tmp_path,
        registry=_registry(),
        evidence_bindings={"fixture": _binding(evidence)},
        selected_identity=_identity(),
        source_anchor_sha="a" * 40,
    )

    assert matrix["statusCounts"] == {"pass": 1, "fail": 0, "not_run": 1}
    assert matrix["researchPrototypeStatus"] == "pass"
    assert matrix["firstUnmetRequirement"] is None


def test_stale_declared_pass_is_rejected_from_opened_payload(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.json"
    write_canonical_json(
        evidence,
        {"executed": False, "declaredPass": True, "packageDigest": _digest("package")},
    )
    matrix = evaluate_research_matrix(
        tmp_path,
        registry=_registry(),
        evidence_bindings={"fixture": _binding(evidence)},
        selected_identity=_identity(),
        source_anchor_sha="b" * 40,
    )

    assert matrix["rows"][0]["status"] == "fail"
    assert "evidence_predicate_failed" in matrix["rows"][0]["reasonCode"]
    assert matrix["researchPrototypeStatus"] == "partial"


def test_deleted_executed_evidence_is_fail_not_not_run(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.json"
    write_canonical_json(evidence, {"executed": True, "packageDigest": _digest("package")})
    binding = _binding(evidence)
    evidence.unlink()
    matrix = evaluate_research_matrix(
        tmp_path,
        registry=_registry(),
        evidence_bindings={"fixture": binding},
        selected_identity=_identity(),
        source_anchor_sha="c" * 40,
    )

    assert matrix["rows"][0]["status"] == "fail"
    assert matrix["rows"][0]["reasonCode"] == "evidence_artifact_missing:fixture"


def test_swapped_cross_package_evidence_fails_identity_join(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.json"
    write_canonical_json(
        evidence,
        {"executed": True, "declaredPass": True, "packageDigest": _digest("other")},
    )
    matrix = evaluate_research_matrix(
        tmp_path,
        registry=_registry(),
        evidence_bindings={"fixture": _binding(evidence)},
        selected_identity=_identity(),
        source_anchor_sha="d" * 40,
    )

    assert matrix["rows"][0]["status"] == "fail"
    assert "package_join" in matrix["rows"][0]["reasonCode"]


def test_mutation_with_preserved_hash_declaration_still_fails_payload_predicate(
    tmp_path: Path,
) -> None:
    evidence = tmp_path / "evidence.json"
    write_canonical_json(evidence, {"executed": True, "packageDigest": _digest("package")})
    binding = _binding(evidence)
    mutated = deepcopy(read_json(evidence))
    assert isinstance(mutated, dict)
    mutated["executed"] = False
    write_canonical_json(evidence, mutated)
    binding["sha256"] = canonical_artifact_sha256(evidence)
    matrix = evaluate_research_matrix(
        tmp_path,
        registry=_registry(),
        evidence_bindings={"fixture": binding},
        selected_identity=_identity(),
        source_anchor_sha="e" * 40,
    )

    assert matrix["rows"][0]["status"] == "fail"


def test_artifact_hash_is_identical_for_lf_and_crlf_checkout_bytes(tmp_path: Path) -> None:
    lf = tmp_path / "lf.json"
    crlf = tmp_path / "crlf.json"
    lf.write_bytes(b'{"executed":true}\n')
    crlf.write_bytes(b'{"executed":true}\r\n')

    assert canonical_artifact_sha256(lf) == canonical_artifact_sha256(crlf)


def test_portable_matrix_rejects_private_evidence_binding(tmp_path: Path) -> None:
    evidence = tmp_path / "private.json"
    write_canonical_json(evidence, {"executed": True, "packageDigest": _digest("package")})
    binding = _binding(evidence)
    binding["classification"] = "private_restricted"
    matrix = evaluate_research_matrix(
        tmp_path,
        registry=_registry(),
        evidence_bindings={"fixture": binding},
        selected_identity=_identity(),
        source_anchor_sha="f" * 40,
    )

    assert matrix["rows"][0]["status"] == "fail"
    assert "portable_evidence_classification_invalid" in matrix["rows"][0]["reasonCode"]
