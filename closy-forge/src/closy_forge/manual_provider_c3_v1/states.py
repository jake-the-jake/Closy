from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MotionState:
    state_id: str
    lateral: float
    depth: float
    twist: float
    vertical: float
    stride: float


MOTION_STATES = (
    MotionState("neutral", 0.000, 0.000, 0.000, 0.000, 0.000),
    MotionState("lean_left", -0.028, 0.006, -0.020, 0.000, 0.000),
    MotionState("lean_right", 0.028, 0.006, 0.020, 0.000, 0.000),
    MotionState("reach_left", -0.018, 0.018, -0.030, 0.006, -0.010),
    MotionState("reach_right", 0.018, 0.018, 0.030, 0.006, 0.010),
    MotionState("twist_left", -0.006, 0.010, -0.055, 0.000, 0.000),
    MotionState("twist_right", 0.006, 0.010, 0.055, 0.000, 0.000),
    MotionState("step_left", -0.006, 0.014, -0.010, -0.008, -0.016),
    MotionState("step_right", 0.006, 0.014, 0.010, -0.008, 0.016),
    MotionState("wind_front", 0.000, 0.032, 0.012, 0.004, 0.000),
    MotionState("settle", 0.000, -0.008, 0.000, -0.012, 0.000),
)

if len(MOTION_STATES) != 11 or len({state.state_id for state in MOTION_STATES}) != 11:
    raise RuntimeError("manual_provider_motion_state_denominator_invalid")
