from __future__ import annotations

from closy_forge.avatar.reference_avatar import (
    avatar_contract,
    build_collision_mesh,
    build_reference_avatar_mesh,
)
from closy_forge.garments.tshirt.assembly import build_constraints, build_simulation_mesh
from closy_forge.garments.tshirt.parameters import TShirtParameters
from closy_forge.garments.tshirt.pattern_generator import build_tshirt_pattern
from closy_forge.package_io.hashing import topology_hash
from closy_forge.pipeline.build_tshirt_demo import _material_physics
from closy_forge.simulation.reference_cloth_solver import settle_reference_cloth


def test_reference_cloth_solver_settles_without_changing_topology() -> None:
    pattern = build_tshirt_pattern(TShirtParameters())
    rest_mesh, edge_maps = build_simulation_mesh(pattern)
    constraints = build_constraints(pattern, edge_maps)
    avatar = avatar_contract(build_reference_avatar_mesh(), build_collision_mesh())

    result = settle_reference_cloth(rest_mesh, constraints, avatar, _material_physics())

    assert topology_hash(result.rest_mesh) == topology_hash(result.settled_mesh)
    assert result.diagnostics["convergenceState"] == "converged"
    assert result.diagnostics["maximumBodyPenetrationMeters"] < 0.012
    assert result.diagnostics["rmsSeamResidualMeters"] < 0.035
    assert result.diagnostics["selfCollision"]["available"] is True
    assert result.diagnostics["selfCollision"]["reportRef"] == "reports/self_collision_report.json"
    assert result.diagnostics["selfCollision"]["highVelocityTunnelling"] == (
        "unsupported_high_velocity_tunnelling"
    )
