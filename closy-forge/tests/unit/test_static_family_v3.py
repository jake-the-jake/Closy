from __future__ import annotations

import importlib.util
import struct
import subprocess
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from closy_forge.family_integration_v1.compiler import PROFILE
from closy_forge.geometry.glb_io import write_indexed_glb
from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.package_io.canonical_json import canonical_dumps, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.security.strict_json import load_strict_json_object
from closy_forge.zeroone import family_adapter_v1 as adapter
from closy_forge.zeroone.derivative_inspection import decode_v3_page_packs
from closy_forge.zeroone.request import _material_id, build_zeroone_request
from closy_forge.zeroone.static_stage_audit_v3 import (
    Triangle,
    audit_static_family,
    compare_triangle_coverage,
    read_leaf_materials,
)
from closy_forge.zeroone.tool import ZeroOneToolResolution


def _triangle() -> Triangle:
    return Triangle(
        ((0.0, 0.0, 0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 1.0, 0.0), (0.0, 1.0, 0.0, 0.0, 1.0)),
        0,
        "panel.source",
    )


def test_cyclic_rotation_and_float32_not_python_double_identity() -> None:
    source = _triangle()
    shifted = replace(source, vertices=source.vertices[1:] + source.vertices[:1], panel="ignored")
    assert compare_triangle_coverage([source], [shifted])["passed"]
    source = replace(source, vertices=((0.1, 0.0, 0.0, 0.0, 0.0), *source.vertices[1:]))
    emitted = replace(
        source,
        vertices=(
            (struct.unpack("<f", struct.pack("<f", 0.1))[0], 0.0, 0.0, 0.0, 0.0),
            *source.vertices[1:],
        ),
    )
    assert compare_triangle_coverage([source], [emitted])["triangleMultisetExactFloat32"]


@pytest.mark.parametrize("fault", ["triangle", "reverse", "uv", "material", "missing", "duplicate"])
def test_equal_counts_do_not_prove_oriented_position_uv_material_coverage(fault: str) -> None:
    source = _triangle()
    changed = source
    if fault == "triangle":
        changed = replace(source, vertices=((0.01, 0.0, 0.0, 0.0, 0.0), *source.vertices[1:]))
    elif fault == "reverse":
        changed = replace(source, vertices=tuple(reversed(source.vertices)))
    elif fault == "uv":
        changed = replace(source, vertices=((0.0, 0.0, 0.0, 0.1, 0.0), *source.vertices[1:]))
    elif fault == "material":
        changed = replace(source, material=1)
    left = [source, source] if fault == "missing" else [source]
    right = [changed, changed] if fault == "duplicate" else [changed]
    assert compare_triangle_coverage(left, right)["passed"] is False


def test_multiset_multiplicity_and_derived_panel_ambiguity() -> None:
    source = _triangle()
    assert compare_triangle_coverage([source, source], [source, source])["passed"]
    result = compare_triangle_coverage(
        [source, replace(source, panel="panel.other")], [source, source]
    )
    assert result["ambiguousDecodedTriangles"] == 2
    assert not result["passed"]
    assert not result["panelCorrespondence"]["embeddedPanelIdsVerified"]


def test_tolerance_matching_and_ambiguity_fail_closed() -> None:
    source = _triangle()
    changed = replace(source, vertices=((0.5e-6, 0.0, 0.0, 0.0, 0.0), *source.vertices[1:]))
    result = compare_triangle_coverage([source], [changed])
    assert result["passed"]
    assert not result["triangleMultisetExactFloat32"]
    result = compare_triangle_coverage([source, changed], [source, changed])
    assert result["ambiguousDecodedTriangles"] == 2
    assert not result["passed"]


@pytest.mark.parametrize("delta", [1.01e-6, float("nan"), float("inf")])
def test_bounds_is_mandatory_even_when_triangle_multiset_exact(delta: float) -> None:
    bounds = {"min": [0.0, 0.0, 0.0], "max": [1.0, 1.0, 0.0], "size": [1.0, 1.0, 0.0]}
    changed = {**bounds, "max": [1.0 + delta, 1.0, 0.0]}
    result = compare_triangle_coverage(
        [_triangle()], [_triangle()], source_bounds=bounds, decoded_bounds=changed
    )
    assert result["triangleMultisetExactFloat32"]
    assert not result["boundsWithinTolerance"]
    assert not result["passed"]


