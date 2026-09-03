from __future__ import annotations

import hashlib
import random
import zipfile
from collections.abc import Mapping, Sequence
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from closy_forge.disjoint_benchmark_v1.compiler import compile_structural_candidate
from closy_forge.disjoint_benchmark_v1.protocol import (
    FIXED_PARAMETERS,
    OBSERVABLE_PARAMETERS,
    PARAMETER_RANGES,
)
from closy_forge.garments.tshirt.parameters import TShirtParameters
from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes

from .observation import apply_crop_and_padding, extract_observation

CORPUS_VERSION = "closy.d0_v4.public_synthetic_tshirt_corpus.v5"
GENERATOR_VERSION = "closy.d0_v4.dual_renderer.compiler_admitted_observable_capture.v5"
CORPUS_ROOT = Path("fixtures/d0_v4_engineering_corpus_v5")
MANIFEST_PATH = CORPUS_ROOT / "manifest.json"
ARCHIVE_PATH = CORPUS_ROOT / "captures.zip"
PUBLIC_TEST_MANIFEST_PATH = CORPUS_ROOT / "public_test.manifest.json"
PUBLIC_TEST_ARCHIVE_PATH = CORPUS_ROOT / "public_test.captures.zip"
PARTITION_COUNTS = {"train": 512, "validation": 128, "public_test": 128}
DEVELOPMENT_PARTITION_COUNTS = {"train": 512, "validation": 128}
PUBLIC_TEST_PARTITION_COUNTS = {"public_test": 128}
PARTITION_SEEDS = {
    "train": "closy-d0-v4-public-development-train-observable-v5-2026-04",
    "validation": "closy-d0-v4-public-development-validation-observable-v5-2026-04",
    "public_test": "closy-d0-v4-untouched-public-test-observable-v5-2026-04",
}
RENDERER_FAMILIES = ("polygon_scanline_v1", "supersampled_antialias_v1")
BASE_COLOURS = (
    (36, 79, 137),
    (164, 55, 71),
    (43, 119, 88),
    (206, 139, 46),
    (101, 76, 139),
    (56, 122, 138),
)
BACKGROUNDS = (
    (236, 234, 228),
    (217, 229, 235),
    (239, 222, 215),
    (222, 235, 218),
    (226, 219, 238),
    (238, 232, 207),
)
LOGO_SHAPES = ("none", "circle", "diamond", "bar")


class PublicTestAccessDenied(ValueError):
    """Raised when development code attempts to read public-test targets."""


def generate_corpus(
    root: Path,
) -> tuple[dict[str, Any], bytes, dict[str, Any], bytes]:
    records: list[dict[str, Any]] = []
    members: dict[str, bytes] = {}
    for partition, count in PARTITION_COUNTS.items():
        records.extend(_generate_partition(partition, count, members))
    prior = _prior_inventory(root)
    separation = _separation_report(records, prior)
    if separation["status"] != "pass":
        raise ValueError("d0_v4_corpus_separation_failed:" + canonical_dumps(separation))
    development_records = [record for record in records if record["partition"] != "public_test"]
    public_records = [record for record in records if record["partition"] == "public_test"]
    development_archive = _zip_members(
        {name: payload for name, payload in members.items() if not name.startswith("public_test/")}
    )
    public_archive = _zip_members(
        {name: payload for name, payload in members.items() if name.startswith("public_test/")}
    )
    development_manifest = _build_manifest(
        development_records,
        partition_counts=DEVELOPMENT_PARTITION_COUNTS,
        archive=development_archive,
        inventory_scope="public_development_train_validation",
        separation=separation,
    )
    public_manifest = _build_manifest(
        public_records,
        partition_counts=PUBLIC_TEST_PARTITION_COUNTS,
        archive=public_archive,
        inventory_scope="guarded_one_shot_public_test",
        separation=separation,
    )
    return development_manifest, development_archive, public_manifest, public_archive


