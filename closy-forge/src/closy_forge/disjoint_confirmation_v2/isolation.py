from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from closy_forge.package_io.canonical_json import write_canonical_json
from closy_forge.package_io.hashing import sha256_file

from .protocol import ROUTES

CONTAINER_IMAGE = "python:3.11-slim-bookworm"


def run_container_negative_controls() -> dict[str, Any]:
    if shutil.which("docker") is None:
        return {
            "isolationClass": "application_process_isolation_only",
            "containerAvailable": False,
            "filesystemReadDenied": False,
            "networkDenied": False,
            "environmentDenied": False,
            "repositoryDenied": False,
            "qualifiesD0Rp04": False,
        }
    _ensure_image()
    with TemporaryDirectory(prefix="closy-m2-boundary-") as temporary:
        root = Path(temporary)
        inputs = root / "inputs"
        outputs = root / "outputs"
        inputs.mkdir()
        outputs.mkdir()
        probe = inputs / "probe.py"
        probe.write_text(
            """import json, os, socket
result = {}
paths = (("filesystemReadDenied", "/evaluator/target.json"),
         ("repositoryDenied", "/repo/.git/HEAD"))
for key, path in paths:
    try:
        open(path, "rb").read(1)
        result[key] = False
    except OSError:
        result[key] = True
result["environmentDenied"] = "CLOSY_EVALUATOR_SECRET" not in os.environ
s = socket.socket()
s.settimeout(2)
try:
    s.connect(("1.1.1.1", 53))
    result["networkDenied"] = False
except OSError:
    result["networkDenied"] = True
finally:
    s.close()
open("/outputs/probe.json", "w", encoding="utf-8").write(json.dumps(result, sort_keys=True))
""",
            encoding="utf-8",
        )
        completed = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--pids-limit",
                "64",
                "--memory",
                "256m",
                "--cpus",
                "1",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--mount",
                _mount(inputs, "/inputs", readonly=True),
                "--mount",
                _mount(outputs, "/outputs", readonly=False),
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=16m",
                CONTAINER_IMAGE,
                "python",
                "-I",
                "/inputs/probe.py",
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            env=_docker_client_environment(),
        )
        if completed.returncode != 0:
            raise ValueError(f"confirmation_v2_boundary_probe_failed:{completed.stderr[-400:]}")
        result = json.loads((outputs / "probe.json").read_text(encoding="utf-8"))
        image_id = subprocess.run(
            ["docker", "image", "inspect", CONTAINER_IMAGE, "--format", "{{.Id}}"],
            capture_output=True,
            text=True,
            check=True,
            env=_docker_client_environment(),
        ).stdout.strip()
        controls = {
            "isolationClass": "docker_container_enforced_filesystem_and_network_denial",
            "containerAvailable": True,
            "containerImage": CONTAINER_IMAGE,
            "containerImageId": image_id,
            **result,
        }
        controls["qualifiesD0Rp04"] = all(
            controls[field]
            for field in (
                "filesystemReadDenied",
                "networkDenied",
                "environmentDenied",
                "repositoryDenied",
            )
        )
        return controls


