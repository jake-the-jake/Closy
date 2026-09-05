from __future__ import annotations

import argparse
from pathlib import Path

from closy_forge.manual_provider_binding_v2.evaluation import run_evaluation


def main() -> int:
    forge = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Explicit exposed V2 binding evaluation; never reruns V1."
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--source-root", type=Path, default=forge / "docs/evidence/manual_provider_c3_v1/packages"
    )
    parser.add_argument("--unit-a-root", type=Path, default=forge / ".tmp/family-final-v2/build1")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Continue only with identical source/input/protocol hashes",
    )
    args = parser.parse_args()
    result = run_evaluation(
        args.output,
        source_root=args.source_root,
        unit_a_root=args.unit_a_root,
        forge_root=forge,
        resume=args.resume,
    )
    print(f"result={args.output / 'result.json'} status={result['status']}", flush=True)
    return int(result["status"] != "pass")


if __name__ == "__main__":
    raise SystemExit(main())