def _build_manifest(
    records: Sequence[Mapping[str, Any]],
    *,
    partition_counts: Mapping[str, int],
    archive: bytes,
    inventory_scope: str,
    separation: Mapping[str, Any],
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "corpusVersion": CORPUS_VERSION,
        "generatorVersion": GENERATOR_VERSION,
        "inventoryScope": inventory_scope,
        "license": "CC0-1.0 project-authored procedural fixtures",
        "qualificationEligible": False,
        "partitionCounts": dict(partition_counts),
        "allPartitionCounts": dict(PARTITION_COUNTS),
        "partitionSeeds": {
            role: sha256_bytes(PARTITION_SEEDS[role].encode("utf-8")) for role in partition_counts
        },
        "rendererFamilies": list(RENDERER_FAMILIES),
        "officialFormat": {
            "width": 128,
            "height": 160,
            "format": "PNG RGBA8 fully opaque",
            "croppedVariantsMayChangeDimensions": True,
        },
        "observableParameters": list(OBSERVABLE_PARAMETERS),
        "variationAxes": [
            "all_observable_parameters",
            "camera",
            "crop",
            "scale",
            "translation",
            "lighting_and_colour",
            "logo",
            "occlusion",
            "missing_rear",
        ],
        "records": [dict(record) for record in records],
        "separation": dict(separation),
        "lostOpaqueV2Relation": "unverified",
        "archiveSha256": sha256_bytes(archive),
        "manifestDigest": "",
    }
    manifest["manifestDigest"] = _digest(manifest, "manifestDigest")
    return manifest


def load_manifest(root: Path) -> dict[str, Any]:
    value = read_json(root / MANIFEST_PATH)
    if not isinstance(value, dict):
        raise ValueError("d0_v4_corpus_manifest_mapping_required")
    issues = validate_manifest(
        value,
        expected_counts=DEVELOPMENT_PARTITION_COUNTS,
        archive_path=root / ARCHIVE_PATH,
    )
    if issues:
        raise ValueError("d0_v4_corpus_manifest_invalid:" + ";".join(issues))
    return value


def validate_manifest(
    manifest: Mapping[str, Any],
    *,
    expected_counts: Mapping[str, int] = DEVELOPMENT_PARTITION_COUNTS,
    archive_path: Path | None = None,
) -> list[str]:
    issues: list[str] = []
    records = _records(manifest.get("records"))
    if manifest.get("corpusVersion") != CORPUS_VERSION:
        issues.append("corpus_version_invalid")
    observed_counts = {
        role: sum(record.get("partition") == role for record in records) for role in expected_counts
    }
    if observed_counts != dict(expected_counts) or manifest.get("partitionCounts") != dict(
        expected_counts
    ):
        issues.append("partition_counts_invalid")
    for field in (
        "identityHash",
        "parameterHash",
        "sourceHash",
        "generatorSeedHash",
        "frontRasterSha256",
    ):
        values = [str(record.get(field, "")) for record in records]
        if len(values) != len(set(values)) or any(len(value) != 64 for value in values):
            issues.append(f"record_{field}_not_unique")
    near = [str(record.get("nearDuplicateHash", "")) for record in records]
    if len(near) != len(set(near)):
        issues.append("near_duplicate_collision")
    if _mapping(manifest.get("separation")).get("status") != "pass":
        issues.append("separation_not_passed")
    if manifest.get("manifestDigest") != _digest(manifest, "manifestDigest"):
        issues.append("manifest_digest_invalid")
    if archive_path is not None:
        if not archive_path.is_file():
            issues.append("capture_archive_missing")
        elif sha256_bytes(archive_path.read_bytes()) != manifest.get("archiveSha256"):
            issues.append("capture_archive_digest_invalid")
    return sorted(set(issues))


