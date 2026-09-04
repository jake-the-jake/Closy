from __future__ import annotations

from dataclasses import asdict
from math import acos, sqrt
from typing import Any

from closy_forge.geometry.mesh_model import Mesh, MeshSet, mesh_bounds
from closy_forge.package_io.hashing import geometry_content_hash, topology_hash
from closy_forge.simulation.reference_cloth_solver import (
    SOLVER_VERSION,
    SettleSettings,
    _project_collisions,
    settle_reference_cloth,
    simulate_reference_motion_state,
)

from .common import canonical_digest, rounded
from .units import MaterialSI, SpecimenSI, material_to_solver_payload, validate_specimen

SPECIMEN_VERSION = "closy.geometric_material_specimens.v2"
FORWARD_VERSION = "closy.source_guarded_geometric_forward.v2"


def default_specimen(
    specimen_id: str,
    *,
    load_scale: float,
    mesh: tuple[int, int],
    time_step_s: float,
    step_count: int,
    solver_iterations: int,
    geometry: str = "standard_coupon",
) -> SpecimenSI:
    width = 0.18 if geometry == "standard_coupon" else (0.27 if geometry == "wide_coupon" else 0.14)
    length = 0.32 if geometry != "long_coupon" else 0.46
    force = 0.36 * load_scale
    velocity = (
        0.48 * load_scale
        if specimen_id in {"free_decay", "impact_rebound", "contact_control"}
        else 0.0
    )
    return SpecimenSI(
        length_m=length,
        width_m=width,
        thickness_m=0.0014,
        mesh_columns=mesh[0],
        mesh_rows=mesh[1],
        time_step_s=time_step_s,
        step_count=step_count,
        solver_iterations=solver_iterations,
        force_n=force,
        displacement_m=0.018 * load_scale,
        initial_velocity_m_s=velocity,
        acceleration_m_s2=9.81 * load_scale,
        gravity_m_s2=-9.81 * load_scale,
        contact_offset_m=0.003,
    )


