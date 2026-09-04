from __future__ import annotations

from math import isfinite
from typing import Any

from closy_forge.solver_material_v1.common import digest, rounded
from closy_forge.solver_material_v1.forward_solver import COUPON_FAMILIES, SUPPORTED_FIELDS

PRODUCTION_SOLVER_VERSION = "closy.coupon_xpbd_production_reference.low_resolution.v1"


def run_production_coupon(fields: dict[str, float], family: str, load: float) -> dict[str, Any]:
    """Execute the lower-resolution production mapping through separately coded update loops."""

    if family not in COUPON_FAMILIES:
        raise ValueError("coupon_family_unsupported")
    if set(fields) != set(SUPPORTED_FIELDS):
        raise ValueError("solver_field_set_invalid")
    count, steps, iterations, dt = 6, 120, 5, 1.0 / 120.0
    state = [0.0] * count
    previous = [0.0] * count
    snapshots: list[list[float]] = []
    contacts = 0
    for step in range(steps):
        old = list(state)
        force = _forcing(family, load, step, steps)
        mass = 0.38 + 1.62 * fields["density"]
        decay = 0.965 - 0.22 * fields["damping"]
        for index in range(1, count):
            velocity = (state[index] - previous[index]) / dt
            weight = index / (count - 1)
            state[index] += velocity * dt * decay + force * weight * dt * dt / mass
        previous = old
        gain = _gain(fields, family)
        for _ in range(iterations):
            for index in range(1, count):
                target = state[index - 1] + _offset(fields, family, load, index, count)
                state[index] += gain * (target - state[index]) / iterations
            state[0] = 0.0
        if family in {"inclined_contact", "contact_control"}:
            cap = max(0.0, load - 0.77 * fields["friction"])
            for index in range(1, count):
                bounded = min(state[index], cap * index / (count - 1))
                contacts += int(bounded != state[index])
                state[index] = bounded
        if family == "vertical_drop" and state[-1] < -0.20:
            state[-1] = -0.20 + fields["restitution"] * abs(state[-1] + 0.20)
            contacts += 1
        if step % 10 == 0 or step == steps - 1:
            snapshots.append([rounded(value) for value in state])
    observable = _metric(family, snapshots, contacts)
    payload: dict[str, Any] = {
        "solverVersion": PRODUCTION_SOLVER_VERSION,
        "family": family,
        "load": rounded(load),
        "sampledStates": snapshots,
        "observable": rounded(observable),
        "diagnostics": {
            "finite": all(isfinite(value) for row in snapshots for value in row),
            "contactEventCount": contacts,
            "nodeCount": count,
            "stepCount": steps,
            "timeStepSeconds": rounded(dt),
            "iterations": iterations,
        },
    }
    payload["trajectoryDigest"] = digest(payload)
    return payload


def _forcing(family: str, load: float, step: int, steps: int) -> float:
    ramp = min(1.0, (step + 1) / max(1, steps // 4))
    if family == "free_decay":
        return load if step == 0 else 0.0
    if family in {"gravity_sag", "cantilever_bend", "vertical_drop"}:
        return -load * ramp
    return load * ramp


def _gain(fields: dict[str, float], family: str) -> float:
    selectors = {
        "warp_tensile": fields["warp"],
        "weft_tensile": fields["weft"],
        "bias_shear": fields["shear"],
        "cantilever_bend": fields["bend"],
        "paired_warp_shear": 0.52 * fields["warp"] + 0.48 * fields["shear"],
    }
    return 0.07 + 0.68 * selectors.get(family, 0.5 * (fields["warp"] + fields["weft"]))


def _offset(fields: dict[str, float], family: str, load: float, index: int, count: int) -> float:
    phase = index / (count - 1)
    if family == "cantilever_bend":
        return -0.0042 * load * (1.02 - fields["bend"]) * phase
    if family == "gravity_sag":
        return -0.0038 * load * (0.28 + fields["density"]) * phase
    return 0.0


def _metric(family: str, states: list[list[float]], contacts: int) -> float:
    if family == "free_decay":
        return sum(abs(row[-1]) for row in states[-4:]) / 4.0
    if family in {"inclined_contact", "contact_control"}:
        return abs(states[-1][-1]) + contacts * 1e-5
    if family == "vertical_drop":
        return max(row[-1] for row in states) - min(row[-1] for row in states)
    return abs(states[-1][-1])