def _source(root: Path, monkeypatch: pytest.MonkeyPatch, *, unused_bounds: bool = False) -> Path:
    package = root / "A"
    mesh = Mesh(
        "source",
        "panel.source",
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)],
        [(0, 1, 2)],
    )
    if unused_bounds:
        mesh = replace(
            mesh,
            vertices=[*mesh.vertices, (10.0, 0.0, 0.0)],
            panel_uvs=[*mesh.panel_uvs, (0.0, 0.0)],
        )
    write_indexed_glb(
        package / "render/fallback.glb", MeshSet([mesh]), "fixture", (0.2, 0.3, 0.4, 1.0)
    )
    for path, doc in {
        "pattern/pattern.json": {"manual": True},
        "simulation/constraints.json": {"constraints": []},
        "simulation/material.json": {"authority": "simulation_not_appearance"},
        "binding/binding_manifest.json": {"binding": True},
        "semantic/garment_graph.json": {
            "panelMapping": {"panel.source": {}},
            "seams": [{"id": "seam.fixture"}],
            "openings": [{"id": "opening.fixture"}],
        },
    }.items():
        write_canonical_json(package / path, doc)
    (package / "binding/sim_to_render.bin").write_bytes(b"tiny_inert_binding")
    manifest = {
        "schemaVersion": 1,
        "profile": PROFILE,
        "family": "tshirt",
        "garmentId": "garment.fixture",
        "avatarId": "avatar.fixture",
        "units": "metres",
        "coordinates": "right_handed_y_up",
        "renderTopology": "a" * 64,
        "parameterSource": "known_structured_manual_input",
        "inventory": [
            {
                "path": p.relative_to(package).as_posix(),
                "sha256": sha256_file(p),
                "byteSize": p.stat().st_size,
            }
            for p in sorted(package.rglob("*"))
            if p.is_file()
        ],
    }
    manifest["packageIdentity"] = sha256_bytes(canonical_dumps(manifest).encode())
    write_canonical_json(package / "manifest.json", manifest)
    monkeypatch.setattr(
        adapter,
        "validate_family",
        lambda _: {
            "validConventionalGeometry": True,
            "physicalQualityPassed": False,
            "testFixtureOnly": True,
        },
    )
    return package


def test_adapter_copies_bytes_and_preserves_request_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path, monkeypatch)
    before = adapter.snapshot_family(source)
    destination = tmp_path / "work/adapter"
    receipt = adapter.create_family_adapter(source, destination)
    manifest = adapter.verify_family_adapter(destination)
    assert manifest["adapterVersion"] == adapter.ADAPTER_VERSION
    assert "packageVersion" not in manifest
    assert manifest["originalFamilyPackageIdentity"] == before["packageIdentity"]
    assert (destination / "source/family_manifest.json").read_bytes() == (
        source / "manifest.json"
    ).read_bytes()
    for path in before["files"]:
        if path != "manifest.json":
            assert (source / path).read_bytes() == (destination / path).read_bytes()
    request = build_zeroone_request(
        invocation_root=tmp_path / "work",
        package=destination,
        output=tmp_path / "work/processor",
        closy_sha="a" * 40,
        request_label="tiny-pure-test",
    )
    assert request["schemaVersion"] == "closy.zeroone.static-request.v1"
    roles = {r["role"]: r["path"] for r in request["canonicalAuthority"]}
    assert len(set(roles.values())) == 6
    assert roles["appearance"] == "appearance/material.json"
    assert roles["source"] == "source/family_source_record.json"
    assert roles["simulation"] == "simulation/constraints.json"
    assert receipt["assetBytesIdentical"]
    assert receipt["sourceValidation"]["physicalQualityPassed"] is False
    assert adapter.snapshot_family(source) == before


@pytest.mark.parametrize("fault", ["asset", "identity", "reserved", "destination", "geometry"])
def test_adapter_rejects_before_creating_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    source = _source(tmp_path, monkeypatch)
    destination = tmp_path / "copy"
    if fault == "asset":
        (source / "binding/sim_to_render.bin").write_bytes(b"corrupt")
    elif fault in {"identity", "reserved"}:
        manifest = load_strict_json_object(source / "manifest.json")
        manifest["avatarId"] = "tampered"
        if fault == "reserved":
            manifest["inventory"][0]["path"] = "source/reserved.json"
            manifest.pop("packageIdentity")
            manifest["packageIdentity"] = sha256_bytes(canonical_dumps(manifest).encode())
        write_canonical_json(source / "manifest.json", manifest)
    elif fault == "destination":
        destination.mkdir()
    else:
        monkeypatch.setattr(
            adapter, "validate_family", lambda _: {"validConventionalGeometry": False}
        )
    with pytest.raises(ValueError):
        adapter.create_family_adapter(source, destination)
    assert not (destination / "manifest.json").exists()


