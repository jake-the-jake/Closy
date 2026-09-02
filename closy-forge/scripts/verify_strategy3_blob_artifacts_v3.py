from __future__ import annotations

import argparse
import json
from pathlib import Path

from closy_forge.strategy3_blob_authority_v3.common import load_json, write_json
from closy_forge.strategy3_blob_authority_v3.preflight import compare_portability_reports


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = sorted(args.input_root.rglob("blob-portability-report.json"))
    reports = [load_json(path) for path in paths]
    aggregation = compare_portability_reports(reports)
    write_json(args.output, aggregation)
    print(json.dumps(aggregation, sort_keys=True))
    return 0 if aggregation["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
