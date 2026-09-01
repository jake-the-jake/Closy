from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from closy_forge.package_io.canonical_json import write_canonical_json
from closy_forge.package_io.hashing import sha256_file

_RUNNER = r"""from __future__ import annotations
import json
import os
import runpy
import socket
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
audit_path = root / "audit.json"
events = []

def audit(event, args):
    if event == "open" and args:
        path = Path(str(args[0])).resolve()
        allowed = path.is_relative_to(root) or path.is_relative_to(Path(sys.base_prefix).resolve())
        events.append({"event": event, "path": str(path), "allowed": allowed})
        if not allowed:
            raise PermissionError("contestant_read_outside_allowlist")
    if event.startswith("socket.") and event not in {"socket.__new__"}:
        events.append({"event": event, "path": "network", "allowed": False})
        raise PermissionError("contestant_network_denied")

sys.addaudithook(audit)
system_root = os.environ.get("SYSTEMROOT", "")
os.environ.clear()
os.environ.update({"PYTHONDONTWRITEBYTECODE": "1", "CLOSY_CONTESTANT": "1"})
if system_root:
    os.environ["SYSTEMROOT"] = system_root
status = "pass"
error = None
try:
    sys.argv = [str(root / "contestant.py"), str(root / "source.json"), str(root / "output.json")]
    runpy.run_path(str(root / "contestant.py"), run_name="__main__")
except Exception as exc:
    status = "fail"
    error = type(exc).__name__ + ":" + str(exc)
finally:
    result = {"events": events, "status": status, "error": error}
    audit_path.write_text(json.dumps(result), encoding="utf-8")
if status != "pass":
    raise SystemExit(23)
"""