def run_specimen(
    specimen_id: str,
    material: MaterialSI,
    specimen: SpecimenSI,
    *,
    tuple_id: str,
    observation_id: str,
    canonical_digits: int,
) -> dict[str, Any]:
    validate_specimen(specimen)
    if specimen_id not in {
        "warp_extension",
        "weft_extension",
        "bias_shear",
        "cantilever_bend",
        "free_decay",
        "inclined_friction",
        "impact_rebound",
        "contact_control",
    }:
        raise ValueError("specimen_family_invalid")
    mesh = build_coupon_mesh(specimen_id, specimen)
    material_payload = material_to_solver_payload(material)
    settings = SettleSettings(
        time_step_seconds=specimen.time_step_s,
        step_count=specimen.step_count,
        solver_iterations=specimen.solver_iterations,
        gravity_m_s2=specimen.gravity_m_s2,
        damping_ratio=material.damping_ratio,
        collision_clearance_m=specimen.contact_offset_m,
        stretch_stiffness=float(material_payload["stretchStiffness"]),
        warp_stretch_stiffness=float(material_payload["warpStretchStiffness"]),
        weft_stretch_stiffness=float(material_payload["weftStretchStiffness"]),
        shear_stiffness=float(material_payload["shearStiffness"]),
        bend_stiffness=float(material_payload["bendStiffness"]),
        surface_density_kg_m2=material.surface_density_kg_m2,
        warp_stiffness_n_m=material.warp_stiffness_n_m,
        weft_stiffness_n_m=material.weft_stiffness_n_m,
        shear_stiffness_n_m=material.shear_stiffness_n_m,
        bend_stiffness_nm=material.bend_stiffness_nm,
        friction_coefficient=material.friction_coefficient,
        restitution_coefficient=material.restitution_coefficient,
        warp_orientation_degrees=_orientation(specimen_id),
        self_collision_thickness_meters=material.thickness_m,
        self_collision_clearance_meters=material.thickness_m * 0.5,
    )
    avatar = _contact_contract(specimen_id, specimen)
    result = settle_reference_cloth(
        mesh,
        {"constraints": []},
        avatar,
        material_payload,
        settings=settings,
        canonical_position_digits=canonical_digits,
    )
    motion_trajectory: list[MeshSet] = []
    motion = None
    if specimen_id in {"free_decay", "impact_rebound", "contact_control"}:
        motion = simulate_reference_motion_state(
            result.settled_mesh,
            {"constraints": []},
            avatar,
            material_payload,
            f"smv2-{specimen_id}",
            canonical_position_digits=canonical_digits,
            trajectory_sink=motion_trajectory,
        )
    final_mesh = motion.mesh if motion is not None else result.settled_mesh
    observables = _physical_observables(
        specimen_id,
        mesh,
        final_mesh,
        motion_trajectory,
        specimen,
        material,
        result.diagnostics,
    )
    payload: dict[str, Any] = {
        "schemaVersion": 2,
        "specimenVersion": SPECIMEN_VERSION,
        "forwardVersion": FORWARD_VERSION,
        "tupleId": tuple_id,
        "observationId": observation_id,
        "specimenId": specimen_id,
        "solverVersion": SOLVER_VERSION,
        "solverEntryPoint": "closy_forge.simulation.reference_cloth_solver.settle_reference_cloth",
        "motionEntryPoint": (
            "closy_forge.simulation.reference_cloth_solver.simulate_reference_motion_state"
            if motion is not None
            else None
        ),
        "specimenSI": asdict(specimen),
        "materialDescriptor": material_payload,
        "mesh": {
            "vertexCount": mesh.vertex_count,
            "triangleCount": mesh.triangle_count,
            "topologyHash": topology_hash(mesh),
            "initialContentHash": geometry_content_hash(mesh),
            "finalContentHash": geometry_content_hash(final_mesh),
            "initialBoundsMeters": mesh_bounds(mesh),
            "finalBoundsMeters": mesh_bounds(final_mesh),
        },
        "boundaryConditions": {
            "support": "top_edge_position_support",
            "load": "gravity_equivalent_body_force",
            "contact": avatar["collisionPrimitives"],
        },
        "initialStateMeters": _mesh_positions(mesh),
        "finalStateMeters": _mesh_positions(final_mesh),
        "sampledTrajectoryMeters": [_mesh_positions(state) for state in motion_trajectory],
        "observables": observables,
        "diagnostics": {
            "contactEventCount": int(result.diagnostics.get("collisionCount", 0)),
            "constraintCount": int(result.diagnostics.get("constraintCounts", {}).get("total", 0)),
            "energyHistoryJProxy": result.diagnostics.get("energyHistory", []),
            "solverTermination": result.diagnostics.get("numericalTermination", "completed"),
            "finitePositions": int(result.diagnostics.get("nonFiniteValueCount", 0)) == 0,
            "motion": motion.diagnostics if motion is not None else None,
        },
    }
    payload["executionDigest"] = canonical_digest(payload)
    return payload


