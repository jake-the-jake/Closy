"""Bounded development sidecar around the unchanged, historical V2 page codec."""

from __future__ import annotations

import math
import re
import struct
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from closy_forge.binding.binary_format import BindingFile, read_binding
from closy_forge.binding.reconstruct import reconstruct_vertices
from closy_forge.geometry.glb_io import audit_glb_geometry, read_glb_meshset
from closy_forge.geometry.mesh_model import MeshSet, Vec3, cross, sub
from closy_forge.manual_provider_binding_v2.binding import (
    BindingV2,
    read_binding_v2,
    reconstruct_v2,
)
from closy_forge.manual_provider_binding_v2.checker import check_rest
from closy_forge.package_io.canonical_json import canonical_dumps, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file, topology_hash
from closy_forge.package_io.managed_output import MARKER_NAME
from closy_forge.security.strict_json import loads_strict_json_object
from closy_forge.simulation.reference_cloth_solver import flatten_mesh, replace_mesh_positions

from .package_v2 import (
    LoadedRuntimePackageV2,
    RuntimeV2Inputs,
    RuntimeV2Limits,
    RuntimeV2Profile,
    build_runtime_package_v2,
    decode_pose_positions,
    encode_pose_positions,
    load_runtime_package_v2,
)

RUNTIME_PACKAGE_V3 = "closy.runtime.conventional.v3"
BINDING_CODEC = "CLSYBND1_zero_offsets"
LOCAL_FRAME_CODEC = "CLSYBV2_local_frame"
POSE_IDS = ("pose.arms_up", "pose.neutral", "pose.torso_twist", "pose.walk_stride")
PROFILES = (
    RuntimeV2Profile("cpu-balanced-64k-v2", 65_536, 32_768),
    RuntimeV2Profile("cpu-compact-32k-v2", 32_768, 16_384),
)
MINIMUM_AREA_M2 = 1e-12
BINDING_TOLERANCE_M = 2e-6
MAX_VERTICES = 262_144
MAX_TRIANGLES = 524_288
MAX_COORDINATE_M = 10.0
MAX_MANIFEST_BYTES = 1_048_576
_SHA = re.compile(r"[0-9a-f]{64}\Z")


class RuntimeV3Error(ValueError):
    pass


@dataclass(frozen=True)
class RuntimeIdentityV3:
    garment_id: str
    avatar_id: str
    profile_id: str
    provenance: str

    def json(self) -> dict[str, str]:
        return {
            "garmentId": self.garment_id,
            "avatarId": self.avatar_id,
            "profileId": self.profile_id,
            "provenance": self.provenance,
        }


@dataclass(frozen=True, kw_only=True)
class LoadedRuntimePackageV3(LoadedRuntimePackageV2):
    identity: RuntimeIdentityV3
    package_identity: str
    cage: MeshSet
    render_mesh: MeshSet
    binding: BindingFile | BindingV2
    cage_poses: dict[str, tuple[Vec3, ...]]
    outfit_members: tuple[RuntimeIdentityV3, ...]
    maximum_binding_error_m: float

    def render_pose(self, pose_id: str) -> MeshSet:
        """Reconstruct from decoded driving bytes, not hidden authoring parameters."""
        moved = replace_mesh_positions(
            self.cage, list(self.cage_poses[pose_id]), flatten_mesh(self.cage).mesh_offsets
        )
        return replace_mesh_positions(
            self.render_mesh,
            reconstruct_binding_v3(moved, self.binding),
            flatten_mesh(self.render_mesh).mesh_offsets,
        )


def manifest_identity(manifest: Mapping[str, Any]) -> str:
    content = dict(manifest)
    content.pop("packageIdentity", None)
    return sha256_bytes(canonical_dumps(content).encode())


def _identity(value: RuntimeIdentityV3) -> None:
    if (
        any(not isinstance(v, str) or not 1 <= len(v) <= 256 for v in value.json().values())
        or not value.garment_id.startswith("garment.")
        or not _SHA.fullmatch(value.provenance)
    ):
        raise RuntimeV3Error("runtime_v3_identity_invalid")


