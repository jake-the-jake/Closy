from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import write_canonical_json
from closy_forge.recovery_foundation_v2.topology_holdout import PUBLIC_DEVELOPMENT_SEED, generate


def run_container_canaries(image: str) -> dict[str, Any]:
    security = _docker_base(image)
    completed = subprocess.run(
        [*security, "--entrypoint", "python", image, "/app/isolation_canary.py"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    try:
        canary = json.loads(completed.stdout.strip())
    except json.JSONDecodeError:
        canary = {"status": "fail", "reason": "unparseable_canary_output"}
    with tempfile.TemporaryDirectory(prefix="closy-strategy3-v3-canary-") as temporary:
        root = Path(temporary)
        inputs = root / "inputs"
        outputs = root / "outputs"
        inputs.mkdir()
        outputs.mkdir()
        outputs.chmod(0o777)
        fixture = generate(PUBLIC_DEVELOPMENT_SEED, qualification_eligible=False)[0]
        contestant_fixture = {
            key: value
            for key, value in fixture.items()
            if key not in {"nonce", "commitment", "qualificationEligible"}
        }
        write_canonical_json(inputs / "fixture.json", contestant_fixture)
        contestant = subprocess.run(
            [
                *security,
                "-v",
                f"{inputs.resolve()}:/inputs:ro",
                "-v",
                f"{outputs.resolve()}:/outputs:rw",
                image,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=45,
        )
        report = outputs / "report.json"
        contestant_pass = contestant.returncode == 0 and report.is_file()
    predicates = {
        "nonRoot": canary.get("nonRoot") is True,
        "networkDenied": canary.get("networkDenied") is True,
        "rootWriteDenied": canary.get("rootWriteDenied") is True,
        "repositoryAbsent": canary.get("repositoryAbsent") is True,
        "oracleAbsent": canary.get("oracleAbsent") is True,
        "seedAbsent": canary.get("seedAbsent") is True,
        "dockerSocketAbsent": canary.get("dockerSocketAbsent") is True,
        "hostHomeAbsent": canary.get("hostHomeAbsent") is True,
        "sensitiveEnvironmentAbsent": canary.get("sensitiveEnvironmentAbsent") is True,
        "contestantPublicCanary": contestant_pass,
    }
    return {
        "isolationVersion": "closy.strategy3.container_isolation.v3",
        "predicates": predicates,
        "allPredicatesPass": all(predicates.values()),
        "canaryReturnCode": completed.returncode,
        "contestantReturnCode": contestant.returncode,
        "sanitizedDiagnostics": {
            "canaryStderrTail": completed.stderr[-500:],
            "contestantStderrTail": contestant.stderr[-500:],
        },
    }


def _docker_base(image: str) -> list[str]:
    return [
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
        "--env",
        "LANG=C.UTF-8",
        "--env",
        "LC_ALL=C.UTF-8",
        "--env",
        "PYTHONHASHSEED=0",
        "--env",
        "PYTHONPATH=/app/src",
    ]
