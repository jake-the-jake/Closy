from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite


@dataclass(frozen=True)
class SimpleSkirtParameters:
    length_meters: float = 0.56
    half_waist_width_meters: float = 0.205
    half_hip_width_meters: float = 0.255
    waist_ease_meters: float = 0.018
    hip_ease_meters: float = 0.025
    flare_meters: float = 0.065
    waist_to_hip_meters: float = 0.19
    seam_allowance_meters: float = 0.018
    target_panel_edge_length_meters: float = 0.045

    def validate(self) -> None:
        bounds = {
            "length_meters": (0.36, 0.86),
            "half_waist_width_meters": (0.15, 0.30),
            "half_hip_width_meters": (0.19, 0.36),
            "waist_ease_meters": (0.0, 0.08),
            "hip_ease_meters": (0.0, 0.10),
            "flare_meters": (0.0, 0.22),
            "waist_to_hip_meters": (0.12, 0.28),
            "seam_allowance_meters": (0.008, 0.04),
            "target_panel_edge_length_meters": (0.025, 0.075),
        }
        values = asdict(self)
        for field, (minimum, maximum) in bounds.items():
            value = values[field]
            if not isfinite(value) or not minimum <= value <= maximum:
                raise ValueError(f"{field}={value} outside safe bounds [{minimum}, {maximum}]")
        waist = self.half_waist_width_meters + self.waist_ease_meters
        hip = self.half_hip_width_meters + self.hip_ease_meters
        if waist >= hip:
            raise ValueError("simple skirt hip width must exceed waist width")
        if self.waist_to_hip_meters >= self.length_meters * 0.72:
            raise ValueError("waist-to-hip depth leaves an invalid lower skirt panel")

    def to_json(self) -> dict[str, float]:
        return asdict(self)