def safe_relative_v3(value: Any) -> str:
    # Reject Windows aliases/ADS as well as traversal, without changing the frozen path helper.
    if not isinstance(value, str) or not value or len(value) > 512:
        raise RuntimeV3Error("runtime_v3_path_invalid")
    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(10)),
        *(f"LPT{i}" for i in range(10)),
    }
    for part in value.split("/"):
        if (
            part in {"", ".", ".."}
            or part[-1:] in {".", " "}
            or any(c in '\\:\x00<>"|?*' or ord(c) < 32 for c in part)
            or part.split(".")[0].upper() in reserved
        ):
            raise RuntimeV3Error("runtime_v3_path_invalid")
    return value


def reject_links_v3(path: Path) -> None:
    for candidate in (path, *path.parents):
        if candidate.is_symlink() or (
            candidate.exists() and getattr(candidate.stat(), "st_file_attributes", 0) & 0x400
        ):
            raise RuntimeV3Error("runtime_v3_link_rejected")


def read_bounded_v3(path: Path, maximum: int) -> bytes:
    reject_links_v3(path)
    if not path.is_file() or path.stat().st_size > maximum:
        raise RuntimeV3Error("runtime_v3_file_limit_or_missing")
    with path.open("rb") as handle:
        data = handle.read(maximum + 1)
    if len(data) > maximum:
        raise RuntimeV3Error("runtime_v3_file_limit_or_missing")
    return data


def inventory_v3(rows: Any, limits: RuntimeV2Limits) -> dict[str, dict[str, Any]]:
    if not isinstance(rows, list) or not 1 <= len(rows) < limits.max_file_count:
        raise RuntimeV3Error("runtime_v3_inventory_limit")
    result: dict[str, dict[str, Any]] = {}
    aliases: set[str] = set()
    total = 0
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeV3Error("runtime_v3_inventory_invalid")
        relative = safe_relative_v3(row.get("path"))
        size, digest = row.get("byteSize"), row.get("sha256")
        if (
            relative.casefold() in aliases
            or relative.casefold() == "manifest.json"
            or type(size) is not int
            or not 0 <= size <= limits.max_file_bytes
            or not isinstance(digest, str)
            or not _SHA.fullmatch(digest)
        ):
            raise RuntimeV3Error("runtime_v3_inventory_invalid")
        aliases.add(relative.casefold())
        total += size
        result[relative] = row
    if total > limits.max_total_bytes:
        raise RuntimeV3Error("runtime_v3_total_size_limit")
    if any(
        parent.as_posix().casefold() in aliases
        for name in result
        for parent in Path(name).parents
        if parent != Path(".")
    ):
        raise RuntimeV3Error("runtime_v3_inventory_path_collision")
    return result


def validate_manifest_v3(
    manifest: dict[str, Any],
    *,
    expected: RuntimeIdentityV3,
    limits: RuntimeV2Limits | None = None,
) -> dict[str, dict[str, Any]]:
    _identity(expected)
    if manifest.get("packageVersion") != RUNTIME_PACKAGE_V3 or manifest.get("schemaVersion") != 3:
        raise RuntimeV3Error("runtime_v3_version_invalid")
    if manifest.get("identity") != expected.json():
        raise RuntimeV3Error("runtime_v3_requested_identity_mismatch")
    if manifest.get("packageIdentity") != manifest_identity(manifest):
        raise RuntimeV3Error("runtime_v3_manifest_identity_mismatch")
    if manifest.get("bindingCodec") not in (BINDING_CODEC, LOCAL_FRAME_CODEC):
        raise RuntimeV3Error("runtime_v3_binding_codec_unsupported")
    if (
        manifest.get("cagePoseIds") != list(POSE_IDS)
        or manifest.get("codec") != "immutable_conventional_v2_compressed_pages"
        or manifest.get("units") != "metres"
        or manifest.get("dynamicZ2") is not False
        or manifest.get("mobileEvidence") is not False
    ):
        raise RuntimeV3Error("runtime_v3_contract_invalid")
    members = manifest.get("outfitMembers")
    if not isinstance(members, list) or len(members) > 16:
        raise RuntimeV3Error("runtime_v3_outfit_members_invalid")
    ids: list[str] = []
    for member in members:
        if not isinstance(member, dict) or set(member) != set(expected.json()):
            raise RuntimeV3Error("runtime_v3_outfit_members_invalid")
        item = RuntimeIdentityV3(
            member["garmentId"], member["avatarId"], member["profileId"], member["provenance"]
        )
        _identity(item)
        if item.avatar_id != expected.avatar_id or item.profile_id != expected.profile_id:
            raise RuntimeV3Error("runtime_v3_outfit_members_invalid")
        ids.append(item.garment_id)
    if (
        len(ids) != len(set(ids))
        or ids != sorted(ids)
        or len(ids) == 1
        or manifest.get("assetKind") != ("outfit" if ids else "garment")
    ):
        raise RuntimeV3Error("runtime_v3_outfit_members_invalid")
    rows = inventory_v3(manifest.get("inventory"), limits or RuntimeV2Limits())
    required = {
        "payload.closyruntime/manifest.json",
        f"payload.closyruntime/{MARKER_NAME}",
        "driving/cage.glb",
        "driving/binding.bin",
        *(f"driving/{pose}.bin" for pose in POSE_IDS),
    }
    if not required <= rows.keys():
        raise RuntimeV3Error("runtime_v3_required_inventory_missing")
    return rows


