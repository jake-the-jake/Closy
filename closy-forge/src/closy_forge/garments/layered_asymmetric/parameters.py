from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite


@dataclass(frozen=True)
class LayeredAsymmetricParameters:
    body_length_meters: float = 0.64
    half_chest_width_meters: float = 0.285
    body_ease_meters: float = 0.04
    shoulder_width_meters: float = 0.60
    shoulder_slope_meters: float = 0.035
    neckline_width_meters: float = 0.19
    front_neckline_depth_meters: float = 0.105
    back_neckline_depth_meters: float = 0.04
    armhole_depth_meters: float = 0.225
    outer_layer_ease_meters: float = 0.028
    outer_asymmetry_drop_meters: float = 0.09
    layer_clearance_meters: float = 0.014
    hem_allowance_meters: float = 0.025
    target_panel_edge_length_meters: float = 0.045

    def validate(self) -> None:
        bounds = {
            "body_length_meters": (0.48, 0.82),
            "half_chest_width_meters": (0.22, 0.38),
            "body_ease_meters": (0.0, 0.12),
            "shoulder_width_meters": (0.44, 0.72),
            "shoulder_slope_meters": (0.0, 0.08),
            "neckline_width_meters": (0.12, 0.28),
            "front_neckline_depth_meters": (0.04, 0.20),
            "back_neckline_depth_meters": (0.01, 0.10),
            "armhole_depth_meters": (0.15, 0.31),
            "outer_layer_ease_meters": (0.012, 0.06),
            "outer_asymmetry_drop_meters": (0.04, 0.16),
            "layer_clearance_meters": (0.008, 0.03),
            "hem_allowance_meters": (0.01, 0.05),
            "target_panel_edge_length_meters": (0.025, 0.075),
        }
        values = asdict(self)
        for field, (minimum, maximum) in bounds.items():
            value = values[field]
            if not isfinite(value) or not minimum <= value <= maximum:
                raise ValueError(f"{field}={value} outside safe bounds [{minimum}, {maximum}]")
        if self.shoulder_width_meters / 2 > (
            self.half_chest_width_meters + self.body_ease_meters + 0.035
        ):
            raise ValueError("shoulder width exceeds layered_asymmetric torso bounds")
        if self.armhole_depth_meters >= self.body_length_meters * 0.58:
            raise ValueError("armhole depth leaves an invalid side seam")
        if self.outer_layer_ease_meters <= self.layer_clearance_meters:
            raise ValueError("outer layer ease must exceed inter-layer clearance")

    def to_json(self) -> dict[str, float]:
        return asdict(self)
