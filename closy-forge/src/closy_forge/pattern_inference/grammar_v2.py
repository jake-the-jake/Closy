from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from closy_forge.garments.button_shirt.parameters import ButtonShirtParameters
from closy_forge.garments.button_shirt.pattern_generator import build_button_shirt_pattern
from closy_forge.garments.jacket_outerwear.parameters import JacketOuterwearParameters
from closy_forge.garments.jacket_outerwear.pattern_generator import (
    build_jacket_outerwear_pattern,
)
from closy_forge.garments.layered_asymmetric.parameters import LayeredAsymmetricParameters
from closy_forge.garments.layered_asymmetric.pattern_generator import (
    build_layered_asymmetric_pattern,
)
from closy_forge.garments.long_sleeved_top.parameters import LongSleevedTopParameters
from closy_forge.garments.long_sleeved_top.pattern_generator import (
    build_long_sleeved_top_pattern,
)
from closy_forge.garments.simple_dress.parameters import SimpleDressParameters
from closy_forge.garments.simple_dress.pattern_generator import build_simple_dress_pattern
from closy_forge.garments.simple_skirt.parameters import SimpleSkirtParameters
from closy_forge.garments.simple_skirt.pattern_generator import build_simple_skirt_pattern
from closy_forge.garments.simple_trousers.parameters import SimpleTrousersParameters
from closy_forge.garments.simple_trousers.pattern_generator import build_simple_trousers_pattern
from closy_forge.garments.sleeveless_top.parameters import SleevelessTopParameters
from closy_forge.garments.sleeveless_top.pattern_generator import build_sleeveless_top_pattern
from closy_forge.geometry.triangulation import validate_panel_boundary
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

GRAMMAR_VERSION_V2 = "closy.structured_pattern_grammar.d0.v2"
PROGRAM_VERSION = "closy.garment_program.d0.v1"


@dataclass(frozen=True)
class FamilySpec:
    parameter_type: type[Any]
    generator: Callable[[Any], dict[str, Any]]
    length_field: str
    width_field: str
    ease_field: str


FAMILY_SPECS: dict[str, FamilySpec] = {
    "sleeveless_top": FamilySpec(
        SleevelessTopParameters,
        build_sleeveless_top_pattern,
        "body_length_meters",
        "half_chest_width_meters",
        "body_ease_meters",
    ),
    "long_sleeved_top": FamilySpec(
        LongSleevedTopParameters,
        build_long_sleeved_top_pattern,
        "body_length_meters",
        "half_chest_width_meters",
        "body_ease_meters",
    ),
    "simple_skirt": FamilySpec(
        SimpleSkirtParameters,
        build_simple_skirt_pattern,
        "length_meters",
        "half_waist_width_meters",
        "waist_ease_meters",
    ),
    "simple_trousers": FamilySpec(
        SimpleTrousersParameters,
        build_simple_trousers_pattern,
        "outseam_length_meters",
        "half_waist_width_meters",
        "waist_ease_meters",
    ),
    "simple_dress": FamilySpec(
        SimpleDressParameters,
        build_simple_dress_pattern,
        "skirt_length_meters",
        "half_chest_width_meters",
        "body_ease_meters",
    ),
    "button_shirt": FamilySpec(
        ButtonShirtParameters,
        build_button_shirt_pattern,
        "body_length_meters",
        "half_chest_width_meters",
        "body_ease_meters",
    ),
    "jacket_outerwear": FamilySpec(
        JacketOuterwearParameters,
        build_jacket_outerwear_pattern,
        "body_length_meters",
        "half_chest_width_meters",
        "body_ease_meters",
    ),
    "layered_asymmetric": FamilySpec(
        LayeredAsymmetricParameters,
        build_layered_asymmetric_pattern,
        "body_length_meters",
        "half_chest_width_meters",
        "body_ease_meters",
    ),
}

SUPPORTED_SHAPING = {"waist_shaping", "asymmetric_hem"}
SUPPORTED_FASTENINGS = {"button_placket", "open_front"}


def default_parameters(family: str) -> dict[str, float | int]:
    spec = _family_spec(family)
    return dict(spec.parameter_type().to_json())


def compile_program(program: dict[str, Any]) -> dict[str, Any]:
    issues = validate_program(program)
    if issues:
        raise ValueError("invalid_garment_program:" + ";".join(issues))
    spec = _family_spec(str(program["garmentFamily"]))
    params = spec.parameter_type(**deepcopy(program["parameters"]))
    params.validate()
    pattern = spec.generator(params)
    pattern_issues = validate_compiled_pattern(pattern)
    if pattern_issues:
        raise ValueError("compiled_pattern_invalid:" + ";".join(pattern_issues))
    return pattern