def trusted_manifest_v3(
    payload: bytes,
    *,
    expected: RuntimeIdentityV3,
    trusted_manifest_hash: str,
    limits: RuntimeV2Limits | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if len(payload) > MAX_MANIFEST_BYTES or sha256_bytes(payload) != trusted_manifest_hash:
        raise RuntimeV3Error("runtime_v3_untrusted_manifest")
    doc = loads_strict_json_object(payload.decode("utf-8"))
    return doc, validate_manifest_v3(doc, expected=expected, limits=limits)


def validate_nested_v3(
    doc: dict[str, Any],
    expected: RuntimeIdentityV3,
    limits: RuntimeV2Limits,
) -> None:
    if (
        doc.get("garmentId") != expected.garment_id
        or doc.get("canonicalPackageDigest") != expected.provenance
        or not isinstance(doc.get("profile"), dict)
        or doc["profile"].get("id") != expected.profile_id
        or set(doc.get("assets", {})) != {"conventionalFallback", *(f"pose:{p}" for p in POSE_IDS)}
    ):
        raise RuntimeV3Error("runtime_v3_nested_identity_mismatch")
    sizes = [a.get("decodedBytes") for a in doc["assets"].values()]
    if (
        any(type(s) is not int or s <= 0 for s in sizes)
        or sum(sizes) > limits.max_decoded_working_set_bytes
    ):
        raise RuntimeV3Error("runtime_v3_decoded_working_set_limit")
    for name, asset in doc["assets"].items():
        maximum = (
            limits.max_file_bytes if name == "conventionalFallback" else 12 + MAX_VERTICES * 12
        )
        if asset["decodedBytes"] > maximum:
            raise RuntimeV3Error("runtime_v3_decoded_asset_limit")


def _glb_preflight(payload: bytes, limits: RuntimeV2Limits) -> None:
    """Bound accessor work before invoking the immutable diagnostic GLB decoder."""
    if (
        len(payload) < 28
        or len(payload) > limits.max_file_bytes
        or struct.unpack_from("<4sII", payload) != (b"glTF", 2, len(payload))
    ):
        raise RuntimeV3Error("runtime_v3_glb_header_invalid")
    cursor = 12
    chunks: list[tuple[int, bytes]] = []
    while cursor < len(payload):
        if cursor + 8 > len(payload):
            raise RuntimeV3Error("runtime_v3_glb_chunk_invalid")
        size, kind = struct.unpack_from("<II", payload, cursor)
        cursor += 8
        if size % 4 or cursor + size > len(payload) or len(chunks) >= 2:
            raise RuntimeV3Error("runtime_v3_glb_chunk_invalid")
        chunks.append((kind, payload[cursor : cursor + size]))
        cursor += size
    if [c[0] for c in chunks] != [0x4E4F534A, 0x004E4942]:
        raise RuntimeV3Error("runtime_v3_glb_chunk_invalid")
    doc = loads_strict_json_object(chunks[0][1].decode("utf-8").rstrip(" "))
    if any(k in doc for k in ("skins", "animations", "extensionsRequired")) or any(
        any(k in node for k in ("matrix", "translation", "rotation", "scale", "skin"))
        for node in doc.get("nodes", [])
    ):
        raise RuntimeV3Error("runtime_v3_glb_transforms_unsupported")
    binary_size = len(chunks[1][1])
    buffers = doc.get("buffers")
    if (
        not isinstance(buffers, list)
        or len(buffers) != 1
        or set(buffers[0]) != {"byteLength"}
        or type(buffers[0]["byteLength"]) is not int
        or not 0 <= binary_size - buffers[0]["byteLength"] <= 3
    ):
        raise RuntimeV3Error("runtime_v3_glb_buffer_invalid")
    views, accessors, meshes = doc.get("bufferViews"), doc.get("accessors"), doc.get("meshes")
    if not all(isinstance(v, list) and 0 < len(v) <= 4096 for v in (views, accessors, meshes)):
        raise RuntimeV3Error("runtime_v3_glb_tables_invalid")
    assert isinstance(views, list) and isinstance(accessors, list) and isinstance(meshes, list)
    nodes = doc.get("nodes", [])
    if (
        doc.get("asset", {}).get("version") != "2.0"
        or len(nodes) != len(meshes)
        or sorted(node.get("mesh", -1) for node in nodes) != list(range(len(meshes)))
        or any("children" in node or "weights" in node for node in nodes)
        or doc.get("scenes") != [{"nodes": list(range(len(nodes)))}]
        or doc.get("scene", 0) != 0
    ):
        raise RuntimeV3Error("runtime_v3_glb_scene_unsupported")
    for view in views:
        start, size = view.get("byteOffset", 0), view.get("byteLength")
        if (
            view.get("buffer") != 0
            or type(start) is not int
            or type(size) is not int
            or start < 0
            or size < 0
            or start + size > buffers[0]["byteLength"]
        ):
            raise RuntimeV3Error("runtime_v3_glb_view_bounds")
    work = 0
    for acc in accessors:
        count, view_index = acc.get("count"), acc.get("bufferView")
        width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}.get(acc.get("type"), 0)
        component = {5121: 1, 5123: 2, 5125: 4, 5126: 4}.get(acc.get("componentType"), 0)
        if (
            type(count) is not int
            or not 1 <= count <= MAX_TRIANGLES * 3
            or type(view_index) is not int
            or not 0 <= view_index < len(views)
            or not width
            or not component
            or "sparse" in acc
            or acc.get("normalized", False)
        ):
            raise RuntimeV3Error("runtime_v3_glb_accessor_invalid")
        view = views[view_index]
        stride, start = view.get("byteStride", width * component), acc.get("byteOffset", 0)
        if (
            type(stride) is not int
            or stride < width * component
            or stride % component
            or type(start) is not int
            or start < 0
            or start % component
            or start + (count - 1) * stride + width * component > view["byteLength"]
        ):
            raise RuntimeV3Error("runtime_v3_glb_accessor_bounds")
        work += count * width * component
    if work > limits.max_decoded_working_set_bytes:
        raise RuntimeV3Error("runtime_v3_glb_working_set_limit")
    vertices = triangles = 0
    for mesh in meshes:
        for primitive in mesh["primitives"]:
            if "targets" in primitive or "weights" in mesh:
                raise RuntimeV3Error("runtime_v3_glb_morph_unsupported")
            if primitive.get("mode", 4) != 4:
                raise RuntimeV3Error("runtime_v3_glb_triangle_mode_required")
            attributes = primitive["attributes"]
            for semantic, shape in (
                ("POSITION", "VEC3"),
                ("NORMAL", "VEC3"),
                ("TANGENT", "VEC4"),
                ("TEXCOORD_0", "VEC2"),
            ):
                index = attributes.get(semantic)
                if type(index) is not int or not 0 <= index < len(accessors):
                    raise RuntimeV3Error("runtime_v3_glb_attribute_invalid")
                if accessors[index]["type"] != shape or accessors[index]["componentType"] != 5126:
                    raise RuntimeV3Error("runtime_v3_glb_attribute_invalid")
            index = primitive.get("indices")
            if type(index) is not int or not 0 <= index < len(accessors):
                raise RuntimeV3Error("runtime_v3_glb_indices_required")
            acc = accessors[index]
            if (
                acc["type"] != "SCALAR"
                or acc["componentType"] not in (5121, 5123, 5125)
                or acc["count"] % 3
            ):
                raise RuntimeV3Error("runtime_v3_glb_indices_invalid")
            vertices += accessors[attributes["POSITION"]]["count"]
            triangles += acc["count"] // 3
    if not 0 < vertices <= MAX_VERTICES or not 0 < triangles <= MAX_TRIANGLES:
        raise RuntimeV3Error("runtime_v3_geometry_limit")