def load_partition(
    root: Path,
    partition: str,
    *,
    allow_public_test: bool = False,
) -> list[dict[str, Any]]:
    if partition == "public_test" and not allow_public_test:
        raise PublicTestAccessDenied("public_test_requires_one_shot_evaluator")
    if partition not in PARTITION_COUNTS:
        raise ValueError("d0_v4_partition_unknown")
    if partition == "public_test":
        manifest_value = read_json(root / PUBLIC_TEST_MANIFEST_PATH)
        if not isinstance(manifest_value, dict):
            raise ValueError("d0_v4_public_test_manifest_mapping_required")
        issues = validate_manifest(
            manifest_value,
            expected_counts=PUBLIC_TEST_PARTITION_COUNTS,
            archive_path=root / PUBLIC_TEST_ARCHIVE_PATH,
        )
        if issues:
            raise ValueError("d0_v4_public_test_manifest_invalid:" + ";".join(issues))
        manifest = manifest_value
        archive_path = root / PUBLIC_TEST_ARCHIVE_PATH
    else:
        manifest = load_manifest(root)
        archive_path = root / ARCHIVE_PATH
    selected = [
        dict(record)
        for record in _records(manifest["records"])
        if record.get("partition") == partition
    ]
    with zipfile.ZipFile(archive_path, "r") as archive:
        for record in selected:
            front = archive.read(str(record["frontMember"]))
            rear_member = record.get("rearMember")
            rear = archive.read(str(rear_member)) if rear_member else None
            if sha256_bytes(front) != record["frontRasterSha256"]:
                raise ValueError("d0_v4_front_raster_digest_invalid")
            if rear is not None and sha256_bytes(rear) != record["rearRasterSha256"]:
                raise ValueError("d0_v4_rear_raster_digest_invalid")
            record["frontPng"] = front
            record["rearPng"] = rear
    return selected


def observation_for_record(record: Mapping[str, Any]) -> dict[str, Any]:
    front = record.get("frontPng")
    rear = record.get("rearPng")
    if not isinstance(front, bytes) or (rear is not None and not isinstance(rear, bytes)):
        raise ValueError("d0_v4_record_capture_bytes_missing")
    capture = _mapping(record.get("capture"))
    return extract_observation(
        front,
        rear,
        metadata={
            "front": {
                "camera": _mapping(capture.get("frontCamera")),
                "observationToOriginalTransform": capture.get("frontTransform"),
            },
            "rear": {
                "camera": _mapping(capture.get("rearCamera")),
                "observationToOriginalTransform": capture.get("rearTransform"),
            },
        },
    )


def _generate_partition(
    partition: str,
    count: int,
    members: dict[str, bytes],
) -> list[dict[str, Any]]:
    rng = random.Random(PARTITION_SEEDS[partition])
    maximum_attempts = count * 20
    permutations = _latin_hypercube_permutations(maximum_attempts, len(OBSERVABLE_PARAMETERS), rng)
    records: list[dict[str, Any]] = []
    attempt = 0
    while len(records) < count and attempt < maximum_attempts:
        ordinal = len(records)
        identity_seed = hashlib.sha256(
            f"{PARTITION_SEEDS[partition]}:{attempt}".encode()
        ).hexdigest()
        local = random.Random(identity_seed)
        parameters = {
            name: round(
                low
                + (high - low)
                * ((permutations[index][attempt] + local.random()) / maximum_attempts),
                9,
            )
            for index, (name, (low, high)) in enumerate(PARAMETER_RANGES.items())
        }
        parameters.update(FIXED_PARAMETERS)
        parameters["target_panel_edge_length"] = 0.075
        TShirtParameters(**parameters).validate()
        try:
            compile_structural_candidate(parameters)
        except ValueError:
            attempt += 1
            continue
        family = RENDERER_FAMILIES[ordinal % len(RENDERER_FAMILIES)]
        background = BACKGROUNDS[local.randrange(len(BACKGROUNDS))]
        garment = BASE_COLOURS[local.randrange(len(BASE_COLOURS))]
        logo_shape = LOGO_SHAPES[ordinal % len(LOGO_SHAPES)]
        variation = {
            "scale": round(local.uniform(0.97, 1.03), 6),
            "translation": [local.randint(-2, 2), local.randint(-2, 2)],
            "lighting": round(local.uniform(0.92, 1.08), 6),
            "cropFraction": 0.04 if ordinal % 13 == 5 else 0.0,
            "paddingFraction": 0.025 if ordinal % 17 == 7 else 0.0,
            "occlusionFraction": 0.035 if ordinal % 11 == 3 else 0.0,
            "rearMissing": ordinal % 10 == 9,
        }
        appearance = {
            "baseColorSrgb": list(garment),
            "logoShape": logo_shape,
            "logoColorSrgb": [238, 231, 214],
            "logoCenterNormalized": [
                round(local.uniform(0.42, 0.58), 6),
                round(local.uniform(0.38, 0.60), 6),
            ],
            "logoScaleNormalized": round(local.uniform(0.07, 0.13), 6),
        }
        front = render_tshirt_capture(
            parameters,
            appearance,
            background=background,
            variation=variation,
            role="front",
            renderer_family=family,
        )
        rear = render_tshirt_capture(
            parameters,
            appearance,
            background=background,
            variation=variation,
            role="rear",
            renderer_family=family,
        )
        front, front_transform = _physical_transform(front, variation, background)
        rear, rear_transform = _physical_transform(rear, variation, background)
        rear_bytes = None if variation["rearMissing"] else rear
        identity_hash = sha256_bytes(f"d0v4:{partition}:{identity_seed}".encode())
        member_base = f"{partition}/{ordinal:04d}-{identity_hash[:12]}"
        front_member = member_base + ".front.png"
        members[front_member] = front
        rear_member = None
        if rear_bytes is not None:
            rear_member = member_base + ".rear.png"
            members[rear_member] = rear_bytes
        parameter_hash = _hash_mapping(parameters)
        source_hash = sha256_bytes(front + (rear_bytes or b"missing_rear"))
        record: dict[str, Any] = {
            "partition": partition,
            "ordinal": ordinal,
            "generatorAttempt": attempt,
            "identityHash": identity_hash,
            "parameterHash": parameter_hash,
            "sourceHash": source_hash,
            "generatorSeedHash": sha256_bytes(identity_seed.encode("ascii")),
            "generatorVersion": GENERATOR_VERSION,
            "rendererFamily": family,
            "parameters": parameters,
            "appearance": appearance,
            "capture": {
                **variation,
                "backgroundSrgb": list(background),
                "frontCamera": _camera("front", variation),
                "rearCamera": _camera("rear", variation),
                "frontTransform": front_transform,
                "rearTransform": rear_transform,
            },
            "frontMember": front_member,
            "rearMember": rear_member,
            "frontRasterSha256": sha256_bytes(front),
            "rearRasterSha256": sha256_bytes(rear_bytes) if rear_bytes else None,
            "nearDuplicateHash": sha256_bytes(
                f"{family}:{ordinal}:{parameter_hash[:24]}:{source_hash[:24]}".encode("ascii")
            ),
        }
        records.append(record)
        attempt += 1
    if len(records) != count:
        raise ValueError(
            f"d0_v4_compiler_admitted_partition_incomplete:{partition}:{len(records)}:{count}"
        )
    return records


