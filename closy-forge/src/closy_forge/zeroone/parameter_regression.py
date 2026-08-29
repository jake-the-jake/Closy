from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Literal, TypeVar, cast

from closy_forge.garments.button_shirt.parameters import (
    BUTTON_COUNT_BOUNDS,
    BUTTON_SHIRT_PARAMETER_BOUNDS,
    ButtonShirtParameters,
)
from closy_forge.garments.jacket_outerwear.parameters import (
    JACKET_OUTERWEAR_PARAMETER_BOUNDS,
    JacketOuterwearParameters,
)
from closy_forge.garments.long_sleeved_top.parameters import (
    LONG_SLEEVED_PARAMETER_BOUNDS,
    LongSleevedTopParameters,
)

AffectedFamily = Literal["long_sleeved_top", "button_shirt", "jacket_outerwear"]
ParameterObject = LongSleevedTopParameters | ButtonShirtParameters | JacketOuterwearParameters
ParameterType = TypeVar(
    "ParameterType", LongSleevedTopParameters, ButtonShirtParameters, JacketOuterwearParameters
)


@dataclass(frozen=True)
class ParameterRegressionCase:
    case_id: str
    classification: str
    parameters: ParameterObject
    covered_boundaries: tuple[str, ...]
    prior_collapse_replay: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "caseId": self.case_id,
            "classification": self.classification,
            "parameters": asdict(self.parameters),
            "coveredBoundaries": list(self.covered_boundaries),
            "priorCollapseReplay": self.prior_collapse_replay,
        }


def parameter_regression_cases(family: AffectedFamily) -> list[ParameterRegressionCase]:
    if family == "long_sleeved_top":
        cases = _long_sleeved_cases()
    elif family == "button_shirt":
        cases = _button_shirt_cases()
    else:
        cases = _jacket_cases()
    for case in cases:
        case.parameters.validate()
    return cases


def declared_parameter_bounds(family: AffectedFamily) -> dict[str, list[float | int]]:
    if family == "long_sleeved_top":
        return {key: [value[0], value[1]] for key, value in LONG_SLEEVED_PARAMETER_BOUNDS.items()}
    if family == "button_shirt":
        return {
            **{key: [value[0], value[1]] for key, value in BUTTON_SHIRT_PARAMETER_BOUNDS.items()},
            "button_count": [BUTTON_COUNT_BOUNDS[0], BUTTON_COUNT_BOUNDS[1]],
        }
    return {key: [value[0], value[1]] for key, value in JACKET_OUTERWEAR_PARAMETER_BOUNDS.items()}


def _long_sleeved_cases() -> list[ParameterRegressionCase]:
    default = LongSleevedTopParameters()
    minimum = _replace_bounds(default, LONG_SLEEVED_PARAMETER_BOUNDS, 0)
    maximum = _replace_bounds(default, LONG_SLEEVED_PARAMETER_BOUNDS, 1)
    return [
        _case("default", "default", default),
        _case(
            "declared_minimums",
            "declared_minimums",
            minimum,
            *_all_bounds("min", LONG_SLEEVED_PARAMETER_BOUNDS),
        ),
        _case(
            "declared_maximums",
            "declared_maximums",
            maximum,
            *_all_bounds("max", LONG_SLEEVED_PARAMETER_BOUNDS),
        ),
        _case(
            "pair_body_min_chest_max",
            "pairwise_boundary",
            replace(default, body_length_meters=0.50, half_chest_width_meters=0.39),
            "body_length_meters:min",
            "half_chest_width_meters:max",
        ),
        _case(
            "pair_shoulder_max_ease_max",
            "pairwise_boundary",
            replace(default, shoulder_width_meters=0.72, body_ease_meters=0.13),
            "shoulder_width_meters:max",
            "body_ease_meters:max",
        ),
        _case(
            "pair_sleeve_min_cuff_min",
            "pairwise_boundary",
            replace(default, sleeve_length_meters=0.42, cuff_width_meters=0.075),
            "sleeve_length_meters:min",
            "cuff_width_meters:min",
        ),
        _case(
            "pair_sleeve_max_cuff_max",
            "pairwise_boundary",
            replace(default, sleeve_length_meters=0.68, cuff_width_meters=0.16),
            "sleeve_length_meters:max",
            "cuff_width_meters:max",
        ),
        _case("prior_default_collapse", "prior_collapse_replay", default, prior=True),
    ]


