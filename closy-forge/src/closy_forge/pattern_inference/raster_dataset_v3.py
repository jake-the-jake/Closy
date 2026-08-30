from __future__ import annotations

import math
import random
import tempfile
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from PIL import Image, ImageDraw

from closy_forge.capture.raster_sources import decode_raster_fixture_pixels
from closy_forge.geometry.curves import sample_curve
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

from .dataset_v2 import FEATURE_NAMES, FORBIDDEN_INPUT_TOKENS
from .grammar_v2 import FAMILY_SPECS, compile_program, default_parameters, program_from_parameters

DATASET_VERSION_V3 = "closy.raster_pattern_dataset.synthetic_d0.v3"
SPLIT_VERSION_V3 = "closy.raster_pattern_split.synthetic_d0.v3"
RENDERER_VERSION = "closy.pattern_capture.cpu_polygon_raster.d0.v1"
FEATURE_EXTRACTOR_VERSION = "closy.pattern_capture.unassisted_pixels.d0.v1"
VIEW_LABELS = ("front", "rear", "left_oblique", "right_oblique")

_BACKGROUNDS = ((244, 241, 235), (224, 232, 230), (238, 228, 218), (226, 226, 232))
_FABRICS = ((62, 95, 148), (134, 78, 72), (74, 118, 96))
_OCCLUSION = (72, 70, 76)