def _vector(fmt: str, values: list[tuple[Any, ...]]) -> bytes:
    return struct.pack("<Q", len(values)) + b"".join(struct.pack("<" + fmt, *v) for v in values)


def _pack(
    root: Path, *, material: int = 0, fault: str = "", materials: list[int] | None = None
) -> None:
    sections = materials if materials is not None else [material]
    positions = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    uvs = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
    if fault == "triangle":
        positions[0] = (0.02, 0.0, 0.0)
    if fault == "uv":
        uvs[0] = (0.1, 0.0)
    indices = [(0,), (2,), (1,)] if fault == "reverse" else [(0,), (1,), (2,)]
    payload = b"".join(
        (
            _vector("fff", positions),
            _vector("fff", [(0.0, 0.0, 1.0)] * 3),
            _vector("ff", uvs),
            _vector("ffff", [(1.0, 0.0, 0.0, 1.0)] * 3),
            _vector("ffff", [(1.0, 1.0, 1.0, 1.0)] * 3),
            _vector("I", indices * len(sections)),
            _vector("i", [(value,) for value in sections]),
        )
    )
    root.mkdir(parents=True, exist_ok=True)
    (root / "packs.bin").write_bytes(payload)
    checksum = 1469598103934665603
    for byte in payload:
        checksum = ((checksum ^ byte) * 1099511628211) & ((1 << 64) - 1)
    write_canonical_json(
        root / "manifest.json",
        {
            "schemaVersion": 3,
            "packs": [
                {
                    "packId": 0,
                    "parentPackId": -1,
                    "offset": 0,
                    "size": len(payload),
                    "checksum": checksum,
                    "triangleCount": len(sections),
                }
            ],
        },
    )


@pytest.mark.parametrize("material", [0, 7, -1])
def test_raw_signed_materials_after_bounded_decode(tmp_path: Path, material: int) -> None:
    _pack(tmp_path, material=material)
    decoded = decode_v3_page_packs(tmp_path)
    if material < 0:
        with pytest.raises(ValueError, match="material_i32_invalid"):
            read_leaf_materials(tmp_path, decoded.audit)
    else:
        assert read_leaf_materials(tmp_path, decoded.audit) == [[material]]


def _derivative(root: Path, package: Path, fault: str) -> Path:
    derivative = root / "derivative"
    _pack(derivative / "native/page_packs", material=1 if fault == "material" else 0, fault=fault)
    (derivative / "native/cooked_asset.z1ddc").write_bytes(b"tiny_inert_cooked_fixture")
    (derivative / "artifact.geomesh").write_bytes(b"tiny_inert_artifact_fixture")
    write_canonical_json(derivative / "lod.json", {"levels": []})
    write_canonical_json(
        derivative / "materials.json",
        {
            "materials": [
                {"denseIndex": 0, "materialId": _material_id("fixture", 0)},
            ]
        },
    )
    write_canonical_json(
        derivative / "garment/stitch_rows.json",
        {
            "rows": [
                {
                    "seamId": "seam.fixture",
                    "panelBoundaryInputA": {"panelId": "panel.source"},
                    "panelBoundaryInputB": {"panelId": "panel.source"},
                }
            ]
        },
    )
    paths = [
        "native/page_packs/packs.bin",
        "native/page_packs/manifest.json",
        "native/cooked_asset.z1ddc",
        "artifact.geomesh",
        "lod.json",
        "materials.json",
        "garment/stitch_rows.json",
    ]
    write_canonical_json(
        derivative / "derivative.json",
        {
            "schemaVersion": "zeroone.closy.static-derivative.v1",
            "garmentId": "garment.fixture",
            "source": {
                "manifestSha256": sha256_file(package / "manifest.json"),
                "inputAssetRelativePath": "render/fallback.glb",
                "inputContentSha256": sha256_file(package / "render/fallback.glb"),
                "topologyHash": "a" * 64,
                "coordinateConventionId": "closy-rh-yup-plus-z-v1",
                "unitScaleMetres": 1,
            },
            "nanite": {"clusterCount": 1, "hierarchyNodeCount": 1, "pagePackCount": 1},
            "compatibility": {
                "canonicalAuthority": "Closy package",
                "conventionalFallbackRequired": True,
                "optionalDerivative": True,
                "safeToDeleteAndRebuild": True,
            },
            "files": [{"path": p, "sha256": sha256_file(derivative / p)} for p in paths],
        },
    )
    return derivative


