from __future__ import annotations

import itertools
import math
import time
from copy import deepcopy
from typing import Any

from closy_forge.geometry.mesh_model import Mesh, MeshSet, finite_mesh, mesh_bounds
from closy_forge.inspection.cpu_raster import rasterize_settled_garment
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import geometry_content_hash, sha256_bytes, topology_hash
from closy_forge.raster.png_codec import decode_png_rgba, encode_png_rgba

from .multiview_corpus_v5 import (
    FEATURE_NAMES,
    VIEW_ROLES,
    extract_view_observables_v2,
)

GRAMMAR_VERSION = "closy.typed_compositional_garment_grammar.d0.v2"
PROGRAM_VERSION = "closy.typed_compositional_garment_program.d0.v2"
DATASET_VERSION = "closy.typed_compositional_dataset.reference_3d.d0.v2"
SPLIT_VERSION = "closy.typed_compositional_split.reference_3d.d0.v2"

TOKEN_AXES = (
    "base",
    "torso",
    "lower",
    "sleeve",
    "neckline",
    "waist",
    "hem",
    "closure",
    "layer",
    "material",
)
TOKEN_VALUES: dict[str, tuple[str, ...]] = {
    "base": ("upper", "lower", "full"),
    "torso": ("none", "two_panel", "split_front", "princess"),
    "lower": ("none", "skirt", "split_leg"),
    "sleeve": ("none", "short", "long"),
    "neckline": ("none", "crew", "v", "collar"),
    "waist": ("straight", "shaped", "waistband"),
    "hem": ("straight", "asymmetric"),
    "closure": ("none", "front_placket", "side"),
    "layer": ("base", "outer"),
    "material": ("jersey", "woven"),
}
CONTINUOUS_AXES = ("length", "width", "ease", "sleeveLength", "flare")
HOLDOUT_GROUPS = {
    "short_v_neck": {"sleeve": "short", "neckline": "v"},
    "princess_placket": {"torso": "princess", "closure": "front_placket"},
    "full_split_leg": {"base": "full", "lower": "split_leg"},
    "outer_asymmetric": {"layer": "outer", "hem": "asymmetric"},
}

_BACKGROUND = (232, 230, 224, 255)
_MATERIALS = {"jersey": (84, 111, 151, 255), "woven": (151, 91, 78, 255)}
_RENDER_LABELS = {
    "front": "front",
    "rear": "back",
    "left": "left_three_quarter",
    "right": "right_three_quarter",
}


def legal_token_values(partial: dict[str, str], axis: str) -> tuple[str, ...]:
    """Return local grammar-state legality without enumerating full signatures."""

    if axis not in TOKEN_VALUES:
        raise ValueError(f"typed_grammar_axis_unknown:{axis}")
    base = partial.get("base")
    torso_present = base in {"upper", "full"}
    if axis == "torso":
        return TOKEN_VALUES[axis][1:] if torso_present else ("none",)
    if axis == "lower":
        return TOKEN_VALUES[axis][1:] if base in {"lower", "full"} else ("none",)
    if axis in {"sleeve", "neckline"}:
        return TOKEN_VALUES[axis][1:] if torso_present else ("none",)
    if axis == "closure":
        if not torso_present:
            return ("none", "side")
        if partial.get("torso") == "none":
            return ("none", "side")
    return TOKEN_VALUES[axis]


