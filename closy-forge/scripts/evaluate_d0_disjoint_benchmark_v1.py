from __future__ import annotations

from pathlib import Path

from closy_forge.disjoint_benchmark_v1.evaluator import reveal_and_evaluate

ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    reveal_and_evaluate(ROOT)
