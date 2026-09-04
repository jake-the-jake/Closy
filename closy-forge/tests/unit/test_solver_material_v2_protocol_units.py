from __future__ import annotations

from collections import Counter

import pytest

from closy_forge.solver_material_v2.protocol import CONTROL_NAMES, build_protocol, validate_protocol
from closy_forge.solver_material_v2.units import (
    FIELD_ORDER,
    SpecimenSI,
    denormalize_fields,
    normalize_material,
    validate_specimen,
)


def test_protocol_freezes_all_required_denominators_and_controls() -> None:
    protocol = build_protocol()
    assert validate_protocol(protocol) == []
    assert Counter(row["partition"] for row in protocol["tuplePlan"]) == {
        "development": 48,
        "locked": 24,
    }
    assert len(CONTROL_NAMES) == 10
    assert protocol["splitPolicy"]["inferenceObservationsPerLockedTuple"] == 6
    assert protocol["splitPolicy"]["withheldPredictionsPerLockedTuple"] == 4
    assert protocol["splitPolicy"]["unseenMotionsPerFamilyPerLockedTuple"] == 8
    assert protocol["singleCanonicalEvaluation"] is True


def test_dimensional_mapping_round_trips_every_field() -> None:
    fields = {field: 0.13 + index * 0.09 for index, field in enumerate(FIELD_ORDER)}
    material = denormalize_fields(fields)
    recovered = normalize_material(material)
    assert recovered == pytest.approx(fields, abs=1e-12)
    assert material.warp_stiffness_n_m > 0.0
    assert material.bend_stiffness_nm > 0.0
    assert material.surface_density_kg_m2 > 0.0


def test_specimen_units_fail_closed() -> None:
    valid = SpecimenSI(0.3, 0.2, 0.001, 3, 3, 1 / 60, 4, 3, 0.2, 0.01, 0.0, 9.81, -9.81, 0.002)
    validate_specimen(valid)
    with pytest.raises(ValueError, match="dimension"):
        validate_specimen(SpecimenSI(**{**valid.__dict__, "width_m": 0.0}))
