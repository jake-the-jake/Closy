from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

FORGE = Path(__file__).resolve().parents[2]


@pytest.fixture
def pub() -> Any:
    spec = importlib.util.spec_from_file_location(
        "family_publication_test_subject",
        FORGE / "scripts/publish_family_integration_v1.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_bundle(pub: Any) -> dict[str, Any]:
    cases = [
        {"caseId": f"{family}/{label}", "family": family, "changes": {}}
        for family in pub.FAMILIES
        for label in pub.LABELS
    ]
    protocol = {
        "version": "family_integration_development_v1",
        "buildCount": 54,
        "cleanRoots": 2,
        "cases": cases,
        "scientificCampaign": False,
        "areaThresholdM2": 1e-12,
        "bindingFloat32ToleranceM": 2e-6,
    }
    source = {"head": pub.PR66, "files": {}}
    rows = []
    for repeat in (1, 2):
        for case in cases:
            identity = pub.digest(case["caseId"].encode())
            audit = {
                "profile": pub.PROFILE,
                "family": case["family"],
                "packageIdentity": identity,
                "semanticsValid": True,
                "canonicalTopologyPreserved": True,
                "validConventionalGeometry": True,
                "physicalQualityPassed": False,
                "bindingCoverage": 3,
                "renderVertexCount": 3,
                "maximumBindingErrorM": 0,
                "motionSupport": "analytic_binding_fidelity_only",
                "layerSupport": "separate_semantic_parts_not_collision_qualified",
                "geometry": {
                    stage: {
                        "valid": True,
                        "triangleCount": 1,
                        "vertexCount": 3,
                        "minimumAreaM2": 0.01,
                        "invalidTriangleCount": 0,
                        "firstFailure": None,
                    }
                    for stage in ("rest", "simulation", "render")
                },
                "boundaries": {
                    "maximumPairedSeamGapM": 0.04,
                    "physicalSeamAcceptance": False,
                    "allOpeningsNoncollapsed": True,
                    "openingMetricScope": "sampled_boundary_length_not_full_opening_shape",
                },
            }
            rows.append(
                {
                    **case,
                    "repeat": repeat,
                    "terminal": "passed",
                    "packageIdentity": identity,
                    "audit": audit,
                    "wallSeconds": 0.1,
                }
            )
    result = {
        "version": "closy.family_integration.result.v1",
        "sourceHead": source["head"],
        "sourceInventoryDigest": pub.digest(pub.canonical(source["files"])),
        "protocolDigest": pub.digest(pub.canonical(protocol)),
        "buildDenominator": 54,
        "passedBuilds": 54,
        "deterministicTwoRoots": True,
        "rows": rows,
        "captures": [
            {"family": family, "passed": False, "error": "unit_fixture_no_renderer"}
            for family in pub.FAMILIES
        ],
        "negatives": [
            {"family": family, "input": value, "rejected": True, "reason": "invalid"}
            for family in pub.FAMILIES
            for value in ("nan", "-100")
        ],
        "physicalQualification": False,
        "globalPhase8Complete": False,
        "host": "pure_unit_fixture_not_host_evaluation",
        "elapsedWallSeconds": 5.4,
    }
    bundle = {"protocol": protocol, "result": result, "source": source}
    synchronize(bundle)
    return bundle


def synchronize(bundle: dict[str, Any]) -> None:
    rows = bundle["result"]["rows"]
    bundle["checkpoint"] = {"rows": copy.deepcopy(rows), "nextBuild": 55}
    bundle["index"] = [
        {
            key: row.get(key)
            for key in (
                "caseId",
                "family",
                "terminal",
                "packageIdentity",
                "audit",
            )
        }
        for row in rows
        if row["repeat"] == 1
    ]


def validate(pub: Any, bundle: dict[str, Any]) -> Any:
    return pub.validate_completed(
        bundle["protocol"],
        bundle["result"],
        bundle["checkpoint"],
        bundle["index"],
        bundle["source"],
        pub.canonical(bundle["protocol"]),
    )


def write_json(pub: Any, path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pub.canonical(value))


def make_saved_fixture(pub: Any, root: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    forge = root / "closy-forge"
    evaluation = forge / ".tmp/final"
    initial = forge / ".tmp/initial"
    bundle = make_bundle(pub)
    for row in bundle["result"]["rows"]:
        package = evaluation / f"build{row['repeat']}" / row["caseId"]
        payloads = {
            "simulation/rest.glb": b"not_real_geometry_unit_fixture",
            "simulation/simulation_mesh.glb": b"not_real_geometry_unit_fixture",
            "render/fallback.glb": b"not_real_geometry_unit_fixture",
            "binding/sim_to_render.bin": b"binding_fixture",
            "simulation/settling.json": pub.canonical({"physicalConvergenceClaimed": False}),
        }
        manifest = {
            "profile": pub.PROFILE,
            "family": row["family"],
            "caseId": row["caseId"],
            "inventory": [
                {"path": path, "byteSize": len(data), "sha256": pub.digest(data)}
                for path, data in payloads.items()
            ],
        }
        identity = pub.digest(pub.canonical(manifest))
        manifest["packageIdentity"] = identity
        row["packageIdentity"] = row["audit"]["packageIdentity"] = identity
        for path, data in payloads.items():
            target = package / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        write_json(pub, package / "manifest.json", manifest)
        write_json(pub, package / "audit.json", row["audit"])
    synchronize(bundle)
    for name, key in (
        ("protocol", "protocol"),
        ("source_inventory", "source"),
        ("result", "result"),
        ("checkpoint", "checkpoint"),
        ("family_index", "index"),
    ):
        write_json(pub, evaluation / f"{name}.json", bundle[key])
    write_json(
        pub,
        initial / "checkpoint.json",
        {
            "rows": [
                {"caseId": "tshirt/nominal", "terminal": "failed", "error": "KeyError:'garmentId'"},
            ],
            "nextBuild": 2,
        },
    )
    write_json(pub, initial / "protocol.json", bundle["protocol"])
    write_json(pub, initial / "source_inventory.json", bundle["source"])
    prototype = next(row for row in bundle["result"]["rows"] if row["family"] == "long_sleeved_top")
    for label in ("prototype1", "prototype2"):
        folder = forge / ".tmp" / label
        write_json(pub, folder / "audit.json", prototype["audit"])
        write_json(pub, folder / "simulation/settling.json", {"physicalConvergenceClaimed": False})
    blueprint = forge / pub.BLUEPRINT_PATH
    blueprint.parent.mkdir(parents=True, exist_ok=True)
    blueprint.write_text("## 17. Roadmap\n### Phase 8\nDeliver:\n- mesh;\n", encoding="utf-8")
    write_json(pub, forge / "docs/blueprint_coverage.json", {"rows": []})
    write_json(
        pub,
        forge / "docs/evidence/static_zeroone_runtime_v2/blueprint_inventory.json",
        {"requirements": []},
    )
    for name in (
        "scripts/evaluate_family_integration_v1.py",
        "scripts/publish_family_integration_v1.py",
        "tests/unit/test_family_integration_v1.py",
        "tests/unit/test_family_publication_v1.py",
    ):
        receipt_path = forge / name
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text("# inert fixture\n", encoding="utf-8")
    monkeypatch.setattr(
        pub,
        "audit_repository",
        lambda _root: {
            "head": pub.PR66,
            "tree": "fixture-tree",
            "protectedBlobCount": 84,
            "fixtureOnly": True,
        },
    )
    monkeypatch.setattr(
        pub,
        "_source_review",
        lambda _forge, _source: {
            "reachableSourceDigest": "fixture-closure",
            "fixtureOnly": True,
        },
    )
    return {
        "forge": forge,
        "evaluation": evaluation,
        "initial": initial,
        "prototype1": forge / ".tmp/prototype1",
        "prototype2": forge / ".tmp/prototype2",
    }


def prepare(pub: Any, paths: dict[str, Path]) -> Any:
    return pub.prepare_publication(
        paths["evaluation"],
        forge_root=paths["forge"],
        initial_root=paths["initial"],
        prototype_roots=(paths["prototype1"], paths["prototype2"]),
    )


def test_complete_matrix_does_not_imply_seam_or_physics_acceptance(pub: Any) -> None:
    bundle = make_bundle(pub)
    counts = validate(pub, bundle)
    assert counts["builds"] == {"planned": 54, "passed": 54, "failed": 0, "notRun": 0}
    assert counts["captures"]["failed"] == 9
    compact = pub.compact_audit(bundle["result"]["rows"][0]["audit"])
    assert compact["validConventionalGeometry"] is True
    assert compact["physicalSeamAcceptance"] is False
    assert compact["physicalQualityPassed"] is False


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("missing_row", "incomplete"),
        ("duplicate", "duplicate"),
        ("active", "not_terminal"),
        ("wrong_family", "protocol_mismatch"),
        ("count", "passed_count"),
        ("index", "index_result"),
        ("captures", "capture_denominator"),
        ("negatives", "negative_denominator"),
        ("protocol", "protocol_digest"),
        ("source", "source_inventory_digest"),
        ("physics", "physical_scope"),
        ("invalid_triangle", "geometry_inconsistent"),
        ("seam", "claim_inconsistent"),
    ],
)
def test_incomplete_or_contradictory_records_rejected(pub: Any, mutation: str, code: str) -> None:
    bundle = make_bundle(pub)
    result = bundle["result"]
    if mutation == "missing_row":
        result["rows"].pop()
    elif mutation == "duplicate":
        result["rows"][1] = copy.deepcopy(result["rows"][0])
    elif mutation == "active":
        bundle["checkpoint"]["active"] = {"caseId": "running"}
    elif mutation == "wrong_family":
        result["rows"][0]["family"] = "jacket_outerwear"
    elif mutation == "count":
        result["passedBuilds"] = 53
    elif mutation == "index":
        bundle["index"][0]["packageIdentity"] = "bad"
    elif mutation == "captures":
        result["captures"].pop()
    elif mutation == "negatives":
        result["negatives"].pop()
    elif mutation == "protocol":
        result["protocolDigest"] = "bad"
    elif mutation == "source":
        result["sourceInventoryDigest"] = "bad"
    elif mutation == "physics":
        result["rows"][0]["audit"]["physicalQualityPassed"] = True
    elif mutation == "invalid_triangle":
        result["rows"][0]["audit"]["geometry"]["render"]["invalidTriangleCount"] = 1
    else:
        result["rows"][0]["audit"]["boundaries"]["physicalSeamAcceptance"] = True
    if mutation not in {"active", "index"}:
        bundle["checkpoint"]["rows"] = copy.deepcopy(result["rows"])
    with pytest.raises(pub.PublicationError, match=code):
        validate(pub, bundle)


