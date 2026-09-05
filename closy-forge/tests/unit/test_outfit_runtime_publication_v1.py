from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/publish_outfit_runtime_v1.py"
spec = importlib.util.spec_from_file_location("outfit_saved_publication", SCRIPT)
assert spec and spec.loader
pub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pub)


def write(root: Path, rel: str, value: Any) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value if isinstance(value, bytes) else pub.canonical(value))


def signed(value: dict[str, Any], field: str) -> dict[str, Any]:
    return {**value, field: pub.digest(pub.canonical(value))}


def inventory(root: Path, paths: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "path": p,
            "bytes": (root / p).stat().st_size,
            "sha256": pub.digest((root / p).read_bytes()),
        }
        for p in paths
    ]


def tiny_roots(tmp_path: Path) -> tuple[dict[str, Path], Path, Path]:
    """Literal tiny failed records, not miniature geometry campaigns."""
    forge, family = tmp_path / "repo/forge", tmp_path / "family"
    write(forge, "anchor.py", b"# frozen\n")
    write(family, "anchor.json", {})
    sources = {"anchor.py": pub.digest((forge / "anchor.py").read_bytes())}
    roots = {s: tmp_path / s for s in pub.ROOT_FILES}
    for root in roots.values():
        root.mkdir(parents=True)
    p = {
        "version": "package_layering_matrix_v1",
        "stateDenominator": 40,
        "adjacentSampleDenominator": 30,
        "negativeDenominator": 13,
        "thresholds": {
            "binding_tolerance_m": 2e-6,
            "iterations": 12,
            "max_displacement_m": 0.045,
            "max_step_m": 0.004,
            "opening_length_drift": 0.1,
            "residual_m": 0.00016,
            "seam_budget_m": 0.008,
        },
        "positiveCases": [{"caseId": f"outfit{i:02d}", "layers": []} for i in range(1, 11)],
        "poseStates": [{"state_id": s} for s in pub.OUTFIT_STATES],
    }
    write(roots["outfit"], "protocol.json", p)
    rows = [
        {"caseId": c["caseId"], "pose": s, "terminal": "failed", "reason": "tiny_fixture"}
        for c in p["positiveCases"]
        for s in pub.OUTFIT_STATES
    ]
    adjacent = [
        {"caseId": c["caseId"], "from": a, "to": b, "terminal": "failed"}
        for c in p["positiveCases"]
        for a, b in zip(pub.OUTFIT_STATES, pub.OUTFIT_STATES[1:], strict=False)
    ]
    write(
        roots["outfit"],
        "result.json",
        {
            "protocolHash": pub.digest(pub.canonical(p)),
            "rows": rows,
            "denominator": 40,
            "qualityPassed": 0,
            "validGeometry": 0,
            "failed": 40,
            "adjacentSamples": adjacent,
            "negatives": [{"case": n, "terminal": "passed_rejection"} for n in pub.NEGATIVES],
            "sourcesUnchanged": True,
        },
    )
    write(roots["outfit"], "source_inventory.json", {"files": sources})
    write(roots["outfit"], "checkpoint.json", {"rows": rows})

    cases = [
        {
            "id": f"{family}-{profile}-build{build}",
            "case": family,
            "group": group,
            "profile": profile,
            "build": build,
        }
        for group, families in (("family", pub.FAMILIES), ("binding", ("B",)), ("outfit", ("O",)))
        for family in families
        for profile in pub.PROFILES
        for build in (1, 2)
    ]
    runtime_protocol = signed(
        {
            "sourceInventory": sources,
            "familyRows": 36,
            "poseRowsPerBuild": 4,
            "resumeRowsPerBuild": 3,
            "poseIds": list(pub.POSES),
            "cases": cases,
            "controlInventory": ["tests/unit/toy.py::test_tiny"],
        },
        "protocolIdentity",
    )
    rr = {c["id"]: {"status": "fail", "reason": "tiny_failure"} for c in cases}
    controls = {"status": "pass", "processExitCode": 0}
    pairs = [
        {"case": c["case"], "profile": c["profile"], "passed": False}
        for c in cases
        if c["build"] == 1
    ]
    write(roots["runtime"], "protocol.json", runtime_protocol)
    write(roots["runtime"], "checkpoint.json", {"rows": rr, "controls": controls})
    write(
        roots["runtime"],
        "result.json",
        {
            "protocolIdentity": runtime_protocol["protocolIdentity"],
            "sourceFresh": True,
            "rows": rr,
            "controls": controls,
            "determinism": pairs,
            "family": {"pass": 0, "fail": 36, "unknown": 0},
        },
    )
    write(
        roots["runtime"],
        "controls.xml",
        b'<testsuites><testsuite><testcase name="test_tiny"/></testsuite></testsuites>',
    )
    write(roots["runtime"], "controls.log", b"tiny fixture only\n")
    for identifier, row in rr.items():
        write(roots["runtime"], f"{identifier}/receipt.json", row)

    for scope in ("static", "prior_static"):
        write(
            roots[scope],
            "protocol.json",
            {"sourceEvaluation": {"anchor.json": pub.digest(pub.canonical({}))}},
        )
        write(roots[scope], "source_receipt.json", {"currentFiles": sources})
        write(
            roots[scope],
            "result.json",
            {
                "familyDenominator": 9,
                "rows": [{"family": f, "terminal": "failed"} for f in pub.FAMILIES],
                "passed": 0,
                "failed": 9,
                "notRun": 0,
                "stageCounts": {},
                "selectedCurrentFilesUnchanged": True,
                "sourceEvaluationUnchanged": True,
            },
        )
        write(
            roots[scope],
            "receipt_manifest.json",
            {
                "files": inventory(
                    roots[scope], ["protocol.json", "source_receipt.json", "result.json"]
                )
            },
        )

    binding = {
        "protocolDigest": pub.digest(pub.canonical({})),
        "sourceAndInputsUnchanged": True,
        "limitsUnchanged": True,
        "baselineRows": [{"status": "fail"} for _ in range(99)],
        "extraPositiveRows": [{"status": "fail"} for _ in range(44)],
        "extras": [{} for _ in range(7)],
        "gates": [{"status": "fail"} for _ in range(17)],
        "baselinePassedRows": 0,
        "baselineFailedRows": 99,
        "unitACompatibility": [],
        "sourceDigest": pub.digest(pub.canonical(sources)),
    }
    write(roots["binding"], "result.json", signed(binding, "resultDigest"))
    write(roots["binding"], "protocol.json", {})
    write(roots["binding"], "source_inventory.json", {"files": sources})
    write(roots["binding"], "input_inventory.json", {})
    write(
        roots["blueprint"],
        "blueprint_current.json",
        {
            "inventory": {"requirements": ["unchanged"]},
            "phaseOverview": {
                "scientificQualification": "blocked",
                "productReadiness": "not_ready",
                "newUnitOutcomes": {"A": {"pass": 54}, "B": "pending", "C": "pending"},
                "phases": [
                    {
                        "roadmapPhase": i,
                        "acceptanceStatus": "failed",
                        "unmetGates": "image/physical gate remains failed",
                    }
                    for i in range(15)
                ],
            },
        },
    )
    write(
        roots["demo"],
        "report.json",
        {
            "familyAudits": [{} for _ in range(9)],
            "outfitReady": False,
            "imageSource": "actual_serialized_geometry_cpu_raster_no_generated_visuals",
        },
    )
    write(roots["demo"], "outfit/report.json", {"ready": False})
    write(roots["demo"], "index.html", b"<html>tiny fixture</html>")
    for name in ("family_contact_sheet", "sleeve_before_after", "binding_before_after"):
        write(roots["demo"], f"inspection/{name}.png", b"\x89PNG\r\n\x1a\nfixture_not_rendered")
    files = [
        p.relative_to(roots["demo"]).as_posix() for p in roots["demo"].rglob("*") if p.is_file()
    ]
    write(roots["demo"], "output_inventory.json", inventory(roots["demo"], files))
    return roots, forge, family


