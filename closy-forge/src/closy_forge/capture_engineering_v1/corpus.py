from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from closy_forge.garments.simple_skirt.parameters import SimpleSkirtParameters
from closy_forge.garments.sleeveless_top.parameters import SleevelessTopParameters
from closy_forge.garments.tshirt.assembly import build_simulation_mesh as build_tshirt_mesh
from closy_forge.garments.tshirt.parameters import TShirtParameters
from closy_forge.garments.tshirt.pattern_generator import build_tshirt_pattern
from closy_forge.geometry.mesh_model import MeshSet
from closy_forge.inspection.cpu_raster import rasterize_settled_garment
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.pattern_inference.grammar_v2 import compile_program, program_from_parameters
from closy_forge.pattern_inference.reference_3d_v1 import build_reference_assembly
from closy_forge.raster.png_codec import encode_png_rgba

from .alternate_renderer import render_ray_triangles
from .common import canonical_digest, sha256_bytes, write_json
from .ontology import AcquisitionPattern, PrimaryMode, SceneCondition, build_session
from .protocol import load_frozen_protocol
from .video_avi import encode_uncompressed_avi

CORPUS_VERSION = "closy.capture_engineering.public_fixture_corpus.v1"
WIDTH = 32
HEIGHT = 44


@dataclass(frozen=True)
class SessionSpec:
    index: int
    opaque_session_id: str
    identity_group_id: str
    primary_mode: PrimaryMode
    scene_condition: SceneCondition
    acquisition_pattern: AcquisitionPattern
    subject_condition: str
    family: str
    split: str
    renderer: str
    avatar: str
    pose: str
    appearance: str
    renderer_camera_family: str
    avatar_shape_family: str
    pose_family: str
    appearance_family: str
    view_roles: tuple[str, ...]


@dataclass(frozen=True)
class CorpusBuild:
    manifest: dict[str, Any]
    evaluator_targets: dict[str, dict[str, float]]


def session_specs() -> list[SessionSpec]:
    development_families = ["tshirt"] * 28 + ["sleeveless_top"] * 16 + ["simple_skirt"] * 16
    validation_families = ["sleeveless_top"] * 8 + ["simple_skirt"] * 8 + ["tshirt"] * 4
    families = development_families + validation_families
    specs: list[SessionSpec] = []
    for index in range(80):
        mode, scene, acquisition, subject = _mode_facets(index)
        specs.append(
            SessionSpec(
                index=index,
                opaque_session_id=f"capture-v1-{index:03d}",
                identity_group_id=f"capture-group-v1-{index:03d}",
                primary_mode=mode,
                scene_condition=scene,
                acquisition_pattern=acquisition,
                subject_condition=subject,
                family=families[index],
                split="development" if index < 60 else "validation",
                renderer="cpu_triangle_zbuffer" if index < 40 else "independent_ray_triangle",
                avatar="fixed_avatar_alpha" if index < 40 else "fixed_avatar_beta",
                pose="neutral" if index < 40 else "varied",
                appearance="plain" if index < 40 else "print_family_beta",
                renderer_camera_family=(
                    "cpu_zbuffer_development"
                    if index < 40
                    else "ray_triangle_development"
                    if index < 60
                    else "ray_triangle_holdout"
                ),
                avatar_shape_family=(
                    "fixed_alpha_development"
                    if index < 40
                    else "fixed_beta_development"
                    if index < 60
                    else "fixed_beta_holdout"
                ),
                pose_family=(
                    "neutral_development"
                    if index < 40
                    else "varied_development"
                    if index < 60
                    else "varied_holdout"
                ),
                appearance_family=(
                    "plain_development"
                    if index < 40
                    else "print_beta_development"
                    if index < 60
                    else "print_beta_holdout"
                ),
                view_roles=_roles(acquisition),
            )
        )
    issues = validate_specs(specs, load_frozen_protocol())
    if issues:
        raise ValueError("invalid_capture_spec_inventory:" + ";".join(issues))
    return specs


