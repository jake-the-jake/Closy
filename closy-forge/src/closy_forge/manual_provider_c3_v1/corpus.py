from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from closy_forge.geometry.mesh_model import Mesh, MeshSet

from .common import digest_file, read_json, validate_embedded_digest


@dataclass(frozen=True)
class LockedSource:
    source_id: str
    raw_asset_id: str
    family: str
    path: Path
    document: dict[str, Any]


def load_locked_sources(fixture_root: Path) -> tuple[dict[str, Any], list[LockedSource]]:
    freeze = read_json(fixture_root / "raw_source_freeze.json")
    validate_embedded_digest(freeze, "freezeDigest")
    if freeze["sourceCount"] != 9 or freeze["familyCounts"] != {
        "simple_skirt": 3,
        "sleeveless_top": 3,
        "tshirt": 3,
    }:
        raise ValueError("raw_source_denominator_mismatch")
    sources: list[LockedSource] = []
    seen_ids: set[str] = set()
    for record in freeze["sources"]:
        relative = Path(str(record["path"]))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("unsafe_raw_source_path")
        path = fixture_root / relative
        if digest_file(path) != record["sha256"] or path.stat().st_size != record["bytes"]:
            raise ValueError("raw_source_byte_identity_mismatch")
        document = read_json(path)
        source_id = str(document["sourceId"])
        if source_id in seen_ids or source_id != record["sourceId"]:
            raise ValueError("raw_source_identity_mismatch")
        seen_ids.add(source_id)
        authorship = document["authorship"]
        licence = document["licence"]
        if (
            authorship["canonicalPatternGeneratorUsed"]
            or authorship["derivedFromOtherCorpusSource"]
            or not licence["projectAuthored"]
            or not licence["redistributionAllowed"]
            or licence["personalData"]
        ):
            raise ValueError("raw_source_provenance_policy_violation")
        sources.append(
            LockedSource(
                source_id=source_id,
                raw_asset_id=str(document["rawAssetId"]),
                family=str(document["family"]),
                path=path,
                document=document,
            )
        )
    return freeze, sorted(sources, key=lambda source: source.source_id)


def raw_meshset(source: LockedSource) -> MeshSet:
    meshes: list[Mesh] = []
    for part in source.document["parts"]:
        vertices = [(float(row[0]), float(row[1]), float(row[2])) for row in part["vertices"]]
        triangles = [(int(row[0]), int(row[1]), int(row[2])) for row in part["triangles"]]
        meshes.append(
            Mesh(
                name=str(part["partId"]),
                panel_id=str(part["semanticHint"]),
                vertices=vertices,
                panel_uvs=[(0.0, 0.0) for _ in vertices],
                triangles=triangles,
                material_id=f"material.manual_provider.{source.family}.v1",
            )
        )
    return MeshSet(meshes)
