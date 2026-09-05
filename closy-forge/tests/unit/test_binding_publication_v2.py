from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from closy_forge.manual_provider_binding_v2.evaluation import (
    BASELINE_SOURCES,
    EXTRA_CASES,
    UNIT_A_FAMILIES,
    _baseline_metrics,
    _report,
    derive_gates,
    failed_rows,
    protocol_document,
    write_extra_input,
)
from closy_forge.manual_provider_binding_v2.package import build_package_v2, digest_json
from closy_forge.package_io.canonical_json import (
    read_json,
    write_canonical_json,
    write_canonical_text,
)
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.security.evidence_hygiene import scan_evidence_files


def _module() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts/publish_binding_v2.py"
    spec = importlib.util.spec_from_file_location("binding_publication_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _save(root: Path, result: dict[str, Any], protocol: dict[str, Any]) -> None:
    result.pop("resultDigest", None)
    result["resultDigest"] = digest_json(result)
    write_canonical_json(root / "result.json", result)
    write_canonical_json(root / "baseline_rows.json", result["baselineRows"])
    write_canonical_json(
        root / "checkpoint.json",
        {
            "identities": {
                key: result[key] for key in ("protocolDigest", "sourceDigest", "inputDigest")
            },
            "active": None,
            "attempts": result["packageAttempts"],
            "extras": result["extras"],
            "unitA": result["unitACompatibility"],
        },
    )
    write_canonical_text(root / "report.md", _report(result))


def _evaluation(root: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, dict[str, Any]]:
    module = _module()
    root.mkdir()
    protocol = protocol_document(Path(module.FORGE))
    sources = {"src/closure_fixture.py": "a" * 64}
    inputs = {
        "sourceRoot": str((root / "old_inputs").resolve()),
        "unitARoot": str((root / "unit_a_inputs").resolve()),
        "files": [],
    }
    monkeypatch.setattr(module, "source_inventory", lambda _: sources)
    monkeypatch.setattr(module, "input_inventory", lambda *_: inputs)
    attempts: list[dict[str, Any]] = [
        {
            "scope": "baseline",
            "repeat": repeat,
            "sourceId": sid,
            "family": family,
            "status": "fail",
            "error": "retained_fixture_failure",
            "rows": failed_rows(sid, family, "retained_fixture_failure"),
        }
        for repeat in (1, 2)
        for sid, family in BASELINE_SOURCES
    ]
    first = sorted(attempts[:9], key=lambda row: row["sourceId"])
    rows = [row for attempt in first for row in attempt["rows"]]
    extras = []
    for case in protocol["extraCases"]:
        reject = case["expected"] == "reject"
        reason = "ValueError:" + case.get("expectedReason", "retained_failure")
        extras.append(
            {
                **case,
                "status": "pass" if reject else "fail",
                "outcome": "rejected",
                "reason": reason,
                "rows": []
                if reject
                else failed_rows(case["caseId"], "development_two_panel_shell", reason),
            }
        )
    metrics = _baseline_metrics(first, False)
    result = {
        "schemaVersion": 2,
        "version": "closy.manual_provider_binding_v2.result.v2",
        "scope": "manual_provider_binding_v2_development",
        "protocolDigest": digest_json(protocol),
        "sourceDigest": digest_json(sources),
        "inputDigest": digest_json(inputs),
        "status": "fail",
        "baselineStatus": "fail",
        "sourceAndInputsUnchanged": True,
        "baselineRowDenominator": 99,
        "baselineRows": rows,
        "metrics": metrics,
        "gates": derive_gates(protocol, metrics),
        "baselinePassedRows": 0,
        "baselineFailedRows": 99,
        "packageAttempts": attempts,
        "extras": extras,
        "extraCaseDenominator": 7,
        "extraPassedCases": 3,
        "extraFailedCases": 4,
        "extraPositiveRowDenominator": 44,
        "extraPositiveRows": [row for extra in extras for row in extra["rows"]],
        "unitACompatibility": [
            {"family": family, "status": "not_run", "reason": "fixture_unavailable"}
            for family in UNIT_A_FAMILIES
        ],
        "otherFamilies": protocol["otherUnitAFamilies"],
        "limitsUnchanged": True,
        "scientificQualification": False,
        "globalC3Complete": False,
        "physicalMobileLatency": "not_run",
        "physicalMobileMemory": "not_run",
    }
    write_canonical_json(root / "protocol.json", protocol)
    write_canonical_json(
        root / "source_inventory.json",
        {
            "head": "1" * 40,
            "files": sources,
            "digest": digest_json(sources),
        },
    )
    write_canonical_json(root / "input_inventory.json", {**inputs, "digest": digest_json(inputs)})
    _save(root, result, protocol)
    return module, result


def test_wrapped_inventories_and_failed_results_publish_without_promoting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "evaluation"
    module, _ = _evaluation(root, monkeypatch)
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    output = tmp_path / "published"
    manifest = module.publish(root, output)
    assert manifest["evaluationStatus"] == manifest["baselineStatus"] == "fail"
    assert manifest["headEqualityRequired"] is False
    assert manifest["sourceHeadAtEvaluationStart"] == "1" * 40
    assert manifest["motionGenerationReexecuted"] is False
    assert manifest["scientificQualification"] is False
    for row in manifest["files"]:
        assert sha256_file(output / row["path"]) == row["sha256"]
    for name in ("source_inventory.json", "result.json"):
        assert (output / name).read_bytes() == before[name]
    projection = read_json(output / "input_inventory.json")
    assert "digest" not in projection
    assert projection["originalInventory"]["sha256"] == sha256_bytes(before["input_inventory.json"])
    assert (
        projection["originalInventory"]["inputDigest"]
        == read_json(root / "result.json")["inputDigest"]
    )
    assert projection["originalInventory"]["publishedBytesAreOriginal"] is False
    assert projection["files"] == read_json(root / "input_inventory.json")["files"]
    assert (
        module._identity(projection, "projectionDigest")
        != projection["originalInventory"]["inputDigest"]
    )
    assert scan_evidence_files(sorted(output.iterdir())) == {}
    assert {p.name: p.read_bytes() for p in root.iterdir()} == before
    assert len(read_json(output / "package_index.json")) == 25
    with pytest.raises(ValueError, match="fresh_destination"):
        module.publish(root, output)


@pytest.mark.parametrize(
    ("relative", "expected"),
    [
        ("workspace/forge/.tmp/evaluation", "forge-relative/.tmp/evaluation"),
        ("workspace/other/input", "workspace-relative/other/input"),
        ("outside/input", "external-local/input"),
    ],
)
def test_portable_location_has_explicit_base_or_redacted_external_label(
    tmp_path: Path, relative: str, expected: str
) -> None:
    assert (
        _module()._portable_location(tmp_path / relative, tmp_path / "workspace/forge", "input")
        == expected
    )


def test_actual_published_evidence_is_portable_and_all_hashes_verify() -> None:
    module = _module()
    root = Path(module.FORGE) / "docs/evidence/manual_provider_binding_v2_development"
    manifest = read_json(root / "publication_manifest.json")
    assert manifest["version"] == module.VERSION
    module._identity(manifest, "identity")
    assert sorted(p.name for p in root.iterdir()) == sorted(
        [row["path"] for row in manifest["files"]] + ["publication_manifest.json"]
    )
    assert len(manifest["files"]) == 7
    for row in manifest["files"]:
        assert (root / row["path"]).stat().st_size == row["byteSize"]
        assert sha256_file(root / row["path"]) == row["sha256"]
    projection = read_json(root / "input_inventory.json")
    module._identity(projection, "projectionDigest")
    original = projection["originalInventory"]
    assert "digest" not in projection
    assert original["publishedBytesAreOriginal"] is False
    assert original["inputDigest"] == read_json(root / "result.json")["inputDigest"]
    assert original["inputDigest"] != projection["projectionDigest"]
    assert len(original["sha256"]) == 64 and original["byteSize"] > 0
    assert manifest["sourceEvaluation"] == "forge-relative/.tmp/binding-final-v2"
    assert projection["sourceRoot"] == "forge-relative/docs/evidence/manual_provider_c3_v1/packages"
    assert projection["unitARoot"] == "forge-relative/.tmp/family-final-v2/build1"
    assert scan_evidence_files(sorted(root.iterdir())) == {}


def test_path_leak_rejected_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "evaluation"
    module, _ = _evaluation(root, monkeypatch)
    monkeypatch.setattr(module, "_portable_location", lambda *_: "Z:\\local\\evaluation")
    with pytest.raises(ValueError, match="evidence_path_or_secret_leak"):
        module.publish(root, tmp_path / "out")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    "fault",
    [
        "result_digest",
        "source_digest",
        "input_digest",
        "missing",
        "checkpoint_active",
        "checkpoint_rows",
        "baseline_file",
        "report",
        "protocol",
        "source_current",
        "inputs_current",
    ],
)
def test_saved_document_corruption_rejected_before_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    root = tmp_path / "evaluation"
    module, _ = _evaluation(root, monkeypatch)
    if fault == "missing":
        (root / "report.md").unlink()
    elif fault == "report":
        (root / "report.md").write_bytes(b"All passed")
    elif fault == "baseline_file":
        write_canonical_json(root / "baseline_rows.json", [])
    elif fault == "source_current":
        monkeypatch.setattr(module, "source_inventory", lambda _: {})
    elif fault == "inputs_current":
        monkeypatch.setattr(module, "input_inventory", lambda *_: {})
    else:
        name, field, value = {
            "result_digest": ("result.json", "resultDigest", "0" * 64),
            "source_digest": ("source_inventory.json", "digest", "0" * 64),
            "input_digest": ("input_inventory.json", "digest", "0" * 64),
            "checkpoint_active": ("checkpoint.json", "active", {"scope": "baseline"}),
            "checkpoint_rows": ("checkpoint.json", "attempts", []),
            "protocol": ("protocol.json", "restLimitMeters", 0.09),
        }[fault]
        doc = read_json(root / name)
        doc[field] = value
        write_canonical_json(root / name, doc)
    with pytest.raises(ValueError):
        module.publish(root, tmp_path / "out")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate_attempt",
        "missing_attempt",
        "state",
        "family",
        "metrics",
        "gate",
        "baseline_count",
        "status",
        "scope",
        "extra_count",
        "negative_reason",
        "extra_duplicate",
        "unit_a",
    ],
)
def test_rehashed_but_inconsistent_rows_gates_status_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    root = tmp_path / "evaluation"
    module, result = _evaluation(root, monkeypatch)
    if fault == "duplicate_attempt":
        result["packageAttempts"][1] = deepcopy(result["packageAttempts"][0])
    elif fault == "missing_attempt":
        result["packageAttempts"].pop()
    elif fault == "state":
        result["packageAttempts"][0]["rows"][1]["stateId"] = "neutral"
    elif fault == "family":
        result["packageAttempts"][0]["rows"][0]["family"] = "wrong"
    elif fault == "metrics":
        result["metrics"]["deterministicTwoBuilds"] = True
    elif fault == "gate":
        result["gates"][8]["status"] = "pass"
    elif fault == "baseline_count":
        result["baselinePassedRows"] = 99
    elif fault == "status":
        result["status"] = "pass"
    elif fault == "scope":
        result["scientificQualification"] = True
    elif fault == "extra_count":
        result["extraPassedCases"] = 7
    elif fault == "negative_reason":
        result["extras"][-1]["reason"] = "ValueError:unrelated"
    elif fault == "extra_duplicate":
        result["extras"][1] = deepcopy(result["extras"][0])
    else:
        result["unitACompatibility"][0]["status"] = "pass"
    _save(root, result, read_json(root / "protocol.json"))
    with pytest.raises(ValueError):
        module.publish(root, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def _tiny(root: Path) -> tuple[Path, dict[str, Any]]:
    clean, semantic = write_extra_input({**EXTRA_CASES[3], "rows": 5, "columns": 5}, root / "input")
    output = root / "package"
    result = build_package_v2(clean, semantic, output, source_id="tiny", family="development_shell")
    return output, result


def _rehash(root: Path, declared: dict[str, Any]) -> None:
    manifest = read_json(root / "manifest.json")
    manifest["inventory"] = [
        {
            "path": p.relative_to(root).as_posix(),
            "bytes": p.stat().st_size,
            "sha256": sha256_file(p),
        }
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.name != "manifest.json"
    ]
    # Include nested motion/manifest.json: only the root manifest is excluded.
    motion = root / "motion/manifest.json"
    manifest["inventory"].append(
        {
            "path": "motion/manifest.json",
            "bytes": motion.stat().st_size,
            "sha256": sha256_file(motion),
        }
    )
    manifest["inventory"].sort(key=lambda row: row["path"])
    manifest.pop("packageDigest")
    manifest["packageDigest"] = digest_json(manifest)
    write_canonical_json(root / "manifest.json", manifest)
    declared["packageDigest"] = manifest["packageDigest"]
    declared["packageBytes"] = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


def test_actual_tiny_saved_package_uses_bytes_and_independent_rest(tmp_path: Path) -> None:
    root, declared = _tiny(tmp_path)
    module = _module()
    receipt = module.validate_saved_package(
        root, declared, source_id="tiny", family="development_shell"
    )
    assert receipt["independentRest"]["independentReconstruction"] is True
    assert receipt["independentRest"]["restMaximumErrorMeters"] < 2e-6
    assert len(declared["rows"]) == 11
    assert all("bytes" in row and "byteSize" not in row for row in receipt["manifest"]["inventory"])


@pytest.mark.parametrize(
    "fault",
    [
        "payload",
        "missing",
        "extra",
        "manifest",
        "association",
        "rest_summary",
        "rest_status",
        "motion_metric",
        "row_status",
        "runtime",
        "inventory_duplicate",
    ],
)
def test_package_corruption_and_rehashed_forgery_rejected(tmp_path: Path, fault: str) -> None:
    root, declared = _tiny(tmp_path)
    if fault == "payload":
        (root / "binding/local_frame_v2.bin").write_bytes(b"corrupt")
    elif fault == "missing":
        (root / "render/clean.glb").unlink()
    elif fault == "extra":
        (root / "unlisted.bin").write_bytes(b"unlisted")
    elif fault == "association":
        declared["packageDigest"] = "0" * 64
    elif fault in ("rest_summary", "rest_status"):
        rest = read_json(root / "reports/rest.json")
        rest["restMaximumErrorMeters" if fault == "rest_summary" else "status"] = (
            0.007 if fault == "rest_summary" else "fail"
        )
        write_canonical_json(root / "reports/rest.json", rest)
        declared["rest"] = rest
        _rehash(root, declared)
    elif fault in ("motion_metric", "row_status"):
        motion = read_json(root / "motion/manifest.json")
        motion["rows"][0]["maximumErrorMeters" if fault == "motion_metric" else "status"] = (
            0.019 if fault == "motion_metric" else "fail"
        )
        declared["rows"] = motion["rows"]
        write_canonical_json(root / "motion/manifest.json", motion)
        _rehash(root, declared)
    else:
        manifest = read_json(root / "manifest.json")
        if fault == "manifest":
            manifest["family"] = "different"
        elif fault == "runtime":
            manifest["runtime"]["binding"] = "../../escape.bin"
        else:
            manifest["inventory"].append(manifest["inventory"][0])
        manifest.pop("packageDigest")
        manifest["packageDigest"] = digest_json(manifest)
        write_canonical_json(root / "manifest.json", manifest)
        declared["packageDigest"] = manifest["packageDigest"]
    with pytest.raises(ValueError):
        _module().validate_saved_package(
            root, declared, source_id="tiny", family="development_shell"
        )


def test_publisher_has_no_motion_generation_or_evaluator_calls() -> None:
    import ast

    module = _module()
    tree = ast.parse(Path(module.__file__ or "").read_text(encoding="utf-8"))
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not calls & {
        "run_evaluation",
        "build_package_v2",
        "check_package_v2",
        "deform_simulation",
        "independently_deform_dense_reference",
        "reconstruct_v2",
    }
