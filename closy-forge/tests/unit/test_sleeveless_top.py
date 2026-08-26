from __future__ import annotations

from closy_forge.avatar.reference_avatar import (
    avatar_contract,
    build_collision_mesh,
    build_reference_avatar_mesh,
)
from closy_forge.binding.builder import build_binding
from closy_forge.garments.assembly import canonicalize_meshset
from closy_forge.garments.sleeveless_top.assembly import (
    CANONICAL_GEOMETRY_DIGITS,
    build_constraints,
    build_simulation_mesh,
)
from closy_forge.garments.sleeveless_top.fitting import (
    fit_sleeveless_top,
    hash_sleeveless_fit_report,
)
from closy_forge.garments.sleeveless_top.motion import (
    CANONICAL_POSITION_DIGITS,
    build_sleeveless_motion_suite,
    hash_sleeveless_motion_report,
)
from closy_forge.garments.sleeveless_top.parameters import SleevelessTopParameters
from closy_forge.garments.sleeveless_top.pattern_generator import (
    build_sleeveless_top_pattern,
)
from closy_forge.garments.sleeveless_top.semantic_graph import (
    build_sleeveless_top_semantic_graph,
)
from closy_forge.geometry.subdivision import subdivide_for_render
from closy_forge.simulation.material_physics import build_material_preset_registry


def test_sleeveless_pattern_has_literal_family_semantics_and_loops() -> None:
    pattern = build_sleeveless_top_pattern(SleevelessTopParameters())
    semantic = build_sleeveless_top_semantic_graph(pattern)
    mesh, edge_maps = build_simulation_mesh(pattern)
    constraints = build_constraints(pattern, edge_maps)

    assert [panel["id"] for panel in pattern["panels"]] == [
        "panel.sleeveless_top.front",
        "panel.sleeveless_top.back",
    ]
    assert {seam["id"] for seam in pattern["seams"]} == {
        "seam.sleeveless_top.shoulder.left",
        "seam.sleeveless_top.shoulder.right",
        "seam.sleeveless_top.side.left",
        "seam.sleeveless_top.side.right",
    }
    assert {opening["id"] for opening in pattern["openings"]} == {
        "opening.sleeveless_top.neck",
        "opening.sleeveless_top.hem",
        "opening.sleeveless_top.armhole.left",
        "opening.sleeveless_top.armhole.right",
    }
    exact_tokens = {
        token
        for identifier in semantic["requiredIds"]["panels"]
        + semantic["requiredIds"]["seams"]
        + semantic["requiredIds"]["openings"]
        for token in identifier.replace("_", ".").split(".")
    }
    assert not {"sleeve", "cuff"} & exact_tokens
    assert mesh.vertex_count > 0 and mesh.triangle_count > 0
    assert len(constraints["openings"]) == 4
    assert all(len(opening["boundaryEdges"]) == 2 for opening in constraints["openings"])
    assert all(
        edge["status"] == "resolved"
        for opening in constraints["openings"]
        for edge in opening["boundaryEdges"]
    )


def test_sleeveless_seams_pair_front_to_back_with_reverse_orientation() -> None:
    pattern = build_sleeveless_top_pattern(SleevelessTopParameters())
    mesh, edge_maps = build_simulation_mesh(pattern)
    constraints = build_constraints(pattern, edge_maps)

    for seam in pattern["seams"]:
        assert [span["orientation"] for span in seam["spans"]] == ["forward", "reverse"]
        assert [span["panelId"] for span in seam["spans"]] == [
            "panel.sleeveless_top.front",
            "panel.sleeveless_top.back",
        ]
    assert {constraint["seamId"] for constraint in constraints["constraints"]} == {
        seam["id"] for seam in pattern["seams"]
    }
    assert all(
        constraint["orientation"] == ["forward", "reverse"]
        for constraint in constraints["constraints"]
    )
    assert mesh.triangle_count == 124


def test_sleeveless_mesh_coordinates_are_canonical() -> None:
    pattern = build_sleeveless_top_pattern(SleevelessTopParameters())
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


def test_sleeveless_bounded_fit_evaluates_real_candidates() -> None:
    fitted, report = fit_sleeveless_top(SleevelessTopParameters())

    assert report["candidateCount"] == 25
    assert len(report["evaluations"]) == 25
    assert report["accepted"] is True
    assert report["learnedFitRun"] is False
    assert report["privateUserFitRun"] is False
    assert report["integrity"]["fitReportHash"] == hash_sleeveless_fit_report(report)
    assert fitted.to_json() == report["fittedParameters"]


def test_sleeveless_motion_executes_material_extremes_and_underarm_stress() -> None:
    pattern = build_sleeveless_top_pattern(SleevelessTopParameters())
    rest, edge_maps = build_simulation_mesh(pattern)
    constraints = build_constraints(pattern, edge_maps)
    render, seeds = subdivide_for_render(rest)
    binding, _manifest = build_binding(rest, render, seeds)
    registry = build_material_preset_registry()
    avatar = avatar_contract(build_reference_avatar_mesh(), build_collision_mesh())

    report, states, selected = build_sleeveless_motion_suite(
        rest_mesh=rest,
        constraints=constraints,
        avatar_contract=avatar,
        preset_registry=registry,
        binding=binding,
    )

    assert report["integrity"]["suiteHash"] == hash_sleeveless_motion_report(report)
    assert report["crossPreset"]["allFourPresetsExecuted"] is True
    assert report["crossPreset"]["allPresetStatesDistinct"] is True
    assert all(report["crossPreset"]["materialExtremesExecuted"].values())
    assert report["underarmStress"]["actualSolverRun"] is True
    assert report["underarmStress"]["accepted"] is True
    assert report["underarmStress"]["armholeMetrics"]["armholeCount"] == 2
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
    assert (
        report["underarmStress"]["diagnostics"]["canonicalPositionDigits"]
        == CANONICAL_POSITION_DIGITS
    )
    assert all(
        record["denseBinding"]["seamConstraintCount"] == len(constraints["constraints"])
        for record in report["presetRecords"]
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
