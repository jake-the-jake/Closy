from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from closy_forge.package_io.canonical_json import read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_file
from closy_forge.recovery_foundation_v2.container_boundary import (
    ALLOWED_ENVIRONMENT,
    CONTAINER_GID,
    CONTAINER_UID,
    build_docker_run_command,
    collect_outputs,
    validate_command,
)

from .protocol import ROUTES


def run_canary(*, image_reference: str) -> dict[str, Any]:
    with TemporaryDirectory(prefix="closy-unit-t-canary-") as temporary:
        root = Path(temporary)
        inputs = root / "inputs"
        outputs = root / "outputs"
        inputs.mkdir()
        outputs.mkdir()
        (inputs / "canary.bin").write_bytes(b"closy-unit-t-exact-lock-canary-v1")
        _prepare_mounts(inputs, outputs)
        command = build_docker_run_command(
            inputs,
            outputs,
            route_id="generic_canary",
            image_reference=image_reference,
        )
        issues = validate_command(command, expected_image_reference=image_reference)
        if issues:
            raise ValueError(";".join(issues))
        started = time.perf_counter_ns()
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=60,
            check=False,
            env=_docker_environment(),
        )
        elapsed = time.perf_counter_ns() - started
        records = collect_outputs(outputs)
        probe = _mapping(read_json(outputs / "probe.json")) if records else {}
        security = _mapping(probe.get("security"))
        return {
            "schemaVersion": 1,
            "imageReference": image_reference,
            "returnCode": completed.returncode,
            "elapsedNanoseconds": elapsed,
            "outputs": records,
            "security": security,
            "uid": probe.get("uid"),
            "gid": probe.get("gid"),
            "inputReadable": probe.get("inputSha256") is not None,
            "outputHostReadable": bool(records),
            "environmentAllowlist": sorted(ALLOWED_ENVIRONMENT),
            "workspaceDestroyedAfterReturn": True,
            "pass": completed.returncode == 0
            and bool(records)
            and probe.get("uid") == CONTAINER_UID
            and probe.get("gid") == CONTAINER_GID
            and all(security.values()),
        }


def execute_route(
    *,
    image_reference: str,
    route_id: str,
    category: str,
    source_paths: Mapping[str, Path],
    model_path: Path | None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if route_id not in ROUTES:
        raise ValueError(f"d0_v3_route_unknown:{route_id}")
    with TemporaryDirectory(prefix=f"closy-unit-t-{route_id}-") as temporary:
        root = Path(temporary)
        inputs = root / "inputs"
        outputs = root / "outputs"
        inputs.mkdir()
        outputs.mkdir()
        write_canonical_json(inputs / "category.json", {"category": category})
        mounted_roles = ["tshirt_category"]
        for role, source in sorted(source_paths.items()):
            if role not in {"front_png", "rear_png"}:
                raise ValueError(f"d0_v3_source_role_forbidden:{role}")
            destination = inputs / ("front.png" if role == "front_png" else "rear.png")
            shutil.copyfile(source, destination)
            mounted_roles.append(role)
        if model_path is not None:
            shutil.copyfile(model_path, inputs / "model.json")
            mounted_roles.append("fitted_model")
        _prepare_mounts(inputs, outputs)
        command = build_docker_run_command(
            inputs,
            outputs,
            route_id=route_id,
            image_reference=image_reference,
        )
        issues = validate_command(command, expected_image_reference=image_reference)
        if issues:
            raise ValueError(";".join(issues))
        started = time.perf_counter_ns()
        try:
            completed = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=30,
                check=False,
                env=_docker_environment(),
            )
            timed_out = False
        except subprocess.TimeoutExpired:
            completed = None
            timed_out = True
        elapsed = time.perf_counter_ns() - started
        output_records = collect_outputs(outputs) if completed and completed.returncode == 0 else []
        prediction_path = outputs / "prediction.json"
        lineage_path = outputs / "lineage.json"
        prediction = (
            _mapping(read_json(prediction_path))
            if prediction_path.is_file() and lineage_path.is_file()
            else None
        )
        lineage = _mapping(read_json(lineage_path)) if lineage_path.is_file() else {}
        success = (
            completed is not None
            and completed.returncode == 0
            and prediction is not None
            and lineage.get("targetOrEvaluatorMounted") is False
            and all(_mapping(lineage.get("security")).values())
        )
        report = {
            "schemaVersion": 1,
            "routeId": route_id,
            "status": "pass" if success else ("timeout" if timed_out else "failed"),
            "returnCode": completed.returncode if completed is not None else None,
            "elapsedNanoseconds": elapsed,
            "mountedRoles": mounted_roles,
            "mountedFileInventory": [
                {
                    "path": path.name,
                    "byteLength": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
                for path in sorted(inputs.iterdir(), key=lambda item: item.name)
            ],
            "outputs": output_records,
            "lineage": lineage,
            "networkDisabled": True,
            "rootReadOnly": True,
            "inputReadOnly": True,
            "repositoryMounted": False,
            "targetStoreMounted": False,
            "rawSeedMounted": False,
            "generatorStateMounted": False,
            "workspaceDestroyedAfterReturn": True,
            "isolationClass": "pinned_nonroot_networkless_readonly_container",
        }
        return prediction if success else None, report


def _prepare_mounts(inputs: Path, outputs: Path) -> None:
    for path in inputs.iterdir():
        path.chmod(0o444)
    inputs.chmod(0o555)
    outputs.chmod(0o777)


def _docker_environment() -> dict[str, str]:
    allowed = ("PATH", "SYSTEMROOT", "WINDIR", "DOCKER_HOST", "DOCKER_CONTEXT")
    return {name: os.environ[name] for name in allowed if name in os.environ}


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
