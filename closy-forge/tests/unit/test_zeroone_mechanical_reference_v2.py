from __future__ import annotations

import json
from pathlib import Path

from closy_forge.package_io.canonical_json import write_canonical_json
from closy_forge.package_io.hashing import sha256_file
from closy_forge.zeroone.dynamic_oracle import (
    BINDINGS,
    FRAME_SIMULATION_POSITIONS,
    RENDER_IDS,
    SIMULATION_IDS,
    TIMESTAMPS,
    decode_bindings,
    decode_document,
    decode_u64,
    decode_vectors,
)
from closy_forge.zeroone.dynamic_request import build_dynamic_request
from closy_forge.zeroone.intersection_manifest import SurfaceRepresentation, audit_surface
from closy_forge.zeroone.mechanical_reference_surface import (
    MECHANICAL_REFERENCE_CORNER_MAP_PATH,
    MECHANICAL_REFERENCE_SURFACE_PATH,
    inspect_mechanical_reference_surface,
    prepare_mechanical_reference_surface,
)
from tests.helpers import build_demo

CLOSY_SHA = "7" * 40


def test_clean_reference_preserves_faces_and_sends_production_weights(tmp_path: Path) -> None:
    package = build_demo(tmp_path)
    manifest_before = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    fallback_before = sha256_file(package / "render" / "fallback.glb")
    prepared = prepare_mechanical_reference_surface(package)
    static = _static_derivative(tmp_path, package)
    bundle = build_dynamic_request(
        package=package,
        invocation_root=tmp_path,
        static_derivative=static,
        output=tmp_path / "dynamic-output",
        closy_sha=CLOSY_SHA,
    )
    request = decode_document(bundle.encoded, request=True)
    simulation_ids = decode_u64(request.sections[SIMULATION_IDS])
    render_ids = decode_u64(request.sections[RENDER_IDS])
    timestamps = decode_u64(request.sections[TIMESTAMPS])
    frames = decode_vectors(request.sections[FRAME_SIMULATION_POSITIONS], 3, 3)
    bindings = decode_bindings(request.sections[BINDINGS])

    assert prepared["status"] == "valid"
    assert prepared["canonicalSimulationVertexCount"] == len(simulation_ids) == 218
    assert prepared["denseCornerCount"] == len(render_ids) == 2496
    assert prepared["triangleCount"] == 832
    assert prepared["deletedTriangleCount"] == 0
    assert len(timestamps) == 13
    assert frames[:218] == frames[-218:]
    assert {record["count"] for record in bindings} == {1, 2}
    assert bundle.influence_inventory["authority"] == (
        "canonical_production_binding_contract_inside_zeroone"
    )
    assert bundle.influence_inventory["missingDestinationCount"] == 0
    assert bundle.clip_inventory["motionAudit"]["passed"] is True
    assert bundle.clip_inventory["motionAudit"]["maximumDestinationDisplacementD"] <= 0.05
    assert sha256_file(package / "render" / "fallback.glb") == fallback_before
    manifest_after = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_after["canonicalPackageDigest"] == manifest_before["canonicalPackageDigest"]

    corner_map = package / MECHANICAL_REFERENCE_CORNER_MAP_PATH
    corner_map.write_bytes(corner_map.read_bytes() + b" ")
    assert inspect_mechanical_reference_surface(package)["status"] == "invalid"


def test_shared_vertex_does_not_hide_crossing_away_from_vertex() -> None:
    crossing = SurfaceRepresentation(
        representation_id="shared_vertex_crossing",
        positions=[
            (0.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
            (0.0, 2.0, 0.0),
            (0.0, 0.0, 0.0),
            (1.0, 1.0, -1.0),
            (1.0, 1.0, 1.0),
        ],
        triangles=[(0, 1, 2), (3, 4, 5)],
        logical_vertex_ids=[0, 1, 2, 0, 3, 4],
        triangle_lineage=[{"panelId": "a"}, {"panelId": "b"}],
    )
    audit = audit_surface(crossing)

    assert audit["intersectingPairCount"] == 1
    assert audit["intersectingPairs"][0]["sharedLogicalVertexIds"] == [0]
    assert audit["intersectingPairs"][0]["expectedTopologicalAdjacency"] is False


def _static_derivative(root: Path, package: Path) -> Path:
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    target = root / "static" / "current"
    write_canonical_json(
        target / "derivative.json",
        {
            "schemaVersion": "zeroone.closy.static-derivative.v1",
            "profile": "closy-static-d0-cpu-v1",
            "garmentId": manifest["garmentId"],
            "source": {
                "inputAssetRelativePath": MECHANICAL_REFERENCE_SURFACE_PATH,
                "inputContentSha256": sha256_file(package / MECHANICAL_REFERENCE_SURFACE_PATH),
                "coordinateConventionId": "closy-rh-yup-plus-z-v1",
                "unitScaleMetres": 1.0,
            },
            "nanite": {
                "clusterCount": 7,
                "hierarchyNodeCount": 13,
                "pageCount": 13,
                "pagePackCount": 13,
                "pagePackFormatVersion": 3,
                "geometryHash": 11,
                "topologyHash": 12,
                "materialHash": 13,
            },
            "garmentSemantics": {"broadGarmentSemanticsClaimed": False},
        },
    )
    return target
