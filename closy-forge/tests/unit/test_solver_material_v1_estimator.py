from __future__ import annotations

import ast
from pathlib import Path

from closy_forge.solver_material_v1.common import read_json
from closy_forge.solver_material_v1.estimator import FIELD_ORDER, estimate_solver_fields
from closy_forge.solver_material_v1.estimator_inputs import strip_truth_for_estimator
from closy_forge.solver_material_v1.production_solver import PRODUCTION_SOLVER_VERSION

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "fixtures/solver_material_v1/locked_corpus.json"


def test_estimator_has_no_forward_or_corpus_import() -> None:
    source = (ROOT / "src/closy_forge/solver_material_v1/estimator.py").read_text(encoding="utf-8")
    imports = {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "closy_forge.solver_material_v1.forward_solver" not in imports
    assert "closy_forge.solver_material_v1.corpus" not in imports


def test_coupled_estimator_reports_rank_and_abstentions() -> None:
    row = read_json(CORPUS)["rows"][48]
    observations = strip_truth_for_estimator(row)
    result = estimate_solver_fields(
        observations,
        {field: [0.0, 1.0] for field in FIELD_ORDER},
        PRODUCTION_SOLVER_VERSION,
    )
    assert len(result["optimizationTrace"]) == 24
    assert result["jacobianRank"] >= 6
    assert result["abstainedFields"] == ["friction", "restitution"]
    assert result["identifiability"] == "partial"