def program_from_parameters(
    family: str,
    parameters: dict[str, float | int],
    *,
    program_id: str,
    base_seed: int,
    corrections: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    spec = _family_spec(family)
    params = spec.parameter_type(**parameters)
    params.validate()
    pattern = spec.generator(params)
    panels = [_panel_node(panel) for panel in pattern["panels"]]
    layer_ids = sorted({str(panel.get("layerId", "layer.base")) for panel in pattern["panels"]})
    layers = [
        {
            "semanticId": layer_id,
            "order": index,
            "parentLayerId": layer_ids[index - 1] if index else None,
        }
        for index, layer_id in enumerate(layer_ids)
    ]
    material_regions = sorted(
        {str(panel.get("materialRegion", "material.unspecified")) for panel in pattern["panels"]}
    )
    program: dict[str, Any] = {
        "schemaVersion": 1,
        "programVersion": PROGRAM_VERSION,
        "grammarVersion": GRAMMAR_VERSION_V2,
        "programId": program_id,
        "garmentFamily": family,
        "generatorId": str(pattern["patternVersion"]),
        "panelNodes": panels,
        "seamPairings": [
            {
                "semanticId": seam["id"],
                "spans": deepcopy(seam.get("spans", [])),
                "easeRatio": float(seam.get("easeRatio", 1.0)),
                "stitchType": str(seam.get("stitchType", "lockstitch")),
                "attachmentOrder": int(seam.get("attachmentOrder", 0)),
                "afterSeamIds": [],
            }
            for seam in pattern["seams"]
        ],
        "openings": [
            {
                "semanticId": opening["id"],
                "boundaryCurveIds": list(opening.get("boundaryEdges", [])),
                "status": str(opening.get("status", "open")),
                "expectedLoopCount": int(opening.get("expectedLoopCount", 1)),
            }
            for opening in pattern["openings"]
        ],
        "shapingFeatures": _shaping_features(family, parameters),
        "materialRegions": [
            {"semanticId": region, "materialClass": _material_class(region)}
            for region in material_regions
        ],
        "layerOrder": layers,
        "fastenings": _fastenings(family, parameters),
        "measurements": [
            {
                "semanticId": name,
                "value": value,
                "unit": "count" if isinstance(value, int) else "metres",
                "confidence": 1.0,
            }
            for name, value in sorted(parameters.items())
        ],
        "parameters": deepcopy(parameters),
        "correctionOperations": deepcopy(corrections or []),
        "provenance": {
            "sourceKind": "project_authored_synthetic_fixture",
            "baseSeed": base_seed,
            "containsPrivateData": False,
            "sourcePatternHash": sha256_bytes(canonical_dumps(pattern).encode("utf-8")),
        },
    }
    issues = validate_program(program)
    if issues:
        raise ValueError("generated_garment_program_invalid:" + ";".join(issues))
    return program


def validate_program(program: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if program.get("programVersion") != PROGRAM_VERSION:
        issues.append("program_version_invalid")
    if program.get("grammarVersion") != GRAMMAR_VERSION_V2:
        issues.append("grammar_version_invalid")
    family = str(program.get("garmentFamily", ""))
    if family not in FAMILY_SPECS:
        issues.append("garment_family_unsupported")

    panels = program.get("panelNodes", [])
    panel_ids = [str(panel.get("semanticId")) for panel in panels]
    curves = [curve for panel in panels for curve in panel.get("boundaryCurves", [])]
    curve_ids = [str(curve.get("semanticId")) for curve in curves]
    seam_ids = [str(seam.get("semanticId")) for seam in program.get("seamPairings", [])]
    opening_ids = [str(item.get("semanticId")) for item in program.get("openings", [])]
    all_ids = panel_ids + curve_ids + seam_ids + opening_ids
    if len(all_ids) != len(set(all_ids)):
        issues.append("duplicate_semantic_id")
    if not panels:
        issues.append("panel_nodes_missing")
    for panel in panels:
        reconstructed = {
            "id": panel.get("semanticId"),
            "boundary": [
                {
                    "id": curve.get("semanticId"),
                    "curve": {
                        "type": curve.get("curveType"),
                        "points": curve.get("controlPoints", []),
                    },
                    "sampleCount": curve.get("sampleCount", 0),
                }
                for curve in panel.get("boundaryCurves", [])
            ],
        }
        try:
            if validate_panel_boundary(reconstructed):
                issues.append("non_simple_panel")
        except (IndexError, KeyError, TypeError, ValueError):
            issues.append("non_simple_panel")

    for seam in program.get("seamPairings", []):
        spans = seam.get("spans", [])
        if len(spans) != 2:
            issues.append("seam_spans_missing")
            continue
        references = {(span.get("panelId"), span.get("edgeId")) for span in spans}
        if len(references) != 2:
            issues.append("impossible_seam_cycle")
        for span in spans:
            if span.get("panelId") not in panel_ids or span.get("edgeId") not in curve_ids:
                issues.append("seam_span_reference_invalid")
            if span.get("orientation") not in {"forward", "reverse"}:
                issues.append("seam_span_orientation_invalid")
        ease = seam.get("easeRatio")
        if not isinstance(ease, int | float) or not 0.75 <= float(ease) <= 1.35:
            issues.append("seam_ease_inconsistent")
    if _has_cycle(
        {
            str(seam.get("semanticId")): list(seam.get("afterSeamIds", []))
            for seam in program.get("seamPairings", [])
        }
    ):
        issues.append("impossible_seam_cycle")

    for opening in program.get("openings", []):
        edges = opening.get("boundaryCurveIds", [])
        if (
            opening.get("status") != "open"
            or not edges
            or any(edge not in curve_ids for edge in edges)
            or int(opening.get("expectedLoopCount", 0)) < 1
        ):
            issues.append("opening_invalid")

    if any(
        item.get("type") not in SUPPORTED_SHAPING for item in program.get("shapingFeatures", [])
    ):
        issues.append("shaping_feature_unsupported")
    if any(item.get("type") not in SUPPORTED_FASTENINGS for item in program.get("fastenings", [])):
        issues.append("fastening_unsupported")
    layers = program.get("layerOrder", [])
    layer_ids = {item.get("semanticId") for item in layers}
    layer_graph = {
        str(item.get("semanticId")): (
            [str(item["parentLayerId"])] if item.get("parentLayerId") is not None else []
        )
        for item in layers
    }
    if any(
        parent not in layer_ids for parents in layer_graph.values() for parent in parents
    ) or _has_cycle(layer_graph):
        issues.append("layer_cycle_or_reference_invalid")
    if family in FAMILY_SPECS:
        try:
            params = FAMILY_SPECS[family].parameter_type(**program.get("parameters", {}))
            params.validate()
        except (TypeError, ValueError):
            issues.append("parameter_out_of_range")
    return sorted(set(issues))


def validate_compiled_pattern(pattern: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    panels = pattern.get("panels", [])
    panel_ids = {panel.get("id") for panel in panels}
    edge_ids = {edge.get("id") for panel in panels for edge in panel.get("boundary", [])}
    if not panels:
        issues.append("compiled_panels_missing")
    for panel in panels:
        issues.extend(f"compiled_{code}" for code in validate_panel_boundary(panel))
    for seam in pattern.get("seams", []):
        if len(seam.get("spans", [])) != 2:
            issues.append("compiled_seam_spans_missing")
        for span in seam.get("spans", []):
            if span.get("panelId") not in panel_ids or span.get("edgeId") not in edge_ids:
                issues.append("compiled_seam_reference_invalid")
    for opening in pattern.get("openings", []):
        if opening.get("status") != "open" or any(
            edge not in edge_ids for edge in opening.get("boundaryEdges", [])
        ):
            issues.append("compiled_opening_invalid")
    return sorted(set(issues))


def _panel_node(panel: dict[str, Any]) -> dict[str, Any]:
    return {
        "semanticId": panel["id"],
        "semanticRole": str(panel.get("semanticRole", "unspecified")),
        "materialRegionId": str(panel.get("materialRegion", "material.unspecified")),
        "layerId": str(panel.get("layerId", "layer.base")),
        "boundaryCurves": [
            {
                "semanticId": edge["id"],
                "curveType": edge["curve"]["type"],
                "controlPoints": deepcopy(edge["curve"]["points"]),
                "sampleCount": int(edge["sampleCount"]),
            }
            for edge in panel["boundary"]
        ],
    }


def _shaping_features(family: str, parameters: dict[str, float | int]) -> list[dict[str, Any]]:
    if family in {"simple_skirt", "simple_trousers", "simple_dress"}:
        return [{"semanticId": f"shape.{family}.waist", "type": "waist_shaping"}]
    if family == "layered_asymmetric":
        return [
            {
                "semanticId": "shape.layered_asymmetric.hem",
                "type": "asymmetric_hem",
                "amountMeters": parameters["outer_asymmetry_drop_meters"],
            }
        ]
    return []


def _fastenings(family: str, parameters: dict[str, float | int]) -> list[dict[str, Any]]:
    if family == "button_shirt":
        return [
            {
                "semanticId": "fastening.button_shirt.front",
                "type": "button_placket",
                "count": int(parameters["button_count"]),
            }
        ]
    if family == "jacket_outerwear":
        return [{"semanticId": "fastening.jacket.front", "type": "open_front"}]
    return []


def _material_class(material_id: str) -> str:
    if "woven" in material_id:
        return "woven"
    if "jersey" in material_id or "knit" in material_id:
        return "knit"
    return "unspecified"


def _has_cycle(graph: dict[str, list[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for child in graph.get(node, []):
            if child in graph and visit(child):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)


def _family_spec(family: str) -> FamilySpec:
    try:
        return FAMILY_SPECS[family]
    except KeyError as exc:
        raise ValueError(f"unsupported_garment_family:{family}") from exc