def render_tshirt_capture(
    parameters: Mapping[str, Any],
    appearance: Mapping[str, Any],
    *,
    background: tuple[int, int, int],
    variation: Mapping[str, Any],
    role: str,
    renderer_family: str,
) -> bytes:
    multiplier = 2 if renderer_family == "supersampled_antialias_v1" else 1
    image = Image.new("RGBA", (128 * multiplier, 160 * multiplier), (*background, 255))
    draw = ImageDraw.Draw(image)
    normalized = {
        name: (float(parameters[name]) - low) / (high - low)
        for name, (low, high) in PARAMETER_RANGES.items()
    }
    scale = float(variation["scale"])
    tx, ty = (int(value) for value in variation["translation"])
    center = 64.0 + tx
    top = 24.0 + ty
    body_height = (72.0 + 30.0 * normalized["garment_body_length"]) * scale
    shoulder = (22.0 + 7.0 * normalized["shoulder_width"]) * scale
    chest = (18.0 + 8.0 * normalized["half_chest_width"]) * scale
    ease = (1.0 + 7.0 * normalized["body_ease"]) * scale
    slope = (1.5 + 7.0 * normalized["shoulder_slope"]) * scale
    armhole = (15.0 + 15.0 * normalized["armhole_depth"]) * scale
    sleeve = (10.0 + 18.0 * normalized["sleeve_length"]) * scale
    cuff = (5.0 + 9.0 * normalized["sleeve_opening_width"]) * scale
    hem_half = chest + ease
    shoulder_line = top + slope
    sleeve_inner_y = shoulder_line + cuff + (armhole - cuff) * 0.55
    armhole_y = shoulder_line + armhole
    left = [
        (center - shoulder, shoulder_line),
        (center - shoulder - sleeve, shoulder_line + cuff),
        (center - shoulder - sleeve + 2.0, sleeve_inner_y),
        (center - chest, armhole_y),
        (center - hem_half, top + body_height),
    ]
    right = [(2 * center - x, y) for x, y in reversed(left)]
    points = left + right
    colour = _lit_colour(appearance["baseColorSrgb"], float(variation["lighting"]))
    _polygon(draw, points, fill=_rgba(colour), multiplier=multiplier)
    neck_width = (7.0 + 9.0 * normalized["neckline_width"]) * scale
    depth_name = "front_neckline_depth" if role == "front" else "back_neckline_depth"
    neck_depth = (4.0 + 11.0 * normalized[depth_name]) * scale
    _ellipse(
        draw,
        (
            center - neck_width,
            shoulder_line - neck_depth * 0.55,
            center + neck_width,
            shoulder_line + neck_depth,
        ),
        fill=_rgba(background),
        multiplier=multiplier,
    )
    if role == "front" and appearance["logoShape"] != "none":
        _draw_logo(draw, appearance, center, top, body_height, multiplier)
    if float(variation["occlusionFraction"]) > 0.0:
        occluder = (
            min(255, background[0] + 12),
            min(255, background[1] + 12),
            min(255, background[2] + 12),
        )
        _polygon(
            draw,
            [
                (center + chest * 0.45, top + armhole * 0.7),
                (center + chest * 1.3, top + armhole * 0.8),
                (center + chest * 1.1, top + armhole * 1.45),
                (center + chest * 0.35, top + armhole * 1.35),
            ],
            fill=_rgba(occluder),
            multiplier=multiplier,
        )
    if multiplier > 1:
        image = image.resize((128, 160), Image.Resampling.LANCZOS)
        opaque = Image.new("RGBA", image.size, (*background, 255))
        opaque.alpha_composite(image)
        image = opaque
    return _encode_png(image)


