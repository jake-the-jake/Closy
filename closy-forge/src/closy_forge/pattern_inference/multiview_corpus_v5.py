from __future__ import annotations

import ctypes
import importlib
import math
import os
import sys
import time
from collections import Counter
from copy import deepcopy
from typing import Any

from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.inspection.cpu_raster import rasterize_settled_garment
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.raster.png_codec import decode_png_rgba, encode_png_rgba

from .grammar_v2 import FAMILY_SPECS, compile_program, default_parameters, program_from_parameters
from .reference_3d_v1 import build_reference_assembly

CORPUS_VERSION = "closy.multiview_reference_assembly_corpus.synthetic_d0.v5"
SPLIT_VERSION = "closy.multiview_reference_assembly_split.synthetic_d0.v5"
RENDERER_VERSION = "closy.cpu_zbuffer.reference_assembly.multiview.v2"
OBSERVABLE_VERSION = "closy.multiview_rgb_observables.v2"

VIEW_ROLES = ("front", "rear", "left", "right")
_RENDER_LABELS = {
    "front": "front",
    "rear": "back",
    "left": "left_three_quarter",
    "right": "right_three_quarter",
}
_VIEW_FEATURES = (
    "present",
    "foregroundFraction",
    "aspectRatio",
    "centroidX",
    "centroidY",
    "upperFraction",
    "hemRatio",
    "centerGap",
    "contourComplexity",
    "bilateralSymmetry",
    "luma",
    "textureResponse",
    "cameraYaw",
    "cameraPitch",
)
FEATURE_NAMES = tuple(f"{role}.{name}" for role in VIEW_ROLES for name in _VIEW_FEATURES)

_BACKGROUNDS = (
    (238, 235, 228, 255),
    (218, 228, 225, 255),
    (231, 222, 214, 255),
    (220, 222, 230, 255),
)
_MATERIALS = (
    (64, 91, 140, 255),
    (137, 75, 69, 255),
    (70, 116, 94, 255),
    (173, 132, 74, 255),
)