def audit_mesh_v3(mesh: MeshSet) -> None:
    if not 0 < mesh.vertex_count <= MAX_VERTICES or not 0 < mesh.triangle_count <= MAX_TRIANGLES:
        raise RuntimeV3Error("runtime_v3_geometry_limit")
    for panel in mesh.meshes:
        for vertex in panel.vertices:
            if any(not math.isfinite(v) or abs(v) > MAX_COORDINATE_M for v in vertex):
                raise RuntimeV3Error("runtime_v3_geometry_coordinate_invalid")
        for tri in panel.triangles:
            if len(set(tri)) != 3 or any(i < 0 or i >= len(panel.vertices) for i in tri):
                raise RuntimeV3Error("runtime_v3_geometry_indices_invalid")
            a, b, c = (panel.vertices[i] for i in tri)
            area = math.sqrt(sum(v * v for v in cross(sub(b, a), sub(c, a)))) / 2
            if not math.isfinite(area) or area <= MINIMUM_AREA_M2:
                raise RuntimeV3Error("runtime_v3_geometry_triangle_invalid")


def decode_glb_v3(payload: bytes, limits: RuntimeV2Limits | None = None) -> MeshSet:
    try:
        _glb_preflight(payload, limits or RuntimeV2Limits())
        with tempfile.TemporaryDirectory(prefix="closy-v3-glb-") as directory:
            path = Path(directory) / "mesh.glb"
            path.write_bytes(payload)
            audit = audit_glb_geometry(path, minimum_triangle_area=MINIMUM_AREA_M2)
            if audit["status"] != "pass":
                raise RuntimeV3Error("runtime_v3_decoded_geometry_invalid")
            mesh = read_glb_meshset(path)
        audit_mesh_v3(mesh)
        return mesh
    except (ValueError, KeyError, IndexError, TypeError, AttributeError, struct.error) as error:
        raise RuntimeV3Error(f"runtime_v3_glb_rejected:{error}") from error