def _draw_logo(
    draw: ImageDraw.ImageDraw,
    appearance: Mapping[str, Any],
    center: float,
    top: float,
    body_height: float,
    multiplier: int,
) -> None:
    cx = center + (float(appearance["logoCenterNormalized"][0]) - 0.5) * 38.0
    cy = top + float(appearance["logoCenterNormalized"][1]) * body_height
    radius = 128.0 * float(appearance["logoScaleNormalized"]) * 0.55
    logo = appearance["logoColorSrgb"]
    colour = (int(logo[0]), int(logo[1]), int(logo[2]), 255)
    shape = appearance["logoShape"]
    if shape == "circle":
        _ellipse(draw, (cx - radius, cy - radius, cx + radius, cy + radius), colour, multiplier)
    elif shape == "diamond":
        _polygon(
            draw,
            [(cx, cy - radius), (cx + radius, cy), (cx, cy + radius), (cx - radius, cy)],
            fill=colour,
            multiplier=multiplier,
        )
    else:
        _polygon(
            draw,
            [
                (cx - radius * 1.4, cy - radius * 0.45),
                (cx + radius * 1.4, cy - radius * 0.45),
                (cx + radius * 1.4, cy + radius * 0.45),
                (cx - radius * 1.4, cy + radius * 0.45),
            ],
            fill=colour,
            multiplier=multiplier,
        )


def _physical_transform(
    png: bytes,
    variation: Mapping[str, Any],
    background: tuple[int, int, int],
) -> tuple[bytes, dict[str, Any]]:
    return apply_crop_and_padding(
        png,
        crop_fraction=float(variation["cropFraction"]),
        padding_fraction=float(variation["paddingFraction"]),
        background_rgb=background,
    )


def _camera(role: str, variation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "projection": "orthographic",
        "azimuthDegrees": 0.0 if role == "front" else 180.0,
        "elevationDegrees": 4.0,
        "orthographicScale": round(1.12 / float(variation["scale"]), 9),
        "principalPointNormalized": [
            round(0.5 + int(variation["translation"][0]) / 128.0, 9),
            round(0.5 + int(variation["translation"][1]) / 160.0, 9),
        ],
        "imageSize": [128, 160],
    }