def test_failed_terminal_rows_remain_in_denominator(pub: Any) -> None:
    bundle = make_bundle(pub)
    row = bundle["result"]["rows"][0]
    row.pop("audit")
    row.pop("packageIdentity")
    row.update(terminal="failed", error="typed_rejection")
    bundle["result"].update(passedBuilds=53, deterministicTwoRoots=False)
    synchronize(bundle)
    counts = validate(pub, bundle)
    assert counts["builds"]["failed"] == 1
    assert counts["builds"]["planned"] == 54
    bundle["result"]["deterministicTwoRoots"] = True
    with pytest.raises(pub.PublicationError, match="determinism_claim"):
        validate(pub, bundle)


@pytest.mark.parametrize(
    "value", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'{"a":1e999}']
)
def test_bad_json_is_rejected(pub: Any, value: bytes) -> None:
    with pytest.raises(pub.PublicationError):
        pub.decode(value)


@pytest.mark.parametrize(
    "relative", ["../escape", "/absolute", "C:/escape", "a\\b", "a/../b", "a//b"]
)
def test_unsafe_paths_rejected(pub: Any, tmp_path: Path, relative: str) -> None:
    with pytest.raises(pub.PublicationError):
        pub.safe_path(tmp_path, relative)


def test_manifest_hashes_every_file_without_self_reference(pub: Any, tmp_path: Path) -> None:
    root = tmp_path / "fresh"
    documents = {"result.json": b'{"passed":false}\n', "notes.md": b"Failure retained.\n"}
    manifest = pub.write_fresh(root, documents)
    expected = {key: value for key, value in manifest.items() if key != "publicationIdentity"}
    assert pub.digest(pub.canonical(expected)) == manifest["publicationIdentity"]
    assert len(manifest["files"]) == 2
    for row in manifest["files"]:
        assert pub.digest((root / row["path"]).read_bytes()) == row["sha256"]
    with pytest.raises(pub.PublicationError, match="must_be_fresh"):
        pub.write_fresh(root, documents)
    (root / "result.json").write_bytes(b"tampered")
    with pytest.raises(pub.PublicationError, match="file_hash_mismatch"):
        pub.verify_publication(root, expected_identity=manifest["publicationIdentity"])