def audit_glb_bytes(payload: bytes) -> dict[str, Any]:
    mesh = decode_glb_v3(payload)
    return {"valid": True, "vertexCount": mesh.vertex_count, "triangleCount": mesh.triangle_count}


def reconstruct_binding_v3(cage: MeshSet, binding: BindingFile | BindingV2) -> list[Vec3]:
    if isinstance(binding, BindingV2):
        return reconstruct_v2(cage, binding)
    return reconstruct_vertices(cage, binding)


def decode_binding_v3(
    payload: bytes,
    cage: MeshSet,
    render: MeshSet,
    *,
    binding_codec: str = BINDING_CODEC,
    cage_glb: bytes | None = None,
    render_glb: bytes | None = None,
) -> BindingFile | BindingV2:
    if binding_codec == LOCAL_FRAME_CODEC:
        if cage_glb is None or render_glb is None or payload[:8] != b"CLSYBV2\0":
            raise RuntimeV3Error("runtime_v3_local_frame_bytes_required")
        with tempfile.TemporaryDirectory(prefix="closy-v3-local-frame-") as directory:
            root = Path(directory)
            (root / "cage.glb").write_bytes(cage_glb)
            (root / "render.glb").write_bytes(render_glb)
            (root / "binding.bin").write_bytes(payload)
            checked = check_rest(root / "cage.glb", root / "render.glb", root / "binding.bin")
            if checked["status"] != "pass":
                raise RuntimeV3Error("runtime_v3_local_frame_rest_failed")
            return read_binding_v2(root / "binding.bin")
    if binding_codec != BINDING_CODEC:
        raise RuntimeV3Error("runtime_v3_binding_codec_unsupported")
    if len(payload) > 96 + MAX_VERTICES * 20 or payload[:8] != b"CLSYBND1":
        raise RuntimeV3Error("runtime_v3_binding_codec_or_size_unsupported")
    with tempfile.TemporaryDirectory(prefix="closy-v3-binding-") as directory:
        path = Path(directory) / "binding.bin"
        path.write_bytes(payload)
        binding = read_binding(path)
    panels = sorted({m.panel_id for m in cage.meshes})
    if (
        binding.simulation_topology_hash != topology_hash(cage)
        or binding.render_topology_hash != topology_hash(render)
        or binding.simulation_triangle_count != cage.triangle_count
        or binding.panel_count != len(panels)
        or len(binding.records) != render.vertex_count
    ):
        raise RuntimeV3Error("runtime_v3_stale_binding")
    triangle_panels = [m.panel_id for m in cage.meshes for _ in m.triangles]
    render_panels = [m.panel_id for m in render.meshes for _ in m.vertices]
    for record, panel in zip(binding.records, render_panels, strict=True):
        u, v = record.barycentric_u, record.barycentric_v
        if (
            not 0 <= record.simulation_triangle_index < len(triangle_panels)
            or not 0 <= record.panel_table_index < len(panels)
            or not all(math.isfinite(w) and 0 <= w <= 1 for w in (u, v))
            or u + v > 1.000001
            or record.normal_offset != 0
            or record.flags != 0
            or panels[record.panel_table_index] != panel
            or triangle_panels[record.simulation_triangle_index] != panel
        ):
            raise RuntimeV3Error("runtime_v3_binding_influence_invalid")
    _error(reconstruct_vertices(cage, binding), flatten_mesh(render).positions)
    return binding