def validate_typed_program_v2(program: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if program.get("programVersion") != PROGRAM_VERSION:
        issues.append("typed_program_version_invalid")
    if program.get("grammarVersion") != GRAMMAR_VERSION:
        issues.append("typed_grammar_version_invalid")
    tokens = program.get("tokens")
    if not isinstance(tokens, dict) or tuple(tokens) != TOKEN_AXES:
        issues.append("typed_token_inventory_invalid")
        return sorted(set(issues))
    partial: dict[str, str] = {}
    for axis in TOKEN_AXES:
        value = str(tokens.get(axis, ""))
        if value not in legal_token_values(partial, axis):
            issues.append(f"typed_token_illegal:{axis}:{value}")
        partial[axis] = value
    parameters = program.get("parameters")
    if not isinstance(parameters, dict) or tuple(parameters) != CONTINUOUS_AXES:
        issues.append("typed_parameter_inventory_invalid")
    else:
        for axis in CONTINUOUS_AXES:
            parameter_value = parameters.get(axis)
            if isinstance(parameter_value, bool) or not isinstance(parameter_value, int | float):
                issues.append(f"typed_parameter_not_numeric:{axis}")
            elif (
                not math.isfinite(float(parameter_value))
                or not 0.0 <= float(parameter_value) <= 1.0
            ):
                issues.append(f"typed_parameter_out_of_range:{axis}")
    if tokens.get("neckline") == "collar" and tokens.get("base") not in {"upper", "full"}:
        issues.append("typed_collar_requires_torso")
    if tokens.get("closure") == "front_placket" and tokens.get("torso") == "none":
        issues.append("typed_placket_requires_torso")
    return sorted(set(issues))


def compile_typed_program_v2(program: dict[str, Any]) -> dict[str, Any]:
    issues = validate_typed_program_v2(program)
    if issues:
        raise ValueError("typed_program_invalid:" + ";".join(issues))
    tokens = {axis: str(program["tokens"][axis]) for axis in TOKEN_AXES}
    parameters = {axis: float(program["parameters"][axis]) for axis in CONTINUOUS_AXES}
    panels = _panel_specs(tokens, parameters)
    meshes = [_panel_mesh(panel, tokens["material"]) for panel in panels]
    meshset = MeshSet(meshes)
    if not finite_mesh(meshset):
        raise ValueError("typed_program_topology_nonfinite")
    boundaries = [row for panel in panels for row in _panel_boundaries(panel)]
    seams = _seam_graph(panels, tokens)
    openings = _opening_graph(panels, tokens)
    areas = {
        panel["role"]: round(float(panel["width"]) * float(panel["height"]), 9) for panel in panels
    }
    seam_lengths = [
        {
            "edge": seam,
            "leftLength": _boundary_length(boundaries, seam[0]),
            "rightLength": _boundary_length(boundaries, seam[1]),
        }
        for seam in seams
    ]
    audit = {
        "panelCount": len(panels),
        "panelRoles": sorted(str(panel["role"]) for panel in panels),
        "boundaryCount": len(boundaries),
        "seamCount": len(seams),
        "openingCount": len(openings),
        "areas": areas,
        "totalPatternArea": round(sum(areas.values()), 9),
        "measurements": _measurements(tokens, parameters),
        "seamLengths": seam_lengths,
        "meshVertexCount": meshset.vertex_count,
        "meshTriangleCount": meshset.triangle_count,
        "meshBounds": mesh_bounds(meshset),
        "topologyHash": topology_hash(meshset),
        "contentHash": geometry_content_hash(meshset),
        "topologyValid": True,
        "physicalSettleClaimed": False,
    }
    return {
        "program": deepcopy(program),
        "panels": panels,
        "boundaries": boundaries,
        "seams": seams,
        "openings": openings,
        "meshset": meshset,
        "audit": audit,
    }


def build_typed_dataset_v2(*, seed: int = 72_119) -> dict[str, Any]:
    start = time.perf_counter_ns()
    combinations = _legal_combinations()
    heldout = _heldout_combinations(combinations)
    ordinary = [tokens for tokens in combinations if not _matching_holdout_groups(tokens)]
    if len(ordinary) < 320 or any(len(rows) < 24 for rows in heldout.values()):
        raise RuntimeError("typed_composition_inventory_insufficient")
    selections: list[tuple[str, str | None, dict[str, str], int]] = []
    selections.extend(("train", None, tokens, index) for index, tokens in enumerate(ordinary[:256]))
    selections.extend(
        ("validation", None, tokens, index + 256) for index, tokens in enumerate(ordinary[256:320])
    )
    for group_index, (group, rows) in enumerate(sorted(heldout.items())):
        selections.extend(
            ("test", group, tokens, 400 + group_index * 100 + index)
            for index, tokens in enumerate(rows[:24])
        )
    records = []
    split_groups: dict[str, list[str]] = {"train": [], "validation": [], "test": []}
    for record_index, (split_name, holdout_group, tokens, variant_index) in enumerate(selections):
        parameters = _continuous_parameters(variant_index, split_name)
        program = {
            "schemaVersion": 1,
            "programVersion": PROGRAM_VERSION,
            "grammarVersion": GRAMMAR_VERSION,
            "programId": f"typed.{split_name}.{record_index:04d}",
            "tokens": tokens,
            "parameters": parameters,
            "materialRegion": f"material.{tokens['material']}",
        }
        compilation = compile_typed_program_v2(program)
        identity = sha256_bytes(canonical_dumps(program).encode("utf-8"))
        split_groups[split_name].append(identity)
        observation, render_audit = _render_observation(compilation, record_index)
        records.append(
            {
                "programIdentity": identity,
                "split": split_name,
                "holdoutCompositionGroup": holdout_group,
                "observation": observation,
                "target": {
                    "program": program,
                    "tokens": tokens,
                    "parameters": parameters,
                    "compilation": _portable_compilation(compilation),
                },
                "captureAudit": render_audit,
            }
        )
    split = {
        "schemaVersion": 1,
        "splitVersion": SPLIT_VERSION,
        "groupKey": "programIdentity_before_rendering",
        "groups": {name: sorted(values) for name, values in split_groups.items()},
        "counts": {name: len(values) for name, values in split_groups.items()},
        "heldoutStructuralCompositionGroups": [
            {
                "groupId": group,
                "atomicConstraint": constraint,
                "testCount": 24,
                "exactCombinationPresentInTraining": False,
                "atomsPresentInTraining": True,
            }
            for group, constraint in sorted(HOLDOUT_GROUPS.items())
        ],
        "programmeLookupPermitted": False,
        "familyLabelPresent": False,
        "targetSignatureMetadataPresent": False,
    }
    dataset: dict[str, Any] = {
        "schemaVersion": 1,
        "datasetVersion": DATASET_VERSION,
        "grammarVersion": GRAMMAR_VERSION,
        "featureNames": list(FEATURE_NAMES),
        "records": records,
        "split": split,
        "source": "project_authored_typed_program_reference_3d_cpu_rasters",
        "containsPrivateData": False,
        "externalDatasets": [],
        "runtime": {
            "wallNanoseconds": time.perf_counter_ns() - start,
            "cpuOnly": True,
            "threadCount": 1,
        },
    }
    issues = validate_typed_dataset_v2(dataset)
    if issues:
        raise ValueError("typed_dataset_invalid:" + ";".join(issues))
    return dataset


def validate_typed_dataset_v2(dataset: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    records = dataset.get("records", [])
    split = dataset.get("split", {})
    if dataset.get("datasetVersion") != DATASET_VERSION:
        issues.append("typed_dataset_version_invalid")
    if split.get("splitVersion") != SPLIT_VERSION:
        issues.append("typed_split_version_invalid")
    if [split.get("counts", {}).get(name) for name in ("train", "validation", "test")] != [
        256,
        64,
        96,
    ]:
        issues.append("typed_split_counts_invalid")
    identities = [str(record.get("programIdentity", "")) for record in records]
    if len(records) != 416 or "" in identities or len(identities) != len(set(identities)):
        issues.append("typed_program_identity_inventory_invalid")
    groups = [
        set(split.get("groups", {}).get(name, [])) for name in ("train", "validation", "test")
    ]
    if groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2]:
        issues.append("typed_split_leakage")
    if set(identities) != set().union(*groups):
        issues.append("typed_split_coverage_invalid")
    holdouts = split.get("heldoutStructuralCompositionGroups", [])
    if len(holdouts) != 4 or any(int(item.get("testCount", 0)) < 12 for item in holdouts):
        issues.append("typed_holdout_group_inventory_invalid")
    panel_counts = {
        int(record["target"]["compilation"]["audit"]["panelCount"]) for record in records
    }
    if len(panel_counts) < 5:
        issues.append("typed_panel_count_literal_breadth_invalid")
    if any(tuple(record.get("observation", {})) != FEATURE_NAMES for record in records):
        issues.append("typed_observable_contract_invalid")
    if any(validate_typed_program_v2(record["target"]["program"]) for record in records):
        issues.append("typed_target_program_invalid")
    if _training_contains_heldout_combinations(records):
        issues.append("typed_heldout_combination_leakage")
    return sorted(set(issues))


def compact_typed_dataset_manifest_v2(dataset: dict[str, Any]) -> dict[str, Any]:
    records = dataset["records"]
    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "datasetVersion": dataset["datasetVersion"],
        "grammarVersion": dataset["grammarVersion"],
        "source": dataset["source"],
        "featureNames": dataset["featureNames"],
        "split": dataset["split"],
        "programInventory": [
            {
                "programIdentity": record["programIdentity"],
                "split": record["split"],
                "holdoutCompositionGroup": record["holdoutCompositionGroup"],
                "panelCount": record["target"]["compilation"]["audit"]["panelCount"],
                "topologyHash": record["target"]["compilation"]["audit"]["topologyHash"],
            }
            for record in records
        ],
        "counts": {
            "records": len(records),
            "train": 256,
            "validation": 64,
            "test": 96,
            "heldoutCompositionGroups": 4,
        },
        "rawRastersPersisted": False,
        "containsPrivateData": False,
        "runtime": dataset["runtime"],
    }
    manifest["manifestHash"] = sha256_bytes(canonical_dumps(manifest).encode("utf-8"))
    return manifest