def execute_contestant(
    *,
    executable: Path,
    route: str,
    input_payload: Mapping[str, Any],
    config: Mapping[str, Any],
    require_container: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if route not in ROUTES:
        raise ValueError(f"confirmation_v2_unknown_route:{route}")
    if require_container:
        return _execute_container(
            executable=executable,
            route=route,
            input_payload=input_payload,
            config=config,
        )
    return _execute_process(
        executable=executable,
        route=route,
        input_payload=input_payload,
        config=config,
    )


def _execute_container(
    *, executable: Path, route: str, input_payload: Mapping[str, Any], config: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    if shutil.which("docker") is None:
        raise ValueError("confirmation_v2_required_container_unavailable")
    _ensure_image()
    with TemporaryDirectory(prefix=f"closy-m2-{route}-") as temporary:
        root = Path(temporary)
        inputs = root / "inputs"
        outputs = root / "outputs"
        inputs.mkdir()
        outputs.mkdir()
        copied = inputs / "contender.py"
        shutil.copyfile(executable, copied)
        write_canonical_json(inputs / "source.json", dict(input_payload))
        write_canonical_json(inputs / "config.json", dict(config))
        write_canonical_json(
            inputs / "permissions.json",
            {
                "schemaVersion": 1,
                "allowedRoutes": [route],
                "allowedReadPaths": ["source.json", "config.json", "permissions.json"],
                "allowedWritePaths": ["prediction.json", "open_audit.json"],
                "targetRolesAllowed": [],
                "networkAllowed": False,
            },
        )
        inventory = _inventory(inputs)
        command = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--pids-limit",
            "64",
            "--memory",
            "256m",
            "--cpus",
            "1",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--mount",
            _mount(inputs, "/inputs", readonly=True),
            "--mount",
            _mount(outputs, "/outputs", readonly=False),
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=16m",
            CONTAINER_IMAGE,
            "python",
            "-I",
            "/inputs/contender.py",
            "--route",
            _legacy_route(route),
            "--input",
            "/inputs/source.json",
            "--config",
            "/inputs/config.json",
            "--permissions",
            "/inputs/permissions.json",
            "--output",
            "/outputs/prediction.json",
            "--audit",
            "/outputs/open_audit.json",
        ]
        # The legacy standalone contender validates its own route spelling.
        permissions = json.loads((inputs / "permissions.json").read_text(encoding="utf-8"))
        permissions["allowedRoutes"] = [_legacy_route(route)]
        write_canonical_json(inputs / "permissions.json", permissions)
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            env=_docker_client_environment(),
        )
        if completed.returncode != 0:
            raise ValueError(
                f"confirmation_v2_contestant_container_failed:{route}:{completed.returncode}:"
                f"{completed.stderr[-400:]}"
            )
        prediction = _mapping(json.loads((outputs / "prediction.json").read_text(encoding="utf-8")))
        prediction["routeId"] = route
        audit = _mapping(json.loads((outputs / "open_audit.json").read_text(encoding="utf-8")))
        return prediction, {
            "schemaVersion": 1,
            "routeId": route,
            "isolationClass": "docker_container_enforced_filesystem_and_network_denial",
            "operatingSystemSandboxClaimed": True,
            "containerNetworkMode": "none",
            "containerRootReadOnly": True,
            "capabilitiesDropped": "ALL",
            "noNewPrivileges": True,
            "repositoryMounted": False,
            "evaluatorTargetsMounted": False,
            "targetHashesMounted": False,
            "rawTranscriptMounted": False,
            "environmentInherited": False,
            "inputInventory": inventory,
            "openedPathCount": len(audit.get("events", [])),
            "allOpenedPathsAllowed": audit.get("allAccessAllowed") is True,
            "outputHash": sha256_file(outputs / "prediction.json"),
            "workspaceDestroyedAfterReturn": True,
        }


def _execute_process(
    *, executable: Path, route: str, input_payload: Mapping[str, Any], config: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    from closy_forge.disjoint_benchmark_v1.isolation import execute_isolated_contender

    prediction, report = execute_isolated_contender(
        executable=executable,
        route=_legacy_route(route),
        input_payload=input_payload,
        config=config,
    )
    prediction["routeId"] = route
    return prediction, {
        **report,
        "routeId": route,
        "isolationClass": "application_process_isolation_only",
        "qualifiesD0Rp04": False,
    }


def _ensure_image() -> None:
    inspected = subprocess.run(
        ["docker", "image", "inspect", CONTAINER_IMAGE],
        capture_output=True,
        check=False,
        env=_docker_client_environment(),
    )
    if inspected.returncode == 0:
        return
    pulled = subprocess.run(
        ["docker", "pull", CONTAINER_IMAGE],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env=_docker_client_environment(),
    )
    if pulled.returncode != 0:
        raise ValueError(f"confirmation_v2_container_image_pull_failed:{pulled.stderr[-400:]}")


def _legacy_route(route: str) -> str:
    return "metadata_category_prior" if route == "metadata_only_control" else route


def _mount(path: Path, destination: str, *, readonly: bool) -> str:
    value = f"type=bind,src={path.resolve()},dst={destination}"
    return f"{value},readonly" if readonly else value


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


def _docker_client_environment() -> dict[str, str]:
    allowed = ("PATH", "SYSTEMROOT", "WINDIR", "DOCKER_HOST", "DOCKER_CONTEXT", "HOME")
    return {key: os.environ[key] for key in allowed if key in os.environ}


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("confirmation_v2_mapping_required")
    return dict(value)