def test_path_failure_writes_no_completion_marker(pub: Any, tmp_path: Path) -> None:
    output = tmp_path / "fresh"
    with pytest.raises(pub.PublicationError, match="unsafe_relative"):
        pub.write_fresh(output, {"../escape": b"bad"})
    assert not output.exists()


def test_input_changes_are_detected(pub: Any, tmp_path: Path) -> None:
    (tmp_path / "record.json").write_bytes(b"{}")
    inputs = pub.Inputs(tmp_path)
    inputs.record(tmp_path / "record.json")
    (tmp_path / "record.json").write_bytes(b"[]")
    with pytest.raises(pub.PublicationError, match="changed_during"):
        inputs.unchanged()
    with pytest.raises(pub.PublicationError, match="changed_during"):
        inputs.record(tmp_path / "record.json")


def test_pure_publication_retains_failures_and_leaves_bc_pending(
    pub: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = make_saved_fixture(pub, tmp_path, monkeypatch)
    documents = prepare(pub, paths)
    assert not (paths["forge"] / "docs/evidence/family_integration_v1").exists()
    assert all(not name.endswith((".glb", ".png", ".bin")) for name in documents)
    result = json.loads(documents["result.json"])
    assert result["counts"]["builds"]["passed"] == 54
    assert result["seamAcceptance"]["failed"] == 54
    assert result["quality"]["unitAComplete"] is False
    assert result["quality"]["manualProviderUnitB"] == "pending_parent_update"
    assert result["quality"]["packageLayerRuntimeUnitC"] == "pending_parent_update"
    retained = json.loads(documents["retained_development.json"])
    assert retained["initial"]["terminalCounts"]["failed"] == 1
    assert retained["initial"]["notRun"] == 53
    assert retained["initial"]["checkpoint"]["rows"][0]["error"] == "KeyError:'garmentId'"
    assert len(retained["longSleevePrototypes"]) == 2
    assert json.loads(documents["blueprint_current.json"])["phaseOverview"]["newUnitOutcomes"]["B"]
    assert len(json.loads(documents["family_index.json"])) == 27
    assert (
        documents["source_inventory.json"]
        == (paths["evaluation"] / "source_inventory.json").read_bytes()
    )
    assert b"Phase 0-14" in documents["progress.md"]
    assert sum(map(len, documents.values())) < 1024 * 1024


@pytest.mark.parametrize("missing", ["result.json", "family_index.json"])
def test_no_publication_before_both_final_outputs_exist(
    pub: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    missing: str,
) -> None:
    paths = make_saved_fixture(pub, tmp_path, monkeypatch)
    (paths["evaluation"] / missing).unlink()
    output = paths["forge"] / "docs/evidence/family_integration_v1"
    with pytest.raises(pub.PublicationError, match="missing_input"):
        pub.publish(
            paths["evaluation"],
            output,
            forge_root=paths["forge"],
            initial_root=paths["initial"],
            prototype_roots=(paths["prototype1"], paths["prototype2"]),
        )
    assert not output.exists()


def test_tampered_payload_cannot_be_published(
    pub: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = make_saved_fixture(pub, tmp_path, monkeypatch)
    (paths["evaluation"] / "build1/tshirt/nominal/render/fallback.glb").write_bytes(b"corrupt")
    with pytest.raises(pub.PublicationError, match="payload_changed"):
        prepare(pub, paths)


def test_ast_closure_resolves_relative_imports_without_execution(pub: Any, tmp_path: Path) -> None:
    sources = {
        "scripts/evaluate.py": "from closy_forge.a import exported\n",
        "src/closy_forge/__init__.py": "raise AssertionError('must never execute')\n",
        "src/closy_forge/a/__init__.py": "from .bridge import exported\n",
        "src/closy_forge/a/bridge.py": "from ..shared import exported\n",
        "src/closy_forge/shared.py": "exported = 1\n",
        "src/closy_forge/unrelated_b.py": "raise AssertionError('unrelated')\n",
    }
    for name, text in sources.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    closure = pub.source_closure(tmp_path, ["scripts/evaluate.py"])
    assert set(closure) == set(sources) - {"src/closy_forge/unrelated_b.py"}


def test_dynamic_module_seeds_are_explicit_and_unknown_loaders_fail(
    pub: Any, tmp_path: Path
) -> None:
    loader = tmp_path / "src/closy_forge/family_integration_v1/registry.py"
    dynamic = tmp_path / "src/closy_forge/garments/tshirt/parameters.py"
    loader.parent.mkdir(parents=True)
    dynamic.parent.mkdir(parents=True)
    loader.write_text(
        "import importlib\nimportlib.import_module(f'closy_forge.{name}')", encoding="utf-8"
    )
    dynamic.write_text("VALUE = 1\n", encoding="utf-8")
    entries = [path.relative_to(tmp_path).as_posix() for path in (loader, dynamic)]
    assert set(pub.source_closure(tmp_path, entries)) == set(entries)
    other = tmp_path / "other.py"
    other.write_text("import importlib\nimportlib.import_module(name)\n", encoding="utf-8")
    with pytest.raises(pub.PublicationError, match="unresolved_dynamic"):
        pub.source_closure(tmp_path, ["other.py"])


def test_broad_inventory_drift_is_not_a_reachable_source_change(
    pub: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    a = tmp_path / "src/closy_forge/a.py"
    b = tmp_path / "src/closy_forge/unrelated_b.py"
    a.parent.mkdir(parents=True)
    a.write_bytes(b"a = 1\n")
    b.write_bytes(b"b = 2\n")
    a_key = a.relative_to(tmp_path).as_posix()
    b_key = b.relative_to(tmp_path).as_posix()
    monkeypatch.setattr(
        pub, "source_closure", lambda _forge, _entries: {a_key: pub.digest(a.read_bytes())}
    )
    source = {"files": {a_key: pub.digest(a.read_bytes()), b_key: pub.digest(b"b = 1\n")}}
    review = pub._source_review(tmp_path, source)
    assert review["reachableRecordedSourcesUnchanged"] is True
    assert review["outsideClosureChanges"][0]["path"] == b_key
    a.write_bytes(b"a = 2\n")
    with pytest.raises(pub.PublicationError, match="reachable_source_changed"):
        pub._source_review(tmp_path, source)


def test_git_blob_reader_checks_raw_payload_identity(
    pub: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = b"line one\nline two\n"
    stream = pub.blob_oid(raw).encode() + b" blob " + str(len(raw)).encode() + b"\n" + raw + b"\n"
    monkeypatch.setattr(pub, "_git", lambda *_args, **_kwargs: stream)
    assert pub._git_blobs(tmp_path, ["HEAD:path"]) == [raw]
    monkeypatch.setattr(
        pub, "_git", lambda *_args, **_kwargs: stream.replace(b"line one", b"line two")
    )
    with pytest.raises(pub.PublicationError, match="oid_mismatch"):
        pub._git_blobs(tmp_path, ["HEAD:path"])
