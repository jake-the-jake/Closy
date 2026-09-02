from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from closy_forge.package_io.canonical_json import write_canonical_json
from closy_forge.recovery_foundation_v2.container_boundary import (
    IMAGE_REFERENCE,
    build_docker_run_command,
    cap_diagnostic,
    collect_outputs,
    validate_command,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--route", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--image", default=IMAGE_REFERENCE)
    parser.add_argument("--destroy-workspace", action="store_true")
    args = parser.parse_args()
    command = build_docker_run_command(
        args.input,
        args.output,
        route_id=args.route,
        image_reference=args.image,
    )
    issues = validate_command(command, expected_image_reference=args.image)
    if issues:
        raise ValueError(";".join(issues))
    result = subprocess.run(command, capture_output=True, timeout=60, check=False)
    outputs = collect_outputs(args.output) if result.returncode == 0 else []
    host_readback = []
    for record in outputs:
        path = args.output / str(record["path"])
        if path.suffix == ".json":
            host_readback.append(json.loads(path.read_text(encoding="utf-8")))
    report = {
        "schemaVersion": 1,
        "preflightVersion": "closy.d0_v3.container_preflight.v1",
        "routeId": args.route,
        "imageReference": args.image,
        "returnCode": result.returncode,
        "stdout": cap_diagnostic(result.stdout),
        "stderr": cap_diagnostic(result.stderr),
        "outputs": outputs,
        "hostReadback": host_readback,
        "pass": result.returncode == 0 and bool(outputs),
    }
    write_canonical_json(args.report, report)
    if args.destroy_workspace:
        shutil.rmtree(args.input, ignore_errors=True)
        shutil.rmtree(args.output, ignore_errors=True)
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
