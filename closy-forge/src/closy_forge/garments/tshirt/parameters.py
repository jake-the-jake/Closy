from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class TShirtParameters:
    garment_body_length: float = 0.68
    half_chest_width: float = 0.285
    body_ease: float = 0.045
    shoulder_width: float = 0.70
    shoulder_slope: float = 0.035
    neckline_width: float = 0.19
    front_neckline_depth: float = 0.085
    back_neckline_depth: float = 0.035
    armhole_depth: float = 0.205
    sleeve_length: float = 0.255
    sleeve_opening_width: float = 0.18
    sleeve_cap_height: float = 0.105
    hem_allowance: float = 0.025
    neckband_width: float = 0.035
    neckband_length_ease_ratio: float = 0.92
    target_panel_edge_length: float = 0.045

    def validate(self) -> None:
        bounds = {
            "garment_body_length": (0.52, 0.82),
            "half_chest_width": (0.22, 0.38),
            "body_ease": (0.0, 0.12),
            "shoulder_width": (0.52, 0.84),
            "neckline_width": (0.12, 0.28),
            "front_neckline_depth": (0.035, 0.16),
            "back_neckline_depth": (0.01, 0.08),
            "armhole_depth": (0.14, 0.30),
            "sleeve_length": (0.14, 0.38),
            "sleeve_opening_width": (0.12, 0.28),
            "sleeve_cap_height": (0.06, 0.17),
            "neckband_width": (0.018, 0.055),
            "neckband_length_ease_ratio": (0.75, 1.05),
            "target_panel_edge_length": (0.025, 0.075),
        }
        values = asdict(self)
        for key, (lo, hi) in bounds.items():
            value = values[key]
            if not lo <= value <= hi:
                raise ValueError(f"{key}={value} outside safe bounds [{lo}, {hi}]")

    def to_json(self) -> dict[str, float]:
        return asdict(self)


PARAMETER_VARIANTS = {
    "default": TShirtParameters(),
    "boxy": TShirtParameters(garment_body_length=0.62, half_chest_width=0.33, sleeve_length=0.22),
    "long_slim": TShirtParameters(
        garment_body_length=0.77, half_chest_width=0.25, sleeve_length=0.30
    ),
}
