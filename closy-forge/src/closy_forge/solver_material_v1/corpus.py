from __future__ import annotations

from typing import Any

from closy_forge.solver_material_v1.common import digest, rounded
from closy_forge.solver_material_v1.forward_solver import (
    COUPON_FAMILIES,
    SUPPORTED_FIELDS,
    ForwardConfig,
    run_forward_coupon,
)
from closy_forge.solver_material_v1.protocol import load_protocol

CORPUS_VERSION = "closy.solver_material.synthetic_coupon_corpus.v1"
_PRIMES = (2, 3, 5, 7, 11, 13, 17, 19)
_FIELD_COUPONS = {
    "warp": "warp_tensile",
    "weft": "weft_tensile",
    "shear": "bias_shear",
    "bend": "cantilever_bend",
    "density": "gravity_sag",
    "damping": "free_decay",
    "friction": "inclined_contact",
    "restitution": "vertical_drop",
}


def build_locked_corpus() -> dict[str, Any]:
    protocol = load_protocol()
    rows: list[dict[str, Any]] = []
    development_loads = [float(value) for value in protocol["loadCases"]["development"]]
    held_out_loads = [float(value) for value in protocol["loadCases"]["heldOut"]]
    for index in range(64):
        partition = "development" if index < 48 else "locked_test"
        fields = _fields_for_index(index)
        available_loads = development_loads if partition == "development" else held_out_loads
        coupons = [
            run_forward_coupon(fields, family, available_loads[index % len(available_loads)])
            for family in COUPON_FAMILIES
        ]
        rows.append(
            {
                "tupleId": f"solver-material-{index:03d}",
                "partition": partition,
                "wholeMaterialHoldout": 48 <= index < 56,
                "fields": fields,
                "coupons": coupons,
                "failures": [],
            }
        )
    interventions = []
    baseline = {field: 0.5 for field in SUPPORTED_FIELDS}
    for field in SUPPORTED_FIELDS:
        family = _FIELD_COUPONS[field]
        runs = []
        for level in (0.2, 0.5, 0.8):
            fields = dict(baseline)
            fields[field] = level
            runs.append(run_forward_coupon(fields, family, 0.55))
        interventions.append(
            {
                "field": field,
                "family": family,
                "levels": [0.2, 0.5, 0.8],
                "trajectoryDigests": [run["trajectoryDigest"] for run in runs],
                "observables": [run["observable"] for run in runs],
                "trajectoryResponds": len({run["trajectoryDigest"] for run in runs}) == 3,
            }
        )
    convergence = []
    alternate = ForwardConfig(
        node_count=7, time_step_seconds=1.0 / 180.0, step_count=180, iterations=6
    )
    for index in range(8):
        fields = _fields_for_index(index)
        family = COUPON_FAMILIES[index]
        primary = run_forward_coupon(fields, family, 0.55)
        comparison = run_forward_coupon(fields, family, 0.55, config=alternate)
        denominator = max(abs(float(primary["observable"])), 1e-9)
        convergence.append(
            {
                "tupleId": f"solver-material-{index:03d}",
                "family": family,
                "configurationCount": 2,
                "relativeObservableDifference": rounded(
                    abs(float(primary["observable"]) - float(comparison["observable"]))
                    / denominator
                ),
                "trajectoryDigestsDistinct": primary["trajectoryDigest"]
                != comparison["trajectoryDigest"],
            }
        )
    corpus: dict[str, Any] = {
        "schemaVersion": 1,
        "corpusVersion": CORPUS_VERSION,
        "protocolDigest": protocol["protocolDigest"],
        "sourceKind": "project_authored_solver_executed_synthetic_coupons",
        "truthClaim": "same_backend_correlated_solver_space_only",
        "tupleCount": len(rows),
        "developmentTupleCount": 48,
        "lockedTestTupleCount": 16,
        "wholeMaterialHoldoutCount": 8,
        "heldOutLoadCaseCount": len(held_out_loads),
        "supportedFieldCount": len(SUPPORTED_FIELDS),
        "executedCouponFamilyCount": len(COUPON_FAMILIES),
        "unsupported": [
            {
                "family": "compression_thickness",
                "status": "not_run",
                "reason": protocol["unsupportedModes"]["compression_thickness"],
            }
        ],
        "rows": rows,
        "interventions": interventions,
        "convergence": convergence,
        "failureAccounting": {name: 0 for name in protocol["failureAccounting"]},
    }
    corpus["corpusDigest"] = digest(corpus)
    return corpus


def _fields_for_index(index: int) -> dict[str, float]:
    return {
        field: rounded(0.12 + 0.76 * _radical_inverse(index + 1, _PRIMES[offset]))
        for offset, field in enumerate(SUPPORTED_FIELDS)
    }


def _radical_inverse(index: int, base: int) -> float:
    result = 0.0
    factor = 1.0 / base
    value = index
    while value:
        result += (value % base) * factor
        value //= base
        factor /= base
    return result