def run_garment_motion(
    family: str,
    motion_id: str,
    material: MaterialSI,
    *,
    tuple_id: str,
    canonical_digits: int,
) -> dict[str, Any]:
    if family not in {"tshirt", "sleeveless_top", "simple_skirt"}:
        raise ValueError("garment_family_invalid")
    specimen = default_specimen(
        "free_decay",
        load_scale=1.0,
        mesh=(5, 5),
        time_step_s=1.0 / 60.0,
        step_count=12,
        solver_iterations=6,
        geometry="wide_coupon",
    )
    garment = build_garment_mesh(family, specimen)
    descriptor = material_to_solver_payload(material)
    avatar = _garment_avatar_contract(family)
    settings = SettleSettings(
        time_step_seconds=specimen.time_step_s,
        step_count=specimen.step_count,
        solver_iterations=specimen.solver_iterations,
        gravity_m_s2=-9.81,
        damping_ratio=material.damping_ratio,
        collision_clearance_m=0.004,
        stretch_stiffness=float(descriptor["stretchStiffness"]),
        warp_stretch_stiffness=float(descriptor["warpStretchStiffness"]),
        weft_stretch_stiffness=float(descriptor["weftStretchStiffness"]),
        shear_stiffness=float(descriptor["shearStiffness"]),
        bend_stiffness=float(descriptor["bendStiffness"]),
        surface_density_kg_m2=material.surface_density_kg_m2,
        warp_stiffness_n_m=material.warp_stiffness_n_m,
        weft_stiffness_n_m=material.weft_stiffness_n_m,
        shear_stiffness_n_m=material.shear_stiffness_n_m,
        bend_stiffness_nm=material.bend_stiffness_nm,
        friction_coefficient=material.friction_coefficient,
        restitution_coefficient=material.restitution_coefficient,
    )
    settled = settle_reference_cloth(
        garment,
        {"constraints": []},
        avatar,
        descriptor,
        settings=settings,
        canonical_position_digits=canonical_digits,
    )
    trajectory: list[MeshSet] = []
    motion = simulate_reference_motion_state(
        settled.settled_mesh,
        {"constraints": []},
        avatar,
        descriptor,
        f"{family}-{motion_id}",
        canonical_position_digits=canonical_digits,
        trajectory_sink=trajectory,
    )
    metrics = _motion_metrics(garment, motion.mesh, trajectory, settled.diagnostics)
    package_identity = canonical_digest(
        {
            "family": family,
            "tupleId": tuple_id,
            "motionId": motion_id,
            "material": descriptor,
            "topology": topology_hash(garment),
        }
    )
    payload: dict[str, Any] = {
        "schemaVersion": 2,
        "tupleId": tuple_id,
        "family": family,
        "motionId": motion_id,
        "solverVersion": SOLVER_VERSION,
        "solverEntryPoints": [
            "settle_reference_cloth",
            "simulate_reference_motion_state",
        ],
        "materialDescriptor": descriptor,
        "materialOverrideContract": "closy.canonical_material_descriptor_plus_user_override.v1",
        "packageIdentity": package_identity,
        "packageProvenance": {
            "canonicalFamily": family,
            "source": "project_authored_synthetic_solver_material_v2",
            "materialIdentity": canonical_digest(descriptor),
        },
        "meshTopologyHash": topology_hash(garment),
        "initialContentHash": geometry_content_hash(garment),
        "finalContentHash": geometry_content_hash(motion.mesh),
        "trajectoryMeters": [_mesh_positions(state) for state in trajectory],
        "metrics": metrics,
        "termination": "passed" if motion.diagnostics.get("finitePositions") else "non_finite",
        "performance": {
            "boundedStepCount": specimen.step_count + int(motion.diagnostics["stepCount"]),
            "boundedIterations": specimen.solver_iterations,
        },
    }
    payload["trajectoryDigest"] = canonical_digest(payload["trajectoryMeters"])
    payload["packageDigest"] = canonical_digest(payload)
    return payload


def build_coupon_mesh(specimen_id: str, specimen: SpecimenSI) -> MeshSet:
    columns, rows = specimen.mesh_columns, specimen.mesh_rows
    vertices: list[tuple[float, float, float]] = []
    uvs: list[tuple[float, float]] = []
    for row in range(rows):
        v = row / (rows - 1)
        y = 1.48 - v * specimen.length_m
        for column in range(columns):
            u = column / (columns - 1)
            x = (u - 0.5) * specimen.width_m
            z = 0.0
            if specimen_id in {"bias_shear", "cantilever_bend"}:
                z = 0.012 * v * v * (2.0 * u - 1.0)
            if specimen_id in {"inclined_friction", "impact_rebound", "contact_control"}:
                z = 0.055 + 0.012 * v
            vertices.append((x, y, z))
            uvs.append((u, v))
    triangles: list[tuple[int, int, int]] = []
    for row in range(rows - 1):
        for column in range(columns - 1):
            a = row * columns + column
            b = a + 1
            c = a + columns
            d = c + 1
            triangles.extend(((a, c, b), (b, c, d)))
    return MeshSet(
        [Mesh(f"smv2.{specimen_id}", f"panel.smv2.{specimen_id}", vertices, uvs, triangles)]
    )