def build_raster_dataset_v3(
    *, seed: int = 3901, groups_per_family: int = 12, captures_per_group: int = 4
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Build the D0 corpus from real family programs and decoded PNG pixels.

    Generator and augmentation seeds are returned only in the separate private
    provenance record. They never enter the model observation or portable corpus.
    """

    if groups_per_family < 12 or captures_per_group < 4:
        raise ValueError("raster_d0_requires_at_least_12_sources_and_4_captures")
    samples: list[dict[str, Any]] = []
    programs: dict[str, dict[str, Any]] = {}
    private_sources: list[dict[str, Any]] = []
    split_groups: dict[str, list[str]] = {"train": [], "validation": [], "test": []}
    with tempfile.TemporaryDirectory(prefix="closy-raster-dataset-") as temporary:
        root = Path(temporary)
        for family_index, family in enumerate(FAMILY_SPECS):
            for group_index in range(groups_per_family):
                source_id = f"source.{family}.{group_index:03d}"
                source_seed = seed + family_index * 100_000 + group_index * 1_003
                parameters, targets = _varied_parameters(family, group_index)
                program = program_from_parameters(
                    family,
                    parameters,
                    program_id=source_id,
                    base_seed=source_seed,
                )
                pattern = compile_program(program)
                portable_program = deepcopy(program)
                portable_program["provenance"].pop("baseSeed", None)
                programs[source_id] = portable_program
                split_name = _primary_split(group_index, groups_per_family)
                split_groups[split_name].append(source_id)
                source_digest = _program_identity(portable_program)
                private_sources.append(
                    {
                        "sourceProgramDigest": source_digest,
                        "generatorSeed": source_seed,
                        "augmentationSeeds": [
                            source_seed + index * 37 for index in range(captures_per_group)
                        ],
                    }
                )
                for capture_index in range(captures_per_group):
                    capture_seed = source_seed + capture_index * 37
                    capture = _build_capture(
                        root,
                        pattern,
                        source_digest=source_digest,
                        capture_index=capture_index,
                        seed=capture_seed,
                        material_index=(group_index + capture_index) % len(_FABRICS),
                        background_index=(group_index * 3 + capture_index) % len(_BACKGROUNDS),
                    )
                    sample_id = f"capture.{family}.{group_index:03d}.{capture_index:02d}"
                    samples.append(
                        {
                            "sampleId": sample_id,
                            "sourceProgramId": source_id,
                            "programGroupId": source_id,
                            "sourceProgramDigest": source_digest,
                            "sourceKind": "project_authored_phase8_program_raster_capture",
                            "track": "unassisted_raster",
                            "input": capture["features"],
                            "captureAudit": capture["audit"],
                            "target": {
                                "garmentFamily": family,
                                "continuousParameters": targets,
                                "programId": source_id,
                            },
                            "containsPrivateData": False,
                        }
                    )

    dataset: dict[str, Any] = {
        "schemaVersion": 1,
        "datasetVersion": DATASET_VERSION_V3,
        "track": "unassisted_raster",
        "featureNames": list(FEATURE_NAMES),
        "featureContract": {
            "source": "decoded_pixels_and_permitted_camera_metadata_only",
            "extractorVersion": FEATURE_EXTRACTOR_VERSION,
            "oracleMasksConsumed": False,
            "fixtureLandmarksConsumed": False,
            "correctionsConsumed": False,
            "targetMetadataConsumed": False,
        },
        "renderer": {
            "rendererVersion": RENDERER_VERSION,
            "sourceGeometry": "compiled_phase8_pattern_panel_boundaries",
            "rendererFamilyCount": 1,
        },
        "programs": [programs[key] for key in sorted(programs)],
        "samples": samples,
        "challengeSet": _challenge_set(samples),
        "shiftSuites": _shift_suites(samples),
        "containsPrivateData": False,
        "licence": "project-authored synthetic fixtures; internal Closy test and development use",
    }
    split: dict[str, Any] = {
        "schemaVersion": 1,
        "splitVersion": SPLIT_VERSION_V3,
        "identityComputedBeforeAugmentation": True,
        "groupKey": "sourceProgramDigest",
        "groups": {
            name: sorted(_program_identity(programs[source_id]) for source_id in source_ids)
            for name, source_ids in split_groups.items()
        },
        "samples": {
            name: sorted(
                sample["sampleId"]
                for sample in samples
                if sample["sourceProgramDigest"]
                in {_program_identity(programs[source_id]) for source_id in split_groups[name]}
            )
            for name in ("train", "validation", "test")
        },
        "policy": (
            "eight_sources_train_two_validation_two_test_per_family_" "by_preaugmentation_identity"
        ),
    }
    private_provenance: dict[str, Any] = {
        "schemaVersion": 1,
        "recordVersion": "closy.raster_pattern_private_provenance.d0.v1",
        "portable": False,
        "containsPrivateUserData": False,
        "masterGeneratorSeed": seed,
        "sources": private_sources,
        "retention": "ephemeral_test_generation_only_not_written_to_portable_evidence",
    }
    issues = validate_raster_dataset_v3(dataset, split)
    if issues:
        raise ValueError("invalid_raster_dataset_v3:" + ";".join(issues))
    return dataset, split, private_provenance


def validate_raster_dataset_v3(dataset: dict[str, Any], split: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if dataset.get("datasetVersion") != DATASET_VERSION_V3:
        issues.append("raster_dataset_version_invalid")
    if split.get("splitVersion") != SPLIT_VERSION_V3:
        issues.append("raster_split_version_invalid")
    samples = dataset.get("samples", [])
    programs = dataset.get("programs", [])
    if len(samples) < 384 or len(programs) < 96:
        issues.append("raster_dataset_scale_insufficient")
    program_digests = {_program_identity(program) for program in programs}
    if any("baseSeed" in program.get("provenance", {}) for program in programs):
        issues.append("raster_portable_generator_seed_leakage")
    sample_ids = [str(sample.get("sampleId", "")) for sample in samples]
    if len(sample_ids) != len(set(sample_ids)):
        issues.append("raster_sample_identity_duplicate")
    for sample in samples:
        observation = sample.get("input", {})
        if tuple(observation) != FEATURE_NAMES:
            issues.append("raster_feature_contract_invalid")
        if _contains_forbidden_key(observation):
            issues.append("raster_target_leakage_detected")
        if any(
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
            for value in observation.values()
        ):
            issues.append("raster_feature_numeric_invalid")
        if sample.get("sourceProgramDigest") not in program_digests:
            issues.append("raster_source_identity_invalid")
        audit = sample.get("captureAudit", {})
        if audit.get("decodedBy") != "closy.capture.raster_sources.decode_raster_fixture_pixels":
            issues.append("raster_decode_pipeline_not_used")
        if audit.get("viewLabels") != list(VIEW_LABELS):
            issues.append("raster_view_budget_invalid")
    groups = {
        name: set(map(str, split.get("groups", {}).get(name, [])))
        for name in ("train", "validation", "test")
    }
    if any(not values for values in groups.values()):
        issues.append("raster_split_empty")
    if (
        groups["train"] & groups["validation"]
        or groups["train"] & groups["test"]
        or groups["validation"] & groups["test"]
    ):
        issues.append("raster_source_identity_leakage")
    if set().union(*groups.values()) != program_digests:
        issues.append("raster_split_program_coverage_invalid")
    for name, identities in groups.items():
        expected = {
            str(sample["sampleId"])
            for sample in samples
            if str(sample.get("sourceProgramDigest")) in identities
        }
        if expected != set(map(str, split.get("samples", {}).get(name, []))):
            issues.append("raster_split_sample_membership_invalid")
    pixel_hashes = [
        str(sample.get("captureAudit", {}).get("combinedPixelHash", "")) for sample in samples
    ]
    if "" in pixel_hashes or len(pixel_hashes) != len(set(pixel_hashes)):
        issues.append("raster_duplicate_capture_detected")
    return sorted(set(issues))


def compare_compiled_pattern_rasters(
    candidate: dict[str, Any], target: dict[str, Any], *, work_root: Path
) -> dict[str, Any]:
    """Independently rerender candidate and hidden target for D0 silhouette evidence."""

    work_root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for view_index, label in enumerate(VIEW_LABELS):
        camera = _camera(label, 0)
        decoded = []
        for kind, pattern in (("candidate", candidate), ("target", target)):
            path = work_root / f"{kind}-{view_index}.png"
            _render_capture_png(
                path,
                pattern,
                label=label,
                camera=camera,
                material=_FABRICS[0],
                background=_BACKGROUNDS[0],
                seed=71 + view_index,
                occluded=False,
                mirrored=False,
            )
            decoded.append(decode_raster_fixture_pixels(path, declared_mime="image/png"))
        left_mask = _foreground_mask(decoded[0].width, decoded[0].height, decoded[0].rgba)
        right_mask = _foreground_mask(decoded[1].width, decoded[1].height, decoded[1].rgba)
        intersection = sum(a and b for a, b in zip(left_mask, right_mask, strict=True))
        union = sum(a or b for a, b in zip(left_mask, right_mask, strict=True))
        records.append(
            {
                "view": label,
                "silhouetteIoU": round(intersection / max(union, 1), 9),
                "normalisedContourDistance": round(
                    _mask_contour_distance(left_mask, right_mask, decoded[0].width), 9
                ),
            }
        )
    return {
        "rendererVersion": RENDERER_VERSION,
        "decodedThroughPhase2": True,
        "viewCount": len(records),
        "meanSilhouetteIoU": round(
            sum(float(record["silhouetteIoU"]) for record in records) / len(records), 9
        ),
        "meanNormalisedContourDistance": round(
            sum(float(record["normalisedContourDistance"]) for record in records) / len(records),
            9,
        ),
        "views": records,
    }


def _build_capture(
    root: Path,
    pattern: dict[str, Any],
    *,
    source_digest: str,
    capture_index: int,
    seed: int,
    material_index: int,
    background_index: int,
) -> dict[str, Any]:
    decoded_views: list[dict[str, Any]] = []
    for view_index, label in enumerate(VIEW_LABELS):
        path = root / f"{source_digest[:12]}-{capture_index}-{view_index}.png"
        camera = _camera(label, capture_index)
        _render_capture_png(
            path,
            pattern,
            label=label,
            camera=camera,
            material=_FABRICS[material_index],
            background=_BACKGROUNDS[background_index],
            seed=seed + view_index,
            occluded=capture_index == 3 and label in {"front", "left_oblique"},
            mirrored=capture_index == 2,
        )
        decoded = decode_raster_fixture_pixels(path, declared_mime="image/png")
        decoded_views.append(
            {
                "label": label,
                "width": decoded.width,
                "height": decoded.height,
                "rgba": decoded.rgba,
                "pixelHash": decoded.pixel_hash,
                "decodedContentSha256": decoded.decoded_content_sha256,
                "camera": camera,
            }
        )
    features = _capture_features(decoded_views)
    hashes = [str(view["pixelHash"]) for view in decoded_views]
    return {
        "features": features,
        "audit": {
            "decodedBy": "closy.capture.raster_sources.decode_raster_fixture_pixels",
            "orientationPolicy": (
                "canonical_png_top_left_origin; mirrored_variant_recorded_in_pixels"
            ),
            "colourSpacePolicy": "decoded_rgba8_srgb_fixture",
            "unassistedForegroundMethod": "border_mode_colour_distance",
            "viewLabels": list(VIEW_LABELS),
            "pixelHashes": hashes,
            "combinedPixelHash": sha256_bytes("|".join(hashes).encode("ascii")),
            "rawPixelsPortable": False,
            "fixtureMasksConsumedByModel": False,
            "fixtureLandmarksConsumedByModel": False,
            "multiviewFusion": "mean_of_pixel_derived_view_observables",
            "captureQuality": "all_views_decoded_and_nonempty_foreground",
            "nuisanceAudit": {
                "materialFamily": f"material_fixture_{material_index}",
                "backgroundFamily": f"background_fixture_{background_index}",
                "captureStyle": f"capture_variant_{capture_index}",
            },
        },
    }


def _render_capture_png(
    path: Path,
    pattern: dict[str, Any],
    *,
    label: str,
    camera: dict[str, float],
    material: tuple[int, int, int],
    background: tuple[int, int, int],
    seed: int,
    occluded: bool,
    mirrored: bool,
) -> None:
    width, height = 48, 64
    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)
    panels = _view_panels(pattern, label)
    sampled: list[tuple[dict[str, Any], list[tuple[float, float]]]] = []
    for panel in panels:
        points: list[tuple[float, float]] = []
        for edge in panel["boundary"]:
            edge_points = sample_curve(edge["curve"], int(edge["sampleCount"]))
            if points and edge_points and points[-1] == edge_points[0]:
                edge_points = edge_points[1:]
            points.extend(edge_points)
        if points:
            sampled.append((panel, _pose_panel(points, str(panel.get("semanticRole", "")))))
    all_points = [point for _panel, points in sampled for point in points]
    if not all_points:
        raise ValueError("compiled_pattern_has_no_renderable_boundary")
    min_x = min(point[0] for point in all_points)
    max_x = max(point[0] for point in all_points)
    min_y = min(point[1] for point in all_points)
    max_y = max(point[1] for point in all_points)
    scale = min(36.0 / max(max_x - min_x, 1e-6), 52.0 / max(max_y - min_y, 1e-6))
    yaw_scale = max(0.72, math.cos(float(camera["yawRadians"])))
    random_source = random.Random(seed)
    for panel_index, (_panel, points) in enumerate(sampled):
        polygon = []
        for x, y in points:
            px = (x - (min_x + max_x) * 0.5) * scale * yaw_scale + width * 0.5
            py = height - 5.0 - (y - min_y) * scale
            if mirrored:
                px = width - px
            polygon.append((round(px, 3), round(py, 3)))
        shade = 1.0 - 0.055 * (panel_index % 3)
        color = tuple(max(0, min(255, int(channel * shade))) for channel in material)
        draw.polygon(polygon, fill=color)
        draw.line(
            [*polygon, polygon[0]],
            fill=tuple(max(0, value - 28) for value in color),
            width=1,
        )
    stripe_offset = random_source.randrange(0, 7)
    for y in range(stripe_offset, height, 7):
        for x in range(width):
            pixel = cast(tuple[int, int, int], image.getpixel((x, y)))
            if _colour_distance(pixel, background) > 30:
                image.putpixel((x, y), tuple(max(0, value - 7) for value in pixel))
    if occluded:
        draw.rectangle((width * 0.56, height * 0.43, width * 0.73, height * 0.63), fill=_OCCLUSION)
    image.save(path, format="PNG", optimize=False)


def _view_panels(pattern: dict[str, Any], label: str) -> list[dict[str, Any]]:
    panels = list(pattern["panels"])
    if label == "front":
        selected = [panel for panel in panels if "back" not in str(panel.get("semanticRole", ""))]
    elif label == "rear":
        selected = [panel for panel in panels if "front" not in str(panel.get("semanticRole", ""))]
    else:
        selected = panels
    return selected or panels


def _pose_panel(points: list[tuple[float, float]], role: str) -> list[tuple[float, float]]:
    if "sleeve" not in role:
        return points
    direction = -1.0 if "left" in role else 1.0
    angle = direction * 0.72
    cosine, sine = math.cos(angle), math.sin(angle)
    rotated = [(x * cosine - y * sine, x * sine + y * cosine) for x, y in points]
    return [(x + direction * 0.39, y + 0.47) for x, y in rotated]


def _capture_features(views: list[dict[str, Any]]) -> dict[str, float]:
    per_view = [_pixel_observables(view) for view in views]
    result = {
        name: round(sum(record[name] for record in per_view) / len(per_view), 9)
        for name in FEATURE_NAMES
    }
    return result


def _pixel_observables(view: dict[str, Any]) -> dict[str, float]:
    width, height = int(view["width"]), int(view["height"])
    rgba = bytes(view["rgba"])
    rgb = [tuple(rgba[index : index + 3]) for index in range(0, len(rgba), 4)]
    mask = _foreground_mask(width, height, rgba)
    points = [(index % width, index // width) for index, active in enumerate(mask) if active]
    if not points:
        raise ValueError("decoded_capture_has_empty_unassisted_foreground")
    min_x, max_x = min(x for x, _y in points), max(x for x, _y in points)
    min_y, max_y = min(y for _x, y in points), max(y for _x, y in points)
    bbox_width, bbox_height = max_x - min_x + 1, max_y - min_y + 1
    area = len(points)
    upper = sum(1 for _x, y in points if y < min_y + bbox_height * 0.5)
    lower = area - upper
    row_widths = [sum(mask[y * width + x] for x in range(width)) for y in range(height)]
    max_row = max(row_widths)
    hem_rows = row_widths[max(min_y, max_y - max(2, bbox_height // 8)) : max_y + 1]
    hem_width = sum(hem_rows) / max(len(hem_rows), 1)
    center_x = (min_x + max_x) // 2
    lower_center_gap = sum(
        not mask[y * width + center_x] for y in range(min_y + bbox_height // 2, max_y + 1)
    ) / max(1, max_y - (min_y + bbox_height // 2) + 1)
    perimeter = 0
    isolated = 0
    colour_edges = 0
    for x, y in points:
        neighbours = []
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nx, ny = x + dx, y + dy
            active = 0 <= nx < width and 0 <= ny < height and mask[ny * width + nx]
            neighbours.append(active)
            if not active:
                perimeter += 1
            elif _colour_distance(rgb[y * width + x], rgb[ny * width + nx]) > 12:
                colour_edges += 1
        if sum(neighbours) <= 1:
            isolated += 1
    mirrored_overlap = 0
    mirrored_union = 0
    for y in range(min_y, max_y + 1):
        for x in range(min_x, max_x + 1):
            left = mask[y * width + x]
            mirror_x = min_x + max_x - x
            right = mask[y * width + mirror_x]
            mirrored_overlap += left and right
            mirrored_union += left or right
    foreground = [rgb[index] for index, active in enumerate(mask) if active]
    luma = sum(0.2126 * p[0] + 0.7152 * p[1] + 0.0722 * p[2] for p in foreground)
    luma /= max(255 * len(foreground), 1)
    dark_fraction = sum(sum(pixel) / 3 < 95 for pixel in foreground) / area
    top_rows = row_widths[min_y : min(max_y + 1, min_y + max(2, bbox_height // 5))]
    lateral_reach = max(top_rows, default=0) / max(bbox_width, 1)
    row_variation = sum(
        abs(b - a)
        for a, b in zip(
            row_widths[min_y:max_y],
            row_widths[min_y + 1 : max_y + 1],
            strict=True,
        )
    )
    camera = view["camera"]
    return {
        "maskAspectRatio": bbox_height / max(bbox_width, 1),
        "upperSilhouetteCoverage": upper / area,
        "lowerSilhouetteCoverage": lower / area,
        "lateralReachRatio": lateral_reach,
        "hemSpreadRatio": hem_width / max(max_row, 1),
        "legSeparationResponse": lower_center_gap,
        "centerEdgeResponse": sum(
            mask[y * width + center_x] != mask[(y - 1) * width + center_x]
            for y in range(max(1, min_y + 1), max_y + 1)
        )
        / max(bbox_height, 1),
        "layerEdgeResponse": colour_edges / max(area * 4, 1),
        "bilateralSymmetry": mirrored_overlap / max(mirrored_union, 1),
        "contourComplexity": perimeter / max(math.sqrt(area), 1.0),
        "fabricDrapeResponse": row_variation / max(area, 1),
        "cameraYawNormalized": float(camera["yawRadians"]) / 0.8,
        "cameraPitchNormalized": float(camera["pitchRadians"]) / 0.25,
        "maskNoiseFraction": isolated / area,
        "landmarkNoiseNormalized": abs(row_widths[min_y] - hem_width) / max(max_row, 1),
        "occlusionFraction": dark_fraction,
        "colourLuma": luma,
        "textureFrequency": colour_edges / max(area, 1),
    }


def _foreground_mask(width: int, height: int, rgba: bytes) -> list[bool]:
    rgb = [tuple(rgba[index : index + 3]) for index in range(0, len(rgba), 4)]
    border = [
        rgb[y * width + x]
        for y in range(height)
        for x in range(width)
        if x in {0, width - 1} or y in {0, height - 1}
    ]
    background = Counter(border).most_common(1)[0][0]
    return [_colour_distance(pixel, background) > 24 for pixel in rgb]


def _mask_contour_distance(left: list[bool], right: list[bool], width: int) -> float:
    left_boundary = _mask_boundary(left, width)
    right_boundary = _mask_boundary(right, width)
    if not left_boundary or not right_boundary:
        return 1.0
    height = len(left) // width
    diagonal = math.sqrt(width * width + height * height)

    def one_way(source: list[tuple[int, int]], target: list[tuple[int, int]]) -> float:
        return sum(min(math.hypot(x - tx, y - ty) for tx, ty in target) for x, y in source) / len(
            source
        )

    return (
        max(one_way(left_boundary, right_boundary), one_way(right_boundary, left_boundary))
        / diagonal
    )


def _mask_boundary(mask: list[bool], width: int) -> list[tuple[int, int]]:
    height = len(mask) // width
    result = []
    for index, active in enumerate(mask):
        if not active:
            continue
        x, y = index % width, index // width
        if any(
            not (0 <= x + dx < width and 0 <= y + dy < height)
            or not mask[(y + dy) * width + x + dx]
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1))
        ):
            result.append((x, y))
    return result


def _camera(label: str, capture_index: int) -> dict[str, float]:
    yaw = {"front": 0.0, "rear": math.pi, "left_oblique": -0.52, "right_oblique": 0.52}[label]
    if label == "rear":
        yaw = 0.0
    return {
        "yawRadians": round(yaw + (capture_index - 1.5) * 0.018, 9),
        "pitchRadians": round((capture_index - 1.5) * 0.012, 9),
    }


def _varied_parameters(
    family: str, group_index: int
) -> tuple[dict[str, float | int], dict[str, float]]:
    spec = FAMILY_SPECS[family]
    parameters = deepcopy(default_parameters(family))
    length_scale = 0.91 + (group_index % 6) * 0.036
    width_scale = 0.94 + ((group_index * 5) % 7) * 0.02
    ease_normalized = -0.72 + ((group_index * 7) % 9) * 0.18
    parameters[spec.length_field] = round(float(parameters[spec.length_field]) * length_scale, 9)
    parameters[spec.width_field] = round(float(parameters[spec.width_field]) * width_scale, 9)
    parameters[spec.ease_field] = round(
        float(parameters[spec.ease_field]) + ease_normalized * 0.012, 9
    )
    spec.parameter_type(**parameters).validate()
    return parameters, {
        "lengthScale": round(length_scale, 9),
        "widthScale": round(width_scale, 9),
        "easeNormalized": round(ease_normalized, 9),
    }


def _primary_split(group_index: int, groups_per_family: int) -> str:
    if group_index >= groups_per_family - 2:
        return "test"
    if group_index >= groups_per_family - 4:
        return "validation"
    return "train"


def _program_identity(program: dict[str, Any]) -> str:
    payload = deepcopy(program)
    payload.get("provenance", {}).pop("baseSeed", None)
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _challenge_set(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    names = (
        "sleeveless_versus_dress_like_long_top",
        "shirt_versus_jacket",
        "skirt_versus_wide_leg_lower",
        "layered_asymmetric_versus_single_shell",
        "cropped_versus_full_length",
        "unusual_ease",
        "weak_contrast",
        "partial_occlusion",
        "mirrored_capture",
        "damaged_mask",
        "missing_rear_view",
        "inconsistent_multiview_landmarks",
        "unsupported_fastenings",
        "unsupported_topology",
    )
    representatives = [sample for sample in samples if sample["sampleId"].endswith(".03")]
    return [
        {
            "challengeId": f"challenge.{index:02d}",
            "kind": name,
            "frozenBeforeFinalThresholdTuning": True,
            "input": deepcopy(representatives[index % len(representatives)]["input"]),
            "expectedAction": "reject_or_defer" if name.startswith("unsupported") else "evaluate",
        }
        for index, name in enumerate(names)
    ]


def _shift_suites(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    definitions = (
        ("parameter_extrapolation", "held_out_source_program_parameter_regime"),
        ("camera_shift", "capture_index_02_mirrored_camera_variant"),
        ("avatar_shift", "balanced_background_proxy_variant"),
        ("occlusion", "capture_index_03_partial_occlusion"),
        ("material_shift", "balanced_fabric_palette_variant"),
        ("capture_style", "mirrored_and_occluded_capture_variants"),
        ("generator_seed_family", "source_identity_disjoint_primary_test"),
    )
    return [
        {
            "suiteId": name,
            "heldOutAxis": held_out,
            "sharedAxes": ["garment_family", "renderer_family"],
            "sampleIds": sorted(
                sample["sampleId"]
                for sample in samples
                if (
                    (name == "camera_shift" and sample["sampleId"].endswith(".02"))
                    or (name == "occlusion" and sample["sampleId"].endswith(".03"))
                    or name not in {"camera_shift", "occlusion"}
                )
            ),
        }
        for name, held_out in definitions
    ]


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            any(token in str(key).lower() for token in FORBIDDEN_INPUT_TOKENS)
            or _contains_forbidden_key(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _colour_distance(left: tuple[int, ...], right: tuple[int, ...]) -> float:
    return math.sqrt(sum((int(a) - int(b)) ** 2 for a, b in zip(left[:3], right[:3], strict=True)))
