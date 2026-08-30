from __future__ import annotations

import argparse
from pathlib import Path

from closy_forge.integrated_runtime.evidence import (
    run_integrated_runtime_evidence,
    validate_integrated_runtime_evidence,
)
from closy_forge.package_io.canonical_json import read_json, write_canonical_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source-sha")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/evidence/integrated_runtime_avatar_outfit_v2.json"),
    )
    parser.add_argument("--validate-committed", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    if args.validate_committed:
        evidence = read_json(output)
        if not isinstance(evidence, dict):
            raise ValueError("integrated_evidence_object_required")
    else:
        if args.source_sha is None:
            parser.error("--source-sha is required unless --validate-committed is used")
        evidence = run_integrated_runtime_evidence(root, source_sha=args.source_sha)
        write_canonical_json(output, evidence)
    issues = validate_integrated_runtime_evidence(evidence)
    if issues:
        raise ValueError(";".join(issues))
    print(
        f"static={evidence['runtimeDecision']['staticSource']} "
        f"motion={evidence['runtimeDecision']['motionSource']} "
        f"contacts={evidence['outfit']['final']['unresolvedContactCount']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