@pytest.mark.parametrize("fault", ["", "triangle", "reverse", "material", "uv"])
def test_v3_real_pack_decode_gates_z4_z8(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    source = _source(tmp_path, monkeypatch)
    package = tmp_path / "adapter"
    adapter.create_family_adapter(source, package)
    derivative = _derivative(tmp_path, package, fault)
    audit = audit_static_family(derivative, adapter_package=package)
    assert audit["failedStageIds"] == (["Z4", "Z8"] if fault else [])
    assert audit["stages"]["Z5"]["status"] == "passed"
    assert audit["stages"]["Z6"]["status"] == "passed"
    assert audit["notRunStageIds"] == ["Z3", "Z7"]
    assert audit["legacyCountsOnlyDiagnostic"]["triangleCoverageExact"]
    assert not audit["claims"]["embeddedPanelIdsVerified"]


def test_adapter_inventory_and_original_lineage_are_rechecked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path, monkeypatch)
    package = tmp_path / "adapter"
    adapter.create_family_adapter(source, package)
    (package / "simulation/material.json").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="inventory_changed"):
        adapter.verify_family_adapter(package)


def _script() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts/evaluate_static_family_v3.py"
    spec = importlib.util.spec_from_file_location("static_family_v3_script_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _completed(root: Path) -> None:
    rows = [
        {
            "repeat": repeat,
            "family": family,
            "caseId": f"{family}/{variation}",
            "terminal": "passed",
            "packageIdentity": "a" * 64,
        }
        for repeat in (1, 2)
        for family in adapter.FAMILY_NAMES
        for variation in ("nominal", "variation1", "variation2")
    ]
    write_canonical_json(
        root / "result.json", {"version": "closy.family_integration.result.v1", "rows": rows}
    )
    write_canonical_json(root / "checkpoint.json", {"rows": rows, "nextBuild": 55})
    write_canonical_json(root / "family_index.json", [])


def test_nine_not_run_receipts_without_trust_no_processor_or_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _script()
    source, output = tmp_path / "A", tmp_path / "static"
    _completed(source)
    monkeypatch.setattr(
        module,
        "source_receipt",
        lambda *_: {
            "localSource": {"matchesFrozenSource": True},
            "currentFiles": {},
        },
    )
    monkeypatch.setattr(
        module,
        "resolve_zeroone_tool",
        lambda *_, **__: ZeroOneToolResolution(
            False, "zeroone_trusted_build_record_required", None, None, None
        ),
    )
    monkeypatch.setattr(module, "create_family_adapter", lambda *_: pytest.fail("must not copy"))
    monkeypatch.setattr(module, "invoke", lambda *_: pytest.fail("must not execute processor"))
    result = module.run(source, output)
    assert result["notRun"] == 9
    assert result["passed"] == result["failed"] == 0
    assert result["stageCounts"]["Z4"]["not_run"] == 9
    checkpoint = load_strict_json_object(output / "checkpoint.json")
    assert len(checkpoint["rows"]) == 9 and checkpoint["nextRun"] == 10
    assert (output / "receipt_manifest.json").is_file()
    with pytest.raises(ValueError, match="fresh_and_disjoint"):
        module.run(source, output)


def test_incomplete_A_is_rejected_before_any_output(tmp_path: Path) -> None:
    module = _script()
    source = tmp_path / "A"
    _completed(source)
    checkpoint = load_strict_json_object(source / "checkpoint.json")
    checkpoint["active"] = {"caseId": "still-running"}
    write_canonical_json(source / "checkpoint.json", checkpoint)
    with pytest.raises(ValueError, match="completed_A_result_required"):
        module.run(source, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_processor_failure_receipt_retains_actual_exit_and_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _script()

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        kwargs["stdout"].write(b'{"success":false}\n')
        kwargs["stderr"].write(b"failure witness")
        return subprocess.CompletedProcess(argv, 17)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    result = module.invoke(
        Path("inert-not-executed.exe"), "cook", tmp_path, tmp_path / "request.json", tmp_path
    )
    assert result["exitCode"] == 17 and not result["passed"]
    assert result["report"] == {"success": False}
    assert (tmp_path / "cook.stderr.log").read_bytes() == b"failure witness"


def test_old_campaign_and_compilation_are_not_invoked() -> None:
    module = _script()
    text = Path(module.__file__ or "").read_text(encoding="utf-8")
    assert "integrate_static" not in text
    assert "compile_family" not in text
    assert "trusted_build_record=configured_record" in text


def test_pack_material_order_not_collapsed_mesh_label(tmp_path: Path) -> None:
    _pack(tmp_path, materials=[7, 0])
    decoded = decode_v3_page_packs(tmp_path)
    assert decoded.meshset.meshes[0].material_id == "material.sections.0,7"
    assert read_leaf_materials(tmp_path, decoded.audit) == [[7, 0]]


def test_material_swaps_with_same_global_set_fail() -> None:
    first = _triangle()
    second = replace(
        first, material=1, vertices=tuple((v[0] + 2.0, *v[1:]) for v in first.vertices)
    )
    result = compare_triangle_coverage(
        [first, second], [replace(first, material=1), replace(second, material=0)]
    )
    assert not result["passed"]


def test_native_bounds_failure_propagates_to_stage_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path, monkeypatch, unused_bounds=True)
    package = tmp_path / "adapter"
    adapter.create_family_adapter(source, package)
    audit = audit_static_family(_derivative(tmp_path, package, ""), adapter_package=package)
    assert audit["sourceGeometry"]["triangleMultisetExactFloat32"]
    assert not audit["sourceGeometry"]["boundsWithinTolerance"]
    assert audit["failedStageIds"] == ["Z4", "Z8"]


def test_source_race_during_validation_fails_before_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path, monkeypatch)

    def mutate(_: Path) -> dict[str, Any]:
        (source / "binding/sim_to_render.bin").write_bytes(b"mutation")
        return {"validConventionalGeometry": True}

    monkeypatch.setattr(adapter, "validate_family", mutate)
    with pytest.raises(ValueError, match="source_changed_before_copy"):
        adapter.create_family_adapter(source, tmp_path / "copy")
    assert not (tmp_path / "copy").exists()