def build_multiview_corpus_v5(
    *,
    seed: int = 82_031,
    programs_per_family: int = 64,
    captures_per_program: int = 4,
    width: int = 24,
    height: int = 36,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Render assembled 3D reference garments and retain only decoded RGB observables.

    The geometry is a deterministic reference assembly, not a settled or physical drape.
    Raw PNGs and decoded RGBA buffers remain ephemeral inside this call.
    """

    if programs_per_family < 4 or captures_per_program < 1:
        raise ValueError("multiview_corpus_profile_too_small")
    if width < 20 or height < 28:
        raise ValueError("multiview_corpus_resolution_too_small")
    start = time.perf_counter_ns()
    starting_rss = _peak_rss_bytes()
    programs: list[dict[str, Any]] = []
    captures: list[dict[str, Any]] = []
    image_hashes: list[str] = []
    split_groups: dict[str, list[str]] = {"train": [], "validation": [], "test": []}
    family_counts: Counter[str] = Counter()
    triangle_counts: list[int] = []
    for family_index, family in enumerate(FAMILY_SPECS):
        for program_index in range(programs_per_family):
            source_seed = seed + family_index * 100_003 + program_index * 977
            parameters, target = _varied_parameters(family, program_index, programs_per_family)
            program = program_from_parameters(
                family,
                parameters,
                program_id=f"program.{family}.{program_index:03d}",
                base_seed=source_seed,
            )
            pattern = compile_program(program)
            reference = build_reference_assembly(family, pattern)
            simulation: MeshSet = reference["simulation"]
            identity = _program_identity(program)
            split_name = _split_name(program_index, programs_per_family)
            split_groups[split_name].append(identity)
            family_counts[family] += 1
            triangle_counts.append(simulation.triangle_count)
            programs.append(
                {
                    "programIdentity": identity,
                    "programId": program["programId"],
                    "family": family,
                    "split": split_name,
                    "program": _portable_program(program),
                    "target": target,
                    "referenceAudit": reference["audit"],
                    "nuisanceGroups": _nuisance_groups(program_index),
                }
            )
            for capture_index in range(captures_per_program):
                capture = _render_capture(
                    simulation,
                    identity=identity,
                    program_index=program_index,
                    capture_index=capture_index,
                    width=width,
                    height=height,
                )
                image_hashes.extend(capture.pop("imageHashes"))
                captures.append(
                    {
                        "captureId": (f"capture.{family}.{program_index:03d}.{capture_index:02d}"),
                        "programIdentity": identity,
                        "split": split_name,
                        "input": capture["input"],
                        "audit": capture["audit"],
                        "target": {"family": family, **target},
                    }
                )
    ending_peak_rss = _peak_rss_bytes()
    split = _split_manifest(split_groups, captures, programs_per_family)
    dataset: dict[str, Any] = {
        "schemaVersion": 1,
        "corpusVersion": CORPUS_VERSION,
        "sourceRepresentation": "assembled_reference_3d_simulation_mesh",
        "physicalSettleClaimed": False,
        "featureNames": list(FEATURE_NAMES),
        "featureContract": {
            "source": "decoded_rgb_pixels_and_declared_camera_role_only",
            "version": OBSERVABLE_VERSION,
            "viewRolesPreserved": list(VIEW_ROLES),
            "viewAveragingBeforeModel": False,
            "targetMasksConsumed": False,
            "depthConsumed": False,
            "normalsConsumed": False,
            "programConsumed": False,
            "targetMetadataConsumed": False,
        },
        "renderer": {
            "version": RENDERER_VERSION,
            "kind": "deterministic_cpu_triangle_zbuffer",
            "width": width,
            "height": height,
            "decodedImageCount": len(image_hashes),
            "captureSetCount": len(captures),
            "rawRastersPersisted": False,
            "decodedCachesPersisted": False,
        },
        "programs": programs,
        "captures": captures,
        "challengeSet": _challenge_set(captures),
        "shiftSuites": _shift_suites(programs),
        "containsPrivateData": False,
        "externalDatasets": [],
        "licence": "project-authored synthetic fixtures; internal Closy test and development use",
        "integrity": {
            "imageHashInventory": sha256_bytes("|".join(sorted(image_hashes)).encode("ascii")),
            "uniqueImageHashCount": len(set(image_hashes)),
            "programInventory": sha256_bytes(
                "|".join(sorted(item["programIdentity"] for item in programs)).encode("ascii")
            ),
        },
        "runtime": {
            "wallNanoseconds": time.perf_counter_ns() - start,
            "peakRssBytes": max(starting_rss, ending_peak_rss),
            "memoryMeasurement": "process_peak_resident_set_size",
            "threadCount": 1,
        },
        "audit": {
            "familyCounts": dict(sorted(family_counts.items())),
            "minimumReferenceTriangleCount": min(triangle_counts),
            "maximumReferenceTriangleCount": max(triangle_counts),
        },
    }
    issues = validate_multiview_corpus_v5(dataset, split)
    if issues:
        raise ValueError("invalid_multiview_corpus_v5:" + ";".join(issues))
    return dataset, split


def validate_multiview_corpus_v5(dataset: dict[str, Any], split: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    programs = dataset.get("programs", [])
    captures = dataset.get("captures", [])
    renderer = dataset.get("renderer", {})
    if dataset.get("corpusVersion") != CORPUS_VERSION:
        issues.append("multiview_corpus_version_invalid")
    if split.get("splitVersion") != SPLIT_VERSION:
        issues.append("multiview_split_version_invalid")
    if tuple(dataset.get("featureNames", [])) != FEATURE_NAMES:
        issues.append("multiview_observable_schema_invalid")
    full_profile = len(programs) == len(FAMILY_SPECS) * 64
    expected_captures = len(programs) * int(split.get("capturesPerProgram", 0))
    if len(captures) != expected_captures:
        issues.append("multiview_capture_count_invalid")
    if int(renderer.get("decodedImageCount", 0)) != len(captures) * len(VIEW_ROLES):
        issues.append("multiview_decoded_image_count_invalid")
    if full_profile and (len(programs) != 512 or len(captures) != 2_048):
        issues.append("multiview_full_profile_count_invalid")
    if full_profile and int(renderer.get("decodedImageCount", 0)) != 8_192:
        issues.append("multiview_full_image_budget_invalid")
    identities = [str(item.get("programIdentity", "")) for item in programs]
    if "" in identities or len(identities) != len(set(identities)):
        issues.append("multiview_program_identity_invalid")
    for capture in captures:
        observation = capture.get("input", {})
        if tuple(observation) != FEATURE_NAMES:
            issues.append("multiview_capture_observable_invalid")
        elif any(
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(float(value))
            for value in observation.values()
        ):
            issues.append("multiview_capture_nonfinite")
        if capture.get("audit", {}).get("viewRoles") != list(VIEW_ROLES):
            issues.append("multiview_role_inventory_invalid")
    groups = {
        name: set(map(str, split.get("groups", {}).get(name, [])))
        for name in ("train", "validation", "test")
    }
    if groups["train"] & groups["validation"] or groups["train"] & groups["test"]:
        issues.append("multiview_split_leakage")
    if groups["validation"] & groups["test"]:
        issues.append("multiview_split_leakage")
    if set(identities) != set().union(*groups.values()):
        issues.append("multiview_split_coverage_invalid")
    if full_profile:
        family_split = split.get("familyCounts", {})
        if any(
            family_split.get(family) != {"train": 40, "validation": 8, "test": 16}
            for family in FAMILY_SPECS
        ):
            issues.append("multiview_family_split_count_invalid")
    return sorted(set(issues))


def compact_corpus_manifest_v5(dataset: dict[str, Any], split: dict[str, Any]) -> dict[str, Any]:
    """Return the committed manifest without pixels, feature rows, or target programmes."""

    programs = dataset["programs"]
    payload: dict[str, Any] = {
        "schemaVersion": 1,
        "corpusVersion": dataset["corpusVersion"],
        "sourceRepresentation": dataset["sourceRepresentation"],
        "physicalSettleClaimed": False,
        "renderer": dataset["renderer"],
        "featureContract": dataset["featureContract"],
        "counts": {
            "programmeIdentities": len(programs),
            "captureSets": len(dataset["captures"]),
            "decodedImages": dataset["renderer"]["decodedImageCount"],
            "families": len(FAMILY_SPECS),
            "captureVariantsPerProgramme": split["capturesPerProgram"],
            "viewsPerCapture": len(VIEW_ROLES),
        },
        "split": split,
        "programInventory": [
            {
                "programIdentity": item["programIdentity"],
                "family": item["family"],
                "split": item["split"],
                "nuisanceGroups": item["nuisanceGroups"],
                "referenceTopologyHash": item["referenceAudit"]["simulationTopologyHash"],
            }
            for item in programs
        ],
        "shiftSuites": dataset["shiftSuites"],
        "integrity": dataset["integrity"],
        "runtime": dataset["runtime"],
        "containsPrivateData": False,
        "rawRastersPersisted": False,
    }
    payload["manifestHash"] = sha256_bytes(canonical_dumps(payload).encode("utf-8"))
    return payload


def extract_view_observables_v2(
    width: int, height: int, rgba: bytes, camera: dict[str, object]
) -> dict[str, float]:
    """Extract the frozen RGB-only per-view schema used by E1 and E2."""

    return _view_observables(width, height, rgba, camera)


def _render_capture(
    meshset: MeshSet,
    *,
    identity: str,
    program_index: int,
    capture_index: int,
    width: int,
    height: int,
) -> dict[str, Any]:
    nuisance = _nuisance_groups(program_index)
    transformed = _transform_mesh(
        meshset,
        avatar_index=int(nuisance["avatarShapeGroup"].rsplit(".", 1)[1]),
        pose_index=(program_index + capture_index) % 4,
    )
    inputs: dict[str, float] = {}
    image_hashes: list[str] = []
    view_audits: list[dict[str, Any]] = []
    for role in VIEW_ROLES:
        camera = _camera(role, program_index, capture_index)
        background = _BACKGROUNDS[(program_index + capture_index) % len(_BACKGROUNDS)]
        material = _MATERIALS[(program_index * 3 + capture_index) % len(_MATERIALS)]
        sampler = _texture_sampler(
            material,
            style_index=int(nuisance["rendererStyleGroup"].rsplit(".", 1)[1]),
            light_index=(program_index + capture_index) % 4,
        )
        raster = rasterize_settled_garment(
            transformed,
            label=_RENDER_LABELS[role],
            width=width,
            height=height,
            camera=camera,
            texture_sampler=sampler,
            background=background,
        )
        rgba = raster.rgba
        missing = capture_index == 3 and role == "rear" and program_index % 3 == 0
        if missing:
            rgba = bytes(background * (width * height))
        elif capture_index == 3 and role in {"front", "left"}:
            rgba = _occlude(rgba, width, height, background)
        png = encode_png_rgba(width, height, rgba)
        decoded = decode_png_rgba(png)
        image_hash = sha256_bytes(decoded.rgba)
        image_hashes.append(image_hash)
        values = _view_observables(decoded.width, decoded.height, decoded.rgba, camera)
        for name in _VIEW_FEATURES:
            inputs[f"{role}.{name}"] = values[name]
        view_audits.append(
            {
                "role": role,
                "renderLabel": _RENDER_LABELS[role],
                "pixelHash": image_hash,
                "renderedTriangleCount": raster.rendered_triangle_count,
                "missingViewVariant": missing,
            }
        )
    return {
        "input": inputs,
        "imageHashes": image_hashes,
        "audit": {
            "sourceProgramDigest": identity,
            "viewRoles": list(VIEW_ROLES),
            "views": view_audits,
            "decodedBy": "closy.raster.png_codec.decode_png_rgba",
            "multiviewFusion": "none_per_view_observables_preserved",
            "rawPixelsPersisted": False,
            "targetMasksConsumed": False,
            "depthConsumed": False,
            "poseVariant": f"pose.{(program_index + capture_index) % 4}",
            **nuisance,
        },
    }


def _view_observables(
    width: int, height: int, rgba: bytes, camera: dict[str, object]
) -> dict[str, float]:
    rgb = [tuple(rgba[index : index + 3]) for index in range(0, len(rgba), 4)]
    border = [
        rgb[y * width + x]
        for y in range(height)
        for x in range(width)
        if x in {0, width - 1} or y in {0, height - 1}
    ]
    background = Counter(border).most_common(1)[0][0]
    mask = [_colour_distance(pixel, background) > 22.0 for pixel in rgb]
    points = [(index % width, index // width) for index, active in enumerate(mask) if active]
    yaw = _camera_number(camera, "azimuthDegrees", 0.0) / 180.0
    pitch = _camera_number(camera, "elevationDegrees", 4.0) / 45.0
    if not points:
        return {name: 0.0 for name in _VIEW_FEATURES} | {
            "cameraYaw": round(yaw, 9),
            "cameraPitch": round(pitch, 9),
        }
    min_x, max_x = min(x for x, _ in points), max(x for x, _ in points)
    min_y, max_y = min(y for _, y in points), max(y for _, y in points)
    box_width = max_x - min_x + 1
    box_height = max_y - min_y + 1
    area = len(points)
    center_x = (min_x + max_x) // 2
    row_widths = [sum(mask[y * width + x] for x in range(width)) for y in range(height)]
    upper = sum(y < min_y + box_height * 0.5 for _, y in points) / area
    hem_rows = row_widths[max(min_y, max_y - max(1, box_height // 8)) : max_y + 1]
    hem_ratio = (sum(hem_rows) / max(len(hem_rows), 1)) / max(max(row_widths), 1)
    lower_start = min_y + box_height // 2
    center_gap = sum(not mask[y * width + center_x] for y in range(lower_start, max_y + 1)) / max(
        max_y - lower_start + 1, 1
    )
    perimeter = 0
    colour_edges = 0
    for x, y in points:
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nx, ny = x + dx, y + dy
            active = 0 <= nx < width and 0 <= ny < height and mask[ny * width + nx]
            if not active:
                perimeter += 1
            elif _colour_distance(rgb[y * width + x], rgb[ny * width + nx]) > 10.0:
                colour_edges += 1
    overlap = union = 0
    for y in range(min_y, max_y + 1):
        for x in range(min_x, max_x + 1):
            left = mask[y * width + x]
            right = mask[y * width + (min_x + max_x - x)]
            overlap += int(left and right)
            union += int(left or right)
    foreground = [rgb[index] for index, active in enumerate(mask) if active]
    luma = sum(0.2126 * p[0] + 0.7152 * p[1] + 0.0722 * p[2] for p in foreground)
    return {
        "present": 1.0,
        "foregroundFraction": round(area / (width * height), 9),
        "aspectRatio": round(box_height / max(box_width, 1), 9),
        "centroidX": round(sum(x for x, _ in points) / area / width, 9),
        "centroidY": round(sum(y for _, y in points) / area / height, 9),
        "upperFraction": round(upper, 9),
        "hemRatio": round(hem_ratio, 9),
        "centerGap": round(center_gap, 9),
        "contourComplexity": round(perimeter / max(math.sqrt(area), 1.0), 9),
        "bilateralSymmetry": round(overlap / max(union, 1), 9),
        "luma": round(luma / max(255 * len(foreground), 1), 9),
        "textureResponse": round(colour_edges / max(area * 4, 1), 9),
        "cameraYaw": round(yaw, 9),
        "cameraPitch": round(pitch, 9),
    }


def _transform_mesh(meshset: MeshSet, *, avatar_index: int, pose_index: int) -> MeshSet:
    x_scale = (0.94, 1.0, 1.06, 1.03)[avatar_index % 4]
    z_scale = (0.96, 1.02, 1.05, 0.93)[avatar_index % 4]
    pose_shift = (-0.012, 0.0, 0.014, -0.006)[pose_index % 4]
    meshes = []
    for mesh in meshset.meshes:
        sleeve_sign = -1.0 if "left" in mesh.panel_id else 1.0
        is_sleeve = "sleeve" in mesh.panel_id
        vertices = [
            (
                x * x_scale + (sleeve_sign * pose_shift if is_sleeve else 0.0),
                y + (abs(x) * pose_shift * 0.25 if is_sleeve else 0.0),
                z * z_scale,
            )
            for x, y, z in mesh.vertices
        ]
        meshes.append(
            Mesh(
                name=mesh.name,
                panel_id=mesh.panel_id,
                vertices=vertices,
                panel_uvs=list(mesh.panel_uvs),
                triangles=list(mesh.triangles),
                material_id=mesh.material_id,
            )
        )
    return MeshSet(meshes)


def _texture_sampler(base: tuple[int, int, int, int], *, style_index: int, light_index: int) -> Any:
    def sample(panel_id: str, uv: tuple[float, float]) -> tuple[int, int, int, int]:
        stripe = int((uv[0] * (5 + style_index) + uv[1] * (3 + light_index)) * 7) % 2
        panel_bias = sum(panel_id.encode("utf-8")) % 11
        shade = 0.78 + light_index * 0.035 + stripe * 0.04 + panel_bias * 0.002
        return (
            min(255, int(base[0] * shade)),
            min(255, int(base[1] * shade)),
            min(255, int(base[2] * shade)),
            255,
        )

    return sample


def _camera(role: str, program_index: int, capture_index: int) -> dict[str, object]:
    base = {"front": 0.0, "rear": 180.0, "left": -32.0, "right": 32.0}[role]
    camera_group = (program_index * 5) % 4
    return {
        "projection": "orthographic",
        "azimuthDegrees": base + (capture_index - 1.5) * 1.4 + camera_group * 0.35,
        "elevationDegrees": 3.0 + capture_index * 0.7,
        "principalPointNormalized": [
            0.5 + (camera_group - 1.5) * 0.004,
            0.5 + (capture_index - 1.5) * 0.003,
        ],
    }


def _occlude(rgba: bytes, width: int, height: int, colour: tuple[int, int, int, int]) -> bytes:
    result = bytearray(rgba)
    for y in range(height * 2 // 5, height * 3 // 5):
        for x in range(width * 3 // 5, width * 4 // 5):
            offset = (y * width + x) * 4
            result[offset : offset + 4] = bytes(colour)
    return bytes(result)


def _varied_parameters(
    family: str, index: int, count: int
) -> tuple[dict[str, float | int], dict[str, Any]]:
    spec = FAMILY_SPECS[family]
    parameters = deepcopy(default_parameters(family))
    denominator = max(count - 1, 1)
    length_n = 2.0 * index / denominator - 1.0
    width_n = 2.0 * ((index * 19) % count) / denominator - 1.0
    ease_n = 2.0 * ((index * 37) % count) / denominator - 1.0
    parameters[spec.length_field] = round(
        float(parameters[spec.length_field]) * (1.0 + length_n * 0.075), 9
    )
    parameters[spec.width_field] = round(
        float(parameters[spec.width_field]) * (1.0 + width_n * 0.055), 9
    )
    parameters[spec.ease_field] = round(float(parameters[spec.ease_field]) + ease_n * 0.0075, 9)
    spec.parameter_type(**parameters).validate()
    return parameters, {
        "continuous": {
            "length": {
                "field": spec.length_field,
                "value": float(parameters[spec.length_field]),
                "normalized": round(length_n, 9),
                "unit": "metre",
            },
            "width": {
                "field": spec.width_field,
                "value": float(parameters[spec.width_field]),
                "normalized": round(width_n, 9),
                "unit": "metre",
            },
            "ease": {
                "field": spec.ease_field,
                "value": float(parameters[spec.ease_field]),
                "normalized": round(ease_n, 9),
                "unit": "metre",
            },
        },
        "parameterRegime": "boundary_extrapolation"
        if index >= count - count // 8
        else "interpolation",
    }


def _split_name(index: int, count: int) -> str:
    if count == 64:
        return "train" if index < 40 else "validation" if index < 48 else "test"
    train_end = max(2, count - 2)
    return "train" if index < train_end else "validation" if index == count - 2 else "test"


def _split_manifest(
    split_groups: dict[str, list[str]], captures: list[dict[str, Any]], programs_per_family: int
) -> dict[str, Any]:
    family_counts: dict[str, dict[str, int]] = {}
    for family in FAMILY_SPECS:
        family_counts[family] = {
            split: sum(
                capture["captureId"].startswith(f"capture.{family}.")
                and capture["programIdentity"] in split_groups[split]
                for capture in captures
            )
            // max(
                sum(
                    capture["programIdentity"] == captures[0]["programIdentity"]
                    for capture in captures
                ),
                1,
            )
            for split in ("train", "validation", "test")
        }
    captures_per_program = len(captures) // max(sum(len(v) for v in split_groups.values()), 1)
    # Recompute counts by identity to avoid coupling them to capture ordering.
    family_counts = {
        family: {
            split: len(
                {
                    capture["programIdentity"]
                    for capture in captures
                    if capture["captureId"].startswith(f"capture.{family}.")
                    and capture["programIdentity"] in split_groups[split]
                }
            )
            for split in ("train", "validation", "test")
        }
        for family in FAMILY_SPECS
    }
    split: dict[str, Any] = {
        "schemaVersion": 1,
        "splitVersion": SPLIT_VERSION,
        "groupKey": "programIdentity_before_capture_derivatives",
        "groups": {name: sorted(values) for name, values in split_groups.items()},
        "captures": {
            name: sorted(
                capture["captureId"]
                for capture in captures
                if capture["programIdentity"] in split_groups[name]
            )
            for name in ("train", "validation", "test")
        },
        "familyCounts": family_counts,
        "programsPerFamily": programs_per_family,
        "capturesPerProgram": captures_per_program,
        "derivativeCoLocation": [
            "views",
            "captures",
            "augmentations",
            "corrections",
            "renderer_derivatives",
        ],
        "leakageAudit": {
            "identityAssignedBeforeRendering": True,
            "groupIntersections": {
                "trainValidation": sorted(
                    set(split_groups["train"]) & set(split_groups["validation"])
                ),
                "trainTest": sorted(set(split_groups["train"]) & set(split_groups["test"])),
                "validationTest": sorted(
                    set(split_groups["validation"]) & set(split_groups["test"])
                ),
            },
        },
    }
    split["splitHash"] = sha256_bytes(canonical_dumps(split).encode("utf-8"))
    return split


def _nuisance_groups(index: int) -> dict[str, str]:
    return {
        "avatarShapeGroup": f"avatar.{(index * 5 + 1) % 4}",
        "cameraLightingGroup": f"camera_light.{(index * 7 + 2) % 5}",
        "rendererStyleGroup": f"renderer.{(index * 11 + 3) % 4}",
    }


def _shift_suites(programs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    definitions = (
        ("avatar_shape_shift", "avatarShapeGroup", "avatar.3"),
        ("camera_lighting_shift", "cameraLightingGroup", "camera_light.4"),
        ("renderer_style_shift", "rendererStyleGroup", "renderer.3"),
        ("continuous_extrapolation", "parameterRegime", "boundary_extrapolation"),
    )
    return [
        {
            "suiteId": suite,
            "heldOutGroupAxis": axis,
            "heldOutGroup": value,
            "programIdentities": sorted(
                item["programIdentity"]
                for item in programs
                if (
                    item.get("nuisanceGroups", {}).get(axis) == value
                    or axis == "parameterRegime"
                    and item["target"]["parameterRegime"] == value
                )
                and item["split"] == "test"
            ),
            "groupAssignedIndependentOfFamily": True,
        }
        for suite, axis, value in definitions
    ]


def _challenge_set(captures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kinds = (
        "non_garment",
        "unsupported_garment",
        "all_views_missing",
        "severe_crop",
        "severe_occlusion",
        "corrupt_pixels",
        "contradictory_views",
        "renderer_outlier",
    )
    return [
        {
            "challengeId": f"challenge.{index:02d}",
            "kind": kind,
            "baseCaptureHash": sha256_bytes(
                canonical_dumps(captures[index]["input"]).encode("utf-8")
            ),
            "expectedAction": "defer",
        }
        for index, kind in enumerate(kinds)
    ]


def _portable_program(program: dict[str, Any]) -> dict[str, Any]:
    value = deepcopy(program)
    value.get("provenance", {}).pop("baseSeed", None)
    return value


def _program_identity(program: dict[str, Any]) -> str:
    return sha256_bytes(canonical_dumps(_portable_program(program)).encode("utf-8"))


def _colour_distance(left: tuple[int, ...], right: tuple[int, ...]) -> float:
    return math.sqrt(sum((left[index] - right[index]) ** 2 for index in range(3)))


def _camera_number(camera: dict[str, object], name: str, default: float) -> float:
    value = camera.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"multiview_camera_number_invalid:{name}")
    return float(value)


class _WindowsProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def _peak_rss_bytes() -> int:
    if os.name == "nt":
        counters = _WindowsProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.WinDLL("kernel32.dll")
        psapi = ctypes.WinDLL("psapi.dll")
        get_current_process = kernel32.GetCurrentProcess
        get_current_process.restype = ctypes.c_void_p
        get_memory_info = psapi.GetProcessMemoryInfo
        get_memory_info.restype = ctypes.c_int
        get_memory_info.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        process = get_current_process()
        success = get_memory_info(process, ctypes.byref(counters), counters.cb)
        if not success:
            raise OSError("multiview_peak_rss_query_failed")
        return int(counters.PeakWorkingSetSize)
    resource_module = importlib.import_module("resource")
    usage = resource_module.getrusage(resource_module.RUSAGE_SELF)
    value = int(usage.ru_maxrss)
    return value if sys.platform == "darwin" else value * 1_024