def validate_specs(specs: list[SessionSpec], protocol: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    raw_counts = protocol["counts"]
    if not isinstance(raw_counts, Mapping):
        return ["protocol_counts_invalid"]
    counts = raw_counts
    facets: dict[str, Counter[str]] = {
        "primaryMode": Counter(spec.primary_mode for spec in specs),
        "sceneCondition": Counter(spec.scene_condition for spec in specs),
        "acquisitionPattern": Counter(spec.acquisition_pattern for spec in specs),
        "family": Counter(spec.family for spec in specs),
        "split": Counter(spec.split for spec in specs),
        "renderer": Counter(spec.renderer for spec in specs),
        "avatar": Counter(spec.avatar for spec in specs),
        "rendererCameraFamily": Counter(spec.renderer_camera_family for spec in specs),
        "avatarShapeFamily": Counter(spec.avatar_shape_family for spec in specs),
        "poseFamily": Counter(spec.pose_family for spec in specs),
        "appearanceFamily": Counter(spec.appearance_family for spec in specs),
    }
    if len(specs) != counts["uniqueCaptureSessions"]:
        issues.append("unique_session_count_invalid")
    for key, actual in facets.items():
        expected = counts.get(key)
        if not isinstance(expected, dict) or dict(sorted(actual.items())) != expected:
            issues.append(f"{key}_count_invalid")
    if len({spec.identity_group_id for spec in specs}) != len(specs):
        issues.append("identity_group_duplicate")
    development = {spec.identity_group_id for spec in specs if spec.split == "development"}
    validation = {spec.identity_group_id for spec in specs if spec.split == "validation"}
    if development & validation or len(validation) < 20:
        issues.append("identity_split_overlap_or_shortfall")
    view_counts: Counter[str] = Counter()
    for spec in specs:
        view_counts.update(spec.view_roles)
    expected_views = counts["viewRoleSourceFrames"]
    if (
        not isinstance(expected_views, Mapping)
        or {role: view_counts[role] for role in sorted(map(str, expected_views))} != expected_views
    ):
        issues.append("view_role_source_frame_count_invalid")
    for family in ("sleeveless_top", "simple_skirt"):
        if sum(spec.family == family and spec.split == "validation" for spec in specs) < 8:
            issues.append(f"{family}_heldout_shortfall")
    return sorted(set(issues))


def build_public_fixture_corpus(output_root: Path) -> CorpusBuild:
    protocol = load_frozen_protocol()
    output_root.mkdir(parents=True, exist_ok=True)
    source_root = output_root / "public_sources"
    source_root.mkdir(parents=True, exist_ok=True)
    sessions: list[dict[str, Any]] = []
    evaluator_targets: dict[str, dict[str, float]] = {}
    source_bytes: list[str] = []
    source_count = 0
    decoded_frame_count = 0
    for spec in session_specs():
        parameters, meshset = _mesh_for_spec(spec)
        evaluator_targets[spec.identity_group_id] = parameters
        source_ids: list[str] = []
        if spec.acquisition_pattern == "guided_video":
            source_id = f"source-{spec.index:03d}-video"
            source_path = source_root / f"{source_id}.avi"
            frames = _video_frames(meshset, spec)
            encoded = encode_uncompressed_avi(WIDTH, HEIGHT, frames, frames_per_second=12)
            source_path.write_bytes(encoded)
            source_ids.extend(f"{source_id}#frame-{index:02d}" for index in range(len(frames)))
            source_bytes.append(sha256_bytes(encoded))
            source_count += 1
            decoded_frame_count += len(frames)
        else:
            for role_index, role in enumerate(spec.view_roles):
                source_id = f"source-{spec.index:03d}-{role_index:02d}"
                rgba = _render(meshset, spec, role)
                if (spec.index + role_index) % 3 == 0:
                    source_path = source_root / f"{source_id}.jpg"
                    encoded = _jpeg_bytes(rgba, WIDTH, HEIGHT)
                    mime = "image/jpeg"
                else:
                    source_path = source_root / f"{source_id}.png"
                    encoded = encode_png_rgba(WIDTH, HEIGHT, rgba)
                    mime = "image/png"
                source_path.write_bytes(encoded)
                source_ids.append(source_id)
                source_bytes.append(sha256_bytes(encoded))
                source_count += 1
                _ = mime
        session = build_session(
            opaque_session_id=spec.opaque_session_id,
            identity_group_id=spec.identity_group_id,
            primary_mode=spec.primary_mode,
            scene_condition=spec.scene_condition,
            acquisition_pattern=spec.acquisition_pattern,
            subject_condition=spec.subject_condition,  # type: ignore[arg-type]
            evidence_tier="public_project_fixture",
            view_roles=spec.view_roles,  # type: ignore[arg-type]
            source_ids=source_ids,
            corrections=[],
        )
        sessions.append(
            {
                **session,
                "family": spec.family,
                "split": spec.split,
                "renderer": spec.renderer,
                "avatar": spec.avatar,
                "pose": spec.pose,
                "appearance": spec.appearance,
                "rendererCameraFamily": spec.renderer_camera_family,
                "avatarShapeFamily": spec.avatar_shape_family,
                "poseFamily": spec.pose_family,
                "appearanceFamily": spec.appearance_family,
                "knownScaleMarkerMeters": 0.5 if spec.primary_mode == "A" else None,
                "evaluatorFieldsPresent": False,
            }
        )
    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "corpusVersion": CORPUS_VERSION,
        "protocolDigest": protocol["protocolDigest"],
        "sessions": sessions,
        "counts": {
            "captureSessions": len(sessions),
            "encodedSources": source_count,
            "decodedVideoSourceFrames": decoded_frame_count,
            "publicPngOrJpegSources": source_count - 12,
        },
        "sourceInventoryDigest": sha256_bytes("|".join(sorted(source_bytes)).encode("ascii")),
        "privacy": {
            "projectAuthoredOnly": True,
            "privateUserEvidence": False,
            "licensedPublicEvidence": False,
            "absolutePathsPersisted": False,
            "rawDigestsPublicOnly": True,
        },
        "targetIsolation": {
            "portableManifestContainsParameters": False,
            "portableManifestContainsGeneratorSeed": False,
            "portableManifestContainsExactCamera": False,
            "evaluatorTargetCount": len(evaluator_targets),
        },
        "manifestDigest": "",
    }
    manifest["manifestDigest"] = canonical_digest(manifest, "manifestDigest")
    write_json(output_root / "session_manifest.json", manifest)
    return CorpusBuild(manifest=manifest, evaluator_targets=evaluator_targets)


