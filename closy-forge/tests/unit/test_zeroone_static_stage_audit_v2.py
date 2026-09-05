from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from closy_forge.geometry.glb_io import read_glb_meshset, write_indexed_glb
from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.package_io.canonical_json import write_canonical_json
from closy_forge.package_io.hashing import sha256_file
from closy_forge.zeroone.static_stage_audit_v2 import (
    StaticStageAuditError,
    audit_static_zeroone_stages,
)


def test_static_stage_audit_decodes_supported_stages_and_abstains_unsupported(
    tmp_path: Path,
) -> None:
    package, derivative = _fixture(tmp_path)

    audit = audit_static_zeroone_stages(derivative, canonical_package=package)

    assert audit["passedStageIds"] == ["Z4", "Z5", "Z6", "Z8"]
    assert audit["notRunStageIds"] == ["Z3", "Z7"]
    assert audit["failedStageIds"] == []
    assert audit["sourceIdentity"]["canonicalBytesCompared"] is True
    assert audit["sourceIdentity"]["passed"] is True
    assert audit["sourceGeometry"]["triangleCoverageExact"] is True
    assert audit["sourceGeometry"]["boundsExactWithinOneMicrometre"] is True
    assert audit["semantics"]["checks"] == {
        "seamIdsExact": True,
        "panelIdsExact": True,
        "materialIdsPresent": True,
        "openingsDeclaredByCanonical": True,
    }
    assert audit["claims"] == {
        "dynamicZ2": False,
        "mobile": False,
        "gpu": False,
        "canonicalAuthorityChanged": False,
    }


def test_static_stage_audit_rejects_inventory_escape_and_hash_corruption(tmp_path: Path) -> None:
    package, derivative = _fixture(tmp_path)
    document = _json(derivative / "derivative.json")
    document["files"][0]["path"] = "../outside.bin"
    write_canonical_json(derivative / "derivative.json", document)
    with pytest.raises(StaticStageAuditError, match="inventory_path_invalid"):
        audit_static_zeroone_stages(derivative, canonical_package=package)

    package, derivative = _fixture(tmp_path / "hash")
    (derivative / "artifact.geomesh").write_bytes(b"changed")
    with pytest.raises(StaticStageAuditError, match="file_identity_mismatch"):
        audit_static_zeroone_stages(derivative, canonical_package=package)


def test_static_stage_audit_fails_nonmonotonic_lod_and_semantic_mismatch(
    tmp_path: Path,
) -> None:
    package, derivative = _fixture(tmp_path)
    lod = _json(derivative / "lod.json")
    lod["levels"] = [
        {"identity": "fine", "measuredError": 0.2, "triangleCount": 1},
        {"identity": "coarse", "measuredError": 0.1, "triangleCount": 1},
    ]
    write_canonical_json(derivative / "lod.json", lod)
    _refresh_derivative_inventory(derivative)
    audit = audit_static_zeroone_stages(derivative, canonical_package=package)
    assert audit["stages"]["Z5"]["status"] == "failed"

    graph = _json(package / "semantic" / "garment_graph.json")
    graph["seams"] = [{"id": "seam.not-the-derivative"}]
    write_canonical_json(package / "semantic" / "garment_graph.json", graph)
    audit = audit_static_zeroone_stages(derivative, canonical_package=package)
    assert audit["stages"]["Z8"]["status"] == "failed"
    assert audit["semantics"]["checks"]["seamIdsExact"] is False


def test_static_stage_audit_without_canonical_package_limits_its_claim(tmp_path: Path) -> None:
    _, derivative = _fixture(tmp_path)

    audit = audit_static_zeroone_stages(derivative)

    assert audit["sourceIdentity"]["canonicalBytesCompared"] is False
    assert audit["sourceGeometry"]["sourceBytesDecoded"] is False
    assert audit["semantics"]["canonicalSemanticsCompared"] is False


