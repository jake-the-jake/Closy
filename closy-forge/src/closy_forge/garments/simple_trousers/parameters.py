from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite


@dataclass(frozen=True)
class SimpleTrousersParameters:
    outseam_length_meters: float = 0.98
    half_waist_width_meters: float = 0.195
    half_hip_width_meters: float = 0.245
    waist_ease_meters: float = 0.018
    hip_ease_meters: float = 0.025
    rise_depth_meters: float = 0.29
    front_rise_extension_meters: float = 0.075
    back_rise_extension_meters: float = 0.105
    leg_gap_half_width_meters: float = 0.035
    leg_cuff_width_meters: float = 0.145
    seam_allowance_meters: float = 0.018
    target_panel_edge_length_meters: float = 0.055

    def validate(self) -> None:
        bounds = {
            "outseam_length_meters": (0.78, 1.12),
            "half_waist_width_meters": (0.15, 0.29),
            "half_hip_width_meters": (0.19, 0.35),
            "waist_ease_meters": (0.0, 0.08),
            "hip_ease_meters": (0.0, 0.10),
            "rise_depth_meters": (0.20, 0.40),
            "front_rise_extension_meters": (0.04, 0.13),
            "back_rise_extension_meters": (0.06, 0.16),
            "leg_gap_half_width_meters": (0.02, 0.07),
            "leg_cuff_width_meters": (0.09, 0.22),
            "seam_allowance_meters": (0.008, 0.04),
            "target_panel_edge_length_meters": (0.035, 0.085),
        }
        values = asdict(self)
        for field, (minimum, maximum) in bounds.items():
            value = values[field]
            if not isfinite(value) or not minimum <= value <= maximum:
                raise ValueError(f"{field}={value} outside safe bounds [{minimum}, {maximum}]")
        waist = self.half_waist_width_meters + self.waist_ease_meters
        hip = self.half_hip_width_meters + self.hip_ease_meters
        if waist >= hip:
            raise ValueError("simple trousers hip width must exceed waist width")
        if self.rise_depth_meters >= self.outseam_length_meters * 0.48:
            raise ValueError("rise depth leaves an invalid trouser leg")
        if self.front_rise_extension_meters >= hip * 0.65:
            raise ValueError("front rise extension is too wide for the hip")
        if self.back_rise_extension_meters <= self.front_rise_extension_meters:
            raise ValueError("back rise extension must exceed front rise extension")

    def to_json(self) -> dict[str, float]:
        return asdict(self)