def _mode_facets(
    index: int,
) -> tuple[PrimaryMode, SceneCondition, AcquisitionPattern, str]:
    if index < 10:
        return ("A", "flat", "single_image", "no_body")
    if index < 20:
        return ("A", "hung", "guided_multi_image", "no_body")
    if index < 28:
        return ("B", "worn", "single_image", "fixed_synthetic_avatar")
    if index < 36:
        return ("B", "worn", "guided_multi_image", "fixed_synthetic_avatar")
    if index < 44:
        return ("C", "flat", "guided_multi_image", "no_body")
    if index < 52:
        return ("C", "hung", "guided_multi_image", "no_body")
    if index < 64:
        return ("D", "worn", "guided_video", "fixed_synthetic_avatar")
    return ("E", "unknown", "single_image", "no_body")


def _roles(acquisition: AcquisitionPattern) -> tuple[str, ...]:
    if acquisition == "single_image":
        return ("front",)
    if acquisition == "guided_multi_image":
        return ("front", "rear", "three-quarter")
    return tuple(["front"] * 6 + ["three-quarter"] * 6 + ["side"] * 6 + ["rear"] * 6)


def _mesh_for_spec(spec: SessionSpec) -> tuple[dict[str, float], MeshSet]:
    width_factor = 0.92 + (spec.index % 9) * 0.02
    length_factor = 0.91 + ((spec.index // 3) % 10) * 0.02
    if spec.family == "tshirt":
        params = TShirtParameters(
            garment_body_length=0.68 * length_factor,
            half_chest_width=0.285 * width_factor,
            body_ease=0.035 + (spec.index % 4) * 0.008,
            sleeve_length=0.22 + (spec.index % 5) * 0.018,
        )
        params.validate()
        mesh, _edges = build_tshirt_mesh(build_tshirt_pattern(params))
        return ({key: float(value) for key, value in params.to_json().items()}, mesh)
    if spec.family == "sleeveless_top":
        sleeveless_params = SleevelessTopParameters(
            body_length_meters=0.64 * length_factor,
            half_chest_width_meters=0.285 * width_factor,
            body_ease_meters=0.03 + (spec.index % 4) * 0.008,
            shoulder_width_meters=0.56 + (spec.index % 3) * 0.015,
        )
        values = {key: float(value) for key, value in sleeveless_params.to_json().items()}
    else:
        skirt_params = SimpleSkirtParameters(
            length_meters=0.56 * length_factor,
            half_waist_width_meters=0.205 * width_factor,
            half_hip_width_meters=0.255 * width_factor,
            waist_ease_meters=0.012 + (spec.index % 4) * 0.006,
            flare_meters=0.04 + (spec.index % 5) * 0.018,
        )
        values = {key: float(value) for key, value in skirt_params.to_json().items()}
    program = program_from_parameters(
        spec.family,
        values,
        program_id=f"program.{spec.opaque_session_id}",
        base_seed=10_000 + spec.index,
    )
    pattern = compile_program(program)
    return (values, build_reference_assembly(spec.family, pattern)["simulation"])


def mesh_for_spec(spec: SessionSpec) -> tuple[dict[str, float], MeshSet]:
    """Expose deterministic fixture geometry to the evaluator, never the contestant."""

    return _mesh_for_spec(spec)


def _render(meshset: MeshSet, spec: SessionSpec, role: str) -> bytes:
    principal = ((spec.index % 3 - 1) * 0.025, ((spec.index // 3) % 3 - 1) * 0.018)
    if spec.renderer == "independent_ray_triangle":
        rendered = render_ray_triangles(
            meshset,
            width=WIDTH,
            height=HEIGHT,
            view_role=role,
            principal_offset=principal,
        ).rgba
    else:
        label = {
            "front": "front",
            "rear": "back",
            "side": "left_three_quarter",
            "three-quarter": "right_three_quarter",
            "detail": "front",
        }[role]
        rendered = rasterize_settled_garment(
            meshset,
            label=label,
            width=WIDTH,
            height=HEIGHT,
            camera={"principalPointNormalized": [0.5 + principal[0], 0.5 + principal[1]]},
            background=(232, 229, 222, 255),
        ).rgba
    return _apply_capture_variation(rendered, spec)


def _video_frames(meshset: MeshSet, spec: SessionSpec) -> list[bytes]:
    frames: list[bytes] = []
    for index, role in enumerate(spec.view_roles):
        base = _render(meshset, spec, role)
        background = tuple(base[:4])
        shift = round(math_wave(index) * 2)
        frame = bytearray(background * (WIDTH * HEIGHT))
        for y in range(HEIGHT):
            for x in range(WIDTH):
                source_x = x - shift
                if not 0 <= source_x < WIDTH:
                    continue
                source = (y * WIDTH + source_x) * 4
                target = (y * WIDTH + x) * 4
                frame[target : target + 4] = base[source : source + 4]
        accent = index % 6
        for pixel in range(WIDTH * HEIGHT):
            offset = pixel * 4
            if tuple(frame[offset : offset + 4]) != background:
                frame[offset] = min(255, frame[offset] + accent)
        frames.append(bytes(frame))
    return frames


def _apply_capture_variation(rgba: bytes, spec: SessionSpec) -> bytes:
    pixels = bytearray(rgba)
    source_background = (232, 229, 222)
    background_delta = (spec.index % 5) - 2
    target_background = tuple(channel + background_delta * 2 for channel in source_background)
    light_factor = 0.90 + (spec.index % 7) * 0.03
    for index in range(WIDTH * HEIGHT):
        offset = index * 4
        color = tuple(pixels[offset : offset + 3])
        if color == source_background:
            pixels[offset : offset + 3] = bytes(target_background)
            continue
        for channel in range(3):
            pixels[offset + channel] = min(255, round(pixels[offset + channel] * light_factor))
        if spec.appearance_family.startswith("print_beta"):
            x, y = index % WIDTH, index // WIDTH
            if (x // 3 + y // 4) % 5 == 0:
                pixels[offset] = min(255, pixels[offset] + 28)
                pixels[offset + 2] = max(0, pixels[offset + 2] - 14)
    if spec.index % 7 == 0:
        for y in range(HEIGHT // 3, HEIGHT // 2):
            for x in range(WIDTH // 5, WIDTH // 3):
                offset = (y * WIDTH + x) * 4
                pixels[offset : offset + 4] = bytes((*target_background, 255))
    return bytes(pixels)


def math_wave(index: int) -> float:
    values = (0.0, 0.5, 0.866, 1.0, 0.866, 0.5, 0.0, -0.5, -0.866, -1.0, -0.866, -0.5)
    return values[index % len(values)]


def _jpeg_bytes(rgba: bytes, width: int, height: int) -> bytes:
    image = Image.frombytes("RGBA", (width, height), rgba).convert("RGB")
    output = BytesIO()
    image.save(output, format="JPEG", quality=88, subsampling=0, optimize=False, progressive=False)
    return output.getvalue()


def corpus_fingerprint(manifest: dict[str, Any]) -> str:
    return sha256_bytes(canonical_dumps(manifest).encode("utf-8"))
