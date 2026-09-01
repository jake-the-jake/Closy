from __future__ import annotations

import argparse
import json
from pathlib import Path

from closy_forge.appearance_correction_v3.prediction import generate_source_only_prediction


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol-commit-sha", required=True)
    parser.add_argument("--implementation-anchor-sha", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = generate_source_only_prediction(
        root,
        protocol_commit_sha=args.protocol_commit_sha,
        implementation_anchor_sha=args.implementation_anchor_sha,
        output=args.output,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