def _error(left: Sequence[Vec3], right: Sequence[Vec3]) -> float:
    if not left or len(left) != len(right):
        raise RuntimeV3Error("runtime_v3_pose_count_mismatch")
    result = max(math.dist(a, b) for a, b in zip(left, right, strict=True))
    if not math.isfinite(result) or result > BINDING_TOLERANCE_M:
        raise RuntimeV3Error("runtime_v3_binding_fidelity_failed")
    return result


def analytic_cage_poses_v3(cage: MeshSet) -> dict[str, list[Vec3]]:
    """The four PR66 analytic drivers, now applied to the serialized cage."""
    audit_mesh_v3(cage)
    neutral = flatten_mesh(cage).positions
    low, high = min(v[1] for v in neutral), max(v[1] for v in neutral)
    height, center = max(high - low, 1e-9), (low + high) / 2
    twists: list[Vec3] = []
    for x, y, z in neutral:
        angle = 0.06 * (y - center) / height
        twists.append(
            (
                x * math.cos(angle) + z * math.sin(angle),
                y,
                -x * math.sin(angle) + z * math.cos(angle),
            )
        )
    return {
        "pose.neutral": list(neutral),
        "pose.arms_up": [
            (x, y + 0.015 * abs(x), z + 0.005 * (y - low) / height) for x, y, z in neutral
        ],
        "pose.torso_twist": twists,
        "pose.walk_stride": [
            (x, y, z + (0.018 if x >= 0 else -0.018) * (high - y) / height) for x, y, z in neutral
        ],
    }


def bound_pose_positions_v3(
    cage: MeshSet,
    binding: BindingFile | BindingV2,
    cage_poses: Mapping[str, Sequence[Vec3]],
) -> dict[str, list[Vec3]]:
    result = {}
    for pose, positions in cage_poses.items():
        if len(positions) != cage.vertex_count:
            raise RuntimeV3Error("runtime_v3_pose_count_mismatch")
        decoded = decode_pose_positions(encode_pose_positions(positions))
        moved = replace_mesh_positions(cage, list(decoded), flatten_mesh(cage).mesh_offsets)
        audit_mesh_v3(moved)
        result[pose] = reconstruct_binding_v3(moved, binding)
    return result