def _prior_inventory(root: Path) -> dict[str, set[str]]:
    hashes: dict[str, set[str]] = {"identity": set(), "parameter": set(), "raster": set()}
    old_training = _mapping(
        read_json(
            root / "fixtures/evidence_authority_recovery_v2/public_pixel_training_inventory.json"
        )
    )
    for record in _records(old_training.get("records")):
        hashes["raster"].update(
            str(record.get(field, "")) for field in ("frontPngSha256", "rearPngSha256")
        )
        parameters = _mapping(record.get("parameters"))
        if parameters:
            hashes["parameter"].add(_hash_mapping(parameters))
    prior_path = root / "fixtures/d0_disjoint_tshirt_confirmation_v2/prior_inventory.json"
    prior = _mapping(read_json(prior_path))
    hashes["identity"].update(str(value) for value in prior.get("identityValues", []))
    hashes["parameter"].update(str(value) for value in prior.get("parameterHashes", []))
    hashes["raster"].update(str(value) for value in prior.get("sourceRasterHashes", []))
    for group in hashes.values():
        group.discard("")
    return hashes


def _separation_report(
    records: Sequence[Mapping[str, Any]], prior: Mapping[str, set[str]]
) -> dict[str, Any]:
    identities = [str(record["identityHash"]) for record in records]
    parameters = [str(record["parameterHash"]) for record in records]
    rasters = [str(record["frontRasterSha256"]) for record in records]
    rasters.extend(
        str(record["rearRasterSha256"])
        for record in records
        if record.get("rearRasterSha256") is not None
    )
    sources = [str(record["sourceHash"]) for record in records]
    seeds = [str(record["generatorSeedHash"]) for record in records]
    near = [str(record["nearDuplicateHash"]) for record in records]
    collisions = {
        "priorIdentity": sorted(set(identities) & prior["identity"]),
        "priorParameter": sorted(set(parameters) & prior["parameter"]),
        "priorRaster": sorted(set(rasters) & prior["raster"]),
    }
    unique = {
        "identity": len(set(identities)),
        "parameter": len(set(parameters)),
        "raster": len(set(rasters)),
        "source": len(set(sources)),
        "generatorSeed": len(set(seeds)),
        "nearDuplicate": len(set(near)),
    }
    expected = len(records)
    passed = (
        all(not values for values in collisions.values())
        and all(
            unique[name] == expected
            for name in ("identity", "parameter", "source", "generatorSeed", "nearDuplicate")
        )
        and unique["raster"] >= expected
    )
    return {
        "status": "pass" if passed else "fail",
        "nominalRecordCount": expected,
        "uniqueCounts": unique,
        "priorInventoryCounts": {name: len(values) for name, values in prior.items()},
        "collisions": collisions,
        "lostOpaqueV2Relation": "unverified",
    }


def _latin_hypercube_permutations(
    count: int, axis_count: int, rng: random.Random
) -> list[list[int]]:
    result: list[list[int]] = []
    for _ in range(axis_count):
        values = list(range(count))
        rng.shuffle(values)
        result.append(values)
    return result


def _zip_members(members: Mapping[str, bytes]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, members[name])
    return output.getvalue()


def _polygon(
    draw: ImageDraw.ImageDraw,
    points: Sequence[tuple[float, float]],
    fill: tuple[int, int, int, int],
    multiplier: int,
) -> None:
    draw.polygon([(round(x * multiplier), round(y * multiplier)) for x, y in points], fill=fill)


def _ellipse(
    draw: ImageDraw.ImageDraw,
    bounds: tuple[float, float, float, float],
    fill: tuple[int, int, int, int],
    multiplier: int,
) -> None:
    draw.ellipse(tuple(round(value * multiplier) for value in bounds), fill=fill)


def _lit_colour(colour: Sequence[Any], lighting: float) -> tuple[int, int, int]:
    return tuple(min(255, max(0, round(int(value) * lighting))) for value in colour)  # type: ignore[return-value]


def _rgba(colour: tuple[int, int, int]) -> tuple[int, int, int, int]:
    return (colour[0], colour[1], colour[2], 255)


def _encode_png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", optimize=False, compress_level=9)
    return output.getvalue()


def _hash_mapping(value: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_dumps(dict(value)).encode("utf-8"))


def _digest(value: Mapping[str, Any], field: str) -> str:
    payload = dict(value)
    payload[field] = ""
    return _hash_mapping(payload)


def _records(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
