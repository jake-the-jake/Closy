from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from closy_forge.binding.binary_format import BindingFile, BindingRecord, write_binding
from closy_forge.geometry.glb_io import write_indexed_glb
from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.package_io.canonical_json import read_json, write_canonical_json
from closy_forge.package_io.hashing import geometry_content_hash, sha256_file, topology_hash
from closy_forge.zeroone.parameter_regression import (
    declared_parameter_bounds,
    parameter_regression_cases,
)
from closy_forge.zeroone.processing_surface import (
    PROCESSING_INFLUENCE_PATH,
    PROCESSING_MANIFEST_PATH,
    PROCESSING_REMAP_PATH,
    PROCESSING_REPORT_PATH,
    PROCESSING_SURFACE_PATH,
    _integrity_hash,
    inspect_processing_surface,
    write_processing_surface_bundle,
)


def test_processing_surface_repairs_float32_degenerate_parent(tmp_path: Path) -> None:
    package = _fixture(tmp_path)
    audit = inspect_processing_surface(package)
    assert audit["status"] == "valid"
    report = read_json(package / PROCESSING_REPORT_PATH)
    assert report["source"]["invalidTriangleCount"] == 1
    assert report["processing"]["invalidTriangleCount"] == 0
    assert report["checks"]["exactOutsideRepairNeighbourhood"] is True
    assert report["canonicalAuthority"]["conventionalFallbackChanged"] is False
    remap = read_json(package / PROCESSING_REMAP_PATH)
    source = _source_mesh()
    assert remap["complete"] is True
    assert len(remap["vertexRows"]) == source.vertex_count
    assert len(remap["triangleRows"]) == source.triangle_count


@pytest.mark.parametrize("family", ["long_sleeved_top", "button_shirt", "jacket_outerwear"])
def test_parameter_regression_cases_cover_declared_bounds_and_replay(family: str) -> None:
    cases = parameter_regression_cases(family)  # type: ignore[arg-type]
    covered = {boundary for case in cases for boundary in case.covered_boundaries}
    bounds = declared_parameter_bounds(family)  # type: ignore[arg-type]
    assert len(cases) >= 8
    assert sum(case.classification == "pairwise_boundary" for case in cases) >= 4
    assert sum(case.prior_collapse_replay for case in cases) == 1
    for field in bounds:
        assert f"{field}:min" in covered
        assert f"{field}:max" in covered


@pytest.mark.parametrize(
    "corruption",
    [
        "zero_area",
        "repeated_index",
        "duplicate_triangle",
        "collapsed_opening",
        "invalid_remap",
        "stale_binding",
        "missing_panel_material",
        "forged_report",
    ],
)
def test_processing_surface_corruption_fails_closed(tmp_path: Path, corruption: str) -> None:
    source_package = _fixture(tmp_path / "source")
    package = tmp_path / f"{corruption}.closygarment"
    shutil.copytree(source_package, package)
    manifest = read_json(package / PROCESSING_MANIFEST_PATH)
    if corruption in {"zero_area", "collapsed_opening"}:
        _write_source_surface(package, _source_mesh())
        _refresh_surface_manifest(package, manifest)
    elif corruption == "repeated_index":
        mesh = _source_mesh().meshes[0]
        corrupted = MeshSet(
            [
                Mesh(
                    mesh.name,
                    mesh.panel_id,
                    mesh.vertices,
                    mesh.panel_uvs,
                    [(0, 0, 2), *mesh.triangles[1:]],
                    mesh.material_id,
                )
            ]
        )
        _write_source_surface(package, corrupted)
        _refresh_surface_manifest(package, manifest)
    elif corruption == "duplicate_triangle":
        mesh = _valid_mesh(package).meshes[0]
        corrupted = MeshSet(
            [
                Mesh(
                    mesh.name,
                    mesh.panel_id,
                    mesh.vertices,
                    mesh.panel_uvs,
                    [*mesh.triangles, mesh.triangles[0]],
                    mesh.material_id,
                )
            ]
        )
        _write_source_surface(package, corrupted)
        _refresh_surface_manifest(package, manifest)
    elif corruption == "invalid_remap":
        remap = read_json(package / PROCESSING_REMAP_PATH)
        remap["complete"] = False
        write_canonical_json(package / PROCESSING_REMAP_PATH, remap)
        _refresh_file_hash(package, manifest, PROCESSING_REMAP_PATH)
    elif corruption == "stale_binding":
        influence = read_json(package / PROCESSING_INFLUENCE_PATH)
        influence["sourceBindingTopologyHash"] = "0" * 64
        write_canonical_json(package / PROCESSING_INFLUENCE_PATH, influence)
        _refresh_file_hash(package, manifest, PROCESSING_INFLUENCE_PATH)
    elif corruption == "missing_panel_material":
        mesh = _valid_mesh(package).meshes[0]
        corrupted = MeshSet(
            [
                Mesh(
                    mesh.name,
                    "panel.missing",
                    mesh.vertices,
                    mesh.panel_uvs,
                    mesh.triangles,
                    "material.missing",
                )
            ]
        )
        _write_source_surface(package, corrupted)
        _refresh_surface_manifest(package, manifest)
    elif corruption == "forged_report":
        report = read_json(package / PROCESSING_REPORT_PATH)
        report["surfaceDistance"]["maximumMeters"] = 0.0
        report["integrity"]["reportHash"] = _integrity_hash(report, "reportHash")
        write_canonical_json(package / PROCESSING_REPORT_PATH, report)
        _refresh_file_hash(package, manifest, PROCESSING_REPORT_PATH)
    write_canonical_json(package / PROCESSING_MANIFEST_PATH, manifest)
    assert inspect_processing_surface(package)["status"] == "invalid"


