from __future__ import annotations

from pathlib import Path

from closy_forge.core_runtime_c3_v4.candidate_deformation import deform_simulation_representation
from closy_forge.core_runtime_c3_v4.oracle import deform_dense_shell_directly
from closy_forge.core_runtime_c3_v4.protocol import HELD_OUT_STATES, build_protocol_lock
from closy_forge.core_runtime_c3_v4.sentinel import build_sentinel
from closy_forge.geometry.glb_io import read_glb_meshset
from closy_forge.package_io.canonical_json import read_json

ROOT = Path(__file__).resolve().parents[2]


def test_h0_resolves_only_the_precommitted_unit_f_sentinel() -> None:
    sentinel = build_sentinel(ROOT)
    assert sentinel["resolutionOutcome"] == "unit_f_exact_fixture_candidate"
    assert sentinel["unitGCohortEligible"] is False
    assert sentinel["pr43DescendantProof"]["allRetainedGeometryPhysicsByteIdentical"] is True
    assert len(sentinel["integrity"]["sentinelManifestDigest"]) == 64


def test_h4_lock_freezes_one_strategy_one_attempt_and_required_coverage() -> None:
    lock = build_protocol_lock(ROOT, build_sentinel(ROOT))
    assert lock == read_json(ROOT / "fixtures/d0_core_runtime_c3_v4/protocol_lock.json")
    assert lock["state"] == "frozen_before_held_out_pose_mount"
    assert lock["bindingStrategyCount"] == 1
    assert lock["maximumHeldOutBindingAttempts"] == 1
    assert len(lock["heldOutStates"]) == 8
    assert max(state["leftArmLiftDegrees"] for state in HELD_OUT_STATES) >= 45
    assert max(state["torsoBendDegrees"] for state in HELD_OUT_STATES) >= 15
    assert max(state["torsoTwistDegrees"] for state in HELD_OUT_STATES) >= 20
    assert max(state["materialStretchU"] for state in HELD_OUT_STATES) >= 1.05


def test_candidate_and_oracle_are_separate_and_nonrigid() -> None:
    package = ROOT / "docs/evidence/d0_texture_rerender_correction_v3/predictions/candidate_package"
    sim = read_glb_meshset(package / "simulation/settled_mesh.glb")
    dense = read_glb_meshset(package / "render/render_mesh.glb")
    state = HELD_OUT_STATES[-1]
    candidate = deform_simulation_representation(sim, state)
    oracle = deform_dense_shell_directly(dense, state)
    assert candidate.vertex_count == sim.vertex_count
    assert oracle.vertex_count == dense.vertex_count
    assert candidate.meshes[0].vertices != sim.meshes[0].vertices
    assert oracle.meshes[0].vertices != dense.meshes[0].vertices