def test_all_failed_tiny_receipts_publish_without_success_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roots, forge, family = tiny_roots(tmp_path)
    expected = pub.capture_expected(roots, forge)
    monkeypatch.setattr(pub, "audit_repository", lambda _: {"protectedBlobCount": 84})
    output = tmp_path / "published"
    manifest = pub.publish(
        roots,
        forge=forge,
        family_root=family,
        output=output,
        expected=expected,
        expected_hash=pub.digest(pub.canonical(expected)),
    )
    summary = pub.decode((output / "summary.json").read_bytes())
    assert summary["outcomes"]["outfit"]["qualityPassed"] == 0
    assert summary["outcomes"]["outfit"]["denominator"] == 40
    assert summary["outcomes"]["runtime"]["groups"]["family"]["fail"] == 36
    assert manifest["geometryReevaluated"] is False
    assert manifest["activePointerUpdated"] is False
    assert (output / "publication_manifest.json").is_file()
    assert not list(output.rglob("*.glb"))
    projected = pub.decode((output / "outfit/result.json").read_bytes())
    notice = projected.pop("_publicationProjection")
    original = (roots["outfit"] / "result.json").read_bytes()
    assert projected == pub.decode(original)
    assert notice["rawReceiptSha256"] == pub.digest(original)
    ledger = pub.decode((output / "projection_manifest.json").read_bytes())
    entry = next(r for r in ledger["receipts"] if r["path"] == "outfit/result.json")
    assert entry["rawReceiptSha256"] == pub.digest(original)
    assert entry["publishedProjectionSha256"] == pub.digest((output / entry["path"]).read_bytes())
    assert entry["rawReceiptSha256"] != entry["publishedProjectionSha256"]
    assert pub.scan_evidence_files(sorted([*output.rglob("*.json"), *output.rglob("*.md")])) == {}
    before = pub.decode((roots["blueprint"] / "blueprint_current.json").read_bytes())
    after = pub.decode((output / "blueprint_current.json").read_bytes())
    assert before["inventory"] == after["inventory"]
    for old, new in zip(
        before["phaseOverview"]["phases"], after["phaseOverview"]["phases"], strict=True
    ):
        assert all(new[k] == v for k, v in old.items())
        assert ("currentBCDerivedOutcome" in new) == (old["roadmapPhase"] in {6, 8, 10, 12, 13})
    assert after["phaseOverview"]["scientificQualification"] == "blocked"
    with pytest.raises(ValueError, match="must_be_fresh"):
        pub.publish(
            roots,
            forge=forge,
            family_root=family,
            output=output,
            expected=expected,
            expected_hash=pub.digest(pub.canonical(expected)),
        )


