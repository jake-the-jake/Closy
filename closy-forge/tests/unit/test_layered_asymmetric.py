from __future__ import annotations

from closy_forge.avatar.reference_avatar import (
    avatar_contract,
    build_collision_mesh,
    build_reference_avatar_mesh,
)
from closy_forge.binding.builder import build_binding
from closy_forge.garments.assembly import canonicalize_meshset
from closy_forge.garments.layered_asymmetric.assembly import (
    CANONICAL_GEOMETRY_DIGITS,
    build_constraints,
    build_simulation_mesh,
)
from closy_forge.garments.layered_asymmetric.fitting import (
    fit_layered_asymmetric,
    hash_layered_asymmetric_fit_report,
)
from closy_forge.garments.layered_asymmetric.motion import (
    CANONICAL_POSITION_DIGITS,
    build_layered_asymmetric_motion_suite,
    hash_layered_asymmetric_motion_report,
)
from closy_forge.garments.layered_asymmetric.parameters import LayeredAsymmetricParameters
from closy_forge.garments.layered_asymmetric.pattern_generator import (
    build_layered_asymmetric_pattern,
)
from closy_forge.garments.layered_asymmetric.semantic_graph import (
    build_layered_asymmetric_semantic_graph,
)
from closy_forge.geometry.subdivision import subdivide_for_render
from closy_forge.simulation.material_physics import build_material_preset_registry


def test_layered_asymmetric_pattern_has_two_literal_layers_and_asymmetric_hem() -> None:
    params = LayeredAsymmetricParameters()
    pattern = build_layered_asymmetric_pattern(params)
    semantic = build_layered_asymmetric_semantic_graph(pattern)
    mesh, edge_maps = build_simulation_mesh(pattern)
    constraints = build_constraints(pattern, edge_maps)

    assert [panel["id"] for panel in pattern["panels"]] == [
        "panel.layered_asymmetric.inner.front",
        "panel.layered_asymmetric.inner.back",
        "panel.layered_asymmetric.outer.front",
        "panel.layered_asymmetric.outer.back",
    ]
    assert pattern["layerCount"] == 2
    assert pattern["asymmetric"] is True
    assert len(pattern["seams"]) == 8
    assert len(pattern["openings"]) == 8
    assert len(constraints["openings"]) == 8
    assert all(len(opening["boundaryEdges"]) == 2 for opening in constraints["openings"])
    assert all(
        edge["status"] == "resolved"
        for opening in constraints["openings"]
        for edge in opening["boundaryEdges"]
    )
    assert semantic["layering"] == {
        "layerCount": 2,
        "orderedLayerIds": [
            "layer.layered_asymmetric.inner",
            "layer.layered_asymmetric.outer",
        ],
        "interLayerCollisionEnabled": False,
        "interLayerCollisionStatus": "declared_order_not_yet_consumed_by_reference_solver",
        "minimumClearanceMeters": params.layer_clearance_meters,
    }
    assert [component["collisionOrder"] for component in semantic["components"]] == [10, 20]
    assert {component["layerClass"] for component in semantic["components"]} == {
        "base_layer",
        "outerwear",
    }
    outer_panels = [panel for panel in pattern["panels"] if ".outer." in panel["id"]]
    for panel in outer_panels:
        hem = next(edge for edge in panel["boundary"] if ".outer.hem." in edge["id"])
        assert abs(hem["curve"]["points"][0][1] - hem["curve"]["points"][1][1]) == (
            params.outer_asymmetry_drop_meters
        )
    mesh_by_id = {part.panel_id: part for part in mesh.meshes}
    inner_z = sum(v[2] for v in mesh_by_id["panel.layered_asymmetric.inner.front"].vertices)
    inner_z /= len(mesh_by_id["panel.layered_asymmetric.inner.front"].vertices)
    outer_z = sum(v[2] for v in mesh_by_id["panel.layered_asymmetric.outer.front"].vertices)
    outer_z /= len(mesh_by_id["panel.layered_asymmetric.outer.front"].vertices)
    assert outer_z - inner_z >= params.layer_clearance_meters


