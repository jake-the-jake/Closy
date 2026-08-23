from __future__ import annotations

from dataclasses import dataclass

from .mesh_model import Mesh, MeshSet, Vec2, Vec3


@dataclass(frozen=True)
class RenderBindingSeed:
    sim_mesh_index: int
    sim_triangle_index: int
    barycentric_u: float
    barycentric_v: float
    panel_id: str


def mix3(a: Vec3, b: Vec3, c: Vec3, u: float, v: float) -> Vec3:
    w = 1.0 - u - v
    return (
        a[0] * w + b[0] * u + c[0] * v,
        a[1] * w + b[1] * u + c[1] * v,
        a[2] * w + b[2] * u + c[2] * v,
    )


def mix2(a: Vec2, b: Vec2, c: Vec2, u: float, v: float) -> Vec2:
    w = 1.0 - u - v
    return (a[0] * w + b[0] * u + c[0] * v, a[1] * w + b[1] * u + c[1] * v)


def subdivide_for_render(sim: MeshSet) -> tuple[MeshSet, list[RenderBindingSeed]]:
    render_meshes: list[Mesh] = []
    bindings: list[RenderBindingSeed] = []
    for mesh_index, mesh in enumerate(sim.meshes):
        verts: list[Vec3] = []
        uvs: list[Vec2] = []
        tris: list[tuple[int, int, int]] = []
        for tri_index, tri in enumerate(mesh.triangles):
            a, b, c = mesh.vertices[tri[0]], mesh.vertices[tri[1]], mesh.vertices[tri[2]]
            auv, buv, cuv = mesh.panel_uvs[tri[0]], mesh.panel_uvs[tri[1]], mesh.panel_uvs[tri[2]]
            barys = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (0.5, 0.0), (0.5, 0.5), (0.0, 0.5)]
            base = len(verts)
            for u, v in barys:
                verts.append(mix3(a, b, c, u, v))
                uvs.append(mix2(auv, buv, cuv, u, v))
                bindings.append(RenderBindingSeed(mesh_index, tri_index, u, v, mesh.panel_id))
            tris.extend(
                [
                    (base + 0, base + 3, base + 5),
                    (base + 3, base + 1, base + 4),
                    (base + 5, base + 4, base + 2),
                    (base + 3, base + 4, base + 5),
                ]
            )
        render_meshes.append(
            Mesh(
                name=f"{mesh.name}.render",
                panel_id=mesh.panel_id,
                vertices=verts,
                panel_uvs=uvs,
                triangles=tris,
                material_id=mesh.material_id,
            )
        )
    return MeshSet(render_meshes), bindings