def _button_shirt_cases() -> list[ParameterRegressionCase]:
    default = ButtonShirtParameters()
    minimum = replace(
        _replace_bounds(default, BUTTON_SHIRT_PARAMETER_BOUNDS, 0),
        button_count=BUTTON_COUNT_BOUNDS[0],
    )
    # Continuous maxima and maximum button count cannot coexist under the declared
    # spacing relation. Each boundary is still exercised by a valid explicit case.
    maximum_continuous = replace(
        _replace_bounds(default, BUTTON_SHIRT_PARAMETER_BOUNDS, 1),
        button_count=BUTTON_COUNT_BOUNDS[0],
    )
    return [
        _case("default", "default", default),
        _case(
            "declared_minimums",
            "declared_minimums",
            minimum,
            *_all_bounds("min", BUTTON_SHIRT_PARAMETER_BOUNDS),
            "button_count:min",
        ),
        _case(
            "declared_continuous_maximums",
            "declared_maximums_coupled_domain",
            maximum_continuous,
            *_all_bounds("max", BUTTON_SHIRT_PARAMETER_BOUNDS),
            "button_count:min",
        ),
        _case(
            "button_count_maximum",
            "declared_integer_maximum",
            replace(
                default,
                body_length_meters=0.86,
                button_count=BUTTON_COUNT_BOUNDS[1],
                top_button_clearance_meters=0.06,
                bottom_button_clearance_meters=0.05,
            ),
            "button_count:max",
        ),
        _case(
            "pair_body_min_chest_max",
            "pairwise_boundary",
            replace(
                default,
                body_length_meters=0.52,
                half_chest_width_meters=0.39,
                front_neckline_depth_meters=0.04,
                button_count=BUTTON_COUNT_BOUNDS[0],
                top_button_clearance_meters=0.06,
                bottom_button_clearance_meters=0.05,
            ),
            "body_length_meters:min",
            "half_chest_width_meters:max",
        ),
        _case(
            "pair_shoulder_max_ease_max",
            "pairwise_boundary",
            replace(default, shoulder_width_meters=0.72, body_ease_meters=0.14),
            "shoulder_width_meters:max",
            "body_ease_meters:max",
        ),
        _case(
            "pair_sleeve_min_cuff_min",
            "pairwise_boundary",
            replace(default, sleeve_length_meters=0.42, cuff_width_meters=0.075),
            "sleeve_length_meters:min",
            "cuff_width_meters:min",
        ),
        _case(
            "pair_sleeve_max_cuff_max",
            "pairwise_boundary",
            replace(default, sleeve_length_meters=0.70, cuff_width_meters=0.17),
            "sleeve_length_meters:max",
            "cuff_width_meters:max",
        ),
        _case("prior_default_collapse", "prior_collapse_replay", default, prior=True),
    ]


def _jacket_cases() -> list[ParameterRegressionCase]:
    default = JacketOuterwearParameters()
    minimum = _replace_bounds(default, JACKET_OUTERWEAR_PARAMETER_BOUNDS, 0)
    maximum = _replace_bounds(default, JACKET_OUTERWEAR_PARAMETER_BOUNDS, 1)
    return [
        _case("default", "default", default),
        _case(
            "declared_minimums",
            "declared_minimums",
            minimum,
            *_all_bounds("min", JACKET_OUTERWEAR_PARAMETER_BOUNDS),
        ),
        _case(
            "declared_maximums",
            "declared_maximums",
            maximum,
            *_all_bounds("max", JACKET_OUTERWEAR_PARAMETER_BOUNDS),
        ),
        _case(
            "pair_body_min_chest_max",
            "pairwise_boundary",
            replace(default, body_length_meters=0.52, half_chest_width_meters=0.39),
            "body_length_meters:min",
            "half_chest_width_meters:max",
        ),
        _case(
            "pair_shoulder_max_ease_max",
            "pairwise_boundary",
            replace(default, shoulder_width_meters=0.72, body_ease_meters=0.14),
            "shoulder_width_meters:max",
            "body_ease_meters:max",
        ),
        _case(
            "pair_sleeve_min_cuff_min",
            "pairwise_boundary",
            replace(default, sleeve_length_meters=0.42, cuff_width_meters=0.075),
            "sleeve_length_meters:min",
            "cuff_width_meters:min",
        ),
        _case(
            "pair_sleeve_max_cuff_max",
            "pairwise_boundary",
            replace(default, sleeve_length_meters=0.70, cuff_width_meters=0.17),
            "sleeve_length_meters:max",
            "cuff_width_meters:max",
        ),
        _case("prior_default_collapse", "prior_collapse_replay", default, prior=True),
    ]


def _replace_bounds(
    value: ParameterType, bounds: dict[str, tuple[float, float]], index: int
) -> ParameterType:
    replaced = replace(
        cast(Any, value), **{field: limits[index] for field, limits in bounds.items()}
    )
    return cast(ParameterType, replaced)


def _all_bounds(side: str, bounds: dict[str, tuple[float, float]]) -> tuple[str, ...]:
    return tuple(f"{field}:{side}" for field in bounds)


def _case(
    case_id: str,
    classification: str,
    parameters: ParameterObject,
    *covered: str,
    prior: bool = False,
) -> ParameterRegressionCase:
    return ParameterRegressionCase(case_id, classification, parameters, tuple(covered), prior)