def _legal_combinations() -> list[dict[str, str]]:
    result = []
    value_rows = [TOKEN_VALUES[axis] for axis in TOKEN_AXES]
    for values in itertools.product(*value_rows):
        tokens = dict(zip(TOKEN_AXES, values, strict=True))
        partial: dict[str, str] = {}
        legal = True
        for axis in TOKEN_AXES:
            if tokens[axis] not in legal_token_values(partial, axis):
                legal = False
                break
            partial[axis] = tokens[axis]
        if legal:
            probe = {
                "programVersion": PROGRAM_VERSION,
                "grammarVersion": GRAMMAR_VERSION,
                "tokens": tokens,
                "parameters": {axis: 0.5 for axis in CONTINUOUS_AXES},
            }
            if not validate_typed_program_v2(probe):
                result.append(tokens)
    return sorted(result, key=lambda row: tuple(row[axis] for axis in TOKEN_AXES))


def _heldout_combinations(
    combinations: list[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {name: [] for name in HOLDOUT_GROUPS}
    for tokens in combinations:
        matching = _matching_holdout_groups(tokens)
        if len(matching) == 1:
            result[matching[0]].append(tokens)
    return result


def _matching_holdout_groups(tokens: dict[str, str]) -> list[str]:
    return [
        name
        for name, constraint in HOLDOUT_GROUPS.items()
        if all(tokens[axis] == value for axis, value in constraint.items())
    ]


def _training_contains_heldout_combinations(records: list[dict[str, Any]]) -> bool:
    return any(
        record["split"] == "train" and _matching_holdout_groups(record["target"]["tokens"])
        for record in records
    )


def _continuous_parameters(index: int, split_name: str) -> dict[str, float]:
    offsets = (3, 11, 19, 29, 37)
    denominator = 63.0 if split_name != "test" else 47.0
    return {
        axis: round(((index * offset + offset * 3) % int(denominator + 1)) / denominator, 9)
        for axis, offset in zip(CONTINUOUS_AXES, offsets, strict=True)
    }


def _panel_specs(tokens: dict[str, str], parameters: dict[str, float]) -> list[dict[str, Any]]:
    panels: list[dict[str, Any]] = []
    width = 0.42 + parameters["width"] * 0.16 + parameters["ease"] * 0.035
    upper_height = 0.48 + parameters["length"] * 0.2
    lower_height = 0.5 + parameters["length"] * 0.35
    waist_y = 0.82
    depth = 0.075 + parameters["ease"] * 0.025
    if tokens["base"] in {"upper", "full"}:
        front_roles = {
            "two_panel": ("torso.front",),
            "split_front": ("torso.front.left", "torso.front.right"),
            "princess": ("torso.front.left", "torso.front.center", "torso.front.right"),
        }[tokens["torso"]]
        panels.extend(_split_face_panels(front_roles, width, upper_height, waist_y, depth, "front"))
        panels.append(_panel("torso.back", width, upper_height, waist_y, -depth, "back"))
        if tokens["sleeve"] != "none":
            sleeve_length = (0.2 if tokens["sleeve"] == "short" else 0.42) * (
                0.72 + parameters["sleeveLength"] * 0.5
            )
            panels.extend(
                (
                    _sleeve_panel("sleeve.left", -1.0, width, upper_height, waist_y, sleeve_length),
                    _sleeve_panel("sleeve.right", 1.0, width, upper_height, waist_y, sleeve_length),
                )
            )
        if tokens["neckline"] == "collar":
            panels.append(
                _panel("collar", width * 0.38, 0.07, waist_y + upper_height, depth * 1.05, "front")
            )
    if tokens["base"] in {"lower", "full"}:
        lower_width = width * (1.0 + parameters["flare"] * 0.32)
        if tokens["lower"] == "skirt":
            panels.extend(
                (
                    _panel(
                        "lower.front",
                        lower_width,
                        lower_height,
                        waist_y - lower_height,
                        depth,
                        "front",
                    ),
                    _panel(
                        "lower.back",
                        lower_width,
                        lower_height,
                        waist_y - lower_height,
                        -depth,
                        "back",
                    ),
                )
            )
        else:
            leg_width = lower_width * 0.47
            for side, sign in (("left", -1.0), ("right", 1.0)):
                center = sign * lower_width * 0.25
                panels.extend(
                    (
                        _panel(
                            f"leg.{side}.front",
                            leg_width,
                            lower_height,
                            waist_y - lower_height,
                            depth,
                            "front",
                            center,
                        ),
                        _panel(
                            f"leg.{side}.back",
                            leg_width,
                            lower_height,
                            waist_y - lower_height,
                            -depth,
                            "back",
                            center,
                        ),
                    )
                )
    if tokens["waist"] == "waistband":
        panels.append(
            _panel("waistband", width * 1.02, 0.075, waist_y - 0.035, depth * 1.08, "front")
        )
    return panels


def _split_face_panels(
    roles: tuple[str, ...], width: float, height: float, y: float, z: float, face: str
) -> list[dict[str, Any]]:
    part_width = width / len(roles)
    return [
        _panel(
            role,
            part_width,
            height,
            y,
            z,
            face,
            -width * 0.5 + part_width * (index + 0.5),
        )
        for index, role in enumerate(roles)
    ]


def _panel(
    role: str,
    width: float,
    height: float,
    y: float,
    z: float,
    face: str,
    center_x: float = 0.0,
) -> dict[str, Any]:
    return {
        "id": f"typed.panel.{role}",
        "role": role,
        "width": round(width, 9),
        "height": round(height, 9),
        "origin": [round(center_x, 9), round(y, 9), round(z, 9)],
        "face": face,
        "rotationZ": 0.0,
    }


def _sleeve_panel(
    role: str,
    sign: float,
    torso_width: float,
    torso_height: float,
    waist_y: float,
    length: float,
) -> dict[str, Any]:
    panel = _panel(
        role,
        length,
        0.16,
        waist_y + torso_height * 0.69,
        0.01,
        "front",
        sign * (torso_width * 0.5 + length * 0.5 - 0.025),
    )
    panel["rotationZ"] = round(sign * -0.18, 9)
    return panel


def _panel_mesh(panel: dict[str, Any], material: str) -> Mesh:
    width = float(panel["width"])
    height = float(panel["height"])
    center_x, y, z = map(float, panel["origin"])
    angle = float(panel["rotationZ"])
    local = [(-width / 2, 0.0), (width / 2, 0.0), (width / 2, height), (-width / 2, height)]
    cosine, sine = math.cos(angle), math.sin(angle)
    vertices = [
        (
            center_x + x * cosine - local_y * sine,
            y + x * sine + local_y * cosine,
            z,
        )
        for x, local_y in local
    ]
    triangles = [(0, 1, 2), (0, 2, 3)] if panel["face"] == "front" else [(0, 2, 1), (0, 3, 2)]
    return Mesh(
        name=str(panel["id"]),
        panel_id=str(panel["id"]),
        vertices=vertices,
        panel_uvs=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
        triangles=triangles,
        material_id=f"material.{material}",
    )


def _panel_boundaries(panel: dict[str, Any]) -> list[dict[str, Any]]:
    width = float(panel["width"])
    height = float(panel["height"])
    points = {
        "bottom": (-width / 2, 0.0, width / 2, 0.0),
        "right": (width / 2, 0.0, width / 2, height),
        "top": (width / 2, height, -width / 2, height),
        "left": (-width / 2, height, -width / 2, 0.0),
    }
    return [
        {
            "id": f"{panel['id']}.boundary.{name}",
            "panelRole": panel["role"],
            "name": name,
            "endpoints": [[values[0], values[1]], [values[2], values[3]]],
            "length": round(math.hypot(values[2] - values[0], values[3] - values[1]), 9),
        }
        for name, values in points.items()
    ]


def _seam_graph(panels: list[dict[str, Any]], tokens: dict[str, str]) -> list[list[str]]:
    roles = {str(panel["role"]) for panel in panels}
    seams: list[list[str]] = []

    def connect(left: str, left_side: str, right: str, right_side: str) -> None:
        if left in roles and right in roles:
            seams.append(
                [
                    f"typed.panel.{left}.boundary.{left_side}",
                    f"typed.panel.{right}.boundary.{right_side}",
                ]
            )

    front_roles = sorted(role for role in roles if role.startswith("torso.front"))
    for left, right in zip(front_roles, front_roles[1:], strict=False):
        connect(left, "right", right, "left")
    if front_roles:
        connect(front_roles[0], "left", "torso.back", "right")
        connect(front_roles[-1], "right", "torso.back", "left")
    connect("sleeve.left", "right", front_roles[0] if front_roles else "", "left")
    connect("sleeve.right", "left", front_roles[-1] if front_roles else "", "right")
    if tokens["lower"] == "skirt":
        connect("lower.front", "left", "lower.back", "right")
        connect("lower.front", "right", "lower.back", "left")
    if tokens["lower"] == "split_leg":
        for side in ("left", "right"):
            connect(f"leg.{side}.front", "left", f"leg.{side}.back", "right")
            connect(f"leg.{side}.front", "right", f"leg.{side}.back", "left")
    if tokens["base"] == "full" and front_roles:
        lower_fronts = sorted(
            role
            for role in roles
            if role.startswith(("lower.front", "leg.")) and role.endswith(("front", "lower.front"))
        )
        if lower_fronts:
            connect(front_roles[0], "bottom", lower_fronts[0], "top")
    return sorted(seams)


def _opening_graph(panels: list[dict[str, Any]], tokens: dict[str, str]) -> list[dict[str, Any]]:
    roles = {str(panel["role"]) for panel in panels}
    openings = []
    torso = sorted(role for role in roles if role.startswith("torso."))
    if torso:
        openings.append(
            {
                "semantic": "neck",
                "boundaryMembership": [f"typed.panel.{role}.boundary.top" for role in torso],
            }
        )
    if tokens["sleeve"] == "none" and torso:
        openings.extend(
            {
                "semantic": f"arm.{side}",
                "boundaryMembership": [
                    f"typed.panel.{torso[0 if side == 'left' else -1]}.boundary.{side}"
                ],
            }
            for side in ("left", "right")
        )
    sleeves = sorted(role for role in roles if role.startswith("sleeve."))
    openings.extend(
        {
            "semantic": f"cuff.{role.rsplit('.', 1)[1]}",
            "boundaryMembership": [f"typed.panel.{role}.boundary.bottom"],
        }
        for role in sleeves
    )
    bottom_roles = sorted(
        role
        for role in roles
        if role.startswith(("lower.", "leg."))
        or role.startswith("torso.")
        and tokens["base"] == "upper"
    )
    if bottom_roles:
        openings.append(
            {
                "semantic": "hem",
                "boundaryMembership": [
                    f"typed.panel.{role}.boundary.bottom" for role in bottom_roles
                ],
            }
        )
    return sorted(openings, key=lambda item: str(item["semantic"]))


def _measurements(tokens: dict[str, str], parameters: dict[str, float]) -> dict[str, float]:
    return {
        "garmentLength": round(0.48 + parameters["length"] * 0.55, 9),
        "garmentWidth": round(0.42 + parameters["width"] * 0.16, 9),
        "sleeveLength": round(
            0.0
            if tokens["sleeve"] == "none"
            else (0.2 if tokens["sleeve"] == "short" else 0.42)
            * (0.72 + parameters["sleeveLength"] * 0.5),
            9,
        ),
        "flare": round(parameters["flare"], 9),
    }


def _boundary_length(boundaries: list[dict[str, Any]], boundary_id: str) -> float:
    return next(float(row["length"]) for row in boundaries if row["id"] == boundary_id)


def _render_observation(
    compilation: dict[str, Any], record_index: int
) -> tuple[dict[str, float], dict[str, Any]]:
    meshset: MeshSet = compilation["meshset"]
    material = _MATERIALS[str(compilation["program"]["tokens"]["material"])]
    allowed = {mesh.panel_id for mesh in meshset.meshes}

    def sampler(_panel: str, uv: tuple[float, float]) -> tuple[int, int, int, int]:
        stripe = int((uv[0] * 7 + uv[1] * 5 + record_index % 3) * 5) % 2
        shade = 0.82 + stripe * 0.08
        return (
            int(material[0] * shade),
            int(material[1] * shade),
            int(material[2] * shade),
            255,
        )

    observation: dict[str, float] = {}
    image_hashes = []
    for role in VIEW_ROLES:
        camera: dict[str, object] = {
            "projection": "orthographic",
            "azimuthDegrees": {"front": 0.0, "rear": 180.0, "left": -32.0, "right": 32.0}[role]
            + (record_index % 5 - 2) * 0.25,
            "elevationDegrees": 3.5 + (record_index % 3) * 0.25,
            "principalPointNormalized": [0.5, 0.5],
        }
        raster = rasterize_settled_garment(
            meshset,
            label=_RENDER_LABELS[role],
            width=24,
            height=36,
            camera=camera,
            texture_sampler=sampler,
            background=_BACKGROUND,
            visible_panel_ids=allowed,
        )
        decoded = decode_png_rgba(encode_png_rgba(24, 36, raster.rgba))
        image_hashes.append(sha256_bytes(decoded.rgba))
        values = extract_view_observables_v2(24, 36, decoded.rgba, camera)
        for name, value in values.items():
            observation[f"{role}.{name}"] = value
    return observation, {
        "renderer": "deterministic_cpu_triangle_zbuffer",
        "viewRoles": list(VIEW_ROLES),
        "decodedImageCount": 4,
        "pixelHashInventory": sha256_bytes("|".join(image_hashes).encode("ascii")),
        "rawPixelsPersisted": False,
        "targetMasksConsumed": False,
    }


def _portable_compilation(compilation: dict[str, Any]) -> dict[str, Any]:
    return {
        "panels": deepcopy(compilation["panels"]),
        "boundaries": deepcopy(compilation["boundaries"]),
        "seams": deepcopy(compilation["seams"]),
        "openings": deepcopy(compilation["openings"]),
        "audit": deepcopy(compilation["audit"]),
    }