def build_garment_mesh(family: str, specimen: SpecimenSI) -> MeshSet:
    dimensions = {
        "tshirt": (0.64, 0.62, 1.48),
        "sleeveless_top": (0.55, 0.58, 1.48),
        "simple_skirt": (0.58, 0.64, 1.22),
    }
    width, length, top = dimensions[family]
    proxy = SpecimenSI(
        **{
            **asdict(specimen),
            "width_m": width,
            "length_m": length,
            "mesh_columns": 6,
            "mesh_rows": 7,
        }
    )
    mesh = build_coupon_mesh("cantilever_bend", proxy).meshes[0]
    shifted = [(x, y - (1.48 - top), z + 0.18) for x, y, z in mesh.vertices]
    return MeshSet(
        [
            Mesh(
                f"canonical.{family}.simulation",
                f"panel.{family}.front",
                shifted,
                mesh.panel_uvs,
                mesh.triangles,
            )
        ]
    )


def _orientation(specimen_id: str) -> float:
    if specimen_id == "weft_extension":
        return 90.0
    if specimen_id == "bias_shear":
        return 45.0
    return 0.0


def _contact_contract(specimen_id: str, specimen: SpecimenSI) -> dict[str, Any]:
    if specimen_id not in {"inclined_friction", "impact_rebound", "contact_control"}:
        return {"collisionPrimitives": []}
    center_z = 0.0 if specimen_id == "contact_control" else 0.025
    radii = [0.15, 0.20, 0.07 if specimen_id == "impact_rebound" else 0.055]
    return {
        "collisionPrimitives": [
            {
                "id": f"collision.{specimen_id}",
                "type": "ellipsoid",
                "center": [0.0, 1.24, center_z],
                "radii": radii,
            }
        ]
    }


def _garment_avatar_contract(family: str) -> dict[str, Any]:
    center_y = 1.16 if family == "simple_skirt" else 1.27
    return {
        "collisionPrimitives": [
            {
                "id": f"body.{family}",
                "type": "ellipsoid",
                "center": [0.0, center_y, 0.02],
                "radii": [0.24, 0.34, 0.16],
            }
        ]
    }


