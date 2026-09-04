from __future__ import annotations

import ast
from pathlib import Path

from closy_forge.solver_material_v2.contestant import _run_controls, audit_contestant_source
from closy_forge.solver_material_v2.estimator import estimate_material
from closy_forge.solver_material_v2.specimens import default_specimen, run_specimen
from closy_forge.solver_material_v2.units import FIELD_ORDER, denormalize_fields


def _observations() -> list[dict[str, object]]:
    material = denormalize_fields({field: 0.5 for field in FIELD_ORDER})
    specimens = (
        "warp_extension",
        "weft_extension",
        "bias_shear",
        "cantilever_bend",
        "free_decay",
        "contact_control",
    )
    rows = []
    for index, specimen_id in enumerate(specimens):
        specimen = default_specimen(
            specimen_id,
            load_scale=0.9,
            mesh=(3, 3),
            time_step_s=1 / 60,
            step_count=3,
            solver_iterations=2,
        )
        executed = run_specimen(
            specimen_id,
            material,
            specimen,
            tuple_id="test-estimator",
            observation_id=f"observation-{index}",
            canonical_digits=8,
        )
        rows.append(
            {
                "observationId": executed["observationId"],
                "specimenId": specimen_id,
                "solverVersion": executed["solverVersion"],
                "unitSystem": "SI",
                "observables": {
                    key: value for key, value in executed["observables"].items() if key != "primary"
                },
            }
        )
    return rows


def test_estimator_has_no_truth_generator_or_seed_import() -> None:
    source = Path(__file__).resolve().parents[2] / "src/closy_forge/solver_material_v2/estimator.py"
    assert audit_contestant_source(source) == []
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imports = {str(node.module) for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert not imports & {"corpus", "evaluation", "safe_private_io"}


def test_estimator_exposes_intervals_rank_profiles_and_robustness() -> None:
    result = estimate_material(_observations())  # type: ignore[arg-type]
    assert set(result["estimatedFields"]) == set(FIELD_ORDER)
    assert set(result["intervals"]) == set(FIELD_ORDER)
    assert all(0.0 < high - low < 1.0 for low, high in result["intervals"].values())
    assert len(result["singularValues"]) == len(FIELD_ORDER)
    assert result["objectiveProfiles"]
    assert result["robustness"]["missingObservationPolicy"] == "abstain_affected_fields"


def test_all_ten_controls_execute_or_reject_as_frozen() -> None:
    controls = _run_controls(_observations())  # type: ignore[arg-type]
    assert len(controls) == 10
    assert sum(row["status"] == "rejected" for row in controls) == 5