@pytest.mark.parametrize(
    "scope,relative",
    [
        ("outfit", "protocol.json"),
        ("runtime", "result.json"),
        ("static", "source_receipt.json"),
        ("demo", "inspection/family_contact_sheet.png"),
    ],
)
def test_snapshot_rejects_changed_protocol_result_source_or_image(
    tmp_path: Path, scope: str, relative: str
) -> None:
    roots, forge, _ = tiny_roots(tmp_path)
    expected = pub.capture_expected(roots, forge)
    (roots[scope] / relative).write_bytes(b"changed")
    with pytest.raises(ValueError, match="snapshot_changed"):
        pub.verify_expected(pub.Reader(roots), expected, pub.digest(pub.canonical(expected)), forge)


def test_resigning_expected_snapshot_cannot_bypass_external_hash(tmp_path: Path) -> None:
    roots, forge, _ = tiny_roots(tmp_path)
    expected = pub.capture_expected(roots, forge)
    trusted = pub.digest(pub.canonical(expected))
    expected["files"]["outfit/protocol.json"] = "0" * 64
    with pytest.raises(ValueError, match="external_snapshot_hash"):
        pub.verify_expected(pub.Reader(roots), expected, trusted, forge)


@pytest.mark.parametrize("tamper", ["count", "duplicate", "source", "threshold"])
def test_outfit_denominators_and_source_freshness_are_derived(tmp_path: Path, tamper: str) -> None:
    roots, forge, _ = tiny_roots(tmp_path)
    root = roots["outfit"]
    r = pub.decode((root / "result.json").read_bytes())
    if tamper == "count":
        r["qualityPassed"] = 40
    elif tamper == "duplicate":
        r["rows"][-1] = r["rows"][0]
    elif tamper == "source":
        write(forge, "anchor.py", b"# changed\n")
    else:
        p = pub.decode((root / "protocol.json").read_bytes())
        p["thresholds"]["residual_m"] = 0.1
        write(root, "protocol.json", p)
        r["protocolHash"] = pub.digest(pub.canonical(p))
    write(root, "result.json", r)
    with pytest.raises(ValueError):
        pub.outfit_summary(pub.Reader(roots), forge)


