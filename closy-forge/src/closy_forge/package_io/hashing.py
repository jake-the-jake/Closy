from __future__ import annotations

import hashlib
import struct
from pathlib import Path

from closy_forge.contracts.mesh import CONTENT_HASH_DOMAIN, TOPOLOGY_HASH_DOMAIN
from closy_forge.geometry.mesh_model import MeshSet


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def topology_hash(meshset: MeshSet) -> str:
    digest = hashlib.sha256()
    digest.update(TOPOLOGY_HASH_DOMAIN)
    for mesh in meshset.meshes:
        panel = mesh.panel_id.encode("utf-8")
        digest.update(struct.pack("<I", len(panel)))
        digest.update(panel)
        digest.update(struct.pack("<II", len(mesh.vertices), len(mesh.triangles)))
        for tri in mesh.triangles:
            digest.update(struct.pack("<III", *tri))
    return digest.hexdigest()


def geometry_content_hash(meshset: MeshSet) -> str:
    digest = hashlib.sha256()
    digest.update(CONTENT_HASH_DOMAIN)
    for mesh in meshset.meshes:
        panel = mesh.panel_id.encode("utf-8")
        digest.update(struct.pack("<I", len(panel)))
        digest.update(panel)
        for vertex in mesh.vertices:
            digest.update(struct.pack("<fff", *vertex))
        for uv in mesh.panel_uvs:
            digest.update(struct.pack("<ff", *uv))
        for tri in mesh.triangles:
            digest.update(struct.pack("<III", *tri))
    return digest.hexdigest()


def package_digest(inventory: list[dict[str, object]]) -> str:
    digest = hashlib.sha256()
    digest.update(b"CLOSY_PACKAGE_DIGEST_V1")
    canonical_entries = [
        entry for entry in inventory if not str(entry.get("path", "")).startswith("zeroone/")
    ]
    for entry in sorted(canonical_entries, key=lambda item: str(item["path"])):
        digest.update(str(entry["path"]).encode("utf-8"))
        digest.update(str(entry["sha256"]).encode("ascii"))
        digest.update(str(entry["role"]).encode("utf-8"))
        digest.update(b"1" if entry.get("canonical") else b"0")
    return digest.hexdigest()