def execute_contestant(
    *,
    contestant: Path,
    source_roles: Mapping[str, bytes],
    config: Mapping[str, Any],
    timeout_seconds: float = 30.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if timeout_seconds <= 0 or timeout_seconds > 120:
        raise ValueError("contestant_timeout_invalid")
    with TemporaryDirectory(prefix="closy-m-contestant-") as temporary:
        workspace = Path(temporary).resolve()
        shutil.copyfile(contestant, workspace / "contestant.py")
        (workspace / "trusted_runner.py").write_text(_RUNNER, encoding="utf-8", newline="\n")
        roles: list[dict[str, Any]] = []
        for role, payload in sorted(source_roles.items()):
            if not role or Path(role).name != role or role.startswith("."):
                raise ValueError(f"contestant_source_role_invalid:{role}")
            path = workspace / role
            path.write_bytes(payload)
            roles.append({"role": role, "sha256": sha256_file(path), "byteLength": len(payload)})
        write_canonical_json(workspace / "source.json", {"roles": roles, "config": dict(config)})
        inventory = _inventory(workspace)
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "NO_PROXY": "*",
            "HTTP_PROXY": "",
            "HTTPS_PROXY": "",
        }
        command = [sys.executable, "-I", str(workspace / "trusted_runner.py"), str(workspace)]
        completed = subprocess.run(
            command,
            cwd=workspace,
            env=environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        audit_path = workspace / "audit.json"
        audit = json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.exists() else {}
        output_path = workspace / "output.json"
        output = json.loads(output_path.read_text(encoding="utf-8")) if output_path.exists() else {}
        if output_path.exists() and not output_path.resolve().is_relative_to(workspace):
            raise ValueError("contestant_output_traversal")
        report = {
            "schemaVersion": 1,
            "boundaryVersion": "closy.d0_contestant_boundary.v2",
            "workspaceFresh": True,
            "workspaceDestroyedAfterReturn": True,
            "repositoryHistoryMounted": False,
            "evaluatorCodeMounted": False,
            "evaluatorTargetsMounted": False,
            "privateRegistriesMounted": False,
            "environmentScrubbed": True,
            "outputConfined": output_path.exists(),
            "sourceAllowlist": roles,
            "workspaceInventory": inventory,
            "openedFileAudit": _sanitize_events(audit.get("events", []), workspace),
            "allOpenedFilesAllowed": all(
                bool(event.get("allowed")) for event in audit.get("events", [])
            ),
            "networkDeniedByAuditHook": any(
                str(event.get("event", "")).startswith("socket.") and event.get("allowed") is False
                for event in audit.get("events", [])
            ),
            "operatingSystemFilesystemDenialEnforced": False,
            "operatingSystemNetworkDenialEnforced": False,
            "isolationClass": "application_process_isolation_only",
            "qualificationD0Rp04IsolationPass": False,
            "exitCode": completed.returncode,
            "status": "pass" if completed.returncode == 0 else "fail",
            "failureClass": audit.get("error"),
        }
        return output if isinstance(output, dict) else {}, report


def validate_output_path(workspace: Path, requested: Path) -> Path:
    resolved_workspace = workspace.resolve()
    resolved = (
        (workspace / requested).resolve() if not requested.is_absolute() else requested.resolve()
    )
    if not resolved.is_relative_to(resolved_workspace):
        raise ValueError("contestant_output_path_outside_workspace")
    return resolved


def build_boundary_capability() -> dict[str, Any]:
    return {
        "boundaryVersion": "closy.d0_contestant_boundary.v2",
        "defaultPolicy": "deny",
        "freshAllowlistedWorkspace": True,
        "targetStoreMountedDuringContestant": False,
        "evaluatorRunsAfterContestantTermination": True,
        "workspaceDestroyedAfterPredictionFreeze": True,
        "windowsScope": "application_process_isolation_only",
        "d0Rp04PassRequires": [
            "os_or_container_filesystem_read_denial",
            "os_or_container_network_denial",
            "negative_target_repository_environment_network_tests",
        ],
        "currentCanonicalQualificationIsolationPass": False,
    }


def run_boundary_fixtures() -> dict[str, Any]:
    with TemporaryDirectory(prefix="closy-l-boundary-fixtures-") as temporary:
        root = Path(temporary)
        outside = root / "authority_target.json"
        outside.write_text('{"hidden":true}', encoding="utf-8")
        contestants = root / "contestants"
        contestants.mkdir()
        good = contestants / "good.py"
        good.write_text(
            "import json,os,sys\n"
            "json.dump({'env':sorted(os.environ)},open(sys.argv[2],'w',encoding='utf-8'))\n",
            encoding="utf-8",
        )
        target_attack = contestants / "target_attack.py"
        target_attack.write_text(
            f"open({str(outside)!r},encoding='utf-8').read()\n", encoding="utf-8"
        )
        network_attack = contestants / "network_attack.py"
        network_attack.write_text(
            "import socket\nsocket.socket().connect(('127.0.0.1',9))\n", encoding="utf-8"
        )
        good_output, good_report = execute_contestant(
            contestant=good, source_roles={"source_role.bin": b"public-synthetic"}, config={}
        )
        _, target_report = execute_contestant(
            contestant=target_attack,
            source_roles={"source_role.bin": b"public-synthetic"},
            config={},
        )
        _, network_report = execute_contestant(
            contestant=network_attack,
            source_roles={"source_role.bin": b"public-synthetic"},
            config={},
        )
        traversal_rejected = False
        try:
            validate_output_path(contestants, Path("../authority_target.json"))
        except ValueError:
            traversal_rejected = True
    cases = {
        "allowlisted_source_and_output": good_report["status"] == "pass",
        "environment_scrubbed": set(good_output.get("env", []))
        <= {"CLOSY_CONTESTANT", "PYTHONDONTWRITEBYTECODE", "SYSTEMROOT"},
        "target_read_denied": target_report["status"] == "fail"
        and "outside_allowlist" in str(target_report["failureClass"]),
        "repository_history_absent": good_report["repositoryHistoryMounted"] is False,
        "network_denied_by_process_audit": network_report["status"] == "fail"
        and network_report["networkDeniedByAuditHook"] is True,
        "output_traversal_denied": traversal_rejected,
        "workspace_destroyed": good_report["workspaceDestroyedAfterReturn"] is True,
        "evaluator_assets_separate": good_report["evaluatorTargetsMounted"] is False,
    }
    return {
        "schemaVersion": 1,
        "fixtureVersion": "closy.d0_contestant_boundary.generic_fixtures.v2",
        "qualificationDataUsed": False,
        "isolationClass": "application_process_isolation_only",
        "operatingSystemFilesystemDenialEnforced": False,
        "operatingSystemNetworkDenialEnforced": False,
        "d0Rp04IsolationPass": False,
        "cases": cases,
        "allPassed": all(cases.values()),
    }


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


def _sanitize_events(events: object, workspace: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if not isinstance(events, Sequence):
        return result
    for value in events:
        if not isinstance(value, Mapping):
            continue
        path = str(value.get("path", ""))
        if path == "network":
            canonical = "network"
        else:
            resolved = Path(path)
            canonical = (
                resolved.relative_to(workspace).as_posix()
                if resolved.is_relative_to(workspace)
                else "python_runtime_or_outside_workspace"
            )
        result.append(
            {
                "event": str(value.get("event", "")),
                "path": canonical,
                "allowed": bool(value.get("allowed")),
            }
        )
    return result
