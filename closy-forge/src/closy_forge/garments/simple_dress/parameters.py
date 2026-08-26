from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite


@dataclass(frozen=True)
class SimpleDressParameters:
    bodice_length_meters: float = 0.48
    skirt_length_meters: float = 0.62
    half_chest_width_meters: float = 0.285
    half_waist_width_meters: float = 0.205
    half_hip_width_meters: float = 0.255
    body_ease_meters: float = 0.035
    waist_ease_meters: float = 0.018
    hip_ease_meters: float = 0.025
    skirt_flare_meters: float = 0.075
    shoulder_width_meters: float = 0.58
    shoulder_slope_meters: float = 0.035
    neckline_width_meters: float = 0.19
    front_neckline_depth_meters: float = 0.105
    back_neckline_depth_meters: float = 0.04
    armhole_depth_meters: float = 0.215
    seam_allowance_meters: float = 0.018
    target_panel_edge_length_meters: float = 0.05

    def validate(self) -> None:
        bounds = {
            "bodice_length_meters": (0.40, 0.58),
            "skirt_length_meters": (0.42, 0.88),
            "half_chest_width_meters": (0.22, 0.38),
            "half_waist_width_meters": (0.15, 0.30),
            "half_hip_width_meters": (0.19, 0.36),
            "body_ease_meters": (0.0, 0.10),
            "waist_ease_meters": (0.0, 0.08),
            "hip_ease_meters": (0.0, 0.10),
            "skirt_flare_meters": (0.0, 0.22),
            "shoulder_width_meters": (0.44, 0.70),
            "shoulder_slope_meters": (0.0, 0.08),
            "neckline_width_meters": (0.12, 0.28),
            "front_neckline_depth_meters": (0.04, 0.20),
            "back_neckline_depth_meters": (0.01, 0.10),
            "armhole_depth_meters": (0.15, 0.30),
            "seam_allowance_meters": (0.008, 0.04),
            "target_panel_edge_length_meters": (0.03, 0.08),
        }
        values = asdict(self)
        for field, (minimum, maximum) in bounds.items():
            value = values[field]
            if not isfinite(value) or not minimum <= value <= maximum:
                raise ValueError(f"{field}={value} outside safe bounds [{minimum}, {maximum}]")
        chest = self.half_chest_width_meters + self.body_ease_meters
        waist = self.half_waist_width_meters + self.waist_ease_meters
        hip = self.half_hip_width_meters + self.hip_ease_meters
        if not waist < chest or not waist < hip:
            raise ValueError("simple dress waist must be narrower than chest and hip")
        if self.shoulder_width_meters / 2 > chest + 0.035:
            raise ValueError("shoulder width exceeds dress bodice bounds")
        if self.armhole_depth_meters >= self.bodice_length_meters * 0.58:
            raise ValueError("armhole depth leaves an invalid bodice side seam")

    def to_json(self) -> dict[str, float]:
        return asdict(self)