def build_runtime_package_v3(
    target: Path,
    *,
    inputs: RuntimeV2Inputs,
    profile: RuntimeV2Profile,
    identity: RuntimeIdentityV3,
    cage: Path,
    binding: Path,
    cage_poses: Mapping[str, Sequence[Vec3]],
    outfit_members: Sequence[RuntimeIdentityV3] = (),
    limits: RuntimeV2Limits | None = None,
    binding_codec: str = BINDING_CODEC,
) -> dict[str, Any]:
    active = limits or RuntimeV2Limits()
    reject_links_v3(target)
    if target.exists():
        raise RuntimeV3Error("runtime_v3_output_must_be_fresh")
    _identity(identity)
    if (
        identity.garment_id != inputs.garment_id
        or identity.profile_id != profile.profile_id
        or identity.provenance != inputs.canonical_package_digest
        or sorted(cage_poses) != list(POSE_IDS)
    ):
        raise RuntimeV3Error("runtime_v3_input_identity_mismatch")
    render_bytes = read_bounded_v3(inputs.conventional_fallback_glb, active.max_file_bytes)
    cage_bytes = read_bounded_v3(cage, active.max_file_bytes)
    binding_bytes = read_bounded_v3(binding, active.max_file_bytes)
    render = decode_glb_v3(render_bytes, active)
    driving = decode_glb_v3(cage_bytes, active)
    decode_binding_v3(
        binding_bytes,
        driving,
        render,
        binding_codec=binding_codec,
        cage_glb=cage_bytes,
        render_glb=render_bytes,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".runtime-v3-", dir=target.parent) as temporary:
        stage = Path(temporary) / "package"
        stage.mkdir()
        (stage / "driving").mkdir()
        (stage / "driving/cage.glb").write_bytes(cage_bytes)
        (stage / "driving/binding.bin").write_bytes(binding_bytes)
        for pose, positions in sorted(cage_poses.items()):
            if len(positions) != driving.vertex_count:
                raise RuntimeV3Error("runtime_v3_pose_count_mismatch")
            (stage / f"driving/{pose}.bin").write_bytes(encode_pose_positions(positions))
        # V2 reads the bytes audited above rather than re-reading a mutable source.
        fallback = Path(temporary) / "source.glb"
        fallback.write_bytes(render_bytes)
        build_runtime_package_v2(
            stage / "payload.closyruntime",
            inputs=replace(inputs, conventional_fallback_glb=fallback),
            profile=profile,
            limits=active,
        )
        rows = [
            {
                "path": p.relative_to(stage).as_posix(),
                "sha256": sha256_file(p),
                "byteSize": p.stat().st_size,
            }
            for p in sorted(stage.rglob("*"))
            if p.is_file()
        ]
        manifest: dict[str, Any] = {
            "schemaVersion": 3,
            "packageVersion": RUNTIME_PACKAGE_V3,
            "identity": identity.json(),
            "inventory": rows,
            "codec": "immutable_conventional_v2_compressed_pages",
            "bindingCodec": binding_codec,
            "units": "metres",
            "cagePoseIds": list(POSE_IDS),
            "assetKind": "outfit" if outfit_members else "garment",
            "outfitMembers": [m.json() for m in sorted(outfit_members, key=lambda m: m.garment_id)],
            "optionalZeroOne": "not_selected_conventional_only",
            "dynamicZ2": False,
            "mobileEvidence": False,
            "motionSupport": "analytic_cage_binding_fidelity_not_cloth",
        }
        manifest["packageIdentity"] = manifest_identity(manifest)
        write_canonical_json(stage / "manifest.json", manifest)
        load_runtime_package_v3(
            stage,
            expected=identity,
            trusted_manifest_hash=sha256_file(stage / "manifest.json"),
            limits=active,
        )
        stage.rename(target)
    return manifest


def build_runtime_outfit_v3(
    target: Path,
    *,
    inputs: RuntimeV2Inputs,
    profile: RuntimeV2Profile,
    identity: RuntimeIdentityV3,
    cage: Path,
    binding: Path,
    cage_poses: Mapping[str, Sequence[Vec3]],
    members: Sequence[RuntimeIdentityV3],
    binding_codec: str = BINDING_CODEC,
) -> dict[str, Any]:
    """Consume an actual whole-outfit cage/render/binding; no collision/cloth claim."""
    if len(members) < 2:
        raise RuntimeV3Error("runtime_v3_outfit_members_invalid")
    return build_runtime_package_v3(
        target,
        inputs=inputs,
        profile=profile,
        identity=identity,
        cage=cage,
        binding=binding,
        cage_poses=cage_poses,
        outfit_members=members,
        binding_codec=binding_codec,
    )


