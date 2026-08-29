from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite

BUTTON_SHIRT_PARAMETER_BOUNDS: dict[str, tuple[float, float]] = {
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
    "placket_width_meters": (0.012, 0.05),
    "top_button_clearance_meters": (0.06, 0.20),
    "bottom_button_clearance_meters": (0.05, 0.18),
    "seam_allowance_meters": (0.008, 0.04),
    "target_panel_edge_length_meters": (0.025, 0.075),
}
BUTTON_COUNT_BOUNDS = (4, 9)


@dataclass(frozen=True)
class ButtonShirtParameters:
    body_length_meters: float = 0.68
    half_chest_width_meters: float = 0.29
    body_ease_meters: float = 0.055
    shoulder_width_meters: float = 0.60
    shoulder_slope_meters: float = 0.035
    neckline_width_meters: float = 0.19
    front_neckline_depth_meters: float = 0.085
    back_neckline_depth_meters: float = 0.04
    armhole_depth_meters: float = 0.225
    sleeve_length_meters: float = 0.58
    cuff_width_meters: float = 0.11
    sleeve_cap_height_meters: float = 0.11
    placket_width_meters: float = 0.026
    button_count: int = 6
    top_button_clearance_meters: float = 0.12
    bottom_button_clearance_meters: float = 0.10
    seam_allowance_meters: float = 0.018
    target_panel_edge_length_meters: float = 0.045

    def validate(self) -> None:
        values = asdict(self)
        for field, (minimum, maximum) in BUTTON_SHIRT_PARAMETER_BOUNDS.items():
            value = values[field]
            if not isinstance(value, int | float) or not isfinite(float(value)):
                raise ValueError(f"{field} must be finite")
            if not minimum <= float(value) <= maximum:
                raise ValueError(f"{field}={value} outside safe bounds [{minimum}, {maximum}]")
        if isinstance(self.button_count, bool) or not isinstance(self.button_count, int):
            raise ValueError("button_count must be an integer")
        if not BUTTON_COUNT_BOUNDS[0] <= self.button_count <= BUTTON_COUNT_BOUNDS[1]:
            raise ValueError(
                f"button_count outside safe bounds [{BUTTON_COUNT_BOUNDS[0]}, "
                f"{BUTTON_COUNT_BOUNDS[1]}]"
            )
        torso_half = self.half_chest_width_meters + self.body_ease_meters
        if self.shoulder_width_meters / 2 > torso_half + 0.035:
            raise ValueError("shoulder width exceeds button-shirt torso bounds")
        if self.armhole_depth_meters >= self.body_length_meters * 0.58:
            raise ValueError("armhole depth leaves an invalid side seam")
        if self.cuff_width_meters >= self.armhole_depth_meters * 0.96:
            raise ValueError("cuff width must remain narrower than sleeve cap")
        usable_placket = (
            self.body_length_meters
            - self.front_neckline_depth_meters
            - self.top_button_clearance_meters
            - self.bottom_button_clearance_meters
        )
        if usable_placket <= 0.18 or usable_placket / (self.button_count - 1) < 0.055:
            raise ValueError("button stations do not fit the bounded front placket")

    def to_json(self) -> dict[str, float | int]:
        return asdict(self)
