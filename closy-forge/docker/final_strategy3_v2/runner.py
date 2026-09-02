from __future__ import annotations

import json
from pathlib import Path

from closy_forge.final_strategy3_v2.evaluator import evaluate_fixture
from closy_forge.package_io.canonical_json import canonical_dumps


def main() -> None:
    fixture_path = Path("/inputs/fixture.json")
    input_files = sorted(path.name for path in fixture_path.parent.iterdir())
    if input_files != ["fixture.json"]:
        raise RuntimeError(f"contestant_input_boundary_invalid:{input_files}")
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    report = evaluate_fixture(fixture)
    output = Path("/outputs/report.json")
    output.write_text(canonical_dumps(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
