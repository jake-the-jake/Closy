from __future__ import annotations

import hashlib
import json
import zlib
from pathlib import Path
from typing import Any

import pytest

from closy_forge.geometry.glb_io import read_glb_meshset
from closy_forge.manual_provider_binding_v2 import evaluation
from closy_forge.manual_provider_binding_v2.evaluation import (
    BASELINE_SOURCES,
    EXTRA_CASES,
    _baseline_metrics,
    derive_gates,
    failed_rows,
    protocol_document,
    source_inventory,
    write_extra_input,
)
from closy_forge.manual_provider_binding_v2.package import (
    RUNTIME_PATHS,
    build_package_v2,
    check_package_v2,
    digest_json,
    read_positions,
    semantic_summary,
)
from closy_forge.manual_provider_c3_v1.states import MOTION_STATES
from closy_forge.package_io.canonical_json import read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_file


def _tiny_package(root: Path, *, states: int = 2) -> dict[str, Any]:
    case = {**EXTRA_CASES[3], "columns": 5, "rows": 5}
    clean, semantics = write_extra_input(case, root / "input")
    return build_package_v2(
        clean,
        semantics,
        root / "package",
        source_id="tiny-authored",
        family="development_shell",
        motion_states=MOTION_STATES[:states],
    )


def _rehash(root: Path) -> None:
    manifest = read_json(root / "manifest.json")
    manifest["inventory"] = [
        {
            "path": p.relative_to(root).as_posix(),
            "bytes": p.stat().st_size,
            "sha256": sha256_file(p),
        }
        for p in sorted(root.rglob("*"))
        if p.is_file() and p != root / "manifest.json"
    ]
    manifest.pop("packageDigest")
    manifest["packageDigest"] = digest_json(manifest)
    write_canonical_json(root / "manifest.json", manifest)


def test_tiny_package_persists_real_geometry_motion_and_paired_seams(tmp_path: Path) -> None:
    result = _tiny_package(tmp_path)
    assert result["status"] == "pass"
    assert result["rest"]["restMaximumErrorMeters"] < 2e-7
    assert result["packageBytes"] < 2097152
    assert len(result["rows"]) == 2
    assert result["rows"][0]["pairedSeams"]["pairCount"] == 10
    assert result["rows"][0]["pairedSeams"]["status"] == "measured"
    assert "maximumSeamCrackDeltaMeters" not in result["rows"][0]
    manifest = read_json(tmp_path / "package/manifest.json")
    assert manifest["runtime"] == RUNTIME_PATHS
    assert len({r["path"] for r in manifest["inventory"]}) == len(manifest["inventory"])
    assert check_package_v2(tmp_path / "package")["packageDigest"] == result["packageDigest"]
    assert (tmp_path / "package/render/clean.glb").read_bytes() == (
        tmp_path / "input/clean.glb"
    ).read_bytes()
    assert (tmp_path / "package/semantic/source.json").read_bytes() == (
        tmp_path / "input/semantics.json"
    ).read_bytes()


def test_two_tiny_builds_are_byte_deterministic(tmp_path: Path) -> None:
    first = _tiny_package(tmp_path / "first", states=1)
    second = _tiny_package(tmp_path / "second", states=1)
    assert first["packageDigest"] == second["packageDigest"]


@pytest.mark.parametrize("report", ["binding", "rest"])
def test_rehashed_forged_rest_summary_is_rejected(tmp_path: Path, report: str) -> None:
    _tiny_package(tmp_path, states=1)
    root = tmp_path / "package"
    document = read_json(root / f"reports/{report}.json")
    document["restMaximumErrorMeters"] = 0.007
    document["restP95ErrorMeters"] = 0.005
    write_canonical_json(root / f"reports/{report}.json", document)
    _rehash(root)
    with pytest.raises(ValueError, match="declared_rest_metric_mismatch"):
        check_package_v2(root)


def test_rehashed_fake_motion_payload_is_not_accepted(tmp_path: Path) -> None:
    _tiny_package(tmp_path, states=1)
    root = tmp_path / "package"
    motion = read_json(root / "motion/manifest.json")
    path = root / "motion/production_states.f32.zlib"
    raw = bytearray(zlib.decompress(path.read_bytes()))
    raw[3] ^= 1
    path.write_bytes(zlib.compress(bytes(raw)))
    motion["payloads"]["production"]["rawSha256"] = hashlib.sha256(raw).hexdigest()
    write_canonical_json(root / "motion/manifest.json", motion)
    _rehash(root)
    with pytest.raises(ValueError, match="motion_not_derived_from_serialized_geometry"):
        check_package_v2(root)


