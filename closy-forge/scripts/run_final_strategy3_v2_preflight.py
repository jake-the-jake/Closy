from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from closy_forge.package_io.canonical_json import write_canonical_json
from closy_forge.recovery_foundation_v2.topology_holdout import (
    PUBLIC_DEVELOPMENT_SEED,
    generate,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="closy-strategy3-preflight-") as temporary:
        root = Path(temporary)
        inputs, outputs = root / "inputs", root / "outputs"
        inputs.mkdir()
        outputs.mkdir()
        outputs.chmod(0o777)
        write_canonical_json(
            inputs / "fixture.json",
            generate(PUBLIC_DEVELOPMENT_SEED, qualification_eligible=False)[0],
        )
        command = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--memory",
            "768m",
            "--cpus",
            "2",
            "--pids-limit",
            "128",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            "-v",
            f"{inputs.resolve()}:/inputs:ro",
            "-v",
            f"{outputs.resolve()}:/outputs:rw",
            args.image,
        ]
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=45)
        report = outputs / "report.json"
        passed = completed.returncode == 0 and report.is_file()
        payload = {
            "status": "pass" if passed else "fail",
            "containerReturnCode": completed.returncode,
            "reportPresent": report.is_file(),
            "contestantInputFiles": [path.name for path in inputs.iterdir()],
            "privateOracleMounted": False,
            "stderr": completed.stderr[-1000:],
        }
        print(json.dumps(payload, sort_keys=True))
        shutil.rmtree(outputs, ignore_errors=True)
        return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
