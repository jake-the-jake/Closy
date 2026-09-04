from __future__ import annotations

import json
from pathlib import Path

import pytest

from closy_forge.solver_material_v2.common import canonical_digest, read_json
from closy_forge.solver_material_v2.independent_checker import check_publication_paths
from closy_forge.solver_material_v2.protocol import validate_protocol
from closy_forge.solver_material_v2.publication import verify_source_freeze

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = ROOT.parent
FIXTURE = ROOT / "fixtures/solver_material_v2"
EVIDENCE = ROOT / "docs/evidence/solver_material_v2"


def test_checked_in_protocol_and_development_studies_are_fresh() -> None:
    protocol = read_json(FIXTURE / "protocol.json")
    assert validate_protocol(protocol) == []
    studies = read_json(EVIDENCE / "development_studies.json")
    assert studies["normalizedRoundTrip"]["passed"] is True
    assert all(row["active"] for row in studies["causalInterventions"])
    assert studies["twoCleanCanonicalBuilds"]["byteIdentical"] is True


def test_legacy_v1_inventory_matches_inherited_bytes() -> None:
    inventory = read_json(EVIDENCE / "legacy_byte_inventory.json")
    assert inventory["semanticsChanged"] is False
    for row in inventory["files"]:
        payload = (REPOSITORY / row["path"]).read_bytes()
        import hashlib

        assert hashlib.sha256(payload).hexdigest() == row["sha256"]


def test_source_freeze_is_enforced_when_present() -> None:
    path = FIXTURE / "source_freeze.json"
    if not path.exists():
        pytest.skip("source freeze is created only after source commit and exact-head CI")
    assert verify_source_freeze(REPOSITORY, read_json(path)) == []


def test_published_result_reproduces_without_estimator_rerun_when_present() -> None:
    envelope = EVIDENCE / "canonical_result_envelope.json"
    if not envelope.exists():
        pytest.skip("single-use publication has not run")
    checker = check_publication_paths(
        FIXTURE / "protocol.json",
        FIXTURE / "locked_public",
        EVIDENCE / "contestant_output.json",
        envelope,
        EVIDENCE / "synthetic_truth_disclosure.json",
        EVIDENCE / "development_studies.json",
    )
    assert checker["terminalOutcome"] == "passed"
    assert checker["estimatorRerun"] is False
    publication = read_json(envelope)
    assert publication["resultDigest"] == canonical_digest(publication, "resultDigest")


def test_schemas_are_valid_json_objects() -> None:
    for path in sorted((ROOT / "schemas/solver_material_v2").glob("*.json")):
        assert isinstance(json.loads(path.read_text(encoding="utf-8")), dict)