def test_runtime_missing_row_cannot_shrink_denominator(tmp_path: Path) -> None:
    roots, forge, _ = tiny_roots(tmp_path)
    r = pub.decode((roots["runtime"] / "result.json").read_bytes())
    r["rows"].pop(next(iter(r["rows"])))
    write(roots["runtime"], "result.json", r)
    with pytest.raises(ValueError, match="row_denominator"):
        pub.runtime_summary(pub.Reader(roots), forge)


def test_junit_failure_and_missing_control_not_hidden() -> None:
    failed = b'<testsuite><testcase name="test_one"><failure/></testcase></testsuite>'
    assert pub.junit_summary(failed, ["tests.py::test_one"])["failed"] == 1
    with pytest.raises(ValueError, match="control_inventory"):
        pub.junit_summary(failed, ["tests.py::test_one", "tests.py::test_two"])
    with pytest.raises(ValueError, match="unsafe_junit"):
        pub.junit_summary(b"<!DOCTYPE foo><testsuite/>", [])


def test_inventory_and_manifest_hash_tampering(tmp_path: Path) -> None:
    write(tmp_path, "asset.bin", b"a")
    rows = inventory(tmp_path, ["asset.bin"])
    write(tmp_path, "manifest.json", signed({"inventory": rows}, "identity"))
    trusted = pub.digest((tmp_path / "manifest.json").read_bytes())
    write(tmp_path, "asset.bin", b"b")
    with pytest.raises(ValueError, match="inventory_hash"):
        pub.verify_manifest(pub.Reader({}), tmp_path, "identity", trusted)
    with pytest.raises(ValueError, match="duplicate_inventory"):
        pub.Reader({}).inventory(tmp_path, inventory(tmp_path, ["asset.bin", "asset.bin"]))
    write(
        tmp_path,
        "manifest.json",
        signed({"inventory": inventory(tmp_path, ["asset.bin"])}, "identity"),
    )
    with pytest.raises(ValueError, match="output_manifest"):
        pub.verify_manifest(pub.Reader({}), tmp_path, "identity", trusted)


@pytest.mark.parametrize("rel", ["../x", "a/../x", "a\\x", "C:/x", "NUL.json", "a.", "a/x "])
def test_unsafe_publication_paths_rejected(tmp_path: Path, rel: str) -> None:
    with pytest.raises(ValueError):
        pub.guarded(tmp_path, rel)