def test_runtime_path_redirection_and_motion_bomb_rejected(tmp_path: Path) -> None:
    _tiny_package(tmp_path, states=1)
    root = tmp_path / "package"
    manifest = read_json(root / "manifest.json")
    manifest["runtime"]["binding"] = "../../different.bin"
    manifest.pop("packageDigest")
    manifest["packageDigest"] = digest_json(manifest)
    write_canonical_json(root / "manifest.json", manifest)
    with pytest.raises(ValueError, match="runtime_contract_invalid"):
        check_package_v2(root)
    with pytest.raises(ValueError, match="motion_budget"):
        read_positions(
            root / "motion/cage_states.f32.zlib", {"stateCount": 11, "vertexCount": 2**32}
        )


def test_absent_pair_correspondence_never_claims_physical_seam_measurement(tmp_path: Path) -> None:
    clean, semantics = write_extra_input(
        {**EXTRA_CASES[0], "columns": 5, "rows": 5}, tmp_path / "input"
    )
    summary = semantic_summary(read_glb_meshset(clean), read_json(semantics))
    assert summary["pairedSeamAvailability"] == "not_available"
    result = build_package_v2(
        clean,
        semantics,
        tmp_path / "package",
        source_id="no-pairs",
        family="development_shell",
        motion_states=MOTION_STATES[:1],
    )
    assert result["rows"][0]["pairedSeams"]["maximumGapMeters"] is None
    assert result["rows"][0]["pairedSeams"]["status"] == "not_available"


@pytest.mark.parametrize("case", EXTRA_CASES[4:], ids=lambda c: c["caseId"])
def test_predeclared_tiny_negative_cases_are_typed_rejections(
    tmp_path: Path, case: dict[str, Any]
) -> None:
    clean, semantics = write_extra_input(case, tmp_path / "input")
    with pytest.raises(ValueError, match=case["expectedReason"]):
        build_package_v2(
            clean,
            semantics,
            tmp_path / "package",
            source_id=case["caseId"],
            family="development_shell",
            motion_states=MOTION_STATES[:1],
        )
    assert (tmp_path / "package/render/clean.glb").is_file()


@pytest.mark.parametrize("case", EXTRA_CASES[:4], ids=lambda c: c["caseId"])
def test_predeclared_small_positive_rest_cases(tmp_path: Path, case: dict[str, Any]) -> None:
    clean, semantics = write_extra_input(case, tmp_path / "input")
    result = build_package_v2(
        clean,
        semantics,
        tmp_path / "package",
        source_id=case["caseId"],
        family="development_shell",
        motion_states=MOTION_STATES,
    )
    assert result["rest"]["status"] == "pass"
    assert result["motionStateCount"] == 11
    assert result["status"] == "pass"
    assert all(row["maximumErrorMeters"] <= 0.02 for row in result["rows"])
    assert all(row["p95ErrorMeters"] <= 0.006 for row in result["rows"])


def test_protocol_preserves_v1_limits_and_declares_separate_denominators() -> None:
    forge = Path(__file__).resolve().parents[2]
    protocol = protocol_document(forge)
    assert len(protocol["baseline"]) == 9 and protocol["baselineRowCount"] == 99
    assert len(protocol["states"]) == 11 and protocol["cleanBuildCount"] == 2
    assert protocol["extraPositiveMotionRows"] == 44
    assert protocol["extraExpectedRejections"] == 3
    assert protocol["cageRefinement"]["version"] == "broad_metric_cell.v1"
    assert len(protocol["retainedDevelopmentFailures"]) == 2
    thresholds = {r["gateId"]: r["threshold"] for r in protocol["gates"]}
    assert thresholds["MPC3-09"] == 0.008 and thresholds["MPC3-10"] == 0.02
    assert thresholds["MPC3-11"] == 0.006 and thresholds["MPC3-12"] == 0.012
    assert thresholds["MPC3-16"] == 2097152
    assert len(protocol["gates"]) == 17
    assert "legacy_uv_extrema" in protocol["gates"][11]["scope"]