def test_existing_resolver_requires_record_without_running_fake_exe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from closy_forge.zeroone import tool

    executable = tmp_path / "not-executable.exe"
    executable.write_bytes(b"pure-test-not-a-tool")
    monkeypatch.delenv(tool.TRUST_RECORD_ENV, raising=False)
    monkeypatch.setattr(
        "closy_forge.zeroone.tool.subprocess.run", lambda *_, **__: pytest.fail("must not execute")
    )
    resolution = tool.resolve_zeroone_tool(executable, expected_source_sha=_script().ZEROONE_HEAD)
    assert not resolution.available
    assert resolution.reason == "zeroone_trusted_build_record_required"


def test_nine_source_failures_are_checkpointed_without_reruns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _script()
    source, output = tmp_path / "A", tmp_path / "static"
    _completed(source)
    monkeypatch.setattr(
        module,
        "source_receipt",
        lambda *_: {
            "localSource": {"matchesFrozenSource": True},
            "currentFiles": {},
        },
    )
    monkeypatch.setattr(
        module,
        "resolve_zeroone_tool",
        lambda *_, **__: ZeroOneToolResolution(True, "available", Path("inert.exe"), "a" * 64, {}),
    )
    monkeypatch.setattr(module, "invoke", lambda *_: pytest.fail("must not execute processor"))
    result = module.run(source, output)
    assert result["failed"] == 9
    assert result["notRun"] == result["passed"] == 0
    assert all("asset_missing" in row["reason"] for row in result["rows"])
    assert len(load_strict_json_object(output / "checkpoint.json")["rows"]) == 9


