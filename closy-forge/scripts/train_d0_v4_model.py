from __future__ import annotations

import argparse
from pathlib import Path

from closy_forge.d0_v4_engineering.corpus import load_partition
from closy_forge.d0_v4_engineering.model import MODEL_ROOT, train_structured_model
from closy_forge.package_io.canonical_json import write_canonical_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trial-id", required=True)
    parser.add_argument("--seed", required=True, type=int)
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    model = train_structured_model(
        load_partition(root, "train"),
        load_partition(root, "validation"),
        trial_id=arguments.trial_id,
        seed=arguments.seed,
    )
    output = root / MODEL_ROOT / f"{arguments.trial_id}.json"
    write_canonical_json(output, model)
    print(model["integrity"]["modelSha256"])
    print(model["validationMetrics"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