def test_layered_asymmetric_seams_pair_each_layer_front_to_back() -> None:
    pattern = build_layered_asymmetric_pattern(LayeredAsymmetricParameters())
    mesh, edge_maps = build_simulation_mesh(pattern)
    constraints = build_constraints(pattern, edge_maps)

    for seam in pattern["seams"]:
        layer = seam["id"].split(".")[2]
        assert [span["orientation"] for span in seam["spans"]] == ["forward", "reverse"]
        assert [span["panelId"] for span in seam["spans"]] == [
            f"panel.layered_asymmetric.{layer}.front",
            f"panel.layered_asymmetric.{layer}.back",
        ]
    assert {constraint["seamId"] for constraint in constraints["constraints"]} == {
        seam["id"] for seam in pattern["seams"]
    }
    assert mesh.vertex_count > 0 and mesh.triangle_count > 0


def test_layered_asymmetric_mesh_coordinates_are_canonical() -> None:
    pattern = build_layered_asymmetric_pattern(LayeredAsymmetricParameters())
    meshset, _edge_maps = build_simulation_mesh(pattern)

    for mesh in meshset.meshes:
        for vertex in mesh.vertices:
            assert all(
                component == round(component, CANONICAL_GEOMETRY_DIGITS) for component in vertex
            )
        for uv in mesh.panel_uvs:
            assert all(component == round(component, CANONICAL_GEOMETRY_DIGITS) for component in uv)

    avatar = canonicalize_meshset(build_reference_avatar_mesh(), CANONICAL_GEOMETRY_DIGITS)
    assert all(
        component == round(component, CANONICAL_GEOMETRY_DIGITS)
        for mesh in avatar.meshes
        for vertex in mesh.vertices
        for component in vertex
    )


def test_layered_asymmetric_bounded_fit_evaluates_real_candidates() -> None:
    fitted, report = fit_layered_asymmetric(LayeredAsymmetricParameters())

    assert report["candidateCount"] == 25
    assert len(report["evaluations"]) == 25
    assert report["accepted"] is True
    assert report["learnedFitRun"] is False
    assert report["privateUserFitRun"] is False
    assert report["integrity"]["fitReportHash"] == hash_layered_asymmetric_fit_report(report)
    assert fitted.to_json() == report["fittedParameters"]


def test_layered_asymmetric_motion_executes_all_materials_and_four_armholes() -> None:
    pattern = build_layered_asymmetric_pattern(LayeredAsymmetricParameters())
    rest, edge_maps = build_simulation_mesh(pattern)
    constraints = build_constraints(pattern, edge_maps)
    render, seeds = subdivide_for_render(rest)
    binding, _manifest = build_binding(rest, render, seeds)
    registry = build_material_preset_registry()
    avatar = avatar_contract(build_reference_avatar_mesh(), build_collision_mesh())

    report, states, selected = build_layered_asymmetric_motion_suite(
        rest_mesh=rest,
        constraints=constraints,
        avatar_contract=avatar,
        preset_registry=registry,
        binding=binding,
    )

    assert report["integrity"]["suiteHash"] == hash_layered_asymmetric_motion_report(report)
    assert report["crossPreset"]["allFourPresetsExecuted"] is True
    assert report["crossPreset"]["allPresetStatesDistinct"] is True
    assert all(report["crossPreset"]["materialExtremesExecuted"].values())
    assert report["underarmStress"]["actualSolverRun"] is True
    assert report["underarmStress"]["accepted"] is True
    assert report["underarmStress"]["armholeMetrics"]["armholeCount"] == 4
    assert report["underarmStress"]["armholeMetrics"]["collapsedArmholeCount"] == 0
    assert report["underarmStress"]["denseBinding"]["maximumSeamCrackMeters"] <= 0.06
    assert all(
        record["diagnostics"]["canonicalPositionDigits"] == CANONICAL_POSITION_DIGITS
        for record in report["presetRecords"]
    )
    assert all(
        value == round(value, 6)
        for record in report["presetRecords"]
        for value in record["diagnostics"]["energyHistory"]
    )
    assert set(states) == {
        "material.lightweight_knit_d0_v1",
        "material.cotton_jersey_d0_v1",
        "material.heavy_jersey_d0_v1",
        "material.lightweight_woven_d0_v1",
        "opening_stress",
    }
    assert selected.vertex_count == rest.vertex_count
    assert all(
        component == round(component, CANONICAL_POSITION_DIGITS)
        for mesh in selected.meshes
        for vertex in mesh.vertices
        for component in vertex
    )