def test_reader_final_freshness_and_strict_json(tmp_path: Path) -> None:
    write(tmp_path, "data.json", {})
    reader = pub.Reader({"data": tmp_path})
    reader.doc("data", "data.json")
    write(tmp_path, "data.json", {"changed": True})
    with pytest.raises(ValueError, match="changed_during"):
        reader.fresh()
    with pytest.raises(ValueError, match="duplicate_json"):
        pub.decode(b'{"a":1,"a":2}')
    with pytest.raises(ValueError, match="nonfinite"):
        pub.decode(b'{"a":NaN}')
    with pytest.raises(ValueError):
        pub.exact(True, 1, "boolean_not_count")


def test_runtime_source_retains_failed_fit_and_rejects_forged_ready(tmp_path: Path) -> None:
    write(tmp_path, "report.json", {"ready": False})
    write(tmp_path, "asset.bin", b"tiny")
    manifest = signed(
        {
            "profile": "package_mesh_layering_development_v1",
            "garmentId": "garment.tiny",
            "avatarId": "avatar.reference",
            "inventory": inventory(tmp_path, ["report.json", "asset.bin"]),
        },
        "identity",
    )
    write(tmp_path, "manifest.json", manifest)
    mh = pub.digest(pub.canonical(manifest))
    source = {
        "root": str(tmp_path),
        "manifest": "manifest.json",
        "manifestSha256": mh,
        "provenance": mh,
        "garmentId": "garment.tiny",
        "avatarId": "avatar.reference",
        "render": "asset.bin",
        "cage": "asset.bin",
        "binding": "asset.bin",
        "sourceQuality": {
            "fitReady": False,
            "reportSha256": pub.digest(pub.canonical({"ready": False})),
        },
    }
    pub.runtime_source(pub.Reader({}), source)
    source["sourceQuality"]["fitReady"] = True
    with pytest.raises(ValueError, match="source_fit_claim"):
        pub.runtime_source(pub.Reader({}), source)


def test_probe_receipt_is_explicitly_snapshotted(tmp_path: Path) -> None:
    roots, forge, _ = tiny_roots(tmp_path)
    probe = tmp_path / "isolated/probe.json"
    write(probe.parent, probe.name, {"passed": 3, "denominator": 3})
    roots["probe-0"] = probe
    snapshot = pub.capture_expected(roots, forge)
    assert snapshot["files"]["probe-0/probe.json"] == pub.digest(probe.read_bytes())


def test_external_memory_is_cumulative_and_missing_is_not_zero(tmp_path: Path) -> None:
    assert pub.external_memory_summary(pub.Reader({}))["maximumSampledProcessPeakBytes"] is None
    path = tmp_path / "memory.json"
    write(
        tmp_path,
        path.name,
        {
            "scope": "external_Windows_process_peak_sampling_not_per_case_isolated_memory",
            "processId": 123,
            "earlierRowsNotIndividuallySampled": 5,
            "samples": [
                {"completedRows": 6, "peakWorkingSetBytes": 48_000_000},
                {"completedRows": 8, "peakWorkingSetBytes": 49_000_000},
            ],
        },
    )
    summary = pub.external_memory_summary(pub.Reader({"probe-host-memory": path}))
    assert summary["maximumSampledProcessPeakBytes"] == 49_000_000
    assert summary["earlierRowsNotIndividuallySampled"] == 5
    assert summary["isolatedPerCaseMemory"] == "not_measured"


