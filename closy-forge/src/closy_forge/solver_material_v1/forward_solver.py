from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from closy_forge.solver_material_v1.common import digest, rounded

FORWARD_SOLVER_VERSION = "closy.coupon_xpbd_forward.high_resolution.v1"


@dataclass(frozen=True)
class ForwardConfig:
    node_count: int = 9
    time_step_seconds: float = 1.0 / 240.0
    step_count: int = 240
    iterations: int = 8


SUPPORTED_FIELDS = (
    "warp",
    "weft",
    "shear",
    "bend",
    "density",
    "damping",
    "friction",
    "restitution",
)

COUPON_FAMILIES = (
    "warp_tensile",
    "weft_tensile",
    "bias_shear",
    "cantilever_bend",
    "gravity_sag",
    "free_decay",
    "inclined_contact",
    "vertical_drop",
    "paired_warp_shear",
    "contact_control",
)


def run_forward_coupon(
    fields: dict[str, float],
    family: str,
    load: float,
    *,
    config: ForwardConfig | None = None,
) -> dict[str, Any]:
    """Execute a bounded one-dimensional strip discretization and persist sampled states.

    The state is integrated, not evaluated from a closed-form response. Parameters are normalized
    solver-space controls because the repository XPBD formulation mixes normalized constraint
    gains with nominal SI-labelled descriptor fields.
    """

    active = config or ForwardConfig()
    if family not in COUPON_FAMILIES:
        raise ValueError("coupon_family_unsupported")
    _validate_fields(fields)
    q = [0.0 for _ in range(active.node_count)]
    v = [0.0 for _ in range(active.node_count)]
    rest = 1.0 / (active.node_count - 1)
    sampled: list[list[float]] = []
    energy: list[float] = []
    contact_events = 0
    dt = active.time_step_seconds
    for step in range(active.step_count):
        external = _load_vector(family, load, step, active.step_count, active.node_count)
        damping = 0.02 + 0.42 * fields["damping"]
        inv_mass = 1.0 / (0.35 + 1.65 * fields["density"])
        for index in range(1, active.node_count):
            v[index] = (v[index] + external[index] * inv_mass * dt) * (1.0 - damping * dt)
            q[index] += v[index] * dt
        for _ in range(active.iterations):
            stiffness = _constraint_gain(fields, family)
            for index in range(1, active.node_count):
                neighbour = q[index - 1]
                target_delta = _rest_offset(family, fields, load, index, rest)
                correction = (neighbour + target_delta - q[index]) * stiffness
                q[index] += correction / active.iterations
            q[0] = 0.0
        if family in {"inclined_contact", "contact_control"}:
            limit = max(0.0, load - fields["friction"] * 0.8)
            for index in range(1, active.node_count):
                before = q[index]
                q[index] = min(q[index], limit * (index / (active.node_count - 1)))
                contact_events += int(before != q[index])
        if family == "vertical_drop" and q[-1] < -0.22:
            q[-1] = -0.22
            v[-1] = abs(v[-1]) * fields["restitution"]
            contact_events += 1
        if step % max(1, active.step_count // 12) == 0 or step == active.step_count - 1:
            sampled.append([rounded(value) for value in q])
        energy.append(sum(value * value for value in v) + sum(value * value for value in q))
    finite = all(isfinite(value) for state in sampled for value in state)
    observable = _observable(family, sampled, energy, contact_events)
    payload: dict[str, Any] = {
        "solverVersion": FORWARD_SOLVER_VERSION,
        "family": family,
        "load": rounded(load),
        "config": {
            "nodeCount": active.node_count,
            "timeStepSeconds": rounded(active.time_step_seconds),
            "stepCount": active.step_count,
            "iterations": active.iterations,
        },
        "sampledStates": sampled,
        "observable": rounded(observable),
        "diagnostics": {
            "finite": finite,
            "contactEventCount": contact_events,
            "initialEnergy": rounded(energy[0]),
            "finalEnergy": rounded(energy[-1]),
            "trajectoryChanged": any(abs(value) > 1e-12 for state in sampled for value in state),
        },
    }
    payload["trajectoryDigest"] = digest(payload)
    return payload


def _validate_fields(fields: dict[str, float]) -> None:
    if set(fields) != set(SUPPORTED_FIELDS):
        raise ValueError("solver_field_set_invalid")
    if not all(isfinite(value) and 0.0 <= value <= 1.0 for value in fields.values()):
        raise ValueError("solver_field_value_invalid")


def _constraint_gain(fields: dict[str, float], family: str) -> float:
    if family == "warp_tensile":
        return 0.08 + 0.72 * fields["warp"]
    if family == "weft_tensile":
        return 0.08 + 0.72 * fields["weft"]
    if family == "bias_shear":
        return 0.06 + 0.64 * fields["shear"]
    if family == "cantilever_bend":
        return 0.04 + 0.58 * fields["bend"]
    if family == "paired_warp_shear":
        return 0.05 + 0.34 * fields["warp"] + 0.31 * fields["shear"]
    return 0.10 + 0.18 * fields["warp"] + 0.14 * fields["weft"]


def _rest_offset(
    family: str, fields: dict[str, float], load: float, index: int, rest: float
) -> float:
    phase = index * rest
    if family == "cantilever_bend":
        return -load * (1.05 - fields["bend"]) * phase * 0.004
    if family == "gravity_sag":
        return -load * (0.25 + fields["density"]) * phase * 0.004
    return 0.0


def _load_vector(family: str, load: float, step: int, steps: int, count: int) -> list[float]:
    ramp = min(1.0, (step + 1) / max(1, steps // 3))
    values = [0.0 for _ in range(count)]
    sign = -1.0 if family in {"gravity_sag", "cantilever_bend", "vertical_drop"} else 1.0
    if family == "free_decay":
        values[-1] = load if step == 0 else 0.0
    else:
        values[-1] = sign * load * ramp
    if family in {"bias_shear", "paired_warp_shear"}:
        values[count // 2] = load * 0.35 * ramp
    return values


def _observable(
    family: str, states: list[list[float]], energy: list[float], contact_events: int
) -> float:
    if family == "free_decay":
        tail = states[-4:]
        return sum(abs(state[-1]) for state in tail) / len(tail)
    if family in {"inclined_contact", "contact_control"}:
        return abs(states[-1][-1]) + contact_events * 1e-5
    if family == "vertical_drop":
        return max(state[-1] for state in states) - min(state[-1] for state in states)
    return abs(states[-1][-1]) + abs(energy[-1] - energy[0]) * 1e-4
