from closy_forge.avatar_variation.fit_solver import (
    AvatarFitError,
    AvatarFitReport,
    fit_avatar_patterns,
)
from closy_forge.avatar_variation.measurement_oracle import (
    IndependentMeasurementReport,
    measure_collision_samples,
)
from closy_forge.avatar_variation.synthetic_suite import (
    AVATAR_CAPABILITY_VERSION,
    DECLARED_RANGES,
    FIT_THRESHOLDS,
    AvatarMeasurements,
    SyntheticAvatarCase,
    build_collision_samples,
    build_frozen_avatar_suite,
)

__all__ = [
    "AVATAR_CAPABILITY_VERSION",
    "DECLARED_RANGES",
    "FIT_THRESHOLDS",
    "AvatarFitError",
    "AvatarFitReport",
    "AvatarMeasurements",
    "IndependentMeasurementReport",
    "SyntheticAvatarCase",
    "build_collision_samples",
    "build_frozen_avatar_suite",
    "fit_avatar_patterns",
    "measure_collision_samples",
]