def _fixture(tmp_path: Path) -> Path:
    package = tmp_path / "fixture.closygarment"
    source = _source_mesh()
    (package / "render").mkdir(parents=True)
    write_indexed_glb(
        package / "render/fallback.glb", source, "fixture.material", (0.2, 0.3, 0.4, 1.0)
    )
    write_canonical_json(
        package / "semantic/garment_graph.json",
        {
            "panelMapping": {"panel.front": {}},
            "seams": [{"id": "seam.fixture"}],
            "openings": [{"id": "opening.fixture"}],
        },
    )
    binding = BindingFile(
        records=[BindingRecord(0, 0.0, 0.0, 0.0, 0) for _ in range(source.vertex_count)],
        simulation_triangle_count=1,
        panel_count=1,
        simulation_topology_hash="1" * 64,
        render_topology_hash=topology_hash(source),
    )
    write_binding(package / "binding/sim_to_render.bin", binding)
    write_processing_surface_bundle(
        package_dir=package,
        source_mesh=source,
        binding=binding,
        semantic_graph=read_json(package / "semantic/garment_graph.json"),
        material_name="fixture.material",
        material_color=(0.2, 0.3, 0.4, 1.0),
    )
    return package


def _source_mesh() -> MeshSet:
    vertices = [(0.5, 0.0, -0.1)]
    panel_uvs = [(0.5, 0.0)]
    for index in range(101):
        x = index / 100.0
        vertices.append((x, 1.0, 0.05 + 0.1 * x))
        panel_uvs.append((x, 0.7 if index == 50 else 1.0))
    triangles = [(0, index, index + 1) for index in range(1, 101)]
    triangles.append((50, 51, 52))
    return MeshSet(
        [
            Mesh(
                "fixture",
                "panel.front",
                vertices,
                panel_uvs,
                triangles,
                "material.fixture",
            )
        ]
    )


def _valid_mesh(package: Path) -> MeshSet:
    from closy_forge.geometry.glb_io import read_glb_meshset

    return read_glb_meshset(package / PROCESSING_SURFACE_PATH)


def _write_source_surface(package: Path, meshset: MeshSet) -> None:
    write_indexed_glb(
        package / PROCESSING_SURFACE_PATH,
        meshset,
        "fixture.material",
        (0.2, 0.3, 0.4, 1.0),
    )


def _refresh_surface_manifest(package: Path, manifest: dict[str, object]) -> None:
    surface = _valid_mesh(package)
    manifest["topologyHash"] = topology_hash(surface)
    manifest["contentHash"] = geometry_content_hash(surface)
    _refresh_file_hash(package, manifest, PROCESSING_SURFACE_PATH)


def _refresh_file_hash(package: Path, manifest: dict[str, object], relative: str) -> None:
    files = manifest["files"]
    assert isinstance(files, dict)
    files[relative] = sha256_file(package / relative)