def _reuse_context(module: ModuleType, monkeypatch: pytest.MonkeyPatch, fault: str = "") -> None:
    version = {
        "tool": "ZeroOneProcess",
        "zeroOneGitSha": module.ZEROONE_HEAD,
        "executableSha256": module.ZEROONE_EXE_SHA256,
        "buildConfiguration": "Release",
        "compiler": "fixture-compiler",
        "sourceDirty": False,
        "headless": True,
        "cpuOnly": True,
        "requiresGpu": False,
        "requiresWindow": False,
        "requestSchemaVersion": "closy.zeroone.static-request.v1",
        "reportSchemaVersion": "zeroone.closy.static-report.v1",
        "profiles": ["closy-static-d0-cpu-v1"],
        "commands": ["inspect", "cook", "validate", "resume"],
    }
    provenance = {
        "localSource": {"matchesFrozenSource": fault != "dirty"},
        "baseRegistry": {
            "commit": module.BASE_PR66,
            "path": "immutable-fixture.json",
            "sha256": "a" * 64,
            "source": {"zeroOneVersion": version},
        },
    }
    monkeypatch.setattr(module, "source_receipt", lambda *_: provenance)
    monkeypatch.setattr(
        module, "sha256_file", lambda _: "b" * 64 if fault == "hash" else module.ZEROONE_EXE_SHA256
    )

    def fake_git(_: Path, *args: str) -> bytes:
        if args == ("rev-parse", "HEAD"):
            return ("b" * 40 if fault == "sourcehead" else module.ZEROONE_HEAD).encode()
        if args == ("rev-parse", "HEAD^{tree}"):
            return str(module.ZEROONE_TREE).encode()
        return b""

    monkeypatch.setattr(module, "_git", fake_git)
    current = {**version, "compiler": "changed"} if fault == "version" else version
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda argv, **_: subprocess.CompletedProcess(
            argv, 17 if fault == "exit" else 0, canonical_dumps(current), ""
        ),
    )


def test_new_reuse_record_is_honest_and_existing_contract_accepts_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _script()
    _reuse_context(module, monkeypatch)
    capture = module.inspect_pr66_reuse(tmp_path, tmp_path, tmp_path / "inert.exe")
    record = capture["record"]
    assert record["trustDomain"] == "owner_controlled_registry"
    assert record["attestation"]["kind"] == "read_only_reuse_of_published_PR66_hash"
    assert record["attestation"]["originalTrustRecordNotRecovered"]
    assert record["attestation"]["buildReexecuted"] is False
    assert record["capture"]["networkAllowed"] is False
    assert record["capture"]["networkIsolationClaimed"] is False
    assert "read-only-reuse-capture" in record["buildId"]
    assert module._validate_trusted_build_record(record, module.ZEROONE_HEAD, "static") is None
    assert (
        module._validate_version(capture["version"], module.ZEROONE_EXE_SHA256, record, "static")
        is None
    )
    # Exercise the unchanged strict JSON record shape and resolver, not only helpers.
    from closy_forge.zeroone import tool

    executable = tmp_path / "inert.exe"
    executable.write_bytes(b"not-an-executable-pure-fixture")
    path = tmp_path / "new-reuse-record.json"
    write_canonical_json(path, record)
    monkeypatch.setattr(
        "closy_forge.zeroone.tool.sha256_file", lambda _: str(module.ZEROONE_EXE_SHA256)
    )
    resolution = tool.resolve_zeroone_tool(
        executable,
        trusted_build_record=path,
        expected_source_sha=module.ZEROONE_HEAD,
        expected_executable_sha256=module.ZEROONE_EXE_SHA256,
    )
    assert resolution.available
    assert resolution.trusted_build_record == record


@pytest.mark.parametrize("fault", ["hash", "dirty", "version", "exit", "sourcehead"])
def test_new_reuse_record_rejects_any_evidence_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    module = _script()
    _reuse_context(module, monkeypatch, fault)
    with pytest.raises(ValueError, match="pr66_reuse"):
        module.inspect_pr66_reuse(tmp_path, tmp_path, tmp_path / "inert.exe")


def test_failed_reuse_capture_retains_nine_not_run_dependencies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _script()
    source = tmp_path / "A"
    _completed(source)
    monkeypatch.setattr(
        module,
        "source_receipt",
        lambda *_: {
            "localSource": {"matchesFrozenSource": True},
            "currentFiles": {},
        },
    )

    def fail(*_: Any) -> None:
        raise ValueError("version_mismatch")

    monkeypatch.setattr(module, "inspect_pr66_reuse", fail)
    monkeypatch.setattr(module, "resolve_zeroone_tool", lambda *_, **__: pytest.fail("no bypass"))
    result = module.run(source, tmp_path / "out", reuse_published_pr66=True)
    assert result["notRun"] == 9
    assert not (tmp_path / "out/read_only_reuse_record.json").exists()
    assert (tmp_path / "out/read_only_reuse_attempt.json").is_file()
