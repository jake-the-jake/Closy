from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite

LONG_SLEEVED_PARAMETER_BOUNDS: dict[str, tuple[float, float]] = {
    "body_length_meters": (0.50, 0.84),
    "half_chest_width_meters": (0.22, 0.39),
    "body_ease_meters": (0.0, 0.13),
    "shoulder_width_meters": (0.44, 0.72),
    "shoulder_slope_meters": (0.0, 0.08),
    "neckline_width_meters": (0.12, 0.28),
    "front_neckline_depth_meters": (0.04, 0.20),
    "back_neckline_depth_meters": (0.01, 0.10),
    "armhole_depth_meters": (0.15, 0.31),
    "sleeve_length_meters": (0.42, 0.68),
    "cuff_width_meters": (0.075, 0.16),
    "sleeve_cap_height_meters": (0.07, 0.18),
    "hem_allowance_meters": (0.01, 0.05),
    "target_panel_edge_length_meters": (0.025, 0.075),
}


@dataclass(frozen=True)
class LongSleevedTopParameters:
    body_length_meters: float = 0.66
    half_chest_width_meters: float = 0.29
    body_ease_meters: float = 0.045
    shoulder_width_meters: float = 0.60
    shoulder_slope_meters: float = 0.035
    neckline_width_meters: float = 0.19
    front_neckline_depth_meters: float = 0.10
    back_neckline_depth_meters: float = 0.04
    armhole_depth_meters: float = 0.225
    sleeve_length_meters: float = 0.56
    cuff_width_meters: float = 0.105
    sleeve_cap_height_meters: float = 0.11
    hem_allowance_meters: float = 0.025
    target_panel_edge_length_meters: float = 0.045

    def validate(self) -> None:
        values = asdict(self)
        for field, (minimum, maximum) in LONG_SLEEVED_PARAMETER_BOUNDS.items():
            value = values[field]
            if not isfinite(value) or not minimum <= value <= maximum:
                raise ValueError(f"{field}={value} outside safe bounds [{minimum}, {maximum}]")
        torso_half = self.half_chest_width_meters + self.body_ease_meters
        if self.shoulder_width_meters / 2 > torso_half + 0.035:
            raise ValueError("shoulder width exceeds long-sleeved torso bounds")
        if self.armhole_depth_meters >= self.body_length_meters * 0.58:
            raise ValueError("armhole depth leaves an invalid side seam")
        if self.cuff_width_meters >= self.armhole_depth_meters * 0.96:
            raise ValueError("cuff width must remain narrower than sleeve cap")

    def to_json(self) -> dict[str, float]:
        return asdict(self)