def load_runtime_package_v3(
    root: Path,
    *,
    expected: RuntimeIdentityV3,
    trusted_manifest_hash: str,
    limits: RuntimeV2Limits | None = None,
) -> LoadedRuntimePackageV3:
    active = limits or RuntimeV2Limits()
    try:
        doc, rows = trusted_manifest_v3(
            read_bounded_v3(root / "manifest.json", MAX_MANIFEST_BYTES),
            expected=expected,
            trusted_manifest_hash=trusted_manifest_hash,
            limits=active,
        )
        actual: set[str] = set()
        for path in root.rglob("*"):
            reject_links_v3(path)
            if path.is_file():
                actual.add(path.relative_to(root).as_posix())
        if actual != rows.keys() | {"manifest.json"}:
            raise RuntimeV3Error("runtime_v3_exact_inventory_mismatch")
        verified: dict[str, bytes] = {}
        for relative, row in rows.items():
            payload = read_bounded_v3(root / relative, row["byteSize"])
            if len(payload) != row["byteSize"] or sha256_bytes(payload) != row["sha256"]:
                raise RuntimeV3Error("runtime_v3_file_identity_mismatch")
            verified[relative] = payload
        nested_bytes = verified["payload.closyruntime/manifest.json"]
        if len(nested_bytes) > MAX_MANIFEST_BYTES:
            raise RuntimeV3Error("runtime_v3_nested_manifest_limit")
        nested = loads_strict_json_object(nested_bytes.decode())
        validate_nested_v3(nested, expected, active)
        # Snapshot verified bytes: V2's own re-reads cannot escape the V3 envelope.
        with tempfile.TemporaryDirectory(prefix="closy-v3-load-") as directory:
            snapshot = Path(directory)
            for relative, payload in verified.items():
                path = snapshot / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
            loaded = load_runtime_package_v2(snapshot / "payload.closyruntime", limits=active)
        render = decode_glb_v3(loaded.conventional_fallback_glb, active)
        cage = decode_glb_v3(verified["driving/cage.glb"], active)
        binding = decode_binding_v3(
            verified["driving/binding.bin"],
            cage,
            render,
            binding_codec=doc["bindingCodec"],
            cage_glb=verified["driving/cage.glb"],
            render_glb=loaded.conventional_fallback_glb,
        )
        cage_poses = {}
        for pose in POSE_IDS:
            data = verified[f"driving/{pose}.bin"]
            if len(data) != 12 + cage.vertex_count * 12:
                raise RuntimeV3Error("runtime_v3_pose_count_mismatch")
            cage_poses[pose] = decode_pose_positions(data)
        maximum = _error(cage_poses["pose.neutral"], flatten_mesh(cage).positions)
        for pose, positions in bound_pose_positions_v3(cage, binding, cage_poses).items():
            maximum = max(maximum, _error(positions, loaded.pose_positions[pose]))
            for coordinates in (positions, loaded.pose_positions[pose]):
                audit_mesh_v3(
                    replace_mesh_positions(
                        render, list(coordinates), flatten_mesh(render).mesh_offsets
                    )
                )
        members = tuple(
            RuntimeIdentityV3(m["garmentId"], m["avatarId"], m["profileId"], m["provenance"])
            for m in doc["outfitMembers"]
        )
        return LoadedRuntimePackageV3(
            package_digest=loaded.package_digest,
            garment_id=loaded.garment_id,
            profile_id=loaded.profile_id,
            conventional_fallback_glb=loaded.conventional_fallback_glb,
            pose_positions=loaded.pose_positions,
            identity=expected,
            package_identity=doc["packageIdentity"],
            cage=cage,
            render_mesh=render,
            binding=binding,
            cage_poses=cage_poses,
            outfit_members=members,
            maximum_binding_error_m=maximum,
        )
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        IndexError,
        AttributeError,
        struct.error,
    ) as error:
        raise RuntimeV3Error(f"runtime_v3_load_rejected:{error}") from error


def load_or_compatible_last_good(
    root: Path,
    *,
    last_good: Path | None,
    expected: RuntimeIdentityV3,
    trusted_manifest_hash: str,
    last_good_manifest_hash: str | None = None,
) -> tuple[LoadedRuntimePackageV3, str | None]:
    try:
        return load_runtime_package_v3(
            root, expected=expected, trusted_manifest_hash=trusted_manifest_hash
        ), None
    except RuntimeV3Error as error:
        if last_good is None or last_good_manifest_hash is None:
            raise RuntimeV3Error(f"runtime_v3_no_verified_compatible_fallback:{error}") from error
        loaded = load_runtime_package_v3(
            last_good, expected=expected, trusted_manifest_hash=last_good_manifest_hash
        )
        reason = f"runtime_v3_verified_last_good:{error}"
        return replace(loaded, fallback_reason=reason), reason