def _fixture(root: Path) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    package = root / "fixture.closygarment"
    derivative = root / "derivative"
    (package / "render").mkdir(parents=True)
    meshset = MeshSet(
        [
            Mesh(
                "fixture",
                "panel.front",
                [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
                [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)],
                [(0, 1, 2)],
                "material.fixture",
            )
        ]
    )
    source_glb = package / "render" / "fallback.glb"
    write_indexed_glb(source_glb, meshset, "material.fixture", (0.2, 0.4, 0.6, 1.0))
    write_canonical_json(package / "manifest.json", {"garmentId": "garment.static.fixture"})
    write_canonical_json(
        package / "semantic" / "garment_graph.json",
        {
            "panelMapping": {"panel.front": {}},
            "seams": [{"id": "seam.fixture"}],
            "openings": [{"id": "opening.neck"}],
        },
    )

    decoded_source = read_glb_meshset(source_glb).meshes[0]
    payload = _payload(decoded_source.vertices, decoded_source.panel_uvs)
    page_root = derivative / "native" / "page_packs"
    page_root.mkdir(parents=True)
    (page_root / "packs.bin").write_bytes(payload)
    write_canonical_json(
        page_root / "manifest.json",
        {
            "schemaVersion": 3,
            "assetGuid": "fixture",
            "cookKey": "fixture",
            "packs": [
                {
                    "packId": 0,
                    "parentPackId": -1,
                    "hierarchyNodeIndex": 0,
                    "offset": 0,
                    "size": len(payload),
                    "checksum": _fnv(payload),
                    "triangleCount": 1,
                    "materialSectionIds": [0],
                }
            ],
        },
    )
    (derivative / "native" / "cooked_asset.z1ddc").write_bytes(b"cooked-fixture")
    (derivative / "artifact.geomesh").write_bytes(b"artifact-fixture")
    write_canonical_json(
        derivative / "garment" / "stitch_rows.json",
        {
            "schemaVersion": "zeroone.garment-stitch-rows.v1",
            "rows": [
                {
                    "seamId": "seam.fixture",
                    "panelBoundaryInputA": {"panelId": "panel.front"},
                    "panelBoundaryInputB": {"panelId": "panel.front"},
                }
            ],
        },
    )
    write_canonical_json(
        derivative / "lod.json",
        {
            "algorithm": "GeoLodPipeline-v1",
            "generated": False,
            "sourceTriangleCount": 1,
            "selectedSourceTriangleCount": 1,
            "selectedLodTriangleCount": 1,
            "selectedLodTriangleRatio": 1.0,
            "levels": [],
        },
    )
    write_canonical_json(
        derivative / "materials.json",
        {
            "schemaVersion": "zeroone.material-map.v1",
            "materials": [{"materialId": "material.fixture"}],
        },
    )
    _write_derivative(package, derivative)
    return package, derivative


def _write_derivative(package: Path, derivative: Path) -> None:
    canonical_files = [
        "artifact.geomesh",
        "native/cooked_asset.z1ddc",
        "native/page_packs/manifest.json",
        "native/page_packs/packs.bin",
        "garment/stitch_rows.json",
        "lod.json",
        "materials.json",
    ]
    files = [{"path": path, "sha256": sha256_file(derivative / path)} for path in canonical_files]
    write_canonical_json(
        derivative / "derivative.json",
        {
            "schemaVersion": "zeroone.closy.static-derivative.v1",
            "profile": "closy-static-d0-v1",
            "garmentId": "garment.static.fixture",
            "source": {
                "manifestSha256": sha256_file(package / "manifest.json"),
                "inputAssetRelativePath": "render/fallback.glb",
                "inputContentSha256": sha256_file(package / "render" / "fallback.glb"),
                "topologyHash": "3" * 64,
                "coordinateConventionId": "closy-rh-y-up-metres-v1",
                "unitScaleMetres": 1.0,
            },
            "nanite": {
                "clusterCount": 1,
                "hierarchyNodeCount": 1,
                "pageCount": 1,
                "pagePackCount": 1,
                "pagePackFormatVersion": 3,
            },
            "garmentSemantics": {"stitchRowCount": 1, "broadGarmentSemanticsClaimed": False},
            "compatibility": {
                "conventionalFallbackRequired": True,
                "canonicalAuthority": "Closy package",
                "optionalDerivative": True,
                "safeToDeleteAndRebuild": True,
            },
            "files": files,
            "canonicalDerivativeHash": "4" * 64,
        },
    )


def _refresh_derivative_inventory(derivative: Path) -> None:
    document = _json(derivative / "derivative.json")
    for row in document["files"]:
        row["sha256"] = sha256_file(derivative / row["path"])
    write_canonical_json(derivative / "derivative.json", document)


def _payload(positions: list[tuple[float, float, float]], uvs: list[tuple[float, float]]) -> bytes:
    return b"".join(
        (
            _vector("f", 3, positions),
            _vector("f", 3, [(0.0, 0.0, 1.0)] * 3),
            _vector("f", 2, uvs),
            _vector("f", 4, [(1.0, 0.0, 0.0, 1.0)] * 3),
            _vector("f", 4, [(1.0, 1.0, 1.0, 1.0)] * 3),
            _vector("I", 1, [0, 1, 2]),
            _vector("I", 1, [0]),
        )
    )


def _vector(fmt: str, width: int, records: list[tuple[float, ...]] | list[int]) -> bytes:
    flattened = [
        value
        for record in records
        for value in (record if isinstance(record, tuple) else (record,))
    ]
    return struct.pack("<Q", len(records)) + struct.pack(f"<{len(flattened)}{fmt}", *flattened)


def _fnv(payload: bytes) -> int:
    value = 1469598103934665603
    for byte in payload:
        value ^= byte
        value = (value * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return value


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value
