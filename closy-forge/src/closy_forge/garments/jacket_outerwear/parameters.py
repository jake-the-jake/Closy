from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite

JACKET_OUTERWEAR_PARAMETER_BOUNDS: dict[str, tuple[float, float]] = {
    "body_length_meters": (0.52, 0.86),
    "half_chest_width_meters": (0.22, 0.39),
    "body_ease_meters": (0.015, 0.14),
    "shoulder_width_meters": (0.44, 0.72),
    "shoulder_slope_meters": (0.0, 0.08),
    "neckline_width_meters": (0.12, 0.28),
    "front_neckline_depth_meters": (0.04, 0.18),
    "back_neckline_depth_meters": (0.01, 0.10),
    "armhole_depth_meters": (0.15, 0.31),
    "sleeve_length_meters": (0.42, 0.70),
    "cuff_width_meters": (0.075, 0.17),
    "sleeve_cap_height_meters": (0.07, 0.18),
    "facing_width_meters": (0.03, 0.09),
    "seam_allowance_meters": (0.008, 0.04),
    "target_panel_edge_length_meters": (0.025, 0.075),
}


@dataclass(frozen=True)
class JacketOuterwearParameters:
    body_length_meters: float = 0.72
    half_chest_width_meters: float = 0.30
    body_ease_meters: float = 0.075
    shoulder_width_meters: float = 0.62
    shoulder_slope_meters: float = 0.035
    neckline_width_meters: float = 0.19
    front_neckline_depth_meters: float = 0.095
    back_neckline_depth_meters: float = 0.04
    armhole_depth_meters: float = 0.24
    sleeve_length_meters: float = 0.60
    cuff_width_meters: float = 0.125
    sleeve_cap_height_meters: float = 0.12
    facing_width_meters: float = 0.055
    seam_allowance_meters: float = 0.02
    target_panel_edge_length_meters: float = 0.045

    def validate(self) -> None:
        values = asdict(self)
        for field, (minimum, maximum) in JACKET_OUTERWEAR_PARAMETER_BOUNDS.items():
            value = values[field]
            if not isinstance(value, int | float) or not isfinite(float(value)):
                raise ValueError(f"{field} must be finite")
            if not minimum <= float(value) <= maximum:
                raise ValueError(f"{field}={value} outside safe bounds [{minimum}, {maximum}]")
        torso_half = self.half_chest_width_meters + self.body_ease_meters
        if self.shoulder_width_meters / 2 > torso_half + 0.035:
            raise ValueError("shoulder width exceeds jacket-outerwear torso bounds")
        if self.armhole_depth_meters >= self.body_length_meters * 0.58:
            raise ValueError("armhole depth leaves an invalid side seam")
        if self.cuff_width_meters >= self.armhole_depth_meters * 0.96:
            raise ValueError("cuff width must remain narrower than sleeve cap")
        if self.facing_width_meters >= self.neckline_width_meters * 0.48:
            raise ValueError("facing width must remain inside the bounded neckline")

    def to_json(self) -> dict[str, float]:
        return asdict(self)
