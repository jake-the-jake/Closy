from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from closy_forge.binding.binary_format import read_binding
from closy_forge.manual_provider_c3_v1.common import (
    digest_value,
    read_json,
    validate_embedded_digest,
)
from closy_forge.manual_provider_c3_v1.corpus import load_locked_sources
from closy_forge.manual_provider_c3_v1.independent_checker import check_publication
from closy_forge.manual_provider_c3_v1.package import build_provider_package, decode_positions
from closy_forge.manual_provider_c3_v1.source_freeze import verify_source_freeze
from closy_forge.manual_provider_c3_v1.topology import clean_and_retopologize, semantic_receipt

FORGE_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = FORGE_ROOT.parent
FIXTURE_ROOT = FORGE_ROOT / "fixtures" / "manual_provider_c3_v1"
PUBLICATION_ROOT = FORGE_ROOT / "docs" / "evidence" / "manual_provider_c3_v1"


def test_parent_verification_freezes_exact_pr64_test_authority() -> None:
    manifest = read_json(FIXTURE_ROOT / "parent_verification_manifest.json")
    expected_digest = manifest["manifestDigest"]
    digest_payload = dict(manifest)
    digest_payload.pop("manifestDigest")
    assert (
        hashlib.sha256(
            json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        == expected_digest
    )
    assert manifest["parentCommit"] == "b56c172fac076c47dd3ea101a024ab3793e4fe0d"
    assert manifest["parentTree"] == "a240d37f9999b41ccb3cc7511ecb5e94428919e7"
    assert manifest["collectedTestCount"] == 1031
    assert len(manifest["collectedTestNodeIds"]) == 1031
    assert len(set(manifest["collectedTestNodeIds"])) == 1031
    assert manifest["workflow"]["requiredJobCount"] == 32


def test_raw_sources_are_nine_disjoint_project_authored_redistributable_shells() -> None:
    freeze, sources = load_locked_sources(FIXTURE_ROOT)
    assert freeze["benchmarkDenominator"]["requiredEvaluationRows"] == 99
    assert {source.family for source in sources} == {"tshirt", "sleeveless_top", "simple_skirt"}
    assert len({source.raw_asset_id for source in sources}) == 9
    assert (
        min(sum(len(part["vertices"]) for part in source.document["parts"]) for source in sources)
        >= 1_400
    )
    assert all(source.document["licence"]["spdx"] == "CC0-1.0" for source in sources)


def test_cleanup_executes_and_semantics_preserve_explicit_abstention() -> None:
    _, sources = load_locked_sources(FIXTURE_ROOT)
    for source in sources:
        clean, cleanup = clean_and_retopologize(source)
        semantics = semantic_receipt(source, cleanup)
        assert cleanup["rawTopology"]["degenerateTriangleCount"] == 2
        assert cleanup["rawTopology"]["duplicateOrientedTriangleCount"] == 2
        assert cleanup["operations"]["removedUnreferencedVertices"] == 4
        assert cleanup["cleanTopology"]["degenerateTriangleCount"] == 0
        assert cleanup["cleanTopology"]["duplicateOrientedTriangleCount"] == 0
        assert cleanup["cleanTopology"]["windingMismatchCount"] == 0
        assert cleanup["status"] == "pass"
        assert clean.vertex_count >= 1_400
        assert semantics["abstainedLabelCount"] == 1
        assert semantics["minimumAcceptedConfidence"] >= 0.9


@pytest.mark.parametrize("source_index", [0, 3, 6])
def test_each_family_builds_real_glb_binding_and_eleven_motion_states(
    tmp_path: Path, source_index: int
) -> None:
    _, sources = load_locked_sources(FIXTURE_ROOT)
    package_root = tmp_path / sources[source_index].source_id
    report = build_provider_package(sources[source_index], package_root)
    manifest = read_json(package_root / "manifest.json")
    validate_embedded_digest(manifest, "packageDigest")
    binding = read_binding(package_root / "binding" / "hybrid_binding.bin")
    motion = read_json(package_root / "motion" / "manifest.json")
    production = decode_positions(
        package_root / "motion" / "production_states.f32.zlib",
        motion["stateCount"],
        motion["vertexCountPerState"],
    )
    assert len(production) == 11
    assert len(report["rows"]) == 11
    assert binding.records
    assert report["binding"]["coverage"] == 1.0
    assert report["binding"]["fallbackDistinct"] is True
    assert report["renderAudit"]["clean"]["hasVec4Tangents"] is True
    assert report["renderAudit"]["cleanGeometry"]["status"] == "pass"


def test_protocol_and_optional_source_freeze_are_self_consistent() -> None:
    protocol = read_json(FIXTURE_ROOT / "protocol.json")
    validate_embedded_digest(protocol, "protocolDigest")
    assert protocol["denominators"]["sourceCount"] == 9
    assert protocol["denominators"]["evaluationRowCount"] == 99
    assert protocol["executionPolicy"]["finalBenchmarkRuns"] == 1
    source_freeze_path = FIXTURE_ROOT / "source_freeze.json"
    if source_freeze_path.exists():
        verify_source_freeze(REPOSITORY, read_json(source_freeze_path))


def test_checked_in_publication_is_independently_recomputed_when_present() -> None:
    result_path = PUBLICATION_ROOT / "result.json"
    if not result_path.exists():
        pytest.skip("immutable manual-provider result is not published at the source checkpoint")
    result = read_json(result_path)
    validate_embedded_digest(result, "resultDigest")
    checker = check_publication(PUBLICATION_ROOT, result_path)
    committed = read_json(PUBLICATION_ROOT / "independent_checker.json")
    assert checker == committed
    assert result["denominators"]["evaluationRowCount"] == 99
    assert result["execution"]["benchmarkRunCount"] == 1
    assert result["claims"]["globalC3Complete"] is False


def test_portable_records_do_not_contain_host_paths() -> None:
    documents = list(FIXTURE_ROOT.rglob("*.json"))
    if PUBLICATION_ROOT.exists():
        documents.extend(PUBLICATION_ROOT.rglob("*.json"))
    for path in documents:
        text = path.read_text(encoding="utf-8")
        assert "E:\\" not in text
        assert "C:\\Users" not in text
        assert str(REPOSITORY) not in text
        json.loads(text)


def test_lineage_roles_are_distinct_by_construction() -> None:
    _, sources = load_locked_sources(FIXTURE_ROOT)
    clean, cleanup = clean_and_retopologize(sources[0])
    roles = [
        sources[0].raw_asset_id,
        cleanup["analyzedAssetId"],
        cleanup["proposedAssetId"],
        cleanup["cleanAssetId"],
        f"bound:{digest_value(clean.vertex_count)}",
        f"package:{sources[0].source_id}:manual-provider-c3-v1",
    ]
    assert len(set(roles)) == len(roles)