def test_failed_cases_remain_in_99_row_denominator_and_fail_numeric_gates() -> None:
    protocol = protocol_document(Path(__file__).resolve().parents[2])
    attempts = [
        {"sourceId": s, "family": f, "status": "fail", "rows": failed_rows(s, f, "failure")}
        for s, f in BASELINE_SOURCES
    ]
    metrics = _baseline_metrics(attempts, False)
    assert metrics["evaluationRowCount"] == 99 and metrics["motionStateCount"] == 11
    assert metrics["maximumRestErrorMeters"] is None
    gates = {g["gateId"]: g for g in derive_gates(protocol, metrics)}
    assert gates["MPC3-03"]["status"] == "pass"
    assert gates["MPC3-09"]["status"] == gates["MPC3-10"]["status"] == "fail"


def test_static_source_inventory_covers_codec_checker_and_immutable_reference() -> None:
    files = source_inventory(Path(__file__).resolve().parents[2])
    for suffix in (
        "manual_provider_binding_v2/binding.py",
        "manual_provider_binding_v2/checker.py",
        "manual_provider_binding_v2/package.py",
        "manual_provider_binding_v2/evaluation.py",
        "manual_provider_c3_v1/reference_deformation.py",
        "geometry/glb_io.py",
    ):
        assert "src/closy_forge/" + suffix in files
    assert all(len(value) == 64 for value in files.values())
    json.dumps(files, allow_nan=False)


def test_checkpoint_precedes_work_and_resume_retains_interrupted_denominator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forge = Path(__file__).resolve().parents[2]
    source, unit_a, output = (
        tmp_path / "missing-source",
        tmp_path / "missing-unit-a",
        tmp_path / "run",
    )
    original_verify = evaluation.verify_saved_source

    def interrupt(*args: object, **kwargs: object) -> None:
        assert (output / "protocol.json").is_file()
        assert (output / "source_inventory.json").is_file()
        assert (output / "input_inventory.json").is_file()
        raise KeyboardInterrupt("simulated interruption before geometry work")

    def no_extra_geometry(*args: object, **kwargs: object) -> None:
        raise ValueError("injected_extra_failure_no_motion_evaluation")

    monkeypatch.setattr(evaluation, "verify_saved_source", interrupt)
    monkeypatch.setattr(evaluation, "write_extra_input", no_extra_geometry)
    with pytest.raises(KeyboardInterrupt):
        evaluation.run_evaluation(output, source_root=source, unit_a_root=unit_a, forge_root=forge)
    assert read_json(output / "checkpoint.json")["active"]["sourceId"] == BASELINE_SOURCES[0][0]
    monkeypatch.setattr(evaluation, "verify_saved_source", original_verify)
    result = evaluation.run_evaluation(
        output, source_root=source, unit_a_root=unit_a, forge_root=forge, resume=True
    )
    assert len(result["packageAttempts"]) == 18
    assert result["baselineFailedRows"] == len(result["baselineRows"]) == 99
    assert len(result["extraPositiveRows"]) == 44
    assert "interrupted_partial" in result["packageAttempts"][0]["error"]
    assert result["status"] == "fail"
    assert (
        evaluation.run_evaluation(
            output, source_root=source, unit_a_root=unit_a, forge_root=forge, resume=True
        )["resultDigest"]
        == result["resultDigest"]
    )
    changed = source / BASELINE_SOURCES[0][0] / "reports/semantics.json"
    write_canonical_json(changed, {})
    with pytest.raises(ValueError, match="resume_identity_mismatch"):
        evaluation.run_evaluation(
            output, source_root=source, unit_a_root=unit_a, forge_root=forge, resume=True
        )


def test_saved_source_manifest_validation_is_read_only() -> None:
    forge = Path(__file__).resolve().parents[2]
    root = forge / "docs/evidence/manual_provider_c3_v1/packages/manual-tshirt-01"
    before = sha256_file(root / "manifest.json")
    manifest = evaluation.verify_saved_source(root, "tshirt")
    assert manifest["family"] == "tshirt"
    assert sha256_file(root / "manifest.json") == before