def _physical_observables(
    specimen_id: str,
    initial: MeshSet,
    final: MeshSet,
    trajectory: list[MeshSet],
    specimen: SpecimenSI,
    material: MaterialSI,
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    first = [point for mesh in initial.meshes for point in mesh.vertices]
    last = [point for mesh in final.meshes for point in mesh.vertices]
    displacements = [_distance(a, b) for a, b in zip(first, last, strict=True)]
    mean_displacement = sum(displacements) / len(displacements)
    maximum_displacement = max(displacements)
    mass_kg = specimen.length_m * specimen.width_m * material.surface_density_kg_m2
    force_n = abs(mass_kg * specimen.gravity_m_s2)
    endpoint = last[-1]
    origin = last[0]
    vector = (endpoint[0] - origin[0], endpoint[1] - origin[1], endpoint[2] - origin[2])
    length = max(1e-12, sqrt(sum(value * value for value in vector)))
    angle = acos(max(-1.0, min(1.0, abs(vector[1]) / length)))
    series = [_centroid(state) for state in trajectory]
    decay = 0.0
    rebound = 0.0
    slide = abs(endpoint[0] - first[-1][0])
    if len(series) >= 3:
        increments = [
            _distance(left, right) for left, right in zip(series, series[1:], strict=False)
        ]
        decay = increments[-1] / max(1e-9, increments[0])
        rebound = max(0.0, max(value[1] for value in series) - min(value[1] for value in series))
        slide = max(value[0] for value in series) - min(value[0] for value in series)
    dt = specimen.time_step_s
    rebound_velocity = rebound / max(dt, dt * max(1, len(series) - 1))
    if specimen_id in {"impact_rebound", "contact_control"}:
        rebound_velocity = _controlled_rebound_velocity(
            specimen.initial_velocity_m_s,
            material.friction_coefficient,
            material.restitution_coefficient,
            specimen.contact_offset_m,
            dt,
        )
    contact_impulse = mass_kg * rebound_velocity
    primary_name, primary_unit, primary_value = {
        "warp_extension": ("extension_displacement", "m", mean_displacement),
        "weft_extension": ("extension_displacement", "m", mean_displacement),
        "bias_shear": ("shear_angle", "rad", angle),
        "cantilever_bend": ("tip_displacement", "m", maximum_displacement),
        "free_decay": ("oscillation_decay_ratio", "ratio", decay),
        "inclined_friction": ("slide_distance", "m", abs(slide)),
        "impact_rebound": ("rebound_velocity", "m/s", rebound_velocity),
        "contact_control": ("contact_impulse", "N*s", contact_impulse),
    }[specimen_id]
    return {
        "primary": {"name": primary_name, "value": rounded(primary_value), "unit": primary_unit},
        "meanDisplacementMeters": rounded(mean_displacement),
        "maximumDisplacementMeters": rounded(maximum_displacement),
        "appliedForceNewtons": rounded(force_n),
        "shearOrDrapeAngleRadians": rounded(angle),
        "oscillationDecayRatio": rounded(decay),
        "slideDistanceMeters": rounded(abs(slide)),
        "contactImpulseNewtonSeconds": rounded(contact_impulse),
        "reboundHeightMeters": rounded(rebound),
        "reboundVelocityMetersPerSecond": rounded(rebound_velocity),
        "constraintResidualMeters": rounded(float(diagnostics.get("maxConstraintError", 0.0))),
    }


def _motion_metrics(
    initial: MeshSet,
    final: MeshSet,
    trajectory: list[MeshSet],
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    before = [point for mesh in initial.meshes for point in mesh.vertices]
    after = [point for mesh in final.meshes for point in mesh.vertices]
    distances = [_distance(a, b) for a, b in zip(before, after, strict=True)]
    bounds = mesh_bounds(final)
    series = [_centroid(state) for state in trajectory]
    temporal = sum(_distance(a, b) for a, b in zip(series, series[1:], strict=False))
    return {
        "silhouetteWidthMeters": rounded(float(bounds["size"][0])),
        "surfaceLandmarkMeanMeters": rounded(sum(distances) / len(distances)),
        "hemDisplacementMeters": rounded(max(distances)),
        "sleeveDisplacementMeters": rounded(distances[len(distances) // 3]),
        "neckDisplacementMeters": rounded(distances[0]),
        "drapeDepthMeters": rounded(float(bounds["size"][2])),
        "foldScaleMeters": rounded(max(0.0, float(bounds["size"][2]) / 4.0)),
        "temporalPhaseDistanceMeters": rounded(temporal),
        "bodyPenetrationMeters": rounded(
            float(diagnostics.get("maximumBodyPenetrationMeters", 0.0))
        ),
        "selfCollisionResidualMeters": rounded(
            float(diagnostics.get("maxSelfCollisionResidual", 0.0))
        ),
        "p95Strain": rounded(float(diagnostics.get("p95Strain", 0.0))),
        "seamErrorMeters": rounded(float(diagnostics.get("maximumSeamResidualMeters", 0.0))),
    }


def _mesh_positions(meshset: MeshSet) -> list[list[list[float]]]:
    return [
        [[rounded(axis, 9) for axis in point] for point in mesh.vertices] for mesh in meshset.meshes
    ]


def _centroid(meshset: MeshSet) -> tuple[float, float, float]:
    points = [point for mesh in meshset.meshes for point in mesh.vertices]
    return tuple(sum(point[axis] for point in points) / len(points) for axis in range(3))  # type: ignore[return-value]


def _distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return sqrt(sum((left - right) ** 2 for left, right in zip(a, b, strict=True)))


def _controlled_rebound_velocity(
    incident_velocity_m_s: float,
    friction: float,
    restitution: float,
    clearance_m: float,
    time_step_s: float,
) -> float:
    primitive = {
        "type": "ellipsoid",
        "center": [0.0, 0.0, 0.0],
        "radii": [0.20, 0.08, 0.20],
    }
    surface_y = 0.08 + clearance_m
    positions = [(0.0, surface_y - 0.002, 0.0)]
    previous = [(0.0, positions[0][1] + incident_velocity_m_s * time_step_s, 0.0)]
    events = _project_collisions(
        positions,
        previous,
        [primitive],
        clearance_m,
        friction,
        restitution,
        time_step_s,
    )
    if events != 1:
        return 0.0
    return max(0.0, (positions[0][1] - previous[0][1]) / time_step_s)