@pytest.mark.parametrize("explicit_memory", [False, True])
def test_cli_selects_new_roots_and_never_auto_attaches_old_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, explicit_memory: bool
) -> None:
    monkeypatch.setattr(pub, "FORGE", tmp_path)
    write(tmp_path, ".tmp/outfit-host-memory.json", {"historical": True})
    current_memory = tmp_path / "current-memory.json"
    write(tmp_path, current_memory.name, {"explicit": True})
    outfit, runtime = tmp_path / "outfit-final-v2", tmp_path / "runtime-v3-final-v2"
    argv = [
        str(SCRIPT),
        "--outfit",
        str(outfit),
        "--runtime",
        str(runtime),
        "--capture-expected",
        str(tmp_path / "snapshot.json"),
    ]
    if explicit_memory:
        argv.extend(["--host-memory", str(current_memory)])
    monkeypatch.setattr(pub.sys, "argv", argv)

    def inspect(roots: dict[str, Path], forge: Path) -> dict[str, Any]:
        assert roots["outfit"] == outfit and roots["runtime"] == runtime
        assert ("probe-host-memory" in roots) is explicit_memory
        if explicit_memory:
            assert roots["probe-host-memory"] == current_memory
        raise ValueError("captured_before_artifact_work")

    monkeypatch.setattr(pub, "capture_expected", inspect)
    with pytest.raises(ValueError, match="captured_before_artifact_work"):
        pub.main()


def test_portable_projection_handles_recursive_keys_commands_and_paths(tmp_path: Path) -> None:
    raw_doc = {
        "roots": {"outfit": r"E:\apps\forge\.tmp\outfit-final-v2"},
        "files": {r"E:\apps\forge\src\solver.py": "a" * 64},
        "command": [
            r"C:\Users\Alice\Python\python.exe",
            "--root",
            "E:/apps/forge/.tmp/outfit-final-v2",
        ],
        "quotedCommand": (
            '"C:\\Program Files\\Python\\python.exe" --input "E:\\apps\\forge\\data.json"'
        ),
        "unc": r"\\private-host\share\input.json",
        "posix": "/home/alice/private/data.json",
        "nested": [{"root": "E:/apps/forge/.tmp/outfit-final-v2", "fitReady": False}],
        "reference": "https://example.com/public/reference",
        "resultDigest": "b" * 64,
    }
    raw = pub.canonical(raw_doc)
    payload = pub.portable_payload(
        {
            "result.json": raw,
            "controls.xml": (
                b"<testsuite><failure>at C:\\Users\\Alice\\test.py:9</failure></testsuite>"
            ),
            "process.log": (
                b"python E:\\apps\\forge\\scripts\\run.py "
                b"--root E:/apps/forge/.tmp/outfit-final-v2"
            ),
            "receipt_array.json": pub.canonical([{"path": r"E:\apps\forge\input.json"}]),
        },
        {"result.json", "controls.xml", "process.log", "receipt_array.json"},
        {"workspace/forge": "E:/apps/forge", "inputs/outfit": "E:/apps/forge/.tmp/outfit-final-v2"},
    )
    doc = pub.decode(payload["result.json"])
    assert doc["roots"]["outfit"] == "inputs/outfit"
    assert list(doc["files"]) == ["workspace/forge/src/solver.py"]
    assert doc["nested"][0]["fitReady"] is False
    assert doc["reference"] == raw_doc["reference"]
    assert doc["resultDigest"] == raw_doc["resultDigest"]
    assert doc["_publicationProjection"]["rawReceiptSha256"] == pub.digest(raw)
    assert "original_unprojected" in doc["_publicationProjection"]["embeddedSourceDigestsApplyTo"]
    ledger = pub.decode(payload["projection_manifest.json"])
    for row in ledger["receipts"]:
        assert row["publishedProjectionSha256"] == pub.digest(payload[row["path"]])
    for rel, data in payload.items():
        write(tmp_path, rel, data)
    assert pub.scan_evidence_files(sorted(p for p in tmp_path.iterdir() if p.is_file())) == {}


def test_projection_rejects_secrets_and_alias_collisions() -> None:
    with pytest.raises(ValueError, match="unsafe_receipt_content"):
        pub.portable_payload(
            {"secret.json": pub.canonical({"value": "ghp_" + "a" * 25})}, {"secret.json"}, {}
        )
    with pytest.raises(ValueError, match="projection_key_collision"):
        pub.PortableProjection({"workspace/forge": "E:/forge"}).value(
            {"E:/forge/a": 1, "E:\\forge\\a": 2}
        )
