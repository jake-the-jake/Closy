from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from closy_forge.appearance_correction_v3.projection import SourceViewInput
from closy_forge.appearance_correction_v3.protocol import load_correction_protocol
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.raster import decode_png_rgba
from closy_forge.visual_understanding.raster_parser import (
    LEFT_SLEEVE_RGBA,
    LOGO_RGBA,
    RIGHT_SLEEVE_RGBA,
    TORSO_RGBA,
)

_GARMENT_COLORS = {TORSO_RGBA, LEFT_SLEEVE_RGBA, RIGHT_SLEEVE_RGBA, LOGO_RGBA}


def load_locked_source_inputs(root: Path) -> tuple[SourceViewInput, ...]:
    protocol = load_correction_protocol(root)
    closure = _mapping(protocol.get("sourceClosure"))
    fixture_path = root / str(closure.get("fixtureManifestPath", ""))
    if sha256_file(fixture_path) != closure.get("fixtureManifestSha256"):
        raise ValueError("d0_appearance_fixture_manifest_hash_mismatch")
    fixture_manifest = _read(fixture_path)
    fixtures = {
        str(_mapping(item).get("viewId", "")): _mapping(item)
        for item in _list(fixture_manifest.get("fixtures"))
    }
    fixture_root = fixture_path.parent
    output = []
    for locked in _list(closure.get("allowedViews")):
        fixture = fixtures.get(str(locked.get("viewId", "")), {})
        _validate_fixture_join(locked, fixture)
        path = fixture_root / str(locked.get("relativePath", ""))
        payload = path.read_bytes()
        expected = str(locked.get("sha256", ""))
        if sha256_bytes(payload) != expected:
            raise ValueError("d0_appearance_source_hash_mismatch")
        image = decode_png_rgba(payload)
        garment = frozenset(
            index
            for index in range(image.width * image.height)
            if tuple(image.rgba[index * 4 : index * 4 + 4]) in _GARMENT_COLORS
        )
        logo = frozenset(
            index for index in garment if tuple(image.rgba[index * 4 : index * 4 + 4]) == LOGO_RGBA
        )
        output.append(
            SourceViewInput(
                view_id=str(locked.get("viewId", "")),
                source_id=str(locked.get("sourceId", "")),
                label="back" if locked.get("role") == "rear" else "front",
                expected_sha256=expected,
                payload=payload,
                image=image,
                camera=dict(_mapping(locked.get("camera"))),
                garment_pixels=garment,
                logo_pixels=logo,
            )
        )
    if len(output) != 2:
        raise ValueError("d0_appearance_source_count_invalid")
    return tuple(output)


def _validate_fixture_join(locked: Mapping[str, Any], fixture: Mapping[str, Any]) -> None:
    checks = {
        "view": locked.get("viewId") == fixture.get("viewId"),
        "path": locked.get("relativePath") == fixture.get("relativePath"),
        "sha": locked.get("sha256") == fixture.get("expectedSha256"),
        "pixel": locked.get("decodedPixelHash") == fixture.get("decodedPixelHash"),
        "camera": locked.get("camera") == fixture.get("camera"),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError(f"d0_appearance_fixture_join_mismatch:{','.join(failed)}")


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"d0_appearance_expected_object:{path.name}")
    return value


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]
