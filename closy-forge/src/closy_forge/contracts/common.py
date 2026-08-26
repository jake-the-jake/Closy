from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CoordinateConventionId = Literal["closy-rh-yup-plus-z-v1"]
GarmentClass = Literal["tshirt", "sleeveless_top"]

COORDINATE_CONVENTION: dict[str, object] = {
    "id": "closy-rh-yup-plus-z-v1",
    "units": "metres",
    "handedness": "right-handed",
    "upAxis": "+Y",
    "forwardAxis": "+Z",
    "triangleWinding": "counter-clockwise-front-face",
    "groundPlane": "Y=0",
    "referenceAvatarRoot": "midpoint_between_grounded_feet_at_x0_z0",
    "neutralFixturePose": "T-pose",
}

FIXED_TIMESTAMP = "2026-01-01T00:00:00Z"
DEFAULT_SEED = 101


@dataclass(frozen=True)
class ArtifactRef:
    path: str
    sha256: str
    media_type: str
    byte_size: int
    role: str
    canonical: bool
    required: bool
