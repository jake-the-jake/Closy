from __future__ import annotations

from pathlib import Path

from closy_forge.disjoint_benchmark_v1.evaluator import freeze_evaluator_predictions

ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    freeze_evaluator_predictions(ROOT)
