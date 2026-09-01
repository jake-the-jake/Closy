from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from closy_forge.package_io.canonical_json import write_canonical_json
from closy_forge.package_io.hashing import sha256_file

from .contender_cli import ROUTES


def execute_isolated_contender(
    *,
    executable: Path,
    route: str,
    input_payload: Mapping[str, Any],
    config: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if route not in ROUTES:
        raise ValueError(f"d0_disjoint_unknown_route:{route}")
    with TemporaryDirectory(prefix=f"closy-g-{route}-") as temporary:
        workspace = Path(temporary)
        closure = workspace / "closure"
        closure.mkdir()
        copied_executable = closure / "contender.py"
        shutil.copyfile(executable, copied_executable)
        input_path = closure / "source.json"
        config_path = closure / "config.json"
        permission_path = closure / "permissions.json"
        output_path = closure / "prediction.json"
        audit_path = closure / "open_audit.json"
        write_canonical_json(input_path, dict(input_payload))
        write_canonical_json(config_path, dict(config))
        write_canonical_json(
            permission_path,
            {
                "schemaVersion": 1,
                "allowedRoutes": [route],
                "allowedReadPaths": ["source.json", "config.json", "permissions.json"],
                "allowedWritePaths": ["prediction.json", "open_audit.json"],
                "targetRolesAllowed": [],
                "networkAllowed": False,
            },
        )
        inventory_before = _inventory(closure)
        command = [
            sys.executable,
            "-I",
            str(copied_executable),
            "--route",
            route,
            "--input",
            str(input_path),
            "--config",
            str(config_path),
            "--permissions",
            str(permission_path),
            "--output",
            str(output_path),
            "--audit",
            str(audit_path),
        ]
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "NO_PROXY": "*",
            "HTTP_PROXY": "",
            "HTTPS_PROXY": "",
        }
        completed = subprocess.run(
            command,
            cwd=closure,
            env=environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        prediction = json.loads(output_path.read_text(encoding="utf-8"))
        open_audit = json.loads(audit_path.read_text(encoding="utf-8"))
        if completed.returncode != 0 or not open_audit["allAccessAllowed"]:
            raise ValueError(f"d0_disjoint_contender_failed:{route}:{completed.returncode}")
        output_identity = sha256_file(output_path)
        input_path.unlink()
        withdrawn = subprocess.run(
            command,
            cwd=closure,
            env=environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        report = {
            "schemaVersion": 1,
            "routeId": route,
            "workspaceFresh": True,
            "workspaceOutsideRepository": True,
            "isolationClass": "application_process_input_isolation",
            "operatingSystemSandboxClaimed": False,
            "repositoryRootMounted": False,
            "gitMounted": False,
            "evaluatorTargetsMounted": False,
            "targetParametersMounted": False,
            "thirdViewsMounted": False,
            "priorResultsMounted": False,
            "networkAllowed": False,
            "inputInventory": inventory_before,
            "openedPaths": _canonical_open_events(open_audit["events"], closure),
            "allOpenedPathsAllowed": open_audit["allAccessAllowed"],
            "outputIdentity": output_identity,
            "sourceRegistryWithdrawn": True,
            "withdrawalExecutionFailedClosed": withdrawn.returncode != 0,
            "withdrawalExitCode": withdrawn.returncode,
        }
        return prediction, report


def _inventory(root: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": sha256_file(path),
            "byteLength": path.stat().st_size,
        }
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def _canonical_open_events(events: list[dict[str, Any]], closure: Path) -> list[dict[str, Any]]:
    canonical: list[dict[str, Any]] = []
    for event in events:
        path = Path(str(event["path"]))
        try:
            relative = path.relative_to(closure).as_posix()
        except ValueError:
            relative = "outside_declared_closure"
        canonical.append({**event, "path": relative})
    return canonical
